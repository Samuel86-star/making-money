# Code Review: strategies/ 实现

> 2026-06-28 · 审查范围: commits 3a02fce..HEAD (a_stock/strategies/ 全包 + morning_scan 接入 + 测试)
> 方法: code-review 技能, 8 finder angles + 1-vote 验证 (recall-biased)
> 985 行新增, 14 文件

## 发现汇总

7 个发现, 按严重度排序。验证结果: 4 CONFIRMED, 3 PLAUSIBLE (含 2 latent + 1 cosmetic)。

| # | 严重度 | 文件:行 | 验证 | 现修? |
|---|--------|---------|------|-------|
| 1 | 高 | registry.py:30 | CONFIRMED | ✅ 应修 |
| 2 | 中 | morning_scan.py:57 | CONFIRMED (有意设计) | 待定 |
| 3 | 中 | morning_scan.py:60 | CONFIRMED | ✅ 应修 |
| 4 | 中 | runner.py:59 | PLAUSIBLE | ✅ 应修 |
| 5 | 低 | runner.py:85 | PLAUSIBLE (latent) | 缓 |
| 6 | 低 | runner.py:95 | PLAUSIBLE (latent-future) | 缓 |
| 7 | 低 | signals.py:44 | CONFIRMED (cosmetic) | 缓 |

---

## #1 [高] 坏子类崩溃整个 `_scan` → 全策略层瘫痪

**文件:** `a_stock/strategies/registry.py:25-32`

**问题:** `try/except` 只包了 `importlib.import_module` (line 21-25)。后续实例化循环 `inst = attr(); _REGISTRY[inst.META.name] = inst` (line 26-31) 在 try 外。`_scanned = True` (line 32) 在循环之后才设。

**触发:** 开发者加一个 abstract 中间基类 (无 `META`, 或未实现 `filter`/`signals`) → `attr()` 抛 `TypeError` 或 `inst.META.name` 抛 `AttributeError` → `_scan` 在 line 30/31 崩 → `_scanned` 未置 True → `get_all()` (line 35 `if not _scanned: _scan()`) 每次重入重崩。

**后果:** morning_scan `run_top` 触发 `get_all→_scan` 反复崩 → try/except (morning_scan.py:51) 回退纯 screener。**所有策略层静默永久禁用**, 不是只坏那一个策略, 而是全部。

**修法:** 把实例化循环也包进 try, 或在 `_scan` 末尾无条件 `_scanned = True` (即使中途异常); 每个策略实例化单独 try/except 跳过坏的。

---

## #2 [中] 评分池缩窄 — 强基本面无信号票被丢

**文件:** `a_stock/morning_scan.py:55-60`

**问题:** 旧代码 `for s in stocks:` 评分全部 fetched top_n。新代码 `scored_codes = strategy_codes | {s["code"] for s in stocks[:10]}` — 只评 策略命中 ∪ screener top10。`--top-n` 现在只控拉取数, 不控评分资格。

**触发:** `--top-n 20` (默认) 时, 净流入排名 11-20、5维评分最高、但无任何策略信号 (强基本面, 无 trend/oversold/limit/sector 触发) 的票被拉取后从不评分, 进不了 top5。

**定性:** **有意设计** (策略前置过滤, commit message + 注释 "策略候选 ∪ screener top10" 明示)。但与原"所有 fetched 都评分"语义是行为回归。是否 bug 取决于设计意图: 若强基本面无信号票应保留评分资格, 这是设计缺口; 否则按写法工作正常。**待用户确认。**

---

## #3 [中] set 迭代 → top5 边界并列票跨 cron 非确定

**文件:** `a_stock/morning_scan.py:57-60`

**问题:** `scored_codes` 是 set (line 57), `for code in scored_codes` (line 60) 迭代 set。string key 的 set 迭代序由 `PYTHONHASHSEED` 决定, 每进程不同。下游 `valid.sort(key=(total, net_flow_yi), reverse=True)` (line 74) 是稳定排序, 不重排并列项 → 并列项相对序继承自 set 迭代序 → 跨进程非确定。

