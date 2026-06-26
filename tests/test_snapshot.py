import json
import a_stock.config as cfg
from a_stock.a_screen.snapshot import save_snapshot, load_snapshot, update_ai_analysis, save_markdown


def test_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "BRIEFS_DIR", tmp_path)
    snap = {"meta": {"code": "000001"}, "snapshot_date": "2026-06-26", "ai_analysis": None}
    p = save_snapshot(snap)
    assert p.exists()
    loaded = load_snapshot("000001", "2026-06-26")
    assert loaded["meta"]["code"] == "000001"


def test_update_ai_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "BRIEFS_DIR", tmp_path)
    snap = {"meta": {"code": "000002"}, "snapshot_date": "2026-06-26", "ai_analysis": None}
    save_snapshot(snap)
    update_ai_analysis("000002", "2026-06-26", "建议观望")
    loaded = load_snapshot("000002", "2026-06-26")
    assert loaded["ai_analysis"] == "建议观望"