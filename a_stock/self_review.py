"""self-review 物理门禁: critical>0 阻断出建议.
抄 UZI-Skill assemble_report.py 的 raise RuntimeError 机制 + issue 带 suggested_fix.
BUG→check→测试闭环: 每踩一个坑沉淀成 check."""
import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import a_stock.config as cfg

ISSUES_FILE = cfg.DATA_DIR / "self_review_issues.json"


@dataclass
class Issue:
    severity: str  # critical / warning / info
    check: str     # check 名
    message: str
    suggested_fix: str = ""
    context: dict = field(default_factory=dict)


def review(research: dict) -> dict:
    """对 deep_research 结果跑所有 check. 返回 {critical, warning, issues}."""
    issues: list[Issue] = []

    # === critical checks (物理阻断) ===
    _check_data_completeness(research, issues)
    _check_valuation_sane(research, issues)
    _check_has_stop_loss(research, issues)
    _check_position_within_limit(research, issues)
    _check_no_veto_stock(research, issues)

    # === warning checks (打印不阻断) ===
    _check_high_pe(research, issues)
    _check_negative_momentum(research, issues)
    _check_low_score(research, issues)

    crit = sum(1 for i in issues if i.severity == "critical")
    warn = sum(1 for i in issues if i.severity == "warning")

    result = {
        "critical_count": crit,
        "warning_count": warn,
        "passed": crit == 0,
        "issues": [
            {"severity": i.severity, "check": i.check, "message": i.message,
             "suggested_fix": i.suggested_fix, "context": i.context}
            for i in issues
        ],
        "reviewed_at": datetime.now().isoformat(),
    }
    _save_issues(research.get("code", ""), result)
    return result


# === critical checks ===

def _check_data_completeness(r: dict, issues: list[Issue]) -> None:
    """数据缺失 → critical (抄 UZI check_empty_dims)."""
    code = r.get("code", "")
    if not r.get("price") or r.get("price", 0) <= 0:
        issues.append(Issue("critical", "data_completeness",
                            f"{code} 无有效价格",
                            "检查实时行情拉取, qt.gtimg.cn 是否可达"))


def _check_valuation_sane(r: dict, issues: list[Issue]) -> None:
    """估值异常 → critical (DCF 目标价偏离现价>100%)."""
    target = r.get("dcf_target", 0)
    price = r.get("price", 0)
    if target and price and abs(target - price) / price > 1.0:
        issues.append(Issue("critical", "valuation_sane",
                            f"DCF目标价{target:.2f}偏离现价{price:.2f}>100%",
                            "重算DCF参数(WACC/g/FCF), 或改用Comps交叉验证",
                            {"target": target, "price": price}))


def _check_has_stop_loss(r: dict, issues: list[Issue]) -> None:
    """建议无止损 → critical."""
    if not r.get("stop_loss") or r.get("stop_loss", 0) <= 0:
        issues.append(Issue("critical", "has_stop_loss",
                            "建议未设止损价",
                            "止损 = 现价 × (1 - 单笔风险/仓位金额), 默认 -8%"))


def _check_position_within_limit(r: dict, issues: list[Issue]) -> None:
    """仓位超限 → critical (单仓>30%)."""
    pos_pct = r.get("position_pct", 0)
    if pos_pct > 30:
        issues.append(Issue("critical", "position_within_limit",
                            f"仓位{pos_pct:.1f}% > 30%上限",
                            "减少股数, 或拆分多次建仓",
                            {"position_pct": pos_pct}))


def _check_no_veto_stock(r: dict, issues: list[Issue]) -> None:
    """veto 标的 → critical."""
    if r.get("veto") or r.get("score", 0) == -100:
        issues.append(Issue("critical", "no_veto_stock",
                            f"{r.get('code','')} 触发一票否决: {r.get('veto_reason','')}",
                            "跳过该标的, 不出建议"))


# === warning checks ===

def _check_high_pe(r: dict, issues: list[Issue]) -> None:
    pe = r.get("pe_ttm", 0)
    if pe > 80:
        issues.append(Issue("warning", "high_pe",
                            f"PE_TTM {pe:.0f} 偏高",
                            "检查是否周期股顶部, 或用 Forward PE"))


def _check_negative_momentum(r: dict, issues: list[Issue]) -> None:
    mom = r.get("momentum_60d", 0)
    if mom < -15:
        issues.append(Issue("warning", "negative_momentum",
                            f"60日动量{mom:.1f}% 深度下跌",
                            "等企稳信号 (放量长阳/RSI<30反弹) 再进"))


def _check_low_score(r: dict, issues: list[Issue]) -> None:
    score = r.get("score", 50)
    if 0 < score < 40:
        issues.append(Issue("warning", "low_score",
                            f"多因子评分{score:.0f}<40",
                            "评分低, 仓位应为0, 谨慎"))


def _save_issues(code: str, result: dict) -> None:
    """落盘 issue 历史 (BUG→check→测试闭环用)."""
    ISSUES_FILE.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if ISSUES_FILE.exists():
        try:
            history = json.loads(ISSUES_FILE.read_text())
        except Exception:
            history = []
    history.append({"code": code, **result})
    # 保留最近 100 条
    ISSUES_FILE.write_text(json.dumps(history[-100:], ensure_ascii=False, indent=2))


def gate(research: dict) -> None:
    """物理门禁: critical>0 raise RuntimeError (抄 UZI assemble_report)."""
    result = review(research)
    if result["critical_count"] > 0:
        crit_issues = [i for i in result["issues"] if i["severity"] == "critical"]
        msgs = "\n".join(f"  ⛔ {i['check']}: {i['message']}\n     修复: {i['suggested_fix']}"
                         for i in crit_issues)
        raise RuntimeError(
            f"⛔ BLOCKED by self-review: {research.get('code','')} 有 "
            f"{result['critical_count']} 个 critical 问题:\n{msgs}\n"
            f"→ 修复后重跑. 强制跳过(仅调试): export A_STOCK_SKIP_REVIEW=1"
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-file", help="deep_research 输出的 JSON 文件")
    args = ap.parse_args()

    if not args.json_file:
        print("用法: python -m a_stock.self_review --json-file <research.json>")
        return

    research = json.loads(Path(args.json_file).read_text())
    result = review(research)
    print(f"\n=== self-review 结果 ===")
    print(f"critical: {result['critical_count']}  warning: {result['warning_count']}  "
          f"passed: {result['passed']}")
    for i in result["issues"]:
        emoji = {"critical": "⛔", "warning": "⚠️", "info": "ℹ️"}[i["severity"]]
        print(f"  {emoji} [{i['check']}] {i['message']}")
        if i["suggested_fix"]:
            print(f"     修复: {i['suggested_fix']}")


if __name__ == "__main__":
    main()
