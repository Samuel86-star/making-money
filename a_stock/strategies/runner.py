"""策略扫描入口: 对单标的跑所有策略."""
import argparse
import json
from .registry import get_all, run_all
from .base import limit_pct


def build_indicators(code: str, name: str = "") -> dict:
    """从 OHLCV 算指标, 供策略用."""
    import pandas as pd
    import a_stock.config as cfg
    f = cfg.OHLCV_DIR / f"{code}.parquet"
    if not f.exists():
        return {"code": code, "name": name}
    try:
        df = pd.read_parquet(f).tail(120)
        closes = df["Close"].tolist()
        n = len(closes)
        if n < 60:
            return {"code": code, "name": name}

        ma5 = sum(closes[-5:]) / 5
        ma20 = sum(closes[-20:]) / 20
        ma60 = sum(closes[-60:]) / 60 if n >= 60 else 0
        high_60d = max(df["High"].tolist()[-60:]) if n >= 60 else max(df["High"])
        change_pct = (closes[-1] - closes[-2]) / closes[-2] * 100 if n >= 2 else 0
        momentum_60d = (closes[-1] - closes[-60]) / closes[-60] * 100 if n >= 60 else 0
        momentum_5d = (closes[-1] - closes[-5]) / closes[-5] * 100 if n >= 5 else 0

        # 量比5日
        vols = df["Volume"].tolist()
        vol_ratio_5d = vols[-1] / (sum(vols[-6:-1]) / 5) if len(vols) >= 6 and sum(vols[-6:-1]) > 0 else 1

        # RSI
        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i - 1]
            gains.append(max(d, 0)); losses.append(max(-d, 0))
        avg_gain = sum(gains[-14:]) / 14 if len(gains) >= 14 else 0
        avg_loss = sum(losses[-14:]) / 14 if len(losses) >= 14 else 0
        rsi = 100 - 100 / (1 + avg_gain / avg_loss) if avg_loss > 0 else 100

        return {
            "code": code, "name": name,
            "close": closes[-1], "open": df["Open"].tolist()[-1],
            "ma5": ma5, "ma20": ma20, "ma60": ma60,
            "high_60d": high_60d,
            "change_pct": change_pct,
            "momentum_60d": momentum_60d, "momentum_5d": momentum_5d,
            "vol_ratio_5d": vol_ratio_5d,
            "rsi_14": rsi,
            "limit_pct": limit_pct(code, name),
        }
    except Exception as e:
        return {"code": code, "name": name, "error": str(e)}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan")
    p_scan.add_argument("code")
    p_scan.add_argument("--name", default="")

    sub.add_parser("list")

    args = ap.parse_args()

    if args.cmd == "list":
        all_s = get_all()
        print(f"已注册 {len(all_s)} 策略:")
        for sid, s in all_s.items():
            print(f"  {sid}: {s.name} (止损{s.META.stop_loss_pct:.0%} 持{s.META.max_hold_days}d)")
    elif args.cmd == "scan":
        ind = build_indicators(args.code, args.name)
        hits = run_all(ind)
        if not hits:
            print(f"{args.code}: 无策略命中")
            print(f"指标: {json.dumps({k:v for k,v in ind.items() if k not in ('close','open')}, ensure_ascii=False, default=str)[:200]}")
        else:
            print(f"\n=== {args.name or args.code} 命中 {len(hits)} 策略 ===")
            for h in hits:
                print(f"  {h['strategy_name']} (score {h['score']:.0f}) "
                      f"止损{h['stop_loss_pct']:.0%} 持{h['max_hold_days']}d")


if __name__ == "__main__":
    main()
