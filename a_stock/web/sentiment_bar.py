"""情绪条数据: 温度+情绪+领涨板块."""
import json
import sqlite3
import a_stock.config as cfg


def _compute_temp() -> dict:
    from a_stock.sentiment import compute_temp
    return compute_temp()


def _leading_sector() -> str:
    """领涨板块: 读 close_scan 落盘的 daily_close.sector_rotation JSON."""
    try:
        conn = sqlite3.connect(str(cfg.SCREENER_DB))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT sector_rotation FROM daily_close ORDER BY date DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row and row["sector_rotation"]:
            data = json.loads(row["sector_rotation"])
            return data.get("current_leader", "") or ""
    except Exception:
        pass
    return ""


def collect_sentiment() -> dict:
    t = _compute_temp()
    return {
        "temp": t.get("temp", 0),
        "mood": t.get("mood", ""),
        "leader": _leading_sector(),
    }