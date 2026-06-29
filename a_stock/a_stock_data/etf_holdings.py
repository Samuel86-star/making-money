"""ETF 成分股(持仓明细)拉取 — 东财基金持仓页。

ETF 直接持有一篮子股票, 季报披露前十大, 半年报/年报披露全部。
用于回答 "我的 ETF 会不会持有北交所股票" 等成分核验问题。

数据源: https://fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import date

from a_stock.a_stock_data._common import em_get, em_cache_get, em_cache_put, retry

_ENDPOINT = "https://fundf10.eastmoney.com/FundArchivesDatas.aspx"
_HEADERS = {"Referer": "https://fundf10.eastmoney.com/"}

# 北交所代码前缀: 430xxx / 830xxx / 870xxx / 920xxx
_NORTH_PREFIXES = ("43", "83", "87", "92")

# 单行: secid 前缀(0=深/北,1=沪) + 6位代码 + 名称 + 占净值%
# 示例: <a href='//quote.eastmoney.com/unify/r/0.300750'>300750</a></td>
#       <td class='tol'><a ...>宁德时代</a> ... <td class='tor'>19.69%</td>
_ROW_RE = re.compile(
    r"//quote\.eastmoney\.com/unify/r/([01])\.(\d{6})'>\d{6}</a></td>"
    r"<td class='tol'><a[^>]*>([^<]+)</a>.*?<td class='tor'>([\d.]+)%</td>",
    re.S,
)
_DATE_RE = re.compile(r"截止至：<font[^>]*>(\d{4}-\d{2}-\d{2})")
_TITLE_RE = re.compile(r"<title>([^<]+)</title>|(\d{6})\s*季度股票投资明细")


@dataclass
class Holding:
    code: str
    name: str
    weight_pct: float
    market: str  # "sh" / "sz" / "bj"


def is_north_code(code: str) -> bool:
    """6位股票代码是否北交所 (43/83/87/92 开头)。"""
    return code[:2] in _NORTH_PREFIXES


def _market_of(code: str, secid_prefix: str) -> str:
    """判定市场。secid_prefix: 0=深/北, 1=沪。北交所按代码前缀优先判。"""
    if is_north_code(code):
        return "bj"
    if secid_prefix == "1" or code.startswith(("6", "5", "9")):
        return "sh"
    return "sz"


def _fetch_raw(code: str, year: int) -> str:
    """拉取持仓页原始文本 (JS 包裹的 HTML)。失败抛异常, 由 retry 兜。"""
    params = {"type": "jjcc", "code": code, "topline": "300",
              "year": str(year), "month": ""}
    r = em_get(_ENDPOINT, params=params, headers=_HEADERS, timeout=15)
    r.raise_for_status()
    return r.text


def get_etf_holdings(code: str, year: int | None = None) -> list[Holding]:
    """拉取 ETF 持仓明细。year 缺省取当前年。返回按报告期披露的全部成分。

    注意: 季报仅披露前十大; 半年报/年报披露全部。返回条数即披露条数。
    """
    code = code.strip()
    year = year or date.today().year
    cache_key = f"etf_holdings_{code}_{year}"
    cached = em_cache_get(cache_key)
    if cached is not None:
        return [Holding(**h) for h in cached]

    text = retry(lambda: _fetch_raw(code, year))
    rows = _ROW_RE.findall(text)
    holdings = [
        Holding(code=code_, name=name, weight_pct=float(pct),
                market=_market_of(code_, prefix))
        for prefix, code_, name, pct in rows
    ]
    em_cache_put(cache_key, [asdict(h) for h in holdings])
    return holdings


def get_as_of_date(code: str, year: int | None = None) -> str | None:
    """持仓报告截止日 (如 '2026-03-31')。拉不到返回 None。"""
    code = code.strip()
    year = year or date.today().year
    text = retry(lambda: _fetch_raw(code, year))
    m = _DATE_RE.search(text)
    return m.group(1) if m else None


def has_north_exchange(code: str, year: int | None = None) -> bool:
    """ETF 是否持有北交所股票 (基于已披露持仓)。"""
    return any(h.market == "bj" for h in get_etf_holdings(code, year))


def summarize(code: str, year: int | None = None) -> dict:
    """便捷汇总: 成分数/报告期/北交所数/top3。"""
    holdings = get_etf_holdings(code, year)
    return {
        "code": code,
        "as_of": get_as_of_date(code, year),
        "count": len(holdings),
        "north_count": sum(1 for h in holdings if h.market == "bj"),
        "top3": [{"code": h.code, "name": h.name, "weight_pct": h.weight_pct}
                 for h in holdings[:3]],
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="ETF 成分股查询")
    ap.add_argument("code", help="ETF 代码, 如 159915")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--summary", action="store_true", help="只输出汇总")
    args = ap.parse_args()
    if args.summary:
        import json
        print(json.dumps(summarize(args.code, args.year), ensure_ascii=False, indent=2))
    else:
        for h in get_etf_holdings(args.code, args.year):
            bj = " [北交所]" if h.market == "bj" else ""
            print(f"{h.code} {h.name:<8} {h.weight_pct:6.2f}% {h.market}{bj}")
