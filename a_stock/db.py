"""SQLite 封装:schema 初始化 + CRUD helper。"""
import sqlite3
from contextlib import contextmanager
import a_stock.config as cfg

DECISIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    name            TEXT,
    strategy        TEXT NOT NULL CHECK(strategy IN ('short', 'mid')),
    action          TEXT NOT NULL CHECK(action IN ('buy', 'add', 'sell', 'close', 'reduce')),
    decision_date   TEXT NOT NULL,
    decision_time   TEXT,
    price           REAL NOT NULL,
    quantity        INTEGER NOT NULL,
    amount          REAL,
    reason          TEXT,
    brief_snapshot_path TEXT,
    plan_stop_loss      REAL,
    plan_target         REAL,
    plan_hold_days      INTEGER,
    plan_max_position_pct REAL,
    close_date      TEXT,
    close_price     REAL,
    close_reason    TEXT CHECK(close_reason IN ('stop_loss', 'target', 'manual', 'expired', 'partial_take_profit', 'partial_stop_loss')),
    pnl_pct         REAL,
    parent_id       INTEGER,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_code ON decisions(code);
CREATE INDEX IF NOT EXISTS idx_strategy_date ON decisions(strategy, decision_date);
CREATE INDEX IF NOT EXISTS idx_open ON decisions(close_date);
CREATE TABLE IF NOT EXISTS watchlist (
    code        TEXT PRIMARY KEY,
    name        TEXT,
    theme       TEXT,
    note        TEXT,
    added_at    TEXT DEFAULT (datetime('now'))
);
"""

SCREENER_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date           TEXT NOT NULL,
    strategy            TEXT NOT NULL CHECK(strategy IN ('short', 'mid')),
    code                TEXT NOT NULL,
    name                TEXT,
    sector              TEXT,
    concept_primary     TEXT,
    net_flow            REAL,
    change_pct          REAL,
    pe_ttm              REAL,
    pb                  REAL,
    mcap_yi             REAL,
    turnover_pct        REAL,
    report_count_7d     INTEGER,
    hot_reason          TEXT,
    on_dragon_tiger     INTEGER DEFAULT 0,
    score               REAL,
    raw_data_path       TEXT,
    UNIQUE(scan_date, strategy, code)
);
CREATE INDEX IF NOT EXISTS idx_strategy_date ON candidate_history(strategy, scan_date);
CREATE INDEX IF NOT EXISTS idx_code ON candidate_history(code);
CREATE TABLE IF NOT EXISTS sector_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date       TEXT NOT NULL,
    sector_type     TEXT NOT NULL CHECK(sector_type IN ('industry', 'concept')),
    name            TEXT NOT NULL,
    change_pct      REAL,
    net_flow        REAL,
    leader_name     TEXT,
    leader_code     TEXT,
    rank            INTEGER,
    UNIQUE(scan_date, sector_type, name)
);
CREATE INDEX IF NOT EXISTS idx_sector_date ON sector_history(scan_date);
CREATE TABLE IF NOT EXISTS daily_summary (
    date                TEXT PRIMARY KEY,
    generated_at        TEXT NOT NULL,
    short_count         INTEGER,
    mid_count           INTEGER,
    sector_count        INTEGER,
    report_path         TEXT,
    brief_snapshots     INTEGER,
    status              TEXT DEFAULT 'ok'
);
CREATE TABLE IF NOT EXISTS dragon_tiger (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date      TEXT NOT NULL,
    code            TEXT NOT NULL,
    name            TEXT,
    reason          TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(trade_date, code)
);
"""


@contextmanager
def conn(db_path):
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _migrate_decisions_v2() -> None:
    """Idempotent migration: add parent_id, update action CHECK, extend close_reason CHECK."""
    with conn(cfg.DECISIONS_DB) as c:
        cols = {row[1] for row in c.execute("PRAGMA table_info(decisions)").fetchall()}
        if "parent_id" in cols:
            return  # Already migrated

        c.executescript("""
            CREATE TABLE decisions_v2 (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                code            TEXT NOT NULL,
                name            TEXT,
                strategy        TEXT NOT NULL CHECK(strategy IN ('short', 'mid')),
                action          TEXT NOT NULL CHECK(action IN ('buy', 'add', 'sell', 'close', 'reduce')),
                decision_date   TEXT NOT NULL,
                decision_time   TEXT,
                price           REAL NOT NULL,
                quantity        INTEGER NOT NULL,
                amount          REAL,
                reason          TEXT,
                brief_snapshot_path TEXT,
                plan_stop_loss      REAL,
                plan_target         REAL,
                plan_hold_days      INTEGER,
                plan_max_position_pct REAL,
                close_date      TEXT,
                close_price     REAL,
                close_reason    TEXT CHECK(close_reason IN ('stop_loss', 'target', 'manual', 'expired', 'partial_take_profit', 'partial_stop_loss')),
                pnl_pct         REAL,
                parent_id       INTEGER,
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now'))
            );
            INSERT INTO decisions_v2 SELECT
                id, code, name, strategy, action, decision_date, decision_time,
                price, quantity, amount, reason, brief_snapshot_path,
                plan_stop_loss, plan_target, plan_hold_days, plan_max_position_pct,
                close_date, close_price, close_reason, pnl_pct, NULL,
                created_at, updated_at
            FROM decisions;
            DROP TABLE decisions;
            ALTER TABLE decisions_v2 RENAME TO decisions;
            CREATE INDEX IF NOT EXISTS idx_code ON decisions(code);
            CREATE INDEX IF NOT EXISTS idx_strategy_date ON decisions(strategy, decision_date);
            CREATE INDEX IF NOT EXISTS idx_open ON decisions(close_date);
        """)


