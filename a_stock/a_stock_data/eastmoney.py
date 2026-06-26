"""东财数据层:研报列表/板块归属/资金流/龙虎榜。"""
import json
import time
from a_stock.a_stock_data._common import em_get, em_cache_get, em_cache_put, _cache_key, get_prefix

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
    from a_stock.a_stock_data._common import get_prefix
    secid = secid_map[get_prefix(code)] + code

    cache_key = _cache_key(SLIST_URL, {"secid": secid})
    cached = em_cache_get(cache_key)
    if cached is not None:
        return cached

    params = {
        "fields": "f12,f14,f128,f136,f152",
        "secid": secid,
        "_": str(int(time.time() * 1000)),
    }
    r = em_get(SLIST_URL, params=params, timeout=15)
    d = r.json().get("data", {})

    out = {"industries": [], "concepts": [], "regions": []}
    if d.get("f128"):  # 行业板块代码
        out["industries"].append({
            "code": d["f128"], "name": d.get("f12", ""),
        })
    # 概念/地域需另调接口(SKILL.md 934-980 详述),简化先返回基础
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
    """日级 120 日资金流,返回 [{"date": "YYYY-MM-DD", "main": x, "large": y, "small": z}]。"""
    secid_map = {"sh": "1.", "sz": "0.", "bj": "0."}
    secid = secid_map[get_prefix(code)] + code

    params = {
        "fields": "f1,f2,f3,f7",
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
            out.append({
                "date":   parts[0],
                "main":   float(parts[1] or 0),
                "large":  float(parts[2] or 0),
                "small":  float(parts[3] or 0),
            })
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