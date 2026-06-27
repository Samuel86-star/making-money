"""加载异动监控目标: 持仓 + watchlist."""
import sqlite3
import a_stock.config as cfg


def load_targets() -> list[dict]:
    """返回 [{code, name}] 持仓 + watchlist 去重."""
    conn = sqlite3.connect(str(cfg.DECISIONS_DB))
    conn.row_factory = sqlite3.Row
    targets = {}
    # 持仓
    for r in conn.execute("""
        SELECT code, name FROM decisions
        WHERE action IN ('buy','add') AND close_date IS NULL
    """).fetchall():
        targets[r["code"]] = {"code": r["code"], "name": r["name"] or r["code"]}
    # watchlist
    for r in conn.execute("SELECT code, name FROM watchlist").fetchall():
        if r["code"] not in targets:
            targets[r["code"]] = {"code": r["code"], "name": r["name"] or r["code"]}
    conn.close()
    return list(targets.values())
