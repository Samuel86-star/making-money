# Agency Agents 评估报告

> 评估日期: 2026-06-28
> 来源项目: [agency-agents](https://github.com/msitarzewski/agency-agents.git) (英文原版) + [agency-agents-zh](https://github.com/jnMetaCode/agency-agents-zh.git) (中文社区版, +51 个原创 agent)

## 项目简介

| | agency-agents (英文) | agency-agents-zh (中文) |
|---|---|---|
| Agent 总数 | ~237 (16 个部门) | 266 (20 个部门) |
| 语言 | 英文 | 简体中文 (所有 agent 内容) |
| 额外部门 | — | hr/ legal/ supply-chain/ (原创) |
| 原版独有 | tools.json, divisions.json | — |
| 市场针对性 | 全球 | 中国市场 (51 原创 agent + 25+ 中文营销) |
| 汇总入口 | README.md | README.md + AGENT-LIST.md + CATALOG.md |
| 安装脚本 | scripts/install.sh | scripts/install.sh + install.ps1 |

**zh 版关键原创 Agent:** 财务预测分析师、发票管理专家、财务反欺诈分析师、风险评估师、高考志愿填报顾问、政务 ToG 顾问、FPGA/ASIC 数字设计工程师、IoT 架构师、钉钉/飞书集成、小红书/抖音/快手/B站 策略师等。

---

## Agent 价值评估矩阵

### 🔥 高价值 — 直接增强现有模块

| Agent | 来源 | 价值点 | 增强目标 |
|-------|------|--------|---------|
| **投资研究员 (Investment Researcher)** | zh | 催化剂时间线追踪、论点破坏者定义、卖方共识分歧分析 | `deep_research.py` |
| **企业风险评估师 (Risk Assessor)** | zh | COSO 风控框架、Veto 逻辑、ESG/供应链风险检查 | `self_review.py`, `risk_metrics.py` |
| **Reality Checker** | en | 证据驱动默认否决、自动 FAIL 触发器、3 步验证工作流 | `self_review.py` 门禁质量 |
| **Financial Analyst** | en | 三表财务模型、敏感性分析 (tornado/Monte Carlo)、WACC 计算 | `deep_research.py` DCF 部分 |

### ✅ 中价值 — 方法论文档参考

| Agent | 来源 | 价值点 | 增强目标 |
|-------|------|--------|---------|
| **FP&A Analyst** | en | 情景规划 (乐观/基准/悲观)、滚动预测方法论 | `goal_sim.py`, `position_sizer.py` |
| **CFO (Chief Financial Officer)** | en | 资本配置框架 (Tier 1-4)、组合构建方法论 | 组合策略层 |
| **工作流架构师 (Workflow Architect)** | zh | 故障路径建模、交接契约、清理清单方法论 | cron 管线健壮性 |
| **Financial Forecasting Analyst (财务预测分析师)** | zh | SaaS 指标、三情景预测、13 周现金流预测 | `goal_sim.py` |

### ⬇️ 低价值 — 当前不适用

| Agent | 原因 |
|-------|------|
| Pricing Analyst | 产品定价模型，与证券估值关联弱 |
| 多智能体系统架构师 | 单体系统当前不需要多 agent 编排 |
| Marketing/Design/GIS/Spatial/GameDev | 与 A 股决策无关 |
| 硬件/嵌入式/FPGA 等原创 | 除非研究半导体产业链 (已有 `analysis/technology/`) |

---

## 编码增强计划 (P0-P2)

### P0 — 立即执行

**1. `self_review.py` 门禁增强**
- 整合风险评估师的 Veto 逻辑: ESG 检查、供应链风险、合规审查
- 增加 Reality Checker 的证据验证层: 输出结论必须有原始数据支撑
- 参考: `specialized-risk-assessor.md` 第三步(风险分析与评级)和 Reality Checker 的 Automatic Fail 触发器

**2. `deep_research.py` 深研增强**
- 增加催化剂时间线 (Catalyst Timeline): 未来 1-3-6 个月关键事件
- 增加论点破坏者追踪 (Thesis Breaker): 什么条件会打破买入/卖出观点
- 增加卖方共识分歧分析: 当前 deep_research 是独立估值，缺少"市场怎么看"
- 参考: `finance-investment-researcher.md` 第四步(论点形成)和第五步(持续监控)

### P1 — 后续执行

**3. `risk_metrics.py` 组合风险仪表盘**
- 增加宏观情景压力测试 (利率/板块集中度/流动性)
- 增加 ESG 风险评分
- 参考: `specialized-risk-assessor.md` 风险热力图 + KRI 指标

### P2 — 长期

**4. `goal_sim.py` 情景规划增强**
- 增加三情景输入 (乐观/基准/悲观)，而非单一蒙特卡洛
- 增加现金流健康度指标
- 参考: `finance-fpa-analyst.md` 年度运营计划 + `finance-financial-forecaster.md` 13周预测

**5. cron 管线工作流审计**
- 用工作流架构师方法论梳理整个管线故障路径
- 记录所有交接契约和清理清单
- 参考: `specialized-workflow-architect.md` 发现审计清单

---

## 安装建议

**不安** 到 `~/.claude/agents/`。原因:
- Agent 文件是行为模板 (workflow + 方法论)，不是可调用的工具
- 更大的价值是把方法论硬编码进 a_stock 模块，持久改进

**读** 以下文件作为代码增强的参考:
- `references/agency-agents-zh/finance/finance-investment-researcher.md`
- `references/agency-agents-zh/specialized/specialized-risk-assessor.md`
- `references/agency-agents/testing/testing-reality-checker.md`
- `references/agency-agents/finance/finance-financial-analyst.md`
- `references/agency-agents/finance/finance-fpa-analyst.md`
- `references/agency-agents/specialized/chief-financial-officer.md`
- `references/agency-agents-zh/specialized/specialized-workflow-architect.md`

---

## 相关引用

- [A股分析规则](/Users/maerun/.claude/projects/-Users-maerun-Projects-make-money/memory/a-share-analysis-rules.md)
- [老板反馈](/Users/maerun/.claude/projects/-Users-maerun-Projects-make-money/memory/boss-feedback.md)

---

# 复核裁决 (2026-06-28, 理财顾问/主架构)

> 复核方法: 读 7 个引用 agent 原文 + 目标模块源码 (self_review.py / deep_research.py), 逐条对照声称价值点是否真实存在且匹配组合。
> 核心问题: 原评估对 agent 内容验证不足, 3 个高价值 agent 里 1 实匹配 / 1 误读 / 1 错配。

## 路径订正

- 两项目实际在 `references/` (repo 根级, .gitignore 未跟踪), 非文档暗示的 `docs/references/`。引用的相对路径 (从 repo 根) 正确, 7 文件全部存在。

## 高价值 Agent 逐条复核

| Agent | 原评估声称 | 原文实际 | 裁决 |
|---|---|---|---|
| 投资研究员 (zh) | 催化剂时间线/论点破坏者/卖方共识分歧 → deep_research | 催化剂时间线 ✅、论点破坏者 ✅ 真实存在 (第四五阶段); **但** agent 明确"引用一手来源, 不引卖方摘要", 不做共识分歧分析 | **部分实匹配**。催化剂+论点破坏者值得做; "卖方共识分歧"是 stretch, 删除 |
| Reality Checker (en) | 证据驱动默认否决/Fail触发器/3步验证 → self_review 门禁 | **Web QA agent**: Playwright 截图 / 响应式 / luxury 幻觉检查。3 步工作流全 web 专属 (`ls views/` / `grep luxury` / playwright) | **误读**。唯一可迁移="默认否决要证据", self_review 已实现 (critical>0 raise RuntimeError)。**边际价值≈0, 丢弃** |
| 风险评估师 (zh) | COSO/Veto/ESG/供应链 → self_review/risk_metrics | **企业风控**: 国企央企 COSO 三道防线 / 审计整改 / 国资委指引 | **错配**。给公司搭风控体系, 非个人股票组合。ESG/供应链审查套 ETF+恒瑞 = 过度设计 |

## 关键错配论证

当前组合 = ETF (消费/通信/创业板) + 恒瑞。原 P0 "self_review 加 ESG/供应链/合规":

- **ETF 做 ESG 检查无意义** (ETF 是一篮子, 非单公司)
- **供应链风险** 适合 `analysis/technology/` 半导体产业链深研, 不适合日常门禁
- **COSO 三道防线** 是企业治理框架, 套个人组合 = 大炮打蚊子

self_review.py 现状已健壮 (5 critical + 3 warning checks, 已实现默认否决), 不需 Reality Checker。

## 修正后计划 (替代原 P0-P2)

### P0 (开做) — deep_research 论点破坏者 + 催化剂重定向

**来源:** 投资研究员 agent 第四阶段 (论点形成) + 关键规则 7 (论点破坏者)。

deep_research.py 现状: 已有 `catalysts_list` 但只接 macro_calendar (宏观事件), 无个股催化剂, **完全无论点破坏者**。

**实施:**
1. 新增 `thesis_breakers(r)`: 基于已有字段 (roe/pe/momentum/score/veto) 生成"什么会打破当前论点"退出触发条件。如:
   - 估值类: PE 跌破行业均值 30% → 论点(估值修复)失效
   - 业绩类: 净利同比转负 → 论点(成长)失效
   - 趋势类: 60日动量 < -15% 持续 → 论点(趋势)失效
2. `catalysts_list` 重定向: 宏观事件保留 (市场级), 增加个股催化维度提示 (财报季/除权除息, 基于代码推断, 不抓外部数据避免依赖)
3. `_to_dict` + `main` 输出 thesis_breakers, 让用户看到"什么情况下该撤"
4. self_review 不动 (论点破坏者属研究输出, 非门禁)

### P1 (可选, 后续) — risk_metrics 借 KRI/情景压力测试思路

**来源:** 风险评估师 agent 第三步 (KRI 关键风险指标) + 定量工具 (蒙特卡洛/敏感性/VaR)。

仅借方法论, 不搬 COSO/ESG/供应链:
- 组合级 VaR (已有 risk_metrics, 看是否补置信区间)
- 板块集中度压力测试 (利率+1%/板块跌10% 的组合冲击)

当前组合 ETF 为主, 增量有限, **标 P1 优先级低**。

### 丢弃 (不实施)

- ❌ Reality Checker → self_review: web QA 误读, 丢弃。
- ❌ Risk Assessor ESG/供应链/COSO → self_review: 企业风控错配组合, 丢弃。
- ❌ "卖方共识分歧": agent 不支持 (明确避卖方摘要), 且 A 股卖方数据管道无, 删除。
- ⏸ FP&A/CFO/Forecaster → goal_sim 三情景: 方法论参考合理, 但 goal_sim 蒙特卡洛已是情景分析一种, 增量小, P2 长期参考。

## 学习沉淀

- 投资研究员的 **可证伪研究** 是该内化的工作方式: 每个论点必带"什么会打破它"。这正是 deep_research 当前缺口, P0 修。
- 复核职责: 把"听起来高级"和"真匹配组合"分开。原评估整体方向对 (借外部方法论), 但内容验证不足致两误归高价值。