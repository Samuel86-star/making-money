# 2026-06-25/26 A股策略回测

## 目标
验证 A 股尾盘假设：前日主力资金大幅流入 + 涨幅<2% → 次日上涨概率高。

## 路径演进
1. 东方财富 push2/push2his → 502 / TLS 1.3 间歇失败
2. 尝试 Clash Verge 规则 (DOMAIN push2his → DIRECT) → 不生效
3. 切 DNS 模式 fakeIp → normal → 间歇性
4. 改用 **yfinance** 拉 1y OHLCV，akshare 拉 A 股列表 → **稳定**

## 数据规模
- 5197 只 A 股 × 1 年 × 1d K线
- 缓存：`data/ohlcv/<code>.parquet`
- 列表：`data/a_share_list.json`（akshare 备份源）
- Yahoo 失败 ~6% (timeout / TLS / 退市)

## 脚本（py/）
| 脚本 | 作用 |
|------|------|
| `fetch-trending.py` | GitHub trending 抓取 |
| `fetch-ashare-list.py` | A股代码列表 (push2 主 + akshare fallback) |
| `download-ohlcv.py` | yfinance 批量下载 OHLCV (resumable) |
| `backtest-volume.py` | 多策略回测框架 (vol × chg 双维度) |
| `closeout-screener.py` | 尾盘选股 (push2 主 + akshare + 10jqka fallback) |

## 回测结果（5197 只 × 1y）

| 策略 | n | 胜率 | 均值 | Δ vs 基准 |
|------|---|:---:|:---:|:---:|
| 放量 + 涨幅<2% (原假设) | 29k | 44.9% | +0.03% | -0.04% ✗ |
| 缩量 + 涨幅<2% | 90k | 47.7% | +0.08% | +0.02% ✓ |
| 放量 + 突破(≥5%) | 36k | 45.7% | +0.30% | -0.23% ✗ |
| 缩量 + 突破(≥5%) | 2.4k | 70.0% | +3.31% | +2.79% ✓ (n小) |
| 放量 + 涨停(≥9.5%) | 13k | 50.5% | +0.94% | -0.42% ✗ |
| **纯涨停(≥9.5%)** ⭐ | 22k | **54.0%** | **+1.35%** | 基准 |

## 结论
1. **放量=有害** 模式稳定 (3/3 跑输基准)
2. **假设未支持**：放量+涨幅<2% 没 edge
3. **涨停次日** 是 A 股最稳定 pattern (54% 胜率, +1.35%)，但实盘 T+1 + 抢筹难执行
4. 单凭"涨幅/成交量"无法稳定跑赢 ~0.3% 交易成本

## 关键发现：基础设施
- **东方财富 push2/push2his 在 Clash MITM 下不稳定** (TLS 1.3 间歇失败)
- **akshare (底层多源) 失败时回退稳** — `fetch-ashare-list.py` 已用此模式
- **yfinance (TLS 1.2) 稳定**，适合长周期历史数据
- **`em_get()` 防封机制缺失**：自建脚本没有 1s 限流 + 抖动，push2 502 部分原因在此

## 已 clone 参考仓库
- `a-stock-data/` (simonlin1212/a-stock-data, v3.2.4)
  - 28 端点 / 13 数据源
  - **含 `em_get()` 防封** + `tdx_client()` fallback
  - 未集成进 py/，可后续重写 closeout-screener.py

## git 状态
- origin: `Samuel86-star/making-money` (main, 推送成功)
- upstream: `simonlin1212/a-stock-data` (添加但未 fetch)
- 已 commit: 12 files / 3268 lines
- `.gitignore`: venv / data/ohlcv / data/trending / tmp / a-stock-data

## 后续选项
- A. 用 a-stock-data 的 `em_get()` 重写 closeout-screener.py (限流防封)
- B. 配 cron 每天 15:30 累积真实资金流向数据，2-3 周后用 push2 数据复测假设
- C. 拉 5-10 年长周期数据验证涨停效应稳定性
- D. 加维度（板块/市值/北向）做交叉过滤
