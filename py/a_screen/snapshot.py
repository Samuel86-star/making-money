"""brief 快照读写。"""
import json
from pathlib import Path
import py.config as cfg


def _path(code: str, date: str, ext: str = "json") -> Path:
    return cfg.BRIEFS_DIR / code / f"{date}.{ext}"


def save_snapshot(snap: dict) -> Path:
    p = _path(snap["meta"]["code"], snap["snapshot_date"], "json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, ensure_ascii=False, indent=2, default=str))
    return p


def load_snapshot(code: str, date: str, force: bool = False) -> dict | None:
    p = _path(code, date, "json")
    if not p.exists() or force:
        return None
    return json.loads(p.read_text())


def save_markdown(snap: dict, md: str) -> Path:
    p = _path(snap["meta"]["code"], snap["snapshot_date"], "md")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md)
    return p


def update_ai_analysis(code: str, date: str, analysis: str) -> None:
    snap = load_snapshot(code, date)
    if snap is None:
        raise FileNotFoundError(f"no snapshot for {code} {date}")
    snap["ai_analysis"] = analysis
    from datetime import datetime
    snap.setdefault("ai_analysis_meta", {})
    snap["ai_analysis_meta"]["analyzed_at"] = datetime.now().isoformat()
    save_snapshot(snap)