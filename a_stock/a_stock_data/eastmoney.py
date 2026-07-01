"""东财数据层:研报列表/板块归属/资金流/龙虎榜/日K线。"""
import json
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from a_stock.a_stock_data._common import em_get, em_cache_get, em_cache_put, _cache_key, get_prefix
import a_stock.config as cfg

# ── 2.1 个股研报列表 ─────────────────────────────────
REPORTAPI_URL = "https://reportapi.eastmoney.com/report/list"

def eastmoney_reports(code: str, max_pages: int = 1) -> list[dict]:
    """拉个股研报列表(标题/机构/评级/日期)。"""
    cache_key = _cache_key(REPORTAPI_URL, {"code": code, "max_pages": max_pages})
    cached = em_cache_get(cache_key)
    if cached is not None:
        return cached

    all_reports = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "50", "industry": "*",
            "rating": "*", "ratingChange": "*", "beginTime": "",
            "endTime": "", "pageNo": str(page), "fields": "",
            "qType": "0", "orgCode": "*", "code": code,
            "rcode": "", "_": str(int(time.time() * 1000)),
        }
        r = em_get(REPORTAPI_URL, params=params, timeout=15)
        d = r.json()
        # 实际响应: d = {"hits": N, "data": [items...], "TotalPage": N, ...}
        # d["data"] 是 list,不是 dict[dataList]
        items = d.get("data", [])
        if not items or not isinstance(items, list):
            break
        for item in items:
            all_reports.append({
                "title":       item.get("title", ""),
                "org":         item.get("orgSName", ""),
                "rating":      item.get("emRatingName", ""),
                "industry":    item.get("industryName", ""),
                "date":        item.get("publishDate", "")[:10],
                "report_id":   item.get("infoCode", ""),
            })
    em_cache_put(cache_key, all_reports)
    return all_reports


def eastmoney_industry_reports(industry_code: str = "*", max_pages: int = 1) -> list[dict]:
    """行业研报列表(同端点,qType=1)。"""
    cache_key = _cache_key(REPORTAPI_URL, {"industry": industry_code, "max_pages": max_pages, "type": "industry"})
    cached = em_cache_get(cache_key)
    if cached is not None:
        return cached

    all_reports = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": industry_code, "pageSize": "50", "industry": "*",
            "rating": "*", "ratingChange": "*", "beginTime": "",
            "endTime": "", "pageNo": str(page), "fields": "",
            "qType": "1", "orgCode": "*", "code": "",
            "rcode": "", "_": str(int(time.time() * 1000)),
        }
        r = em_get(REPORTAPI_URL, params=params, timeout=15)
        d = r.json()
        items = d.get("data", [])
        if not items or not isinstance(items, list):
            break
        for item in items:
            all_reports.append({
                "title":     item.get("title", ""),
                "org":       item.get("orgSName", ""),
                "rating":    item.get("emRatingName", ""),
                "industry":  item.get("industryName", ""),
                "date":      item.get("publishDate", "")[:10],
                "report_id": item.get("infoCode", ""),
            })
    em_cache_put(cache_key, all_reports)
    return all_reports


# ── 3.3 个股板块归属 ─────────────────────────────────
SLIST_URL = "https://push2.eastmoney.com/api/qt/stock/get"

def eastmoney_concept_blocks(code: str) -> dict:
    """返回 {industries: [...], concepts: [...], regions: [...]}。"""
    secid_map = {"sh": "1.", "sz": "0.", "bj": "0."}
    secid = secid_map[get_prefix(code)] + code

    cache_key = _cache_key(SLIST_URL, {"secid": secid})
    cached = em_cache_get(cache_key)
    if cached is not None:
        return cached

    # 实际响应: f127=行业(如"白酒Ⅱ"), f128=地域, f129=概念(comma-separated)
    params = {
        "fields": "f12,f14,f127,f128,f129",
        "secid": secid,
        "_": str(int(time.time() * 1000)),
    }
    r = em_get(SLIST_URL, params=params, timeout=15)
    d = r.json().get("data", {})

    out = {"industries": [], "concepts": [], "regions": []}

    # 行业
    industry = d.get("f127", "")
    if industry:
        out["industries"].append({"name": industry})

    # 地域
    region = d.get("f128", "")
    if region:
        out["regions"].append({"name": region})

    # 概念(comma-separated)
    concepts_str = d.get("f129", "")
    if concepts_str:
        for c in concepts_str.split(","):
            c = c.strip()
            if c:
                out["concepts"].append({"name": c})

    em_cache_put(cache_key, out)
    return out


# ── 3.4 分钟资金流 ─────────────────────────────────
FUND_FLOW_MIN_URL = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"