**触发:** 两票 `(total, net_flow_yi)` 完全相同且卡在 top5 边界 (第 4/5 名)。reachable: morning_scan.py:61 对策略产出但不在 screener top 的 code 用 fallback `{"net_flow":0}`, 映射到 `net_flow_yi=0.0`; 多个 net_flow=0 且 total 相同的票并列。

**后果:** 09:35 推送票 X, 09:50 (独立进程, 不同 hash seed) 推送票 Y。watchlist 落盘 + Mac 弹窗跨次 cron 结果不一致, 无代码变更。

**修法:** `scored_codes` 改 list 并按确定性 key 排序 (如 code 字典序), 或 scored 列表按 (net_flow_yi desc, code) 预排再稳定 sort。

---

## #4 [中] prev_close=0 数据异常 → moneyflow_surge 假买

**文件:** `a_stock/strategies/runner.py:58-59` + `a_stock/strategies/moneyflow_surge.py:22`

**问题:** `change_pct` 用 falsy 守卫 `if prev["close"] else 0.0` 屏蔽 `prev_close=0.0`。但 `moneyflow_surge.py:22` 直接比 `ind["last_close"] > ind["prev_close"]` (不走 change_pct)。两消费者语义分裂。

**触发:** 某票 parquet 一根 `prev_close=0.0` (数据缺口/异常填充; load_ohlcv 无过滤, build_indicators 无上游守卫) → `change_pct=0.0` (掩盖) → moneyflow_surge rank≤10 且 `last_close>0 > 0` → 发 0.6 假买信号, reason 显示 `收涨+0.0%` (异常 tell)。

**安全面:** near_limit_up (change_pct>7 门) 和 sector_momentum (change_pct>3 门) 因 change_pct=0 不触发, 只有 moneyflow_surge 中招。A 股价合法不为 0, 需数据异常触发, 故 PLAUSIBLE 非必现。

**修法:** build_indicators 对 prev_close≤0 返回 None (跳过该 code), 或 moneyflow_surge 改用 change_pct>0 判断收涨。

---

## #5 [低·latent] singleton 注入无清理 — 长进程陈旧读

**文件:** `a_stock/strategies/runner.py:83-95`

**问题:** `run_all` 把 `_rank`/`_sector_result` 注入 registry 缓存的 singleton 实例 (get_all 返回同一批对象), 无清理。注入后状态残留在实例上。

**触发条件:** 长生命周期进程 (非 cron 的 fresh-process-per-tick) + `run_all` 后直接调 `st.evaluate()`。当前 cron 每分钟 fresh subprocess + 单次 run_all, **不触发**。repl/notebook/未来常驻调度器里 `run_all([A,B])` 注入 `_rank={A:1,B:2}` 后, 直接 `MoneyflowSurge().evaluate('A')` 读陈旧 rank=1 发假买。

**定性:** latent-only, 当前部署不炸。代码异味值得修 (run_all 开头清 `_rank`/`_sector_result`, 或走参数传递)。

---

## #6 [低·latent-future] break 假设单 _sector_result 策略

**文件:** `a_stock/strategies/runner.py:88-95`

**问题:** `_sector_result` 注入循环 `break` 在首个命中策略后。第二个声明 `_sector_result` 的策略永不被注入, 回退每候选 `_analyze()` (sector_rotation.analyze, 市场级 DB 扫描) N× 冗余。

**触发条件:** 当前仅 SectorMomentum 有 `_sector_result`, break 无害。未来加第二个 `_sector_result` 策略 → 不注入 → 每候选重算, 性能回归, 无测试覆盖。

**定性:** latent-future-only。`break` 假设"单 _sector_result 策略"不变式未强制未文档化。

---

## #7 [低·cosmetic] top_reason 平局非确定

**文件:** `a_stock/strategies/signals.py:42-45`

**问题:** `v.signals.append(s)` (line 42) 先于检查 (line 44)。`max(sig.confidence for sig in v.signals)` 含 s 自身 → 条件等价 `s.confidence >= existing_max_before_append`。平局时 (`>=`) 后迭代信号覆盖 top_reason。"后"取决于 pkgutil 文件系统序 (非 hash 随机, 同文件系统稳定)。

**触发:** 同 code 被 moneyflow_surge(0.6) + near_limit_up(0.6) 同命中 → top_reason 显示后者。

