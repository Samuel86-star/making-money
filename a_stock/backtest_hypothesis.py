"""假设回测框架: 输入setup → 算命中率/expectancy + 样本量/过拟合警告.

借鉴 edge-pipeline/backtest-expert (docs/references/trading-skills-methodology.md 第6条).
喂给 docs/review/daily.md 验证区 5工作日回测 — 让假设验证有硬框架非拍脑袋.

判定:
- 样本量 n≥30 才充分 (sample_adequate)
- expectancy_pct > 0 且 n≥30 → 建议保留setup
- expectancy_pct ≤ 0 且 n≥30 → 建议停用setup
- n<30 → 不下结论, 继续攒样本
"""
import argparse
import a_stock.stats as stats


def run(setup: str, window_days: int | None = None) -> dict:
    """回测某setup. 返回 {setup, n, expectancy_pct, sample_adequate, verdict, warnings}."""
    exp = stats.expectancy(setup=setup, window_days=window_days)
    if not isinstance(exp, dict) or "n" not in exp:
        exp = {"n": 0, "win_rate": 0, "expectancy_pct": 0}
    n = exp.get("n", 0)
    e = exp.get("expectancy_pct", 0)
    adequate = n >= 30
    warnings = []
    if not adequate:
        warnings.append(f"样本不足: n={n}<30, 不下结论, 继续攒样本")
    if adequate and e <= 0:
        warnings.append(f"expectancy={e}%≤0 且样本充分, 建议停用该setup")
    if adequate and e > 0:
        warnings.append(f"expectancy={e}%>0 且样本充分, 建议保留该setup")
    if adequate and exp.get("win_rate", 0) > 0.9:
        warnings.append("胜率>90% 警惕过拟合: 检查是否只挑了盈利样本")
    verdict = "保留" if (adequate and e > 0) else ("停用" if (adequate and e <= 0) else "待样本")
    return {**exp, "sample_adequate": adequate, "verdict": verdict, "warnings": warnings}


def main():
    ap = argparse.ArgumentParser(description="假设回测框架 (setup验证)")
    ap.add_argument("--setup", required=True, help="setup标签: pullback/breakout/anomaly/rule")
    ap.add_argument("--days", type=int, default=None, help="回看窗口天数")
    args = ap.parse_args()
    r = run(args.setup, args.days)
    print(f"=== 假设回测: setup={args.setup} ===")
    print(f"样本量 n: {r['n']}  (充分? {'是' if r['sample_adequate'] else '否, 需≥30'})")
    print(f"胜率: {r.get('win_rate', 0)*100:.1f}%  ({r.get('wins',0)}盈/{r.get('losses',0)}亏)")
    print(f"平均盈: +{r.get('avg_win',0)}%  平均亏: -{r.get('avg_loss',0)}%")
    print(f"expectancy: {r.get('expectancy_pct',0):+}%")
    print(f"裁决: {r['verdict']}")
    if r["warnings"]:
        print("警告:")
        for w in r["warnings"]:
            print(f"  ⚠️  {w}")


if __name__ == "__main__":
    main()
