"""morning_scan candidate_history 持久化测试 (Issue1).

背景: morning_scan 落盘只写 JSON + watchlist, 没写 screener.candidate_history 表
→ candidate_history 一直空 → [A][B][C] 假设 (强势入场/surge不追/scorer失效) 到回测日无数据源.
本测验证 _persist_candidates 把 top 候选正确写入表, 字段映射对, 幂等.
"""
import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _build_tmp_screener_db(tmp_path, monkeypatch):
    """建 tmp screener DB + monkeypatch cfg.SCREENER_DB. 返回 db_path."""
    import a_stock.config as cfg
    import a_stock.db as db
    tmp_db = tmp_path / "screener.sqlite"
    monkeypatch.setattr(cfg, "SCREENER_DB", tmp_db)
    with db.conn(tmp_db) as c:
        c.executescript(db.SCREENER_SCHEMA)
    return tmp_db


def test_persist_candidates_writes_history(tmp_path, monkeypatch):
    """_persist_candidates 把 top 候选写入 candidate_history (strategy=mid 默认).

    字段映射: net_flow_yi(亿) → net_flow(元, ×1e8); total → score.
    """
    _build_tmp_screener_db(tmp_path, monkeypatch)
    import a_stock.morning_scan as ms
    import a_stock.db as db
    import a_stock.config as cfg

    top = [
        {"code": "T_AA", "name": "测试A", "total": 65.3, "level": "偏多",
         "net_flow_yi": 2.5, "change_pct": 3.2,
         "factors": {"sector": {"detail": {"industry": "医药生物"}}}},
        {"code": "T_BB", "name": "测试B", "total": 58.0, "level": "中性",
         "net_flow_yi": -1.1, "change_pct": -0.5},
    ]
    n = ms._persist_candidates("2026-07-01", top)

    assert n == 2
    with db.conn(cfg.SCREENER_DB) as c:
        rows = c.execute(
            "SELECT code, name, score, net_flow, change_pct, strategy, sector "
            "FROM candidate_history WHERE scan_date=? ORDER BY score DESC",
            ("2026-07-01",)).fetchall()
    assert len(rows) == 2
    assert rows[0]["code"] == "T_AA"
    assert rows[0]["score"] == 65.3
    assert rows[0]["net_flow"] == pytest.approx(2.5e8)  # 亿→元
    assert rows[0]["strategy"] == "mid"  # 默认策略
    assert rows[0]["sector"] == "医药生物"  # 从 factors.sector.detail.industry 取
    assert rows[1]["code"] == "T_BB"
    assert rows[1]["net_flow"] == pytest.approx(-1.1e8)
    assert rows[1]["sector"] is None  # T_BB 无 factors → sector=None


def test_persist_candidates_idempotent(tmp_path, monkeypatch):
    """UNIQUE(scan_date,strategy,code) → 同候选重复调不重复写 (upsert)."""
    _build_tmp_screener_db(tmp_path, monkeypatch)
    import a_stock.morning_scan as ms
    import a_stock.db as db
    import a_stock.config as cfg

    top = [{"code": "T_AA", "name": "A", "total": 60.0,
            "net_flow_yi": 1.0, "change_pct": 1.0}]
    ms._persist_candidates("2026-07-01", top)
    ms._persist_candidates("2026-07-01", top)  # 重复调

    with db.conn(cfg.SCREENER_DB) as c:
        cnt = c.execute(
            "SELECT COUNT(*) FROM candidate_history WHERE scan_date=?",
            ("2026-07-01",)).fetchone()[0]
    assert cnt == 1


def test_persist_candidates_resilient_to_missing_fields(tmp_path, monkeypatch):
    """候选缺字段 (如策略层产出的裸 code) 不 crash, 用默认值写入."""
    _build_tmp_screener_db(tmp_path, monkeypatch)
    import a_stock.morning_scan as ms
    import a_stock.db as db
    import a_stock.config as cfg

    top = [{"code": "T_BARE", "name": "裸code"}]  # 无 total/net_flow/level
    n = ms._persist_candidates("2026-07-01", top)

    assert n == 1  # .get 容错, 不阻断
    with db.conn(cfg.SCREENER_DB) as c:
        row = c.execute(
            "SELECT score, net_flow FROM candidate_history WHERE code=?",
            ("T_BARE",)).fetchone()
    assert row["score"] is None
    assert row["net_flow"] == 0
