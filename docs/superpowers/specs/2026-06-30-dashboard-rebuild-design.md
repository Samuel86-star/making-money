# Dashboard 重写: vue3 + fastapi

> 替代 `a_stock/web/dashboard.py` (streamlit). 解决 `st.dialog` 触发全脚本 rerun 痛点.
> 沿用所有现有数据/决策模块, 不动.

**日期:** 2026-06-30
**状态:** Approved (待实施)

## 1. 背景与动机

当前 `a_stock/web/dashboard.py` 用 streamlit. 每次 `?action=...` 触发, streamlit 整个 main
重新执行, 行情/卡片/数据库 query 全跑一遍. 弹窗 ≠ 不重渲染, 体感"刷新后才弹".

越做越像交易终端, streamlit 模型限制显现:
- 弹窗不独立 (绑 rerun)
- 局部更新难 (无组件级 reactive)
- 实时推送靠轮询

## 2. 目标

1. 弹窗不重渲染主区 (Teleport + 客户端 modal)
2. 行情实时变 (1-2s) 不刷整页 (WS 推送)
3. 加/减/建仓 100 股铁律后端把关 (422 拒绝非整手)
4. 视觉对齐当前 streamlit 版本
5. 现有 `a_stock/` 模块 0 修改, 全部 import 复用

非目标:
- 不重写 CLI 工具 (morning_scan / monitor / goal_sim 继续 cron 跑)
- 不加鉴权 (本地 dev only)
- 不上云

## 3. 架构

```
+--------------------------------+     WS /ws/quotes
|  FastAPI :8000                 |<-----------------------------+
|  - REST /api/*                 |                              |
|  - WS /ws/quotes (转发)         |---+                          |
|  - 1 个东财 WS 客户端           |   | aiohttp 维持单连          |
+--------------------------------+   | 多前端订阅同一后端         |
        |                            | 进程内 cache 最新价         |
        | import (不改)              +--------------------------+
        v
+--------------------------------+
|  a_stock/ (现有, 0 改)          |
|  - a_stock_data/eastmoney.py   |
|  - a_screen/decision_log.py    |
|  - risk_metrics.py             |
|  - opportunity_feed.py         |
|  - sentiment.py                |
+--------------------------------+

vite dev :5173  ──proxy /api, /ws──>  fastapi :8000
```

## 4. 项目结构

```
make-money/
├── a_stock/                       (现有, 0 改)
│   ├── ...
│   ├── web/dashboard.py            (旧, 保留归档, 不删)
│   └── api/                        ← 新增
│       ├── __init__.py
│       ├── app.py                  fastapi 入口
│       ├── ws.py                   WS 路由 + 东财 WS 客户端管理
│       ├── routes/
│       │   ├── portfolio.py        /api/portfolio
│       │   ├── positions.py        /api/positions + POST add/reduce/new
│       │   ├── opportunities.py    /api/opportunities
│       │   ├── quotes.py           /api/ticker /api/quote/{code}
│       │   └── sentiment.py        /api/sentiment
│       └── models.py               pydantic schemas
│
├── frontend/                       ← 新增
│   ├── package.json
│   ├── vite.config.ts              proxy /api + /ws → :8000
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.ts
│       ├── App.vue
│       ├── api/
│       │   ├── http.ts
│       │   └── client.ts           typed API methods
│       ├── ws/
│       │   └── client.ts           WS singleton, reconnect
│       ├── stores/                 pinia
│       │   ├── portfolio.ts
│       │   ├── positions.ts
│       │   ├── opportunities.ts
│       │   └── dialog.ts
│       ├── views/
│       │   ├── Dashboard.vue
│       │   ├── TickerBar.vue
│       │   ├── AssetBar.vue
│       │   ├── OpportunityFeed.vue
│       │   ├── OpportunityCard.vue
│       │   ├── PositionsList.vue
│       │   └── HoldingCard.vue
│       └── components/
│           └── TradingDialog.vue   3-mode (add/reduce/new), Teleport 到 body
│
└── docs/superpowers/plans/2026-06-30-dashboard-rebuild.md   ← writing-plans 出
```

## 5. API 契约

### REST