**定性:** 纯显示文本 (console print + push body), 不影响 total_confidence/排名/入选。cosmetic。

---

## 建议处理

| # | 动作 |
|---|------|
| 1 | **现修** — try 包实例化循环 + `_scanned` 末尾无条件置 True |
| 2 | **待用户定** — 保留策略前置过滤 vs 改回全评分 |
| 3 | **现修** — scored_codes 排序确保确定 |
| 4 | **现修** — prev_close≤0 守卫 |
| 5 | 缓 (latent, 当前不炸) |
| 6 | 缓 (latent-future) |
| 7 | 缓 (cosmetic) |

## 验证记录

- Finder A (line-by-line): 4 候选
- Finder B (removed-behavior + cross-file): 5 候选
- 去重后 7 候选, 各 1-vote 验证
- 结果: #1/#3/#4 CONFIRMED (真 bug), #2 CONFIRMED (有意设计), #5/#6 PLAUSIBLE latent, #7 CONFIRMED cosmetic
- 测试现状: 77 passed 16 skipped — 但测试未覆盖上述边界 (坏子类/prev_close=0/并列边界/长进程注入)

---

## 修复执行指示 (给修复会话窗口)

> 裁决人: 理财顾问 (主架构设计者), 2026-06-28
> #1-#7 全修。#2 设计如此不动。
> 修复顺序: #1 → #4 → #3 → #5 → #6 → #7 (高危先, latent/cosmetic 后)
> 每条改完跑 `.venv/bin/python -m pytest tests/ -q` 确认不破现有 77 passed 16 skipped, 再继续下一条。

### 总规则
- **不要重构无关代码**。只改下面指出的行。
- **不要动 #2** (morning_scan.py:55-60 评分池逻辑)。设计如此: 策略前置过滤是 Signal Bridge 架构核心, 强基本面无信号票不进评分池 = 对非专业投资者更安全 (减少噪音, 强基本面深研走 deep_research 主动喊)。
- **不要删持仓/改真实数据**。测试用 T_ 前缀。
- 每条修完在该条末尾标 `[已修 YYYY-MM-DD]` 并贴 pytest 末行。

---

### #1 [高·必修] 坏子类崩溃整个 `_scan` → 全策略层瘫痪

**文件:** `a_stock/strategies/registry.py:25-32`

**改法:** 把实例化循环 (line 26-31) 包进 try, 每个策略实例化单独 try/except 跳过坏的; `_scanned` 末尾无条件置 True。

**目标代码 (替换 line 21-32):**
```python
        try:
            mod = importlib.import_module(f"a_stock.strategies.{modname}")
        except Exception as e:
            print(f"⚠ 策略模块 {modname} 导入失败, 跳过: {e}")
            continue
        for attr in vars(mod).values():
            if (isinstance(attr, type) and issubclass(attr, BaseStrategy)
                    and attr is not BaseStrategy
                    and attr.__module__ == mod.__name__):
                try:
                    inst = attr()
                    _REGISTRY[inst.META.name] = inst
                except Exception as e:
                    print(f"⚠ 策略 {attr.__name__} 实例化失败, 跳过: {e}")
                    continue
        _scanned = True  # 无条件置 True, 即使中途有策略炸, 不让 get_all 反复重崩
```

**验证测试 (新增):** 建一个 abstract 中间基类 (无 META) 放进 strategies/, 确认 `_scan` 不崩、`_scanned` 置 True、其余正常策略仍注册。或 monkeypatch 注入一个坏类后断言 `get_all()` 不抛、返回正常策略列表。

[已修 2026-06-28] `79 passed, 16 skipped in 1.85s` (新增 2 测试: 坏子类不崩 _scan + get_all 幂等)

---

### #4 [中·修] prev_close=0 数据异常 → moneyflow_surge 假买

**文件:** `a_stock/strategies/runner.py:39-66` (build_indicators)

**改法:** build_indicators 对 `prev_close<=0` 返回 None (跳过该 code), 从源头屏蔽。不只改 moneyflow_surge, 因为 data 缺口应在上游守卫, 下游消费者 (现在+未来) 统一安全。