def eastmoney_fund_flow_minute(code: str) -> list[dict]:
    """返回 60 分钟级别资金流 dict 列表。"""
    secid_map = {"sh": "1.", "sz": "0.", "bj": "0."}
    from a_stock.a_stock_data._common import get_prefix
    secid = secid_map[get_prefix(code)] + code

    params = {
        "fields": "f1,f2,f3,f7",
        "secid": secid,
        "klt": "1", "lmt": "60",  # 1 分钟 K, 60 根
    }
    r = em_get(FUND_FLOW_MIN_URL, params=params, timeout=15)
    d = r.json().get("data", {})
    klines = d.get("klines", [])
    return [
        {"time": k.split(",")[0], "main": float(k.split(",")[1] or 0),
         "large": float(k.split(",")[2] or 0), "small": float(k.split(",")[3] or 0)}
        for k in klines if len(k.split(",")) >= 4
    ]


# ── 4.5 120 日资金流 ─────────────────────────────────
FFLOW_DAY_URL = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"

def stock_fund_flow_120d(code: str) -> list[dict]:
    """日级 120 日资金流. 字段 f1-f7 (东财 fflow daykline 标准映射):

    [{"date","main"(主力=超大+大),"super"(超大单),"big"(大单),"medium"(中单),"small"(小单),"main_pct"}]
    main 字段向后兼容 (screener/moneyflow_scorer 用). super/big 供个股资金流细化.
    注: 字段语义待交易日自检 (main ≈ super+big), 见 test_moneyflow_scorer 一致性测试.
    """
    secid_map = {"sh": "1.", "sz": "0.", "bj": "0."}
    secid = secid_map[get_prefix(code)] + code

    params = {
        "fields": "f1,f2,f3,f4,f5,f6,f7",
        "secid": secid,
        "klt": "101",   # 101 = daily K-line
        "lmt": "120",   # 120 records
    }
    try:
        r = em_get(FFLOW_DAY_URL, params=params, timeout=15)
        d = r.json().get("data", {})
        klines = d.get("klines", [])
        out = []
        for k in klines:
            parts = k.split(",")
            if len(parts) < 4:
                continue
            row = {"date": parts[0], "main": float(parts[1] or 0)}
            # 细分字段 (旧数据可能只有4列, 防御性解析)
            if len(parts) >= 7:
                row["super"] = float(parts[5] or 0)     # f6 超大单
                row["big"] = float(parts[4] or 0)       # f5 大单
                row["medium"] = float(parts[3] or 0)    # f4 中单
                row["small"] = float(parts[2] or 0)     # f3 小单
                row["main_pct"] = float(parts[6] or 0)  # f7 主力占比
            else:
                # 兼容旧的 f1,f2,f3,f7 格式 (已弃用, 保留防回退)
                row["super"] = 0.0
                row["big"] = 0.0
                row["medium"] = 0.0
                row["small"] = 0.0
                row["main_pct"] = 0.0
            out.append(row)
        return out
    except Exception:
        return []


# ── 3.8 全市场龙虎榜 ─────────────────────────────────
DRAGON_TIGER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

def daily_dragon_tiger(trade_date: str | None = None, min_net_buy: float = None) -> dict:
    """返回 {"data": [{...龙虎榜记录...}], "total": N}。"""
    if trade_date is None:
        from datetime import date
        trade_date = date.today().isoformat()

    # 实际字段格式 "2026-06-25 00:00:00",不是 "2026-06-25"
    filter_date = trade_date if " " in trade_date else f"{trade_date} 00:00:00"

    params = {
        "reportName": "RPT_DAILYBILLBOARD_DETAILS",
        "columns": "ALL",
        "filter": f"(TRADE_DATE='{filter_date}')",
        "pageNumber": "1", "pageSize": "100",
        "sortColumns": "BILLBOARD_NET_AMT", "sortTypes": "-1",
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DRAGON_TIGER_URL, params=params, timeout=15)
    d = r.json()
    rows = d.get("result", {}).get("data", []) if d.get("result") else []
    if min_net_buy is not None:
        rows = [row for row in rows if (row.get("BILLBOARD_NET_AMT") or 0) >= min_net_buy]
    return {"data": rows, "total": len(rows), "date": trade_date}

