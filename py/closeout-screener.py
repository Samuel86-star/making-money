#!/usr/bin/env python3
"""A-Share EOD momentum screener — 尾盘选股分析

Fetches A-share capital flow data from EastMoney push2 API (primary),
with akshare and 同花顺 (10jqka.com.cn) as fallbacks.
Identifies candidates for end-of-day momentum trading.

Usage:
    python3 py/closeout-screener.py                    # full analysis
    python3 py/closeout-screener.py --top-n 20         # top 20
    python3 py/closeout-screener.py --save             # save JSON to data/closeout/

Strategy outputs:
  1. 板块轮动 — top sectors by net fund flow
  2. 强势股回调 — stocks with high net flow but low gain (<3%)
  3. 主力强买 — stocks with high net flow + moderate gain (1-7%)

Data source: data.10jqka.com.cn (同花顺) — server-rendered HTML, no JS needed.
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.request
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "closeout"
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


# ── Scraper ────────────────────────────────────────────────────────────

def fetch_html(url: str) -> str:
    """Fetch page, decode GBK."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
        raw = resp.read()
    return raw.decode("gbk", errors="replace")


def parse_table(html: str) -> list[list[str]]:
    """Parse <table> rows into list of row-lists (text only)."""
    rows = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.DOTALL)
        if not tds:
            continue
        texts = [re.sub(r'<[^>]+>', '', td).strip() for td in tds]
        texts = [t for t in texts if t]
        if len(texts) >= 3:
            rows.append(texts)
    return rows


# ── Adapted to 10jqka table format ─────────────────────────────────────

def _fetch_industry_sectors_10jqka(top_n: int) -> list[dict]:
    """行业板块资金流 — /funds/hyzjl/ (10jqka fallback)

    Columns: 序号, 行业, 行业指数, 涨跌幅%, 流入资金(亿), 流出资金(亿),
             净额(亿), 公司家数, 领涨股, 领涨股涨跌幅%, 当前价(元)
    """
    html = fetch_html("http://data.10jqka.com.cn/funds/hyzjl/")
    rows = parse_table(html)
    items = []
    for row in rows[:top_n]:
        if len(row) < 7:
            continue
        try:
            net_flow = float(row[6]) if row[6] else 0  # 净额(亿)
            pct = float(row[3].rstrip("%")) if row[3] else 0
        except ValueError:
            continue
        items.append({
            "name": row[1] if len(row) > 1 else "",
            "index_value": row[2] if len(row) > 2 else "",
            "change_pct": pct,
            "inflow": float(row[4]) if len(row) > 4 and row[4] else 0,
            "outflow": float(row[5]) if len(row) > 5 and row[5] else 0,
            "net_flow": net_flow,
            "company_count": row[7] if len(row) > 7 else "",
            "leader_name": row[8] if len(row) > 8 else "",
            "leader_pct": row[9] if len(row) > 9 else "",
        })
    return items


def _fetch_concept_sectors_10jqka(top_n: int) -> list[dict]:
    """概念板块 — /funds/gnzjl/ (10jqka fallback)"""
    try:
        html = fetch_html("http://data.10jqka.com.cn/funds/gnzjl/")
    except Exception:
        return []
    rows = parse_table(html)
    items = []
    for row in rows[:top_n]:
        if len(row) < 6:
            continue
        try:
            net_flow = float(row[6]) if len(row) > 6 and row[6] else 0
            pct = float(row[3].rstrip("%")) if len(row) > 3 and row[3] else 0
        except ValueError:
            continue
        items.append({
            "name": row[1] if len(row) > 1 else "",
            "change_pct": pct,
            "net_flow": net_flow,
            "leader_name": row[8] if len(row) > 8 else "",
        })
    return items


def parse_stock_row(row: list[str]) -> dict | None:
    """Parse one stock table row into a dict."""
    if len(row) < 9:
        return None
    try:
        change_pct = float(row[4].rstrip("%")) if row[4] else 0
        return {
            "code": row[1],
            "name": row[2],
            "price": float(row[3]) if row[3] else 0,
            "change_pct": change_pct,
            "turnover_rate": row[5],
            "net_flow_str": row[8],
            "net_flow": _parse_yuan(row[8]),
        }
    except (ValueError, IndexError):
        return None


