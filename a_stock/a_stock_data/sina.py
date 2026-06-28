"""新浪财经数据源: 全市场资金流排行 (东财 push2 备用源).

免 key 免登录, 真非东财源. 东财挂时降级用此.
接口: vip.stock.finance.sina.com.cn MoneyFlow.ssl_bkzj_ssggzj
  - 按主力净流入 (netamount) 降序全市场排行
  - 字段对齐 screener.fetch_market_stocks 输出 (code/name/price/change_pct/net_flow/inflow/outflow)

口径说明: 新浪 netamount = 主力净额 (流入-流出), 与东财 f62 (主力净流入) 略有差异
但都是衡量资金净流入, 排名口径一致. 验证: 前3名与东财重叠 2/3.
"""
import json
import re

from a_stock.a_stock_data._common import em_get

SINA_FUND_FLOW_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "MoneyFlow.ssl_bkzj_ssggzj"
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://vip.stock.finance.sina.com.cn/",
}


def _parse_symbol(symbol: str) -> tuple[str, str]:
    """'sz000725' → ('000725', 'sz'). 沪深前缀剥离."""
    m = re.match(r"^([a-z]+)(\d{6})$", symbol or "", re.IGNORECASE)
    if not m:
        return symbol or "", ""
    return m.group(2), m.group(1).lower()


def _to_float(v, default: float = 0.0) -> float:
    """字符串/None → float, 失败返 default."""
    try:
        return float(v) if v not in (None, "") else default
    except (ValueError, TypeError):
        return default


def fetch_market_fund_flow_rank(top_n: int = 20) -> list[dict]:
    """新浪全市场资金流排行 (东财备用源).

    按主力净流入 (netamount) 降序, 返回 top_n 只.
    字段对齐 screener.fetch_market_stocks:
        {code, name, price, change_pct, net_flow, inflow, outflow}
    异常/空返回 [] (供降级链判断, 不抛).

    Args:
        top_n: 返回条数 (新浪单页支持, 直接 num=top_n)
    """
    params = {
        "page": "1",
        # 多拉 (×3) 再过滤 ETF/债券, 保证过滤后仍有 top_n 只个股
        "num": str(max(top_n * 3, 10)),
        "sort": "netamount",   # 按主力净流入降序
        "asc": "0",            # 0=降序
        "bankuai": "",
    }
    try:
        r = em_get(SINA_FUND_FLOW_URL, params=params, headers=_HEADERS, timeout=15)
        data = json.loads(r.text)
    except Exception:
        return []

    if not isinstance(data, list) or not data:
        return []

    out = []
    for row in data:
        code, _ = _parse_symbol(row.get("symbol", ""))
        if not code:
            continue
        # 只保留 A 股个股: 6(沪)/0/3(深) 开头, 排除 5(基金/ETF)/1(债券)/9/8(北交所可保留)
        if not code.startswith(("6", "0", "3", "8", "9")):
            continue
        name = row.get("name") or code
        # name 为 False/None/空 → 用 code 兜底
        if not isinstance(name, str) or not name.strip():
            name = code
        out.append({
            "code": code,
            "name": name,
            "price": _to_float(row.get("trade")),
            "change_pct": round(_to_float(row.get("changeratio")) * 100, 2),
            "net_flow": _to_float(row.get("netamount")),
            "inflow": _to_float(row.get("inamount")),
            "outflow": _to_float(row.get("outamount")),
        })
    # 二次保险: 按 net_flow 降序 (新浪已排, 防接口变化)
    out.sort(key=lambda x: x["net_flow"], reverse=True)
    return out[:top_n]
