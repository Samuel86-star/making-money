"""行业板块排名(东财)."""
from a_stock.a_stock_data._common import em_get


def industry_comparison(top_n: int = 20) -> dict:
    """
    全行业涨跌幅排名(东财行业板块, ~100 个行业)。
    返回: {top: [...], bottom: [...], total: int}
    """
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1", "pz": "100", "po": "1", "np": "1",
        "fltt": "2", "invt": "2",
        "fs": "m:90+t:2",
        "fields": "f2,f3,f4,f12,f13,f14,f62,f104,f105,f128,f136,f140,f141,f207",
    }
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    r = em_get(url, params=params, headers=headers, timeout=15)
    d = r.json()
    items = d.get("data", {}).get("diff", [])
    if not items:
        return {"top": [], "bottom": [], "total": 0}

    rows = []
    for i, item in enumerate(items):
        rows.append({
            "rank": i + 1,
            "name": item.get("f14", ""),
            "change_pct": item.get("f3", 0),
            "code": item.get("f12", ""),
            "up_count": item.get("f104", 0),
            "down_count": item.get("f105", 0),
            "leader": item.get("f140", ""),
            "leader_change": item.get("f136", 0),
            "net_flow": int(item.get("f62") or 0) * 10000,  # push2 万元→元
        })

    return {
        "top": rows[:top_n],
        "bottom": rows[-top_n:],
        "total": len(rows),
    }