def _fetch_stocks_10jqka(top_n: int) -> list[dict]:
    """Fetch stocks via 同花顺 /funds/ggzjl/ pagination (10jqka fallback)."""
    all_stocks = []
    # Keep fetching pages until we have enough stocks in each gain bracket
    # or hit a page with no data (end of list)
    max_pages = 20
    page = 1
    while page <= max_pages:
        url = f"http://data.10jqka.com.cn/funds/ggzjl/page/{page}/"
        html = fetch_html(url)
        rows = parse_table(html)
        fetched = 0
        for row in rows:
            s = parse_stock_row(row)
            if s:
                all_stocks.append(s)
                fetched += 1
        if fetched == 0:
            break  # no more data

        # Check if we have enough stocks in the <7% gain range
        # (the high-gain stocks are at the front, lower gains at later pages)
        low_gain = [s for s in all_stocks if s["change_pct"] <= 7]
        if len(low_gain) >= top_n * 3 and len(all_stocks) >= top_n * 4:
            break

        page += 1

    # Re-sort by net flow descending (the original sort is by gain%)
    all_stocks.sort(key=lambda s: s["net_flow"], reverse=True)
    return all_stocks


def _parse_yuan(s: str) -> float:
    """Parse '1.23亿' or '4567万' or '12345' into yuan."""
    s = s.replace(",", "").strip()
    if not s:
        return 0
    if "亿" in s:
        return float(s.replace("亿", "")) * 100_000_000
    if "万" in s:
        return float(s.replace("万", "")) * 10_000
    try:
        return float(s)
    except ValueError:
        return 0


# ── EastMoney push2 API (primary data source) ──────────────────────────


