"""行情滚动条: 持仓+watchlist+候选 代码列表."""
import sqlite3
import a_stock.config as cfg


def _holding_codes() -> list[str]:
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    rows = conn.execute(
        "SELECT DISTINCT code FROM decisions WHERE action IN('buy','add') AND close_date IS NULL"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def _watchlist_codes() -> list[str]:
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    rows = conn.execute("SELECT code FROM watchlist").fetchall()
    conn.close()
    return [r[0] for r in rows]


def _candidate_codes() -> list[str]:
    conn = sqlite3.connect(str(cfg.SCREENER_DB))
    rows = conn.execute("""
        SELECT code FROM candidate_history
        WHERE scan_date=(SELECT MAX(scan_date) FROM candidate_history)
        ORDER BY score DESC LIMIT 5
    """).fetchall()
    conn.close()
    return [r[0] for r in rows]


def collect_ticker_codes() -> list[str]:
    """去重合并."""
    seen = []
    for c in _holding_codes() + _watchlist_codes() + _candidate_codes():
        if c not in seen:
            seen.append(c)
    return seen