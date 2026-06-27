"""总评分入口: 调5个因子 → 加权 → 评级."""
import argparse
import json
from . import TotalScore, score_to_position_scale
from . import technical_scorer, moneyflow_scorer, fundamental_scorer, sector_scorer, event_scorer


def score_candidate(code: str, name: str = "") -> TotalScore:
    """对单标的打分."""
    ts = TotalScore(code=code, name=name or code)
    ts.technical = technical_scorer.score(code)
    ts.moneyflow = moneyflow_scorer.score(code)
    ts.fundamental = fundamental_scorer.score(code)
    ts.sector = sector_scorer.score(code)
    ts.event = event_scorer.score(code, name)
    ts.calculate()
    return ts


def to_dict(ts: TotalScore) -> dict:
    return {
        "code": ts.code, "name": ts.name,
        "total": ts.total, "level": ts.level,
        "veto": ts.veto, "veto_reason": ts.veto_reason,
        "position_scale": score_to_position_scale(ts.total),
        "factors": {
            "technical": {"score": ts.technical.score, "veto": ts.technical.veto, "detail": ts.technical.detail},
            "moneyflow": {"score": ts.moneyflow.score, "veto": ts.moneyflow.veto, "detail": ts.moneyflow.detail},
            "fundamental": {"score": ts.fundamental.score, "detail": ts.fundamental.detail},
            "sector": {"score": ts.sector.score, "detail": ts.sector.detail},
            "event": {"score": ts.event.score, "veto": ts.event.veto, "detail": ts.event.detail},
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code")
    ap.add_argument("--name", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ts = score_candidate(args.code, args.name)
    d = to_dict(ts)

    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2, default=str))
        return

    print(f"\n=== {ts.name}({ts.code}) 多因子评分 ===")
    print(f"总分: {ts.total}  {ts.level}")
    if ts.veto:
        print(f"⛔ 否决: {ts.veto_reason}")
    print(f"仓位缩放: ×{d['position_scale']}")
    print()
    print(f"{'因子':<14} {'权重':<6} {'得分':<6} {'明细'}")
    for k, w in [("technical", 0.35), ("moneyflow", 0.35), ("fundamental", 0.10),
                 ("sector", 0.10), ("event", 0.10)]:
        f = d["factors"][k]
        veto_mark = " ⛔" if f.get("veto") else ""
        print(f"{k:<14} {w:<6.0%} {f['score']:<6.0f} {f.get('detail', {})}{veto_mark}")


if __name__ == "__main__":
    main()