def _fetch_push2(url: str) -> dict | None:
    """Fetch EastMoney push2 JSON, return data dict or None on failure.

    Uses SSL bypass (Surge local environment). Returns None on any error
    so callers can fall through to akshare / 10jqka.
    """
    req = urllib.request.Request(
        url,
        headers={**HEADERS, "Referer": "https://quote.eastmoney.com/"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload and payload.get("data") and payload["data"].get("diff"):
            return payload["data"]
    except Exception:
        pass
    return None


def fetch_sectors(sector_type: str = "industry", top_n: int = 15) -> list[dict]:
    """板块资金净流入 — EastMoney push2, fallback akshare → 10jqka.

    sector_type
      "industry" — 行业板块 (fs=m:90+t:2)
      "concept"  — 概念板块 (fs=m:90+t:3)

    Returns list sorted by net flow descending. Each item:
      name, change_pct, net_flow (元), inflow (元), outflow (元), leader_name
    """
    fs_map = {"industry": "m:90+t:2", "concept": "m:90+t:3"}
    fs = fs_map.get(sector_type, "m:90+t:2")

    # push2 返回 f62/f66/f72 单位为 万元 → 内部统一用 元 ( * 10000)
    fields = "f12,f14,f62,f66,f72,f3,f204,f205"
    url = (
        f"https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={top_n}&po=1&np=1"
        f"&ut=bd1d9ddb04089700cf9c27f6f7426281"
        f"&fltt=2&invt=2&fid=f62&fs={fs}&fields={fields}"
    )
    data = _fetch_push2(url)
    if data is not None:
        items = []
        for row in data["diff"]:
            f62 = row.get("f62") or 0
            f66 = row.get("f66") or 0
            f72 = row.get("f72") or 0
            items.append({
                "name": row.get("f14", ""),
                "change_pct": row.get("f3", 0) or 0,
                "net_flow": int(f62) * 10_000,
                "inflow": int(f66) * 10_000,
                "outflow": int(f72) * 10_000,
                "leader_name": row.get("f205", ""),
                "leader_code": row.get("f204", ""),
            })
        return items

    # Fallback: akshare
    try:
        import akshare as ak
        st = "行业资金流" if sector_type == "industry" else "概念资金流"
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type=st)
        items = []
        for _, r in df.head(top_n).iterrows():
            items.append({
                "name": r.get("名称", ""),
                "change_pct": float(r.get("涨跌幅", 0)),
                "net_flow": float(r.get("主力净流入-净额", 0)),
                "inflow": float(r.get("主力净流入-净额", 0)),
                "outflow": 0,
                "leader_name": r.get("领涨股", ""),
            })
        return items
    except Exception:
        pass

    # Fallback: 10jqka (original logic)
    fn = _fetch_industry_sectors_10jqka if sector_type == "industry" else _fetch_concept_sectors_10jqka
    return fn(top_n)


def fetch_stocks(top_n: int) -> list[dict]:
    """个股资金净流入 — EastMoney push2, fallback 10jqka.

    Sorts by net flow descending (fid=f62, po=1).
    Returns list sorted by net_flow (元).
    """
    fs = "m:0+t:6+f:!50,m:0+t:80+f:!50,m:0+t:81+f:!50,m:0+t:82+f:!50"
    fields = "f12,f14,f2,f3,f62,f66,f72,f204,f205"
    url = (
        f"https://push2.eastmoney.com/api/qt/clist/get"
        f"?pn=1&pz={top_n}&po=1&np=1"
        f"&ut=bd1d9ddb04089700cf9c27f6f7426281"
        f"&fltt=2&invt=2&fid=f62&fs={fs}&fields={fields}"
    )
    data = _fetch_push2(url)
    if data is not None:
        items = []
        for row in data["diff"]:
            f62 = row.get("f62") or 0
            items.append({
                "code": row.get("f12", ""),
                "name": row.get("f14", ""),
                "price": row.get("f2", 0) or 0,
                "change_pct": row.get("f3", 0) or 0,
                "turnover_rate": row.get("f204", ""),
                "net_flow_str": "",
                "net_flow": int(f62) * 10_000,
            })
        items.sort(key=lambda s: s["net_flow"], reverse=True)
        return items

    # Fallback: 10jqka
    return _fetch_stocks_10jqka(top_n)


# ── Proxy / Surge diagnostics ──────────────────────────────────────────

def _check_10jqka() -> bool:
    try:
        fetch_html("http://data.10jqka.com.cn/funds/hyzjl/")
        return True
    except Exception:
        return False


# ── Screening ──────────────────────────────────────────────────────────

def screen_strong_pullback(stocks: list[dict], top_n: int) -> list[dict]:
    """High net flow but gain < 3%."""
    cand = [
        s for s in stocks
        if s["net_flow"] > 0
        and 0 <= s["change_pct"] < 3
    ]
    cand.sort(key=lambda s: s["net_flow"], reverse=True)
    return cand[:top_n]


def screen_strong_buy(stocks: list[dict], top_n: int) -> list[dict]:
    """High net flow + moderate gain."""
    cand = [
        s for s in stocks
        if s["net_flow"] > 0
        and 1 <= s["change_pct"] <= 7
    ]
    cand.sort(key=lambda s: s["net_flow"], reverse=True)
    return cand[:top_n]


# ── Formatting ─────────────────────────────────────────────────────────

def fmt_yuan(val: float) -> str:
    if abs(val) >= 100_000_000:
        return f"{val/100_000_000:.2f}亿"
    if abs(val) >= 10_000:
        return f"{val/10_000:.0f}万"
    return f"{val:.0f}"


def print_table(title: str, headers: list[str], rows: list[list], widths: list[int]):
    sep = "─" * (sum(widths) + len(widths) + 1)
    print(f"\n  {title}")
    print(f"  {sep}")
    hdr = " │ ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(f"  {hdr}")
    print(f"  {sep}")
    for row in rows:
        line = " │ ".join(str(v).ljust(w) for v, w in zip(row, widths))
        print(f"  {line}")
    print(f"  {sep}")


def print_sectors(data: list[dict], label: str):
    rows = []
    for s in data:
        rows.append([
            s["name"],
            f'{s["net_flow"]:.2f}亿',
            f'{s["change_pct"]:.2f}%',
            s.get("leader_name", ""),
        ])
    print_table(label, ["板块", "净流入(亿)", "涨跌幅", "领涨股"], rows, [18, 12, 8, 14])


def print_stocks(data: list[dict], label: str):
    rows = []
    for s in data:
        rows.append([
            s["code"], s["name"],
            f'{s["price"]:.2f}',
            f'{s["change_pct"]:.2f}%',
            fmt_yuan(s["net_flow"]),
        ])
    print_table(label, ["代码", "名称", "最新价", "涨幅", "净流入"], rows, [10, 12, 10, 8, 14])


# ── Diagnostics ────────────────────────────────────────────────────────

def run_diagnostics():
    print("=" * 56)
    print("  连接诊断 — A 股数据源")
    print("=" * 56)

    import socket

    # DNS
    for host in ["push2.eastmoney.com", "data.10jqka.com.cn"]:
        try:
            ip = socket.getaddrinfo(host, 443)[0][4][0]
            print(f"  📡 {host:30s} → {ip}")
        except Exception as e:
            print(f"  📡 {host:30s} → ✗ {e}")

    # push2
    push2_url = (
        "https://push2.eastmoney.com/api/qt/clist/get"
        "?pn=1&pz=1&po=1&np=1"
        "&ut=bd1d9ddb04089700cf9c27f6f7426281"
        "&fltt=2&invt=2&fid=f62&fs=m:90+t:2&fields=f12"
    )
    push2_ok = _fetch_push2(push2_url) is not None
    print(f"  🏦 push2:       {'✓ 可访问' if push2_ok else '✗ 不通'}")

    # 10jqka
    jq_ok = _check_10jqka()
    print(f"  🏦 10jqka:      {'✓ 可访问' if jq_ok else '✗ 不通'}")

    print(f"\n  {'─' * 40}")
    ok = push2_ok or jq_ok
    if ok:
        src = "push2" if push2_ok else "10jqka"
        print(f"  数据源可用 ✓ (将通过 {src} 获取)")
    else:
        print("  数据源不可用 — 请检查网络/代理设置")


# ── Main ───────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="A-Share 尾盘选股分析")
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--diagnose", action="store_true")
    args = parser.parse_args()

    if args.diagnose:
        run_diagnostics()
        return

    top_n = args.top_n

    print("⏳ 正在拉取数据...")
    t0 = time.time()

    print("  行业板块资金流...", end=" ", flush=True)
    industry = fetch_sectors("industry", top_n)
    print(f"{len(industry)} 个")

    print("  概念板块资金流...", end=" ", flush=True)
    concept = fetch_sectors("concept", top_n)
    print(f"{len(concept)} 个")

    print("  个股资金净流入...", end=" ", flush=True)
    stocks = fetch_stocks(top_n * 4)
    print(f"{len(stocks)} 个")

    elapsed = time.time() - t0

    if not industry and not stocks:
        print("\n✗ 无法获取数据。请运行 --diagnose 排查。")
        return

    # ── Output ──────────────────────────────────────────────────────
    print("\n" + "=" * 58)
    print(f"  尾盘选股分析 — {datetime.now().strftime('%Y-%m-%d %H:%M')}  ({elapsed:.0f}s)")
    print(f"  数据源: EastMoney push2 + 同花顺")
    print("=" * 58)

    if industry:
        print_sectors(industry, "📊 行业板块资金净流入 TOP")

    if stocks:
        pullback = screen_strong_pullback(stocks, top_n)
        strong = screen_strong_buy(stocks, top_n)
        print_stocks(pullback, "📈 强势股回调 — 净流入大/涨幅<3% (潜在反包)")
        print_stocks(strong, "📈 主力强买 — 净流入大/涨幅1-7%")

        hot = [s["name"] for s in industry[:5]]
        if hot:
            print(f"\n  💡 今日热门板块: {'  '.join(hot)}")
        print("  💡 尾盘关注: 板块方向 + 强势股回调")
    else:
        print("\n  ⚠ 无个股数据")

    # ── Save ────────────────────────────────────────────────────────
    if args.save:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        output = {
            "fetched_at": ts,
            "source": "eastmoney_push2",
            "industry_sectors": industry,
            "concept_sectors": concept,
            "pullback_candidates": screen_strong_pullback(stocks, top_n) if stocks else [],
            "strong_buy_candidates": screen_strong_buy(stocks, top_n) if stocks else [],
        }
        path = DATA_DIR / f"{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n  💾 已保存 → {path}")


if __name__ == "__main__":
    main()