**目标代码 (替换 line 47-59, 在算 change_pct 前加守卫):**
```python
    closes = df["close"]
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last
    # 数据异常守卫: A 股合法价不为 0; prev_close<=0 = parquet 缺口/异常填充
    if prev["close"] <= 0 or last["close"] <= 0:
        return None
    vol_ma5 = df["volume"].iloc[-6:-1].mean() if len(df) >= 6 else df["volume"].mean()
```

**说明:** 保留 line 58 `if prev["close"] else 0.0` falsy 守卫不删 (双保险), 但新增的 <=0 守卫在更早处拦截, moneyflow_surge L22 `last_close>prev_close` 不再碰到 0。

**验证测试 (新增):** monkeypatch `load_ohlcv` 返回末根 `prev_close=0` 的 df, 断言 `build_indicators(code)` 返回 None; 断言 `MoneyflowSurge().evaluate(code)` 返回 `[]` (filter 因 build_indicators None 不通过)。

[已修 2026-06-28] `82 passed, 16 skipped in 1.60s` (新增 3 测试: prev_close=0/last_close=0 返回 None + moneyflow_surge 不假买)

---

### #3 [中·修] set 迭代 → top5 边界并列票跨 cron 非确定

**文件:** `a_stock/morning_scan.py:57-60`

**改法:** `scored_codes` 改 list 并按确定性 key 排序 (code 字典序), 消除 PYTHONHASHSEED 依赖。稳定 sort 后并列项相对序固定。

**目标代码 (替换 line 57):**
```python
    scored_codes = sorted(strategy_codes | {s["code"] for s in stocks[:10]})
```

**说明:** `sorted(...)` 对 string 默认字典序, 返回 list。下游 `valid.sort(key=...)` (line 74) 是稳定排序, 并列项相对序继承自 list 的字典序 → 跨进程确定。无需改 line 60 的 `for code in scored_codes`。

**验证测试 (新增, 可选):** 构造两票 `(total, net_flow_yi)` 完全相同卡 top5 边界, 用不同 `PYTHONHASHSEED` 跑 scan, 断言 top5 集合 + 顺序一致。

[已修 2026-06-28] `83 passed, 16 skipped in 2.55s` (新增 1 测试: tests/test_morning_scan.py 子进程 PYTHONHASHSEED 0/1/42 确定性 + 字典序断言; 已验证回滚 fix 后测试失败)

---

### #5 [低·修] singleton 注入无清理 — 长进程陈旧读

**文件:** `a_stock/strategies/runner.py:74-95` (run_all)

**改法:** `run_all` 开头清所有策略实例的 `_rank`/`_sector_result` 到 None, 防上次 run_all 残留状态污染本次。

**目标代码 (在 line 78 `from ... get_all` 后, line 80 注释前插入):**
```python
    strategies = get_all()
    # 清上次注入残留 (防长进程/repl 里陈旧 rank/sector 读)
    for st in strategies:
        if hasattr(st, "_rank"):
            st._rank = None
        if hasattr(st, "_sector_result"):
            st._sector_result = None
```

**说明:** 原代码 line 82 `strategies = get_all()` 移到上面。注入逻辑 (line 84-95) 不变。

**验证测试 (新增):** 两次 `run_all` 用不同 candidates, 断言第二次注入前实例 `_rank` 已是 None (或断言第二次 ranking 正确反映第二次 candidates, 不受第一次污染)。

[已修 2026-06-28] `85 passed, 16 skipped in 2.47s` (新增 2 测试: _rank 陈旧残留清理 + _sector_result 陈旧残留清理)

---

### #6 [低·修] break 假设单 _sector_result 策略

**文件:** `a_stock/strategies/runner.py:88-95`

**改法:** 去掉 `break` (line 95), 让循环注入所有声明 `_sector_result` 的策略。

**目标代码 (替换 line 88-95):**
```python
    # 注入板块轮动结果 (市场级, 全候选共享, 避免每候选重算)
    sector_result = None
    for st in strategies:
        if hasattr(st, "_sector_result"):
            if sector_result is None:
                try:
                    from a_stock.sector_rotation import analyze as _sr_analyze
                    sector_result = _sr_analyze()
                except Exception:
                    sector_result = None
            st._sector_result = sector_result  # 共享同一结果, 只算一次
```