def init_decisions_db() -> None:
    with conn(cfg.DECISIONS_DB) as c:
        c.executescript(DECISIONS_SCHEMA)
    _migrate_decisions_v2()


def init_screener_db() -> None:
    with conn(cfg.SCREENER_DB) as c:
        c.executescript(SCREENER_SCHEMA)


def insert_decision(*, code, name=None, strategy, action, decision_date, price, quantity,
                    decision_time=None, reason=None, brief_snapshot_path=None,
                    plan_stop_loss=None, plan_target=None, plan_hold_days=None,
                    plan_max_position_pct=None, parent_id=None) -> int:
    amount = price * quantity
    with conn(cfg.DECISIONS_DB) as c:
        cur = c.execute("""
            INSERT INTO decisions
            (code, name, strategy, action, decision_date, decision_time,
             price, quantity, amount,
             reason, brief_snapshot_path, plan_stop_loss, plan_target,
             plan_hold_days, plan_max_position_pct, parent_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (code, name, strategy, action, decision_date, decision_time,
              price, quantity, amount,
              reason, brief_snapshot_path, plan_stop_loss, plan_target,
              plan_hold_days, plan_max_position_pct, parent_id))
        return cur.lastrowid


def update_decision_close(decision_id, close_date, close_price, close_reason, pnl_pct) -> None:
    with conn(cfg.DECISIONS_DB) as c:
        c.execute("""
            UPDATE decisions SET close_date=?, close_price=?, close_reason=?, pnl_pct=?,
                updated_at=datetime('now')
            WHERE id=?
        """, (close_date, close_price, close_reason, pnl_pct, decision_id))


def upsert_candidate(scan_date, strategy, code, **fields) -> None:
    cols = ["scan_date", "strategy", "code"] + list(fields.keys())
    placeholders = ",".join("?" * len(cols))
    update_cols = ",".join(f"{k}=excluded.{k}" for k in fields.keys())
    values = [scan_date, strategy, code] + list(fields.values())
    with conn(cfg.SCREENER_DB) as c:
        c.execute(f"""
            INSERT INTO candidate_history ({",".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(scan_date, strategy, code) DO UPDATE SET {update_cols}
        """, values)


def upsert_sector(scan_date, sector_type, name, **fields) -> None:
    cols = ["scan_date", "sector_type", "name"] + list(fields.keys())
    placeholders = ",".join("?" * len(cols))
    update_cols = ",".join(f"{k}=excluded.{k}" for k in fields.keys())
    values = [scan_date, sector_type, name] + list(fields.values())
    with conn(cfg.SCREENER_DB) as c:
        c.execute(f"""
            INSERT INTO sector_history ({",".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(scan_date, sector_type, name) DO UPDATE SET {update_cols}
        """, values)


def upsert_daily_summary(date, **fields) -> None:
    cols = ["date"] + list(fields.keys())
    placeholders = ",".join("?" * len(cols))
    update_cols = ",".join(f"{k}=excluded.{k}" for k in fields.keys())
    values = [date] + list(fields.values())
    with conn(cfg.SCREENER_DB) as c:
        c.execute(f"""
            INSERT INTO daily_summary ({",".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(date) DO UPDATE SET {update_cols}
        """, values)


def upsert_dragon_tiger(trade_date: str, code: str, name: str = "", reason: str = "") -> None:
    """写入/更新龙虎榜记录."""
    with conn(cfg.SCREENER_DB) as c:
        c.execute("""
            INSERT INTO dragon_tiger (trade_date, code, name, reason)
            VALUES (?,?,?,?)
            ON CONFLICT(trade_date, code) DO UPDATE SET
                name=excluded.name, reason=excluded.reason
        """, (trade_date, code, name, reason))