def limit_up_pool(trade_date: str | None = None) -> dict:
    """涨停池 (东财 getTopicZTPool). 抄 quantdash fetch_sentiment_cycle_snapshots.py:307-343.
    返回 {first_board, second_board, third_board, high_board, total, data:[...]}"""
    from datetime import date as _date
    if trade_date is None:
        trade_date = _date.today().strftime("%Y%m%d")
    else:
        trade_date = trade_date.replace("-", "")
    url = "https://push2ex.eastmoney.com/getTopicZTPool"
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": "0",
        "pagesize": "100",
        "date": trade_date,
    }
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    try:
        r = em_get(url, params=params, headers=headers, timeout=15)
        d = r.json()
        pool = d.get("data", {}).get("pool", [])
    except Exception:
        return {"first_board": 0, "second_board": 0, "third_board": 0,
                "high_board": 0, "total": 0, "data": []}

    # 按连板数分桶 (lbc 字段)
    first = sum(1 for s in pool if (s.get("lbc") or 0) == 1)
    second = sum(1 for s in pool if (s.get("lbc") or 0) == 2)
    third = sum(1 for s in pool if (s.get("lbc") or 0) == 3)
    high = sum(1 for s in pool if (s.get("lbc") or 0) >= 4)
    return {
        "first_board": first, "second_board": second,
        "third_board": third, "high_board": high,
        "total": len(pool), "data": pool,
    }


def broken_board_pool(trade_date: str | None = None) -> dict:
    """炸板池 (东财 getTopicZBPool). 抄 quantdash fetch_sentiment_cycle_snapshots.py:395-422."""
    from datetime import date as _date
    if trade_date is None:
        trade_date = _date.today().strftime("%Y%m%d")
    else:
        trade_date = trade_date.replace("-", "")
    url = "https://push2ex.eastmoney.com/getTopicZBPool"
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": "0",
        "pagesize": "100",
        "date": trade_date,
    }
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    try:
        r = em_get(url, params=params, headers=headers, timeout=15)
        d = r.json()
        pool = d.get("data", {}).get("pool", [])
    except Exception:
        return {"total": 0, "data": []}
    return {"total": len(pool), "data": pool}


# ── 3.9 东财日K线 (push2his) ──────────────────────
KLINE_HIS_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

def stock_kline_daily(code: str, limit: int = 120) -> list[dict]:
    """拉个股日K线 (东财push2his, 前复权).
    用 em_get 限流, 带 beg/end 参数保证周末也能拉.

    Args:
        code: 6位代码
        limit: 返回条数

    Returns: [{"date":"YYYY-MM-DD","open":x,"high":x,"low":x,"close":x,"volume":x}]
    """
    from datetime import date, timedelta

    secid_map = {"sh": "1.", "sz": "0.", "bj": "0."}
    secid = secid_map[get_prefix(code)] + code
    end = date.today()
    beg = end - timedelta(days=limit)

    params = {
        "secid": secid,
        "fields1": "f1,f2,f3",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
        "klt": "101",        # 日K
        "fqt": "1",          # 前复权
        "beg": beg.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
    }
    try:
        r = em_get(KLINE_HIS_URL, params=params, timeout=15)
        d = r.json().get("data", {})
        klines = d.get("klines", [])
        if not klines:
            return []
        out = []
        for k in klines:
            parts = k.split(",")
            if len(parts) < 7:
                continue
            out.append({
                "date":   parts[0],
                "open":   float(parts[1] or 0),
                "close":  float(parts[2] or 0),
                "high":   float(parts[3] or 0),
                "low":    float(parts[4] or 0),
                "volume": int(float(parts[5] or 0)),
            })
        return out
    except Exception as e:
        print(f"⚠ stock_kline_daily({code}) 失败: {e}")
        return []


def refresh_ohlcv_parquet(codes: list[str] | None = None, days: int = 10) -> dict:
    """更新一批股票OHLCV parquet缓存.

    读现存 parquet → 合并新K线 → 去重 → 写回.
    仅更新最近 days 天, 避免全量拉取.

    Args:
        codes: 股票列表 (None=读已缓存的)
        days: 拉取近N天日K

    Returns: {"updated": n, "errors": [code,...]}
    """
    from a_stock.ohlcv import load_ohlcv

    if codes is None:
        codes = sorted(p.stem for p in cfg.OHLCV_DIR.glob("*.parquet"))

    updated = 0
    errors = []

    for code in codes:
        try:
            fetched = stock_kline_daily(code, limit=days)
            if not fetched:
                continue

            new_df = pd.DataFrame(fetched)
            new_df["date"] = pd.to_datetime(new_df["date"])
            new_df = new_df.set_index("date")
            new_df.index.name = "Date"
            new_df = new_df.rename(columns={
                "open": "Open", "high": "High",
                "low": "Low", "close": "Close", "volume": "Volume",
            })
            new_df = new_df.sort_index()

            # 合并到现有 parquet
            path = cfg.OHLCV_DIR / f"{code}.parquet"
            if path.exists():
                old = pd.read_parquet(path)
                merged = pd.concat([old, new_df])
                # 去重 (同日期保留新数据)
                merged = merged[~merged.index.duplicated(keep="last")]
                merged = merged.sort_index()
            else:
                merged = new_df

            merged.to_parquet(path)
            updated += 1

        except Exception as e:
            errors.append(code)
            print(f"  ⚠ {code} 更新失败: {e}")

    return {"updated": updated, "errors": errors, "total": len(codes)}