```
GET  /api/portfolio
  → 200 {
      total, stock_mv, cash, unrealized, realized, target_pct,
      n_positions
    }

GET  /api/positions
  → 200 [{
      code, name, qty, cost, price, pnl, pnl_pct, stop_loss
    }]

GET  /api/opportunities
  → 200 [{
      type: "pullback"|"anomaly"|"candidate"|"rule",
      code, name, desc, meta, time, tag, action_label
    }]

GET  /api/ticker
  → 200 [{code, name, price}]

GET  /api/sentiment
  → 200 {temp, mood, leader}

GET  /api/quote/{code}
  → 200 {code, price, change, ts}

POST /api/positions                       # 建仓
  body: {code, name, strategy, price, qty, reason?}
  → 201 {id, code, name}
  → 422 {error}      # 100 股铁律 / 字段缺失

POST /api/positions/{code}/add            # 加仓
  body: {strategy, price, qty, reason?}
  → 201 {id, code}
  → 422 {error}

POST /api/positions/{code}/reduce         # 减仓
  body: {price, qty, reason}
  → 201 {id, code, realized}
  → 422 {error}
  → 409 {error}      # 超过持仓
```

### WS /ws/quotes

```
client → server:  {action: "sub", codes: ["600276", "159915"]}
server → client:  {type: "ack", codes: [...]}
server → client:  {type: "quote", code, price, change, ts}   # 持续
server → client:  {type: "error", msg}

client → server:  {action: "ping"}                          # 30s 心跳
server → client:  {action: "pong"}
```

生命周期:
- 后端进程启动时, 1 个 asyncio task 维持东财 WS 客户端 (eastmoney_ws)
- 接收到的 quote 进进程内 dict[str, Quote] cache
- 前端连 /ws/quotes, 发 sub, 后端只推订阅的 code
- 写决策 (POST) 后, 后端推 {type: "refresh", target: "positions"} 触发前端 re-fetch

## 6. 前端架构

### 组件树

```
App.vue
├── TickerBar.vue           顶部滚动行情 (WS 订阅)
├── AssetBar.vue            5 格 KPI (REST /api/portfolio)
└── Dashboard.vue           2 列主区
    ├── OpportunityFeed.vue (左)
    │   └── OpportunityCard.vue ×N
    │       └── <button @click="dialog.open({mode:'add', code, cost})">加仓</button>
    └── PositionsList.vue   (右)
        └── HoldingCard.vue ×N
            ├── <button @click="dialog.open({mode:'add', ...})">+</button>
            ├── <button @click="dialog.open({mode:'reduce', ...})">-</button>
            └── <span class="pnl">{pnl_pct}</span>

<TradingDialog />           Teleport to body, v-if=dialog.open
```

### Pinia stores

```typescript
// stores/dialog.ts
export const useDialog = defineStore('dialog', () => {
  const open = ref(false)
  const mode = ref<'add'|'reduce'|'new'|null>(null)
  const payload = ref<any>({})
  function show(m: 'add'|'reduce'|'new', p: any = {}) {
    mode.value = m; payload.value = p; open.value = true
  }
  function close() { open.value = false }
  return { open, mode, payload, show, close }
})

// stores/positions.ts
export const usePositions = defineStore('positions', () => {
  const list = ref<Position[]>([])
  async function refresh() {
    list.value = await api.getPositions()
  }
  return { list, refresh }
})
```

### WS 客户端 (singleton)

```typescript
// ws/client.ts
class QuoteWS {
  private ws: WebSocket | null = null
  private subs = new Set<string>()
  private handlers = new Map<string, (q: Quote) => void>()

  connect() { /* auto-reconnect with backoff */ }
  subscribe(codes: string[], handler: (q: Quote) => void) { ... }
  unsubscribe(codes: string[]) { ... }
}
export const quoteWS = new QuoteWS()
```

关键: 价格更新 = 直接改 `position.price` reactive, 卡片自动重渲染自己, 不重 mount 列表.

## 7. 弹窗 (根治痛点)

```vue
<!-- TradingDialog.vue -->
<Teleport to="body">
  <Transition name="fade">
    <div v-if="dialog.open" class="modal-mask" @click.self="dialog.close()">
      <div class="modal-body">
        <component :is="formComponent" v-bind="dialog.payload"
                   @success="onSuccess" @cancel="dialog.close()" />
      </div>
    </div>
  </Transition>
</Teleport>
```

