"""morning_scan 确定性测试 (code-review #3).

#3 修复: scored_codes 从 set 改 sorted list, 消除 PYTHONHASHSEED 依赖.
测试: 两个 (total, net_flow_yi) 完全并列的候选, 在不同 PYTHONHASHSEED 下 top5 顺序一致.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYTHON = str(REPO / ".venv" / "bin" / "python")

# 内联脚本: monkeypatch 所有外部依赖, 构造并列候选, 跑 scan(dry_run=True), 打印 top codes.
# 关键: 候选码 T_ZZZ/T_AAA/T_MMM 的 stocks 插入序与字典序相反, 排序键 (total, net_flow_yi) 全并列.
# 旧代码 (set 迭代) → 顺序随 PYTHONHASHSEED 变; 新代码 (sorted list) → 固定字典序 T_AAA,T_MMM,T_ZZZ.
_INLINE_SCRIPT = textwrap.dedent("""
    import sys, tempfile
    sys.path.insert(0, %r)
    import a_stock.morning_scan as ms
    from a_stock.scorers import TotalScore

    # 拉取: 3 只候选, 插入序 ZZZ,AAA,MMM (与字典序相反), net_flow 全相同 → net_flow_yi 并列
    def fake_fetch(top_n=20):
        return [
            {"code": "T_ZZZ", "name": "Z", "net_flow": int(1e8), "change_pct": 1},
            {"code": "T_AAA", "name": "A", "net_flow": int(1e8), "change_pct": 1},
            {"code": "T_MMM", "name": "M", "net_flow": int(1e8), "change_pct": 1},
        ]
    ms.fetch_market_stocks = fake_fetch

    # 策略层: 无候选 (隔离 screener 路径, scored_codes = sorted top10 codes)
    import a_stock.strategies.runner as _r
    _r.run_top = lambda cands, top_m=20: []

    # 评分: 全部 total=60 (并列), 无 veto
    def fake_score(code, name=""):
        ts = TotalScore(code=code, name=name)
        ts.total = 60
        ts.level = "B"
        ts.veto = False
        ts.veto_reason = ""
        return ts
    def fake_to_dict(ts):
        return {"code": ts.code, "name": ts.name, "total": ts.total, "level": ts.level,
                "veto": ts.veto, "veto_reason": ts.veto_reason,
                "position_scale": 1.0, "factors": {}}
    ms.score_candidate = fake_score
    ms.to_dict = fake_to_dict

    # 板块轮动: 返回 None (跳过)
    import a_stock.sector_rotation as _sr
    _sr.analyze = lambda: None

    # 落盘到 tmp (避免污染 data/)
    ms.cfg.DAILY_DIR = __import__("pathlib").Path(tempfile.gettempdir())

    result = ms.scan(top_n=20, score_top=5, dry_run=True)
    tops = [t["code"] for t in result.get("top", [])]
    print(",".join(tops))
""") % str(REPO)


def _run_scan_under_hashseed(seed: str) -> str:
    """以指定 PYTHONHASHSEED 跑内联脚本, 返回 stdout (top codes 逗号分隔)."""
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = seed
    # PYTHONHASHSEED 只在解释器启动时生效, 必须用独立子进程
    proc = subprocess.run(
        [PYTHON, "-c", _INLINE_SCRIPT],
        capture_output=True, text=True, env=env, cwd=str(REPO),
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"scan under PYTHONHASHSEED={seed} failed (rc={proc.returncode}):\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    # 取最后一非空行 (脚本可能有其他 print 噪音)
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def test_scored_codes_deterministic_across_hashseeds():
    """#3: 并列候选在不同 PYTHONHASHSEED 下 top5 顺序一致 (字典序 T_AAA,T_MMM,T_TZZZ).

    旧代码 scored_codes 是 set, 迭代序随 hash seed 变 → 并列项相对序非确定.
    新代码 sorted list → 字典序固定.
    """
    out_seed0 = _run_scan_under_hashseed("0")
    out_seed1 = _run_scan_under_hashseed("1")
    out_seed42 = _run_scan_under_hashseed("42")

    # 三个不同 seed 输出必须完全一致 (确定性)
    assert out_seed0 == out_seed1 == out_seed42, (
        f"非确定: seed0={out_seed0!r} seed1={out_seed1!r} seed42={out_seed42!r}"
    )

    # 且顺序是字典序 (T_AAA < T_MMM < T_ZZZ), 证明并列按 code 确定性打破
    # (插入序是 ZZZ,AAA,MMM; 若按插入序或 hash 序则不会得到字典序)
    assert out_seed0 == "T_AAA,T_MMM,T_ZZZ", (
        f"预期字典序 T_AAA,T_MMM,T_ZZZ, 实际 {out_seed0!r}"
    )
