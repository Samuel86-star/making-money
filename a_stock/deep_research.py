"""深度研究: DCF + Comps + DD清单 + 催化剂 + beat/miss.
抄 UZI-Skill 17机构方法选6个, A股参数化 (rf=2.5%/ERP=6%/税率25%/g=2.5%).
输出过 self_review.gate() 门禁才生效."""
import argparse
import json
from dataclasses import dataclass, field
from datetime import datetime, date
import a_stock.config as cfg

# A股参数 (抄 UZI compute_deep_methods A股参数化)
RF = 0.025          # 无风险利率 (10年国债)
ERP = 0.06          # 股权风险溢价
TAX_RATE = 0.25     # 企业所得税
TERMINAL_G = 0.025  # 永续增长率
WACC_DEFAULT = RF + ERP  # 8.5%


@dataclass
class DeepResearch:
    code: str
    name: str
    price: float
    # 基本面 (可选, 拉不到降级)
    eps: float = 0
    pe_ttm: float = 0
    net_profit_yoy: float = 0
    roe: float = 0
    # 评分 (接 Phase 3)
    score: float = 50
    veto: bool = False
    veto_reason: str = ""
    # 仓位建议
    position_pct: float = 0
    stop_loss: float = 0
    target: float = 0
    # 动量
    momentum_60d: float = 0
    # 输出
    dcf_target: float = 0
    comps_target: float = 0
    dd_flags: list = field(default_factory=list)
    catalysts: list = field(default_factory=list)
    verdict: str = ""


def dcf(eps: float, growth_5y: float = 0.10, wacc: float = WACC_DEFAULT,
        g: float = TERMINAL_G) -> float | None:
    """两段FCF DCF (简化: 用EPS代理FCF). 返回目标价.
    抄 UZI DCF 两段+Gordon终值思路, 简化."""
    if eps <= 0:
        return None
    # 前5年 EPS (增长率 growth_5y)
    eps_proj = [eps * (1 + growth_5y) ** i for i in range(1, 6)]
    # 折现
    pv_explicit = sum(e / (1 + wacc) ** i for i, e in enumerate(eps_proj, 1))
    # 终值 (Gordon): EPS_5 × (1+g) / (wacc - g)
    terminal = eps_proj[-1] * (1 + g) / (wacc - g)
    pv_terminal = terminal / (1 + wacc) ** 5
    intrinsic = pv_explicit + pv_terminal
    return round(intrinsic, 2)


def comps(pe_ttm: float, eps: float, sector_pe_median: float = 25) -> float | None:
    """Comps 同行对标: 目标价 = 行业中位PE × EPS.
    抄 UZI Comps PE分位思路, 简化."""
    if eps <= 0 or sector_pe_median <= 0:
        return None
    return round(sector_pe_median * eps, 2)


def dd_checklist(r: DeepResearch) -> list[str]:
    """DD尽调清单 (抄 UZI DD 21项, 简化为关键项)."""
    flags = []
    if r.roe > 0 and r.roe < 5:
        flags.append("ROE<5% 盈利能力弱")
    if r.net_profit_yoy < -20:
        flags.append("净利同比<-20% 业绩下滑")
    if r.pe_ttm > 80:
        flags.append("PE>80 估值过高")
    if r.pe_ttm > 0 and r.pe_ttm < 10:
        flags.append("PE<10 可能价值陷阱或周期顶部")
    if r.momentum_60d < -20:
        flags.append("60日跌>20% 趋势走坏")
    if not flags:
        flags.append("✅ DD无明显红旗")
    return flags


def catalysts_list(code: str) -> list[str]:
    """催化剂日历 (简化: 接 macro_calendar)."""
    from a_stock.macro_calendar import list_events
    try:
        events = list_events(days_ahead=60, impact="high")
        return [f"{e['date']} {e['name']}" for e in events[:5]]
    except Exception:
        return []