**说明:** 把 `_sr_analyze()` 提到循环外算一次, 所有 `_sector_result` 策略共享。消除"单 `_sector_result` 策略"隐式不变式。未来加第二个板块类策略自动安全。

**验证测试 (新增, 可选):** monkeypatch 两个策略都声明 `_sector_result`, 断言两个都被注入同一结果对象, `analyze` 只被调一次。

[已修 2026-06-28] `87 passed, 16 skipped in 2.51s` (新增 2 测试: 2 个 _sector_result 策略共享同一对象 + analyze 只调一次 / analyze 返回 None 时 sentinel 防重算)

**适配说明 (minimal adaptation):** md 目标代码用 `if sector_result is None:` 守卫, 但 `analyze()` 合法返回 None (无轮动数据, 生产中发生, 见 test_sector_momentum_no_rotation_data) 时, 该守卫会为每个后续 `_sector_result` 策略重算 (None 与"未算"无法区分), 违反 md 描述"只算一次"与其建议测试"analyze 只被调一次"。改用 sentinel `_NOT_COMPUTED = object()` 区分"未算"与"算了得 None", 最小改动达成 md 既定意图。已验证回滚到 `is None` 守卫时 `test_run_all_sector_result_none_not_recomputed` 失败 (调 2 次), sentinel 修复后通过 (调 1 次)。

**注 (非本次修复范围, 报告用):** `sector_momentum.py:27` `signals()` 有独立 fallback `self._sector_result if ... is not None else _analyze()`, 当注入的 `_sector_result=None` 时每候选重算 analyze。此为 #6 之外的路由, 本次 #6 测试用 `_load_ohlcv=None` (filter=False) 隔离之, 未触碰该行。

---

### #7 [低·修] top_reason 平局非确定

**文件:** `a_stock/strategies/signals.py:42-45`

**改法:** `>=` 改 `>`, 平局保留先到的 (稳定, 不被后迭代覆盖)。

**目标代码 (替换 line 42-45):**
```python
        v.signals.append(s)
        # top_reason 取当前最高 confidence 那条; 平局 (>不>=) 保留先到, 跨次稳定
        if s.confidence > max(sig.confidence for sig in v.signals[:-1], default=-1):
            v.top_reason = s.reason
```

**说明:** 用 `v.signals[:-1]` (append 后排除自身) + `default=-1` 处理首条。首条 confidence>-1 必成立 → top_reason 设为首条 reason, 符合"先到"语义。平局 (`s.confidence == existing_max`) 不覆盖。

**验证测试 (新增, 可选):** 两信号同 confidence, 断言 top_reason 是先 append 的那条。

[已修 2026-06-28] `90 passed, 16 skipped in 2.23s` (新增 3 测试: 平局保留先到 / 首条信号必设 top_reason / 更高 confidence 仍覆盖; 已验证回滚到 `>=` 后平局测试失败)

**适配说明 (minimal):** md 目标代码 `max(sig.confidence for sig in v.signals[:-1], default=-1)` 在 Python 3 触发 `SyntaxError: Generator expression must be parenthesized` (generator + keyword arg `default=` 语法歧义)。加括号 `max((sig.confidence for sig in v.signals[:-1]), default=-1)`, 语义不变。

---

## 修复后自检清单

- [ ] #1 registry.py: try 包实例化循环 + `_scanned` 无条件置 True
- [ ] #4 runner.py: build_indicators prev_close<=0 守卫
- [ ] #3 morning_scan.py: scored_codes 改 sorted list
- [ ] #5 runner.py: run_all 开头清 _rank/_sector_result
- [ ] #6 runner.py: 去 break, sector_result 算一次共享
- [ ] #7 signals.py: `>=` 改 `>`, 平局保留先到
- [ ] #2 不动 (设计如此)
- [ ] 全部改完: `.venv/bin/python -m pytest tests/ -q` → 应 ≥77 passed 16 skipped
- [ ] 新增边界测试覆盖: 坏子类 / prev_close=0 / 并列边界 / 长进程注入
- [ ] 不要碰持仓真实数据 (600276/159915 等), 测试用 T_ 前缀
