# Code Review: 测试污染生产 decisions.sqlite

> 2026-06-28 · P1 risk_metrics 验证暴露 → 溯源 → 清理 + 隔离修复
> 严重度: 高 (污染真实持仓数据, 影响 risk_metrics/goal_sim/stats 等所有读 DB 的模块)

## 发现

P1 risk_metrics CLI 验证时, 输出五粮液 000858 单仓 74%、消费板块 89%。用户指出从未持有五粮液 → 溯源发现测试套件长期污染生产库。

### 污染现状 (清理前)

| code | 性质 | 条数 | id 范围 | 说明 |
|---|---|---|---|---|
| 000858 | 测试污染 | 64 | 542~1039 | 32 活跃 + 32 已平, 全 06-28 01:02~06:14 批量生成, strategy='short', 成对出现 |
| T_AA | 测试残留 | 1 | 1052+ | 已平, 源码无引用 (test_stats 早期遗留) |
| T_BB | 测试残留 | 1 | 1053+ | 同上 |

真实持仓仅 5 只 (600276/515650/300059/159801/159915, 各 1 条 06-26 录入), 但被 64 条 000858 淹没, 导致 risk_metrics 误报"五粮液单仓 74%"。

---

## 根因

### 主犯: `tests/test_db.py` (旧版)

```python
# 旧代码 (bug) - 直接写生产库 + 真实代码
def test_insert_and_query_decision():
    db.init_decisions_db()  # 用真实 cfg.DECISIONS_DB
    new_id = db.insert_decision(
        code="000858", ...   # ← 真实股票代码, 非 T_ 前缀
    )
# 无隔离, 无 teardown
```

每跑一次插 2 条 (insert 测试 + close 测试), 32 次跑 = 64 条。

### 共犯: `tests/test_decision_log.py` / `tests/test_stats.py`

用 T_ 前缀 (正确), 但仅 `setup_function` 清理, **无 `teardown_function`** → 每个测试函数最后一个写的 T_ 数据残留。test_stats 的 `test_stats_by_strategy` 写 T_AA/T_BB 后无人清。

### conftest.py

无 DB 隔离 fixture, 只管 sys.path。所有测试共享生产 `data/decisions.sqlite`。

---

## 修复

### 1. `tests/test_db.py` — tmp DB 隔离 + T_ 前缀

```python
@pytest.fixture
def isolated_dbs(tmp_path, monkeypatch):
    """每个测试用独立 tmp DB, 不碰生产 data/decisions.sqlite."""
    dec = tmp_path / "decisions.sqlite"
    scr = tmp_path / "screener.sqlite"
    monkeypatch.setattr(cfg, "DECISIONS_DB", dec)
    monkeypatch.setattr(cfg, "SCREENER_DB", scr)
    db.init_decisions_db()
    db.init_screener_db()
    return dec, scr

# 测试代码用 T_858 (非真实 000858), 每个测试接收 isolated_dbs fixture
```

db.py 内 `with conn(cfg.DECISIONS_DB)` 读 monkeypatch 后的 tmp 路径, 生产库零接触。

### 2. `tests/test_decision_log.py` / `tests/test_stats.py` — 加 teardown

```python
def setup_function(_):
    db.init_decisions_db()
    _clean_test_data()

def teardown_function(_):
    """测试后清 T_ 数据, 防残留污染生产库."""
    _clean_test_data()

def _clean_test_data():
    with db.conn(cfg.DECISIONS_DB) as c:
        c.execute("DELETE FROM decisions WHERE code LIKE ?", (f"{T}%",))
        c.execute("DELETE FROM watchlist WHERE code LIKE ?", (f"{T}%",))
```

保留 setup/teardown 模式 (非 tmp DB), 因这俩测试断言 `stats.compute_overall()` 看全表, tmp 空表可能影响断言。setup/teardown + T_ 前缀足够隔离。

---

## 脏数据清理

1. 备份 `data/decisions.sqlite` → `data/decisions.sqlite.bak.20260628` (53KB, 含污染可回滚)
2. `DELETE FROM decisions WHERE code IN ('000858','T_AA','T_BB')` — 删 66 条
3. 删 `data/screen/briefs/000858/` 目录 (测试生成的 brief 快照)
4. 修复后清残留 2 条 (T_AA/T_BB, 修复前最后一次跑测试留下)

---

## 验证

- 全套: 118 passed 16 skipped
- **连续两次跑全套, 零残留**: 000858=0, T_=0, 总记录=5
- 5 只真实持仓完好:
  - 600276 恒瑞医药 200
  - 515650 消费50ETF 13000
  - 300059 东方财富 300
  - 159801 芯片ETF 2000
  - 159915 创业板ETF 2700
- 总资产 78,788 元 (匹配 PROJECT_STATE 目标基线)
- risk_metrics CLI 真实输出: 最大单仓 29.1%, 板块分散, ✅ 风险可控

---

## 教训沉淀

1. **测试写真实 DB 是高危反模式**。即使 T_ 前缀, 也必须 teardown 清理或用 tmp DB 隔离。
2. **setup 清理不够**, 必须配对 teardown — 最后一个测试的数据无人清。
3. **真实股票代码 (000858) 进测试夹具 = 定时炸弹**, 必须用 T_ 前缀或明显假码。
4. P1 risk_metrics 的板块集中度/压力测试反而成了污染检测器 — 真实数据下五粮液 74% 单仓一眼异常, 才暴露问题。这是 P1 的意外价值。

## 相关

- 备份: `data/decisions.sqlite.bak.20260628` (确认无误后可删)
- P1 实施: `code-review/2026-06-28-deep-research-p0.md` (同日 P0/P1 记录)