def research(code: str, name: str = "", price: float | None = None,
             score: float | None = None) -> dict:
    """完整深研. 返回 dict (供 self_review.gate)."""
    # 拉实时价
    if price is None:
        from a_stock.anomaly import _live_quote
        q = _live_quote(code)
        price = q["price"] if q else 0

    # 拉基本面 (降级容忍)
    eps, pe_ttm, net_profit_yoy, roe = 0, 0, 0, 0
    try:
        from a_stock.a_stock_data import tencent_quote
        tq = tencent_quote(code)
        if tq:
            pe_ttm = tq.get("pe_ttm") or tq.get("pe") or 0
    except Exception:
        pass

    # 评分 (接 Phase 3)
    if score is None:
        try:
            from a_stock.scorers.total_scorer import score_candidate
            ts = score_candidate(code, name)
            score = ts.total
            veto = ts.veto
            veto_reason = ts.veto_reason
        except Exception:
            score, veto, veto_reason = 50, False, ""
    else:
        veto = score == -100
        veto_reason = "ST/暴雷" if veto else ""

    # 动量
    momentum_60d = 0
    try:
        from a_stock.strategies.runner import build_indicators
        ind = build_indicators(code, name)
        momentum_60d = ind.get("momentum_60d", 0)
    except Exception:
        pass

    r = DeepResearch(
        code=code, name=name or code, price=price,
        eps=eps, pe_ttm=pe_ttm,
        net_profit_yoy=net_profit_yoy, roe=roe,
        score=score, veto=veto, veto_reason=veto_reason,
        momentum_60d=momentum_60d,
    )

    # DCF (用 EPS, 拉不到 EPS 用 PE 反推)
    if eps <= 0 and pe_ttm > 0 and price > 0:
        eps = price / pe_ttm
    growth = max(0.05, net_profit_yoy / 100) if net_profit_yoy > 0 else 0.08
    r.dcf_target = dcf(eps, growth_5y=growth) or 0
    r.comps_target = comps(pe_ttm, eps) or 0

    # 目标价 = DCF + Comps 均值
    targets = [t for t in [r.dcf_target, r.comps_target] if t > 0]
    r.target = round(sum(targets) / len(targets), 2) if targets else price * 1.1

    # 止损 -8%
    r.stop_loss = round(price * 0.92, 2) if price else 0

    # 仓位 (评分缩放)
    from a_stock.scorers import score_to_position_scale
    scale = score_to_position_scale(score)
    r.position_pct = round(min(30, 15 * scale), 1)

    # DD + 催化剂
    r.dd_flags = dd_checklist(r)
    r.catalysts = catalysts_list(code)

    # 结论
    if r.veto:
        r.verdict = "❌ 否决, 不建议"
    elif score >= 70 and r.target > price:
        r.verdict = "✅ 建议关注"
    elif score >= 50:
        r.verdict = "⚠️ 观望"
    else:
        r.verdict = "❌ 评分低, 回避"

    return _to_dict(r)


def _to_dict(r: DeepResearch) -> dict:
    return {
        "code": r.code, "name": r.name, "price": r.price,
        "eps": r.eps, "pe_ttm": r.pe_ttm,
        "net_profit_yoy": r.net_profit_yoy, "roe": r.roe,
        "score": r.score, "veto": r.veto, "veto_reason": r.veto_reason,
        "position_pct": r.position_pct, "stop_loss": r.stop_loss, "target": r.target,
        "momentum_60d": r.momentum_60d,
        "dcf_target": r.dcf_target, "comps_target": r.comps_target,
        "dd_flags": r.dd_flags, "catalysts": r.catalysts,
        "verdict": r.verdict,
        "researched_at": datetime.now().isoformat(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("--name", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--skip-review", action="store_true")
    args = ap.parse_args()

    import os
    r = research(args.code, args.name)

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
        return

    print(f"\n=== {r['name']}({r['code']}) 深度研究 ===")
    print(f"现价: {r['price']}  PE: {r['pe_ttm']}")
    print(f"评分: {r['score']}  veto: {r['veto']} ({r['veto_reason']})")
    print(f"\n估值:")
    print(f"  DCF目标: {r['dcf_target']}  Comps目标: {r['comps_target']}")
    print(f"  综合目标: {r['target']}  止损: {r.stop_loss if hasattr(r,'stop_loss') else r['stop_loss']}")
    print(f"  建议仓位: {r['position_pct']}%")
    print(f"\nDD尽调:")
    for f in r["dd_flags"]:
        print(f"  • {f}")
    print(f"\n催化剂:")
    for c in r["catalysts"]:
        print(f"  • {c}")
    print(f"\n结论: {r['verdict']}")

    # 门禁
    if not args.skip_review and not os.environ.get("A_STOCK_SKIP_REVIEW"):
        from a_stock.self_review import gate, review
        try:
            gate(r)
            print("\n✅ self-review 通过")
        except RuntimeError as e:
            print(f"\n{e}")
    else:
        rv = review(r)
        print(f"\n[skip-review] critical={rv['critical_count']} warning={rv['warning_count']}")


if __name__ == "__main__":
    main()
