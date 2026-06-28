# Code Review: deep_research P0 + CLI bug

> 2026-06-28 · 理财顾问复核 agency-agents 评估 → 实施 P0 (论点破坏者) → CLI 验证暴露现存 bug

## 背景

agency-agents 评估复核 (见 `docs/references/agency-agents-assessment.md` 复核裁决段) 后开 P0: deep_research 加论点破坏者 (thesis_breakers)。CLI 真实验证时暴露 1 个现存 bug。

## 发现

| # | 严重度 | 文件:行 | 验证 | 处置 |
|---|--------|---------|------|------|
| 1 | 中 | deep_research.py:302-311 | CONFIRMED | ✅ 已修 |

---

## #1 [中] `--skip-review` 分支 UnboundLocalError

**文件:** `a_stock/deep_research.py` (main 门禁段, 原 line 302-311)

**问题:** `from a_stock.self_review import gate, review` 写在 `if not args.skip_review` 分支内 (条件 import)。`review` 仅在 if 分支局部绑定。else 分支 (`--skip-review` 或 `A_STOCK_SKIP_REVIEW=1`) 调 `review(r)` → `UnboundLocalError: cannot access local variable 'review'`。

**触发:** 任何 `--skip-review` 或 `export A_STOCK_SKIP_REVIEW=1` 的 CLI 调用必崩。

```python
# 原代码 (bug)
if not args.skip_review and not os.environ.get("A_STOCK_SKIP_REVIEW"):
    from a_stock.self_review import gate, review   # ← review 仅此分支绑定
    try:
        gate(r)
    except RuntimeError as e:
        print(f"\n{e}")
else:
    rv = review(r)   # ← UnboundLocalError: review 未定义
```

**定性:** 重构前就存在的逻辑缺陷, 非新引入。之前无人用 skip-review 跑真实 CLI, 故未暴露。P0 验证时用 `--skip-review` (离线无网络避免门禁误报) 触发。

**修法:** import 提到分支外 (无条件 import, 两分支共用)。

```python
# 修复
from a_stock.self_review import gate, review
if not args.skip_review and not os.environ.get("A_STOCK_SKIP_REVIEW"):
    try:
        gate(r)
        print("\n✅ self-review 通过")
    except RuntimeError as e:
        print(f"\n{e}")
else:
    rv = review(r)
    print(f"\n[skip-review] critical={rv['critical_count']} warning={rv['warning_count']}")
```

**验证:**
- `python -m a_stock.deep_research 600276 --name 恒瑞医药 --skip-review` → 不崩, 正常输出 `[skip-review] critical=2 warning=0`
- `pytest tests/` → 101 passed 16 skipped, 0 回归

---

## P0 实施: thesis_breakers (论点破坏者)

**来源:** agency-agents-zh 投资研究员 agent 关键规则7 (论点破坏者) + 第四阶段论点形成。评估复核裁决: 唯一实匹配的高价值增强点。

**改动 `a_stock/deep_research.py`:**
- 新增 `thesis_breakers(r)`: 5 维退出触发 (净利转负/ROE弱/PE过高/动量走坏/评分恶化), 每条带可操作退出条件
- `DeepResearch` dataclass 加 `thesis_breakers` 字段
- research() / `_to_dict` / main() 输出论点破坏者
- 重构: 网络/parquet 依赖抽离为 `_live_quote_safe` / `_fetch_fundamentals` / `_momentum_from_parquet` / `_score_safe` (原内联在 research 无法 mock, 现可测试)

**新测试 `tests/test_deep_research.py`:** 11 条 (thesis_breakers 7 + dd_checklist 回归 2 + catalysts 1 + research 集成 1)

**CLI 验证 (600276 恒瑞):**
- momentum_60d = -12.4% (真实读 parquet, 未触 -15% 阈值, 正确)
- target = 53.54 (无 EPS/PE 降级为 price×1.1, 符合降级逻辑)
- thesis_breakers: "暂无明确破坏者" (弱而不破, 正确)

## 验证记录

- TDD: 先写 11 测试 (红, ImportError) → 实现 → 绿
- 全套: 90 → 101 passed 16 skipped, 0 回归
- 现存 bug #1 顺手修 (验证暴露, 非 P0 引入)
