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
            "net_flow": int(item.get("f62") or 0),  # push2 f62 元口径
        })

    return {
        "top": rows[:top_n],
        "bottom": rows[-top_n:],
        "total": len(rows),
    }


def industry_fund_flow(top_n: int = 10) -> dict:
    """行业资金流TOP流入/流出 (07-01上午实战新增, 每日必看).

    返回: {inflow_top:[{name,change_pct,net_flow_yi,leader}],
           outflow_top:[...], total}
    net_flow_yi = 净流入亿元 (正=流入, 负=流出).

    07-01教训: 科技硬件(电子/通信/半导体)常"涨却巨量流出"=出货,
    不看资金流会被"涨"骗.

    单位: 板块 push2 f62 为元口径, /1e8 得亿."""
    r = industry_comparison(100)
    seen = set()
    rows = []
    for x in r["top"] + r["bottom"]:
        k = (x["code"], x["name"])
        if k in seen:
            continue
        seen.add(k)
        rows.append(x)
    out = [
        {
            "name": x["name"],
            "change_pct": x["change_pct"],
            "net_flow_yi": round(x["net_flow"] / 1e8, 2),
            "leader": x["leader"],
        }
        for x in rows
    ]
    inflow = sorted(out, key=lambda x: x["net_flow_yi"], reverse=True)[:top_n]
    outflow = sorted(out, key=lambda x: x["net_flow_yi"])[:top_n]
    return {"inflow_top": inflow, "outflow_top": outflow, "total": len(rows)}