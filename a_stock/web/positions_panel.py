"""持仓栏数据: 复用 risk_metrics._load_positions + ohlcv ATR止损."""
from a_stock.risk_metrics import _load_positions
from a_stock.ohlcv import atr, struct_stop_loss


def _atr_stop(code: str, cost: float) -> float | None:
    """ATR结构止损价. 无数据返回 None."""
    a = atr(code, 14)
    return round(struct_stop_loss(cost, a), 3) if a else None


def collect_positions() -> list[dict]:
    """返回持仓行: code/name/qty/cost/price/pnl_pct/pnl/stop_loss/mv."""
    out = []
    for p in _load_positions():
        cost = p.get("cost", 0)
        price = p.get("price", 0)
        pnl_pct = (price - cost) / cost * 100 if cost else 0
        out.append({
            "code": p["code"], "name": p.get("name", p["code"]),
            "qty": p["qty"], "cost": round(cost, 4), "price": round(price, 4),
            "pnl_pct": round(pnl_pct, 2),
            "pnl": round(p.get("unrealized_pnl", 0)),
            "stop_loss": _atr_stop(p["code"], cost),
            "mv": round(p.get("mv", 0)),
        })
    return out