- 弹窗 = 单个组件, Teleport to body 挂 body 下, 不嵌在 Dashboard 树里
- v-if 控制显隐, 关闭 = dialog.close(), 不 unmount Dashboard
- 提交 = POST → 成功后 emit success → 父组件调 positions.refresh() (只刷持仓列表)
- 价格继续走 WS 推, 不动

## 8. 错误处理

| 错误 | 来源 | 表现 |
|---|---|---|
| 100 股非整数倍 | _validate_lot | 422 + error, 弹窗红字提示 |
| 减仓超持仓 | 业务校验 | 422 + error |
| 东财 WS 断 | 后端 aiohttp | 静默重连, 前端 WS 收到 error → store mark degraded |
| 网络断 | 前端 fetch | 弹窗顶部黄条"网络异常, 重试中" |
| 后端 5xx | fastapi | 弹窗显示 error, 不关弹窗, 用户可改后重提 |

## 9. 测试

- 后端: pytest 测 4 个 POST 端点 + 100 股铁律 + 业务校验
- 前端: vitest 测 stores + ws client (mock), 不测组件
- 集成: 启动 fastapi + vite, playwright 走通建仓→加仓→减仓, 截图对照

## 10. 分期实施

| 期 | 内容 | 验收 | 估时 |
|---|---|---|---|
| P0 骨架 | fastapi hello + vite hello, 联调通 | 浏览器 :5173 看到 :8000 数据 | 0.5d |
| P1 REST 只读 | 4 个 GET + vue 5 区渲染 | 视觉对齐当前 streamlit | 1d |
| P2 WS | 东财 WS 客户端 + /ws/quotes + 前端订阅 | 持仓价格 1-2s 动 | 1d |
| P3 写 | 3 个 POST + 弹窗 3 mode + 100 股铁律后端 | 点 +/- 弹窗, 写库成功 | 1d |
| P4 打磨 | 错误提示 / 加载态 / 移动适配 / 文档 | 完整体验, 旧 dashboard.py 标注 deprecated | 0.5d |

风险点 P2: 东财 WS 协议/限流. 备用方案: 用 tencent.py 或新浪轮询, 2s 一次.

## 11. 兼容性

- 旧 a_stock/web/dashboard.py 保留, 不删. setup_cron.sh 不动.
- 新前端启动方式: bash a_stock/api/run_dev.sh (一键起后端 + 前端)
- 数据库 schema 0 改. 写操作走同一 decision_log 函数.
- 测试 pytest tests/ 不受影响 (P0/P1 阶段 import 现有函数).

## 12. 文件清单 (新增)

后端 (~12 文件):
```
a_stock/api/__init__.py
a_stock/api/app.py
a_stock/api/ws.py
a_stock/api/run_dev.sh
a_stock/api/models.py
a_stock/api/routes/__init__.py
a_stock/api/routes/portfolio.py
a_stock/api/routes/positions.py
a_stock/api/routes/opportunities.py
a_stock/api/routes/quotes.py
a_stock/api/routes/sentiment.py
```

测试 (~3 文件):
```
tests/test_api_portfolio.py
tests/test_api_positions.py
tests/test_api_ws.py
```

前端 (~28 文件):
```
frontend/package.json
frontend/vite.config.ts
frontend/tsconfig.json
frontend/tsconfig.node.json
frontend/index.html
frontend/.gitignore
frontend/src/main.ts
frontend/src/App.vue
frontend/src/env.d.ts
frontend/src/types.ts
frontend/src/api/http.ts
frontend/src/api/client.ts
frontend/src/ws/client.ts
frontend/src/stores/portfolio.ts
frontend/src/stores/positions.ts
frontend/src/stores/opportunities.ts
frontend/src/stores/dialog.ts
frontend/src/stores/sentiment.ts
frontend/src/views/Dashboard.vue
frontend/src/views/TickerBar.vue
frontend/src/views/AssetBar.vue
frontend/src/views/OpportunityFeed.vue
frontend/src/views/OpportunityCard.vue
frontend/src/views/PositionsList.vue
frontend/src/views/HoldingCard.vue
frontend/src/components/TradingDialog.vue
frontend/src/components/AddForm.vue
frontend/src/components/ReduceForm.vue
frontend/src/components/NewPositionForm.vue
frontend/src/styles/tokens.css
frontend/src/styles/global.css
```

文档:
```
docs/superpowers/plans/2026-06-30-dashboard-rebuild.md
```

总: ~44 个新文件, 0 个旧文件改.
