"""validate_state 单元测试. 校验 PROJECT_STATE 成本列与 db 一致."""
import a_stock.config as cfg
import a_stock.db as db
from a_stock.validate_state import validate, _load_db_costs


def _setup_db(tmp_path, monkeypatch):
    tmp_db = tmp_path / "t_val.sqlite"
    monkeypatch.setattr(cfg, "DECISIONS_DB", tmp_db)
    db.init_decisions_db()
    return tmp_db


def test_validate_passes_when_costs_match(tmp_path, monkeypatch):
    """文档成本与db一致 → 无不一致."""
    _setup_db(tmp_path, monkeypatch)
    db.insert_decision(code="600276", name="恒瑞", strategy="mid",
                       action="buy", decision_date="2026-06-26",
                       price=49.121, quantity=100)
    state = tmp_path / "state.md"
    state.write_text(
        "## 当前持仓\n```\n"
        "600276  恒瑞医药          100  49.121    5,293\n"
        "```\n"
    )
    assert validate(state) == []


def test_validate_flags_mismatch(tmp_path, monkeypatch):
    """文档成本与db不一致 → 报告."""
    _setup_db(tmp_path, monkeypatch)
    db.insert_decision(code="300059", name="东财", strategy="mid",
                       action="buy", decision_date="2026-06-26",
                       price=21.279, quantity=300)
    state = tmp_path / "state.md"
    state.write_text(
        "## 当前持仓\n```\n"
        "300059  东方财富          300  20.07    6,021\n"  # 错: 20.07 vs 21.279
        "```\n"
    )
    mismatches = validate(state)
    assert len(mismatches) == 1
    assert mismatches[0]["code"] == "300059"
    assert mismatches[0]["db_cost"] == 21.279


def test_validate_skips_code_not_in_db(tmp_path, monkeypatch):
    """文档有持仓但db已清仓 → 跳过 (不报不一致)."""
    _setup_db(tmp_path, monkeypatch)
    state = tmp_path / "state.md"
    state.write_text(
        "## 当前持仓\n```\n"
        "600000  浦发银行          100  10.50    1,050\n"  # db无此持仓
        "```\n"
    )
    assert validate(state) == []


def test_load_db_costs_nets_reduces(tmp_path, monkeypatch):
    """db成本正确减去 reduce: 买1000@10 减600 → 剩400 成本仍10."""
    from a_stock.a_screen.decision_log import reduce_position
    _setup_db(tmp_path, monkeypatch)
    pid = db.insert_decision(code="T_VAL1", name="T", strategy="mid",
                             action="buy", decision_date="2026-06-29",
                             price=10.0, quantity=1000)
    reduce_position(pid, reduce_price=11.0, reduce_qty=600, reason="partial_take_profit")
    costs = _load_db_costs()
    assert costs["T_VAL1"] == 10.0  # 成本不变
