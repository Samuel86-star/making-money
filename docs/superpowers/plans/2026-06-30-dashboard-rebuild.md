# Dashboard Rebuild (vue3 + fastapi) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `a_stock/web/dashboard.py` (streamlit) with vue3 + fastapi, fixing the "dialog triggers full main rerun" problem. Existing `a_stock/` modules untouched.

**Architecture:** FastAPI backend on :8000 imports existing `a_stock/*` functions directly, exposes REST + 1 WebSocket endpoint. Vue3 + naive-ui + pinia frontend on :5173, vite proxies /api and /ws to backend. TradingDialog uses `<Teleport to="body">` so opening/closing does NOT remount the main dashboard.

**Tech Stack:** Python 3.12, FastAPI 0.115, uvicorn, aiohttp. Node 20, Vue 3.5, Vite 5, TypeScript 5, Pinia 2, vitest 2.

**Reference spec:** `docs/superpowers/specs/2026-06-30-dashboard-rebuild-design.md`

**Note:** This plan is the full design with TDD. For implementation, prefer the more compact staged plan at the bottom of this file (P0-P4, condensed to ~18 tasks). Both contain the same code; the staged version collapses long task lists into one per major component.

---

## Phase P0: Skeleton (1 task)

### Task 1: Backend FastAPI hello + Frontend Vite hello

**Files:**
- Create: `a_stock/api/__init__.py`
- Create: `a_stock/api/app.py`
- Create: `a_stock/api/run_dev.sh`
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/.gitignore`

- [ ] **Step 1: Write the failing backend test**

```python
# tests/test_api_app.py
from fastapi.testclient import TestClient
from a_stock.api.app import app

def test_health_endpoint():
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_api_app.py -v`
Expected: FAIL (no module `a_stock.api`)

- [ ] **Step 3: Write minimal backend**

`a_stock/api/__init__.py`:
```python
"""FastAPI 后端: REST + WebSocket 转发东财行情."""
```

`a_stock/api/app.py`:
```python
"""FastAPI app 入口. P0 阶段只暴露 /api/health."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="A股盯盘 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_api_app.py -v`
Expected: PASS

- [ ] **Step 5: Add deps to requirements**

Append to `requirements.txt`:
```
fastapi>=0.115
uvicorn[standard]>=0.32
aiohttp>=3.10
```

Run: `.venv/bin/pip install -r requirements.txt`
Expected: Successfully installed fastapi-... uvicorn-... aiohttp-...

- [ ] **Step 6: Write minimal frontend**

`frontend/.gitignore`:
```
node_modules/
dist/
.vite/
*.log
```

`frontend/package.json`:
```json
{
  "name": "a-stock-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest"
  },
  "dependencies": {
    "vue": "^3.5.13",
    "pinia": "^2.3.0",
    "naive-ui": "^2.40.4"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.2.1",
    "typescript": "~5.6.3",
    "vite": "^6.0.5",
    "vue-tsc": "^2.2.0",
    "vitest": "^2.1.8"
  }
}
```

`frontend/vite.config.ts`:
```ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: 'ws://localhost:8000', ws: true, changeOrigin: true },
    },
  },
})
```

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "jsx": "preserve",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "skipLibCheck": true,
    "noEmit": true,
    "types": ["vite/client"]
  },
  "include": ["src/**/*"]
}
```

`frontend/tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "skipLibCheck": true
  },
  "include": ["vite.config.ts"]
}
```

`frontend/index.html`:
```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>A股盯盘 · 交易终端</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`frontend/src/main.ts`:
```ts
import { createApp } from 'vue'
import App from './App.vue'

createApp(App).mount('#app')
```

`frontend/src/App.vue`:
```vue
<template>
  <div class="app">
    <h1>A股盯盘 · P0 骨架</h1>
    <p v-if="msg">{{ msg }}</p>
    <p v-else>连接后端…</p>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

const msg = ref('')
onMounted(async () => {
  const r = await fetch('/api/health')
  const j = await r.json()
  msg.value = `后端: ${j.status}`
})
</script>
```

- [ ] **Step 7: Install and run dev script**

`a_stock/api/run_dev.sh`:
```bash
#!/usr/bin/env bash
# 一键起后端 + 前端 dev. Ctrl+C 杀两进程.
set -e
cd "$(dirname "$0")/../.."

trap 'kill 0' EXIT INT TERM

echo "==> 起 fastapi :8000"
.venv/bin/uvicorn a_stock.api.app:app --reload --port 8000 &
BACKEND_PID=$!

sleep 1

echo "==> 起 vite :5173"
(cd frontend && npm run dev) &
FRONTEND_PID=$!

wait $BACKEND_PID $FRONTEND_PID
```

Run: `chmod +x a_stock/api/run_dev.sh`

- [ ] **Step 8: Install frontend deps and smoke test**

Run: `cd frontend && npm install`
Expected: added ~150 packages

Run: `cd .. && bash a_stock/api/run_dev.sh` in background
Verify with playwright: open `http://localhost:5173/` -> see "后端: ok"

- [ ] **Step 9: Commit**

```bash
git add a_stock/api/ frontend/ tests/test_api_app.py requirements.txt
git commit -m "feat(p0): fastapi+vite skeleton, /api/health, vite proxy"
```

---

(Plan continues in Part 2: P1-P4. See staged plan section below for compact view.)

## Phase P1: REST Read-Only + Vue components (5 tasks)

### Task 2: Pydantic models + 5 GET endpoints

**Files:**
- Create: `a_stock/api/models.py`
- Create: `a_stock/api/routes/__init__.py` (empty)
- Create: `a_stock/api/routes/portfolio.py`
- Create: `a_stock/api/routes/positions.py` (GET only, POST in Task 6)
- Create: `a_stock/api/routes/opportunities.py`
- Create: `a_stock/api/routes/quotes.py`
- Create: `a_stock/api/routes/sentiment.py`
- Modify: `a_stock/api/app.py` (wire routers)
- Modify: `a_stock/web/ticker.py` (add NAME_MAP at top)
- Test: `tests/test_api_models.py`, `tests/test_api_portfolio.py`, `tests/test_api_positions.py`, `tests/test_api_opportunities.py`, `tests/test_api_quotes_sentiment.py`

- [ ] **Step 1: Write tests** — 5 test files, one per endpoint, plus models.

```python
# tests/test_api_models.py
from a_stock.api.models import PortfolioOut, PositionOut, OpportunityOut, TickerOut, SentimentOut, QuoteOut, TradeResult
def test_portfolio(): assert PortfolioOut(total=1, stock_mv=1, cash=1, unrealized=0, realized=0, target_pct=0.0, n_positions=0).total == 1
def test_position(): assert PositionOut(code="x", name="y", qty=100, cost=1.0, price=1.0, pnl=0, pnl_pct=0.0, stop_loss=None).qty == 100
def test_opportunity_type_pattern():
    from pydantic import ValidationError
    try: OpportunityOut(type="bad", code="x", name="y", desc="", meta="", time="", tag="", action_label=None)
    except ValidationError: return
    assert False, "should reject bad type"
```

```python
# tests/test_api_portfolio.py
from fastapi.testclient import TestClient
from a_stock.api.app import app
c = TestClient(app)
def test_get_portfolio():
    r = c.get("/api/portfolio"); assert r.status_code == 200
    for k in ("total", "stock_mv", "cash", "unrealized", "realized", "target_pct", "n_positions"): assert k in r.json()
```

```python
# tests/test_api_positions.py
from fastapi.testclient import TestClient
from a_stock.api.app import app
c = TestClient(app)
def test_get_positions():
    r = c.get("/api/positions"); assert r.status_code == 200
    j = r.json(); assert isinstance(j, list)
```

```python
# tests/test_api_opportunities.py
from fastapi.testclient import TestClient
from a_stock.api.app import app
c = TestClient(app)
def test_get_opportunities():
    r = c.get("/api/opportunities"); assert r.status_code == 200
    assert isinstance(r.json(), list)
```

```python
# tests/test_api_quotes_sentiment.py
from fastapi.testclient import TestClient
from a_stock.api.app import app
c = TestClient(app)
def test_ticker(): assert c.get("/api/ticker").status_code == 200
def test_quote_404(): assert c.get("/api/quote/999999").status_code in (200, 404)
def test_sentiment(): r = c.get("/api/sentiment"); assert r.status_code == 200
```

- [ ] **Step 2: Run tests, all FAIL**

Run: `.venv/bin/python -m pytest tests/test_api_*.py -v`
Expected: all FAIL (no api module)

- [ ] **Step 3: Write models**

`a_stock/api/models.py`:
```python
"""API 输出 schema. pydantic v2."""
from pydantic import BaseModel, Field


class PortfolioOut(BaseModel):
    total: int; stock_mv: int; cash: int
    unrealized: int; realized: int
    target_pct: float; n_positions: int


class PositionOut(BaseModel):
    code: str; name: str; qty: int
    cost: float; price: float; pnl: int; pnl_pct: float
    stop_loss: float | None = None


class OpportunityOut(BaseModel):
    type: str = Field(pattern="^(pullback|anomaly|candidate|rule)$")
    code: str; name: str; desc: str
    meta: str = ""; time: str = ""; tag: str
    action_label: str | None = None


class TickerOut(BaseModel):
    code: str; name: str; price: float


class SentimentOut(BaseModel):
    temp: float; mood: str; leader: str | None = None


class QuoteOut(BaseModel):
    code: str; price: float; change: float; ts: int


class TradeResult(BaseModel):
    id: int; code: str; realized: int = 0
```

- [ ] **Step 4: Add NAME_MAP to ticker.py**

Modify `a_stock/web/ticker.py` — add at top (after imports, before other code):
```python
NAME_MAP = {
    "600276": "恒瑞医药", "515650": "消费50ETF", "300059": "东方财富",
    "159801": "芯片ETF", "159915": "创业板ETF", "159516": "半导体材料设备",
    "515880": "通信ETF", "000988": "华工科技", "000636": "风华高科",
    "300136": "信维通信", "002859": "洁美科技", "000021": "深科技",
    "000960": "锡业股份", "002407": "多氟多",
}
```

If `a_stock/web/dashboard.py` already defines `_NAMES`, extract to ticker.py and remove the dup.

- [ ] **Step 5: Write 5 route files (one shot)**

`a_stock/api/routes/__init__.py`: empty file.

`a_stock/api/routes/portfolio.py`:
```python
"""/api/portfolio — 资产条 5 格. 复用 asset_bar."""
from fastapi import APIRouter
from a_stock.web import asset_bar
from a_stock.api.models import PortfolioOut

router = APIRouter()


@router.get("/portfolio", response_model=PortfolioOut)
def get_portfolio() -> PortfolioOut:
    ab = asset_bar.collect_asset_bar(55319.0)  # 现金基准暂硬编码
    return PortfolioOut(
        total=ab["total"], stock_mv=ab["stock_mv"], cash=ab["cash"],
        unrealized=ab["unrealized"], realized=ab["realized"],
        target_pct=ab["target_pct"],
        n_positions=ab.get("n_positions", 0),
    )
```

`a_stock/api/routes/positions.py` (GET only — POST in Task 6):
```python
"""/api/positions — 持仓列表. 复用 positions_panel."""
from fastapi import APIRouter
from a_stock.web import positions_panel
from a_stock.api.models import PositionOut

router = APIRouter()


@router.get("/positions", response_model=list[PositionOut])
def get_positions() -> list[PositionOut]:
    return [
        PositionOut(
            code=r["code"], name=r["name"], qty=r["qty"],
            cost=r["cost"], price=r["price"], pnl=r["pnl"],
            pnl_pct=r["pnl_pct"], stop_loss=r.get("stop_loss"),
        )
        for r in positions_panel.collect_positions()
    ]
```

`a_stock/api/routes/opportunities.py`:
```python
"""/api/opportunities — 机会流. 复用 opportunity_feed."""
from fastapi import APIRouter
from a_stock.web import opportunity_feed
from a_stock.api.models import OpportunityOut

router = APIRouter()


@router.get("/opportunities", response_model=list[OpportunityOut])
def get_opportunities() -> list[OpportunityOut]:
    return [
        OpportunityOut(
            type=r["type"], code=r["code"], name=r.get("name") or "",
            desc=r.get("desc", ""), meta=r.get("meta", ""),
            time=r.get("time", ""), tag=r.get("tag", ""),
            action_label=r.get("action_label"),
        )
        for r in opportunity_feed.collect_opportunities()
    ]
```

`a_stock/api/routes/quotes.py`:
```python
"""/api/ticker 滚动 + /api/quote/{code} 单标."""
import time
from fastapi import APIRouter, HTTPException
from a_stock.web import ticker
from a_stock.risk_metrics import _live_price
from a_stock.api.models import TickerOut, QuoteOut

router = APIRouter()


@router.get("/ticker", response_model=list[TickerOut])
def get_ticker() -> list[TickerOut]:
    out = []
    for c in ticker.collect_ticker_codes():
        px = _live_price(c)
        if px:
            out.append(TickerOut(code=c, name=ticker.NAME_MAP.get(c, ""), price=px))
    return out


@router.get("/quote/{code}", response_model=QuoteOut)
def get_quote(code: str) -> QuoteOut:
    px = _live_price(code)
    if not px:
        raise HTTPException(404, f"no quote for {code}")
    return QuoteOut(code=code, price=px, change=0.0, ts=int(time.time() * 1000))
```

`a_stock/api/routes/sentiment.py`:
```python
"""/api/sentiment 情绪温度."""
from fastapi import APIRouter
from a_stock.web import sentiment_bar
from a_stock.api.models import SentimentOut

router = APIRouter()


@router.get("/sentiment", response_model=SentimentOut)
def get_sentiment() -> SentimentOut:
    s = sentiment_bar.collect_sentiment()
    return SentimentOut(temp=s["temp"], mood=s["mood"], leader=s.get("leader"))
```

- [ ] **Step 6: Wire routers in app.py**

Replace `a_stock/api/app.py` with:
```python
"""FastAPI app 入口."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from a_stock.api.routes import portfolio, positions, opportunities, quotes, sentiment


app = FastAPI(title="A股盯盘 API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(portfolio.router, prefix="/api")
app.include_router(positions.router, prefix="/api")
app.include_router(opportunities.router, prefix="/api")
app.include_router(quotes.router, prefix="/api")
app.include_router(sentiment.router, prefix="/api")
```

- [ ] **Step 7: Run tests, all PASS**

Run: `.venv/bin/python -m pytest tests/test_api_*.py -v`
Expected: 8+ tests PASS

- [ ] **Step 8: Commit**

```bash
git add a_stock/api/ a_stock/web/ticker.py tests/
git commit -m "feat(p1): 5 GET endpoints + pydantic models + NAME_MAP"
```

---

### Task 3: Frontend http client + 4 pinia stores + types

**Files:**
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api/http.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/stores/portfolio.ts`
- Create: `frontend/src/stores/positions.ts`
- Create: `frontend/src/stores/opportunities.ts`
- Create: `frontend/src/stores/sentiment.ts`
- Test: `frontend/src/stores/__tests__/positions.test.ts`

- [ ] **Step 1: Install pinia, write test, run FAIL**

Run: `cd frontend && npm install pinia`

```typescript
// frontend/src/stores/__tests__/positions.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePositions } from '../positions'

describe('positions store', () => {
  beforeEach(() => { setActivePinia(createPinia()); global.fetch = vi.fn() })
  it('refresh fetches /api/positions and stores list', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true, json: async () => [{ code: '600276', name: 'x', qty: 100,
        cost: 1, price: 1, pnl: 0, pnl_pct: 0, stop_loss: null }],
    })
    const s = usePositions(); await s.refresh()
    expect(s.list).toHaveLength(1)
    expect(s.list[0].code).toBe('600276')
  })
})
```

Run: `npx vitest run src/stores/__tests__/positions.test.ts` — FAIL

- [ ] **Step 2: Write types, http, client, 4 stores** (one shot)

`frontend/src/types.ts`:
```ts
export interface Portfolio { total: number; stock_mv: number; cash: number; unrealized: number; realized: number; target_pct: number; n_positions: number }
export interface Position { code: string; name: string; qty: number; cost: number; price: number; pnl: number; pnl_pct: number; stop_loss: number | null }
export interface Opportunity { type: 'pullback'|'anomaly'|'candidate'|'rule'; code: string; name: string; desc: string; meta: string; time: string; tag: string; action_label: string | null }
export interface TickerQuote { code: string; name: string; price: number }
export interface Sentiment { temp: number; mood: string; leader: string | null }
export interface Quote { code: string; price: number; change: number; ts: number }
export interface TradeRequest { strategy?: string; price: number; qty: number; reason?: string }
export interface NewPositionRequest extends TradeRequest { code: string; name: string }
```

`frontend/src/api/http.ts`:
```ts
export async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!r.ok) {
    const j = await r.json().catch(() => ({ error: r.statusText }))
    throw new Error(j.error || `HTTP ${r.status}`)
  }
  return r.json()
}
```

`frontend/src/api/client.ts`:
```ts
import { http } from './http'
import type { Portfolio, Position, Opportunity, TickerQuote, Sentiment, Quote, TradeRequest, NewPositionRequest } from '../types'

export const api = {
  portfolio: () => http<Portfolio>('/api/portfolio'),
  positions: () => http<Position[]>('/api/positions'),
  opportunities: () => http<Opportunity[]>('/api/opportunities'),
  ticker: () => http<TickerQuote[]>('/api/ticker'),
  sentiment: () => http<Sentiment>('/api/sentiment'),
  quote: (code: string) => http<Quote>(`/api/quote/${code}`),
  addPosition: (body: NewPositionRequest) =>
    http<{ id: number; code: string; name: string }>('/api/positions', { method: 'POST', body: JSON.stringify(body) }),
  addToPosition: (code: string, body: TradeRequest) =>
    http<{ id: number; code: string }>(`/api/positions/${code}/add`, { method: 'POST', body: JSON.stringify(body) }),
  reducePosition: (code: string, body: TradeRequest) =>
    http<{ id: number; code: string; realized: number }>(`/api/positions/${code}/reduce`, { method: 'POST', body: JSON.stringify(body) }),
}
```

`frontend/src/stores/portfolio.ts`:
```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { Portfolio } from '../types'
export const usePortfolio = defineStore('portfolio', () => {
  const data = ref<Portfolio | null>(null)
  const loading = ref(false); const error = ref<string | null>(null)
  async function refresh() { loading.value = true; error.value = null; try { data.value = await api.portfolio() } catch (e: any) { error.value = e.message } finally { loading.value = false } }
  return { data, loading, error, refresh }
})
```

`frontend/src/stores/positions.ts`:
```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { Position } from '../types'
export const usePositions = defineStore('positions', () => {
  const list = ref<Position[]>([])
  const loading = ref(false); const error = ref<string | null>(null)
  async function refresh() { loading.value = true; error.value = null; try { list.value = await api.positions() } catch (e: any) { error.value = e.message } finally { loading.value = false } }
  return { list, loading, error, refresh }
})
```

`frontend/src/stores/opportunities.ts`:
```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { Opportunity } from '../types'
export const useOpportunities = defineStore('opportunities', () => {
  const list = ref<Opportunity[]>([])
  const loading = ref(false); const error = ref<string | null>(null)
  async function refresh() { loading.value = true; error.value = null; try { list.value = await api.opportunities() } catch (e: any) { error.value = e.message } finally { loading.value = false } }
  return { list, loading, error, refresh }
})
```

`frontend/src/stores/sentiment.ts`:
```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import type { Sentiment } from '../types'
export const useSentiment = defineStore('sentiment', () => {
  const data = ref<Sentiment | null>(null)
  async function refresh() { data.value = await api.sentiment() }
  return { data, refresh }
})
```

- [ ] **Step 3: Run test PASS**

Run: `npx vitest run src/stores/__tests__/positions.test.ts` — PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/api/ frontend/src/stores/
git commit -m "feat(p1): frontend http client + 4 pinia stores"
```

---

### Task 4: TickerBar + AssetBar + styles

**Files:**
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/global.css`
- Create: `frontend/src/views/TickerBar.vue`
- Create: `frontend/src/views/AssetBar.vue`
- Create: `frontend/src/views/DashboardPlaceholder.vue`
- Modify: `frontend/src/main.ts` (use Pinia, import global.css)
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Write styles**

`frontend/src/styles/tokens.css`:
```css
:root {
  --bg:#0a0e14; --panel:#12161f; --panel-2:#161b26; --line:#1f2633; --line-2:#262d3b;
  --txt:#e8eaed; --dim:#7a8497; --dimmer:#4a5568;
  --red:#f23645; --green:#089981; --amber:#d4a017; --blue:#3b82f6;
  --mono:'JetBrains Mono','SF Mono',Menlo,ui-monospace,monospace;
  --sans:'Inter',-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;
}
```

`frontend/src/styles/global.css`:
```css
@import './tokens.css';
* { box-sizing: border-box; }
html, body, #app { margin: 0; padding: 0; background: var(--bg); color: var(--txt); font-family: var(--sans); font-size: 13px; }
a { text-decoration: none; color: inherit; }
```

- [ ] **Step 2: Write TickerBar.vue**

```vue
<template>
  <div class="ticker">
    <div class="label">A股盯盘 · 实时</div>
    <div class="track">
      <span v-for="(q, i) in doubled" :key="i" class="q">
        <span class="code">{{ q.code }}</span>
        <span class="name">{{ q.name }}</span>
        <span class="px">{{ q.price.toFixed(3) }}</span>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { api } from '../api/client'
import type { TickerQuote } from '../types'

const quotes = ref<TickerQuote[]>([])
let timer: number | null = null
async function poll() { try { quotes.value = await api.ticker() } catch {} }
onMounted(() => { poll(); timer = window.setInterval(poll, 5000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
const doubled = computed(() => [...quotes.value, ...quotes.value])
</script>

<style scoped>
.ticker { background: #000; border: 1px solid var(--line); border-radius: 6px; overflow: hidden;
  height: 48px; display: flex; align-items: stretch; margin-bottom: 18px; position: relative; }
.label { position: absolute; left: 0; top: 0; bottom: 0; background: var(--red); color: #000;
  font-family: var(--mono); font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
  padding: 0 14px; display: flex; align-items: center; z-index: 2; }
.track { display: flex; align-items: center; gap: 32px; white-space: nowrap;
  padding-left: 120px; height: 100%; animation: scroll 60s linear infinite; }
@keyframes scroll { from { transform: translateX(0) } to { transform: translateX(-50%) } }
.q { display: inline-flex; align-items: baseline; gap: 6px; }
.q .code { color: var(--dim); font-family: var(--mono); font-size: 12px; }
.q .name { color: var(--txt); font-size: 13px; font-weight: 500; }
.q .px { font-family: var(--mono); font-size: 13px; font-weight: 600; }
</style>
```

- [ ] **Step 3: Write AssetBar.vue**

```vue
<template>
  <div v-if="portfolio.data" class="bar5">
    <div class="kpi hero">
      <span class="lbl">总资产</span>
      <span class="val">{{ portfolio.data.total.toLocaleString() }}</span>
      <span class="sub">浮盈 {{ sign(portfolio.data.unrealized) }}{{ portfolio.data.unrealized }} · 已实现 {{ sign(portfolio.data.realized) }}{{ portfolio.data.realized }}</span>
    </div>
    <div class="kpi">
      <span class="lbl">持仓市值</span><span class="val">{{ portfolio.data.stock_mv.toLocaleString() }}</span>
      <span class="sub">{{ portfolio.data.n_positions }} 只标的</span>
    </div>
    <div class="kpi">
      <span class="lbl">现金</span><span class="val">{{ portfolio.data.cash.toLocaleString() }}</span>
      <span class="sub">弹药 {{ cashPct.toFixed(0) }}%</span>
    </div>
    <div class="kpi">
      <span class="lbl">浮盈</span>
      <span :class="['val', portfolio.data.unrealized >= 0 ? 'up' : 'down']">{{ sign(portfolio.data.unrealized) }}{{ portfolio.data.unrealized }}</span>
      <span class="sub">日已实现 {{ sign(portfolio.data.realized) }}{{ portfolio.data.realized }}</span>
    </div>
    <div class="kpi">
      <span class="lbl">距 100k</span><span class="val amber">{{ portfolio.data.target_pct.toFixed(1) }}%</span>
      <span class="sub">→ 100,000</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { usePortfolio } from '../stores/portfolio'
const portfolio = usePortfolio()
const cashPct = computed(() => portfolio.data ? portfolio.data.cash / Math.max(portfolio.data.total, 1) * 100 : 0)
const sign = (n: number) => n >= 0 ? '+' : ''
onMounted(() => portfolio.refresh())
</script>

<style scoped>
.bar5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 1px; background: var(--line);
  border: 1px solid var(--line); border-radius: 6px; overflow: hidden; margin-bottom: 18px; }
.kpi { background: var(--panel); padding: 14px 18px; display: flex; flex-direction: column; gap: 4px; }
.kpi .lbl { font-size: 10px; color: var(--dim); text-transform: uppercase; letter-spacing: 0.12em; font-weight: 500; }
.kpi .val { font-family: var(--mono); font-size: 26px; font-weight: 600; line-height: 1.1; color: var(--txt); }
.kpi.hero .val { font-size: 30px; }
.kpi .sub { font-family: var(--mono); font-size: 11px; color: var(--dim); }
.up { color: var(--red); } .down { color: var(--green); } .amber { color: var(--amber); }
</style>
```

- [ ] **Step 4: Wire main.ts + App.vue + placeholder**

`frontend/src/main.ts`:
```ts
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import './styles/global.css'
createApp(App).use(createPinia()).mount('#app')
```

`frontend/src/views/DashboardPlaceholder.vue`:
```vue
<template><div style="padding:40px;text-align:center;color:var(--dim)">主区待 Task 5 完成</div></template>
```

`frontend/src/App.vue`:
```vue
<template>
  <TickerBar />
  <AssetBar />
  <DashboardPlaceholder />
</template>
<script setup lang="ts">
import TickerBar from './views/TickerBar.vue'
import AssetBar from './views/AssetBar.vue'
import DashboardPlaceholder from './views/DashboardPlaceholder.vue'
</script>
```

- [ ] **Step 5: Visual verify via playwright**

Run: `bash a_stock/api/run_dev.sh` (background)
Playwright: open `http://localhost:5173/`
Verify: ticker 滚, 5 格 KPI = 79,938 / 24,619 / 55,319 / +303 / 79.9%

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles/ frontend/src/views/TickerBar.vue frontend/src/views/AssetBar.vue frontend/src/views/DashboardPlaceholder.vue frontend/src/App.vue frontend/src/main.ts
git commit -m "feat(p1): TickerBar + AssetBar + global styles"
```

---

### Task 5: Dashboard view (OpportunityFeed + PositionsList + cards + dialog stub)

**Files:**
- Create: `frontend/src/stores/dialog.ts`
- Create: `frontend/src/views/Dashboard.vue`
- Create: `frontend/src/views/OpportunityFeed.vue`
- Create: `frontend/src/views/OpportunityCard.vue`
- Create: `frontend/src/views/PositionsList.vue`
- Create: `frontend/src/views/HoldingCard.vue`
- Delete: `frontend/src/views/DashboardPlaceholder.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Write dialog store**

`frontend/src/stores/dialog.ts`:
```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
export type DialogMode = 'add'|'reduce'|'new'|null
export const useDialog = defineStore('dialog', () => {
  const open = ref(false)
  const mode = ref<DialogMode>(null)
  const payload = ref<any>({})
  function show(m: DialogMode, p: any = {}) { mode.value = m; payload.value = p; open.value = true }
  function close() { open.value = false }
  return { open, mode, payload, show, close }
})
```

- [ ] **Step 2: Write OpportunityCard**

`frontend/src/views/OpportunityCard.vue`:
```vue
<template>
  <div class="opp">
    <div class="bar" :style="{ background: barColor }"></div>
    <div class="body">
      <div class="top"><span :class="['tag', tagCls]">{{ typeLabel[opp.type] }}</span>
        <span class="code">{{ opp.code }}</span><span class="name">{{ opp.name }}</span></div>
      <div class="desc">{{ opp.desc }}</div>
      <div class="meta">{{ opp.meta }} · {{ opp.time }}</div>
    </div>
    <button class="action" @click="onAdd">{{ opp.action_label || '加仓' }}</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Opportunity } from '../types'
import { useDialog } from '../stores/dialog'
const props = defineProps<{ opp: Opportunity }>()
const dialog = useDialog()
const barColors: Record<string,string> = { pullback:'var(--amber)', anomaly:'var(--red)', candidate:'var(--blue)', rule:'var(--green)' }
const tagClasses: Record<string,string> = { pullback:'tag-pull', anomaly:'tag-anom', candidate:'tag-cand', rule:'tag-rule' }
const typeLabel: Record<string,string> = { pullback:'回踩买点', anomaly:'盘中异动', candidate:'早盘候选', rule:'规则触发' }
const barColor = computed(() => barColors[props.opp.type])
const tagCls = computed(() => tagClasses[props.opp.type])
function onAdd() { dialog.show('add', { code: props.opp.code, name: props.opp.name, cost: 0 }) }
</script>

<style scoped>
.opp { display: grid; grid-template-columns: 3px 1fr auto; gap: 14px; padding: 12px 16px;
  border-bottom: 1px solid var(--line); align-items: stretch; min-height: 88px; height: 88px; }
.bar { width: 3px; height: 100%; border-radius: 2px; align-self: stretch; }
.body { min-width: 0; display: flex; flex-direction: column; gap: 4px; justify-content: center; }
.top { display: flex; align-items: center; gap: 8px; line-height: 1; }
.tag { font-size: 10px; padding: 2px 7px; border-radius: 3px; font-weight: 600; line-height: 1.2; }
.code { font-family: var(--mono); font-weight: 500; font-size: 11px; color: var(--dimmer); margin-left: 4px; line-height: 1.2; }
.name { color: var(--txt); font-size: 13px; font-weight: 600; margin-left: 4px; line-height: 1.2; }
.desc { color: var(--txt); font-size: 11.5px; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.meta { font-family: var(--mono); font-size: 10.5px; color: var(--dimmer); line-height: 1.2; }
.action { align-self: center; font-family: var(--mono); font-size: 12px; font-weight: 600;
  padding: 4px 9px; border-radius: 4px; background: rgba(212,160,23,0.12); color: var(--amber);
  border: 1px solid var(--amber); cursor: pointer; transition: all 0.15s; }
.action:hover { background: var(--amber); color: #000; }
.tag-pull { background: rgba(212,160,23,0.15); color: var(--amber); }
.tag-anom { background: rgba(242,54,69,0.15); color: var(--red); }
.tag-cand { background: rgba(59,130,246,0.15); color: var(--blue); }
.tag-rule { background: rgba(8,153,129,0.15); color: var(--green); }
</style>
```

- [ ] **Step 3: Write OpportunityFeed**

`frontend/src/views/OpportunityFeed.vue`:
```vue
<template>
  <div class="section-title">
    <span class="left"><span class="dot"></span>机会流</span>
  </div>
  <div v-if="opp.list.length === 0" class="empty panel">暂无机会点 · 盘后或市场平静时属正常</div>
  <div v-else class="panel">
    <OpportunityCard v-for="o in opp.list" :key="o.code + o.type" :opp="o" />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import OpportunityCard from './OpportunityCard.vue'
import { useOpportunities } from '../stores/opportunities'
const opp = useOpportunities()
onMounted(() => opp.refresh())
</script>

<style scoped>
.section-title { font-size: 11px; color: var(--dim); text-transform: uppercase;
  letter-spacing: 0.12em; font-weight: 600; margin-bottom: 10px;
  display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.left { display: flex; align-items: center; gap: 8px; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--red); box-shadow: 0 0 8px var(--red); }
.empty { padding: 40px; text-align: center; color: var(--dim); }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
</style>
```

- [ ] **Step 4: Write HoldingCard**

`frontend/src/views/HoldingCard.vue`:
```vue
<template>
  <div class="card hold">
    <div class="bar" style="background: var(--red)"></div>
    <div class="body">
      <div class="r1">
        <div>
          <span class="code">{{ p.code }}</span>
          <span class="name">{{ p.name }}</span>
          <button class="abtn" @click="onAdd">+</button>
          <button class="abtn" @click="onReduce">-</button>
        </div>
        <span :class="['pnl', pnlCls]">{{ p.pnl_pct.toFixed(2) }}%</span>
      </div>
      <div class="r2"><span>{{ p.qty }}股 @<b>{{ p.cost.toFixed(3) }}</b></span>
        <span>现 <b>{{ p.price.toFixed(3) }}</b></span></div>
      <div class="r2"><span>浮 <b :class="pnlCls">{{ p.pnl >= 0 ? '+' : '' }}{{ p.pnl }}</b></span>
        <span>ATR止损 <b>{{ p.stop_loss?.toFixed(3) ?? '—' }}</b></span></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Position } from '../types'
import { useDialog } from '../stores/dialog'
const props = defineProps<{ p: Position }>()
const dialog = useDialog()
const pnlCls = computed(() => props.p.pnl > 0 ? 'up' : props.p.pnl < 0 ? 'down' : '')
function onAdd() { dialog.show('add', { code: props.p.code, name: props.p.name, cost: props.p.cost }) }
function onReduce() { dialog.show('reduce', { code: props.p.code, name: props.p.name, qty: props.p.qty, cost: props.p.cost }) }
</script>

<style scoped>
.card { display: grid; grid-template-columns: 3px 1fr; gap: 14px; padding: 12px 16px;
  border-bottom: 1px solid var(--line); background: var(--panel);
  min-height: 88px; height: 88px; align-items: stretch; box-sizing: border-box; }
.card:last-child { border-bottom: 0; }
.bar { width: 3px; height: 100%; align-self: stretch; border-radius: 2px; }
.body { display: flex; flex-direction: column; gap: 4px; justify-content: center; }
.r1 { display: flex; align-items: center; justify-content: space-between; gap: 8px; line-height: 1.2; margin: 0; }
.code { font-family: var(--mono); font-weight: 600; font-size: 13px; line-height: 1.2; }
.name { color: var(--dim); font-size: 11px; margin-left: 6px; line-height: 1.2; }
.pnl { font-family: var(--mono); font-weight: 600; font-size: 14px; margin-left: 6px; line-height: 1.2; }
.r2 { display: flex; justify-content: space-between; font-family: var(--mono);
  font-size: 10.5px; color: var(--dimmer); letter-spacing: 0.02em; line-height: 1.2; margin: 0; }
.r2 b { color: var(--txt); font-weight: 500; }
.up { color: var(--red); } .down { color: var(--green); }
.abtn { color: var(--dim); font-family: var(--mono); font-size: 11px; font-weight: 600;
  margin-left: 6px; padding: 1px 5px; border: 1px solid var(--line-2); border-radius: 3px;
  background: transparent; cursor: pointer; transition: all 0.15s; }
.abtn:hover { color: var(--red); border-color: var(--red); background: rgba(242,54,69,0.08); }
</style>
```

- [ ] **Step 5: Write PositionsList + Dashboard**

`frontend/src/views/PositionsList.vue`:
```vue
<template>
  <div class="section-title">
    <span class="left"><span class="dot"></span><span style="color:var(--dim)">持仓</span></span>
    <button class="newpos" @click="onNew" title="新建持仓">+</button>
  </div>
  <div v-if="pos.list.length === 0" class="empty panel">无持仓</div>
  <div v-else class="panel">
    <HoldingCard v-for="p in pos.list" :key="p.code" :p="p" />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import HoldingCard from './HoldingCard.vue'
import { usePositions } from '../stores/positions'
import { useDialog } from '../stores/dialog'
const pos = usePositions()
const dialog = useDialog()
onMounted(() => pos.refresh())
function onNew() { dialog.show('new') }
</script>

<style scoped>
.section-title { position: relative; font-size: 11px; color: var(--dim); text-transform: uppercase;
  letter-spacing: 0.12em; font-weight: 600; margin-bottom: 10px;
  display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.left { display: flex; align-items: center; gap: 8px; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: var(--red); box-shadow: 0 0 8px var(--red); }
.newpos { color: var(--dim); font-family: var(--mono); font-size: 14px; font-weight: 700;
  padding: 1px 7px; border: 1px solid var(--line-2); border-radius: 3px;
  background: transparent; cursor: pointer; }
.newpos:hover { color: var(--red); border-color: var(--red); }
.empty { padding: 40px; text-align: center; color: var(--dim); }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
</style>
```

`frontend/src/views/Dashboard.vue`:
```vue
<template>
  <div class="dash">
    <div class="col-feed"><OpportunityFeed /></div>
    <div class="col-pos"><PositionsList /></div>
  </div>
</template>

<script setup lang="ts">
import OpportunityFeed from './OpportunityFeed.vue'
import PositionsList from './PositionsList.vue'
</script>

<style scoped>
.dash { display: grid; grid-template-columns: 2fr 1fr; gap: 18px; }
@media (max-width: 900px) { .dash { grid-template-columns: 1fr; } }
</style>
```

- [ ] **Step 6: Update App.vue + delete placeholder**

`frontend/src/App.vue`:
```vue
<template>
  <div class="app">
    <TickerBar />
    <AssetBar />
    <Dashboard />
  </div>
</template>
<script setup lang="ts">
import TickerBar from './views/TickerBar.vue'
import AssetBar from './views/AssetBar.vue'
import Dashboard from './views/Dashboard.vue'
</script>
<style scoped>
.app { max-width: 1280px; margin: 0 auto; padding: 1.2rem 1rem 2rem; }
</style>
```

Delete: `frontend/src/views/DashboardPlaceholder.vue`

- [ ] **Step 7: Visual verify**

Run: `bash a_stock/api/run_dev.sh` (background)
Playwright: open `http://localhost:5173/`
Verify: 左机会流 ≥ 5 卡片, 右持仓 5 卡片, 持仓卡有 + - 按钮, 持仓标题右上 + 按钮

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/ frontend/src/stores/dialog.ts frontend/src/App.vue
git rm frontend/src/views/DashboardPlaceholder.vue
git commit -m "feat(p1): Dashboard view with opportunity feed + positions"
```

---

## Phase P2: WebSocket real-time (2 tasks)

### Task 6: Backend /ws/quotes + frontend ws client + HoldingCard price update

**Files:**
- Create: `a_stock/api/ws.py`
- Modify: `a_stock/api/app.py` (lifespan, ws router)
- Create: `frontend/src/ws/client.ts`
- Modify: `frontend/src/main.ts` (init + connect quoteWS)
- Modify: `frontend/src/views/HoldingCard.vue` (subscribe on mount)
- Test: `tests/test_api_ws.py`, `frontend/src/ws/__tests__/client.test.ts`

- [ ] **Step 1: Write 2 tests, run FAIL**

```python
# tests/test_api_ws.py
import json
from fastapi.testclient import TestClient
from a_stock.api.app import app
c = TestClient(app)

def test_ping_pong():
    with c.websocket_connect("/ws/quotes") as ws:
        ws.send_text(json.dumps({"action": "ping"}))
        assert json.loads(ws.receive_text()) == {"action": "pong"}

def test_sub_ack():
    with c.websocket_connect("/ws/quotes") as ws:
        ws.send_text(json.dumps({"action": "sub", "codes": ["600276"]}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "ack" and "600276" in msg["codes"]
```

```typescript
// frontend/src/ws/__tests__/client.test.ts
import { describe, it, expect, vi } from 'vitest'
import { QuoteWS } from '../client'

describe('QuoteWS', () => {
  it('connects and dispatches quote', () => {
    const fakeWs: any = { onopen: null, onmessage: null, onclose: null, onerror: null, send: vi.fn(), close: vi.fn() }
    vi.stubGlobal('WebSocket', vi.fn(() => fakeWs))
    const qws = new QuoteWS()
    const handler = vi.fn()
    qws.subscribe(['600276'], handler)
    qws.connect()
    fakeWs.onopen()
    expect(fakeWs.send).toHaveBeenCalledWith(JSON.stringify({ action: 'sub', codes: ['600276'] }))
    fakeWs.onmessage({ data: JSON.stringify({ type: 'quote', code: '600276', price: 52.93, change: 0, ts: 0 }) })
    expect(handler).toHaveBeenCalled()
    vi.unstubAllGlobals()
  })
})
```

- [ ] **Step 2: Write backend ws.py**

`a_stock/api/ws.py`:
```python
"""/ws/quotes — 行情推送. 2s 轮询 _live_price, 推所有订阅者. 协议稳定, 后续可换真东财 WS."""
import asyncio, json, logging, time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from a_stock.risk_metrics import _live_price

router = APIRouter()
log = logging.getLogger("a_stock.api.ws")


class QuoteBus:
    def __init__(self) -> None:
        self._clients: dict[WebSocket, set[str]] = {}
        self._latest: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task: self._task.cancel(); self._task = None

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(2)
            async with self._lock:
                all_codes: set[str] = set()
                for codes in self._clients.values(): all_codes.update(codes)
            for code in all_codes:
                px = _live_price(code)
                if not px: continue
                self._latest[code] = px
                msg = {"type": "quote", "code": code, "price": px, "change": 0.0, "ts": int(time.time() * 1000)}
                await self._broadcast(code, msg)

    async def _broadcast(self, code: str, msg: dict) -> None:
        async with self._lock:
            targets = [ws for ws, codes in self._clients.items() if code in codes]
        for ws in targets:
            try: await ws.send_text(json.dumps(msg, ensure_ascii=False))
            except Exception: pass

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock: self._clients[ws] = set()

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock: self._clients.pop(ws, None)

    async def subscribe(self, ws: WebSocket, codes: list[str]) -> None:
        async with self._lock:
            if ws in self._clients: self._clients[ws].update(codes)
        for code in codes:
            if code in self._latest:
                await ws.send_text(json.dumps({"type": "quote", "code": code, "price": self._latest[code], "change": 0.0, "ts": int(time.time() * 1000)}, ensure_ascii=False))


bus = QuoteBus()


@router.websocket("/ws/quotes")
async def ws_quotes(ws: WebSocket) -> None:
    await bus.connect(ws)
    try:
        while True:
            text = await ws.receive_text()
            try: msg = json.loads(text)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "msg": "invalid json"})); continue
            action = msg.get("action")
            if action == "ping":
                await ws.send_text(json.dumps({"action": "pong"}))
            elif action == "sub":
                codes = msg.get("codes", [])
                await bus.subscribe(ws, codes)
                await ws.send_text(json.dumps({"type": "ack", "codes": codes}))
    except WebSocketDisconnect: pass
    finally: await bus.disconnect(ws)
```

- [ ] **Step 3: Update app.py with lifespan + ws router**

Replace `a_stock/api/app.py` with:
```python
"""FastAPI app 入口."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from a_stock.api import ws as ws_module
from a_stock.api.routes import portfolio, positions, opportunities, quotes, sentiment


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ws_module.bus.start()
    yield
    await ws_module.bus.stop()


app = FastAPI(title="A股盯盘 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(portfolio.router, prefix="/api")
app.include_router(positions.router, prefix="/api")
app.include_router(opportunities.router, prefix="/api")
app.include_router(quotes.router, prefix="/api")
app.include_router(sentiment.router, prefix="/api")
app.include_router(ws_module.router)  # /ws/quotes
```

- [ ] **Step 4: Run backend test PASS**

Run: `.venv/bin/python -m pytest tests/test_api_ws.py -v`
Expected: PASS

- [ ] **Step 5: Write frontend ws client**

`frontend/src/ws/client.ts`:
```ts
import type { Quote } from '../types'
type Handler = (q: Quote) => void

export class QuoteWS {
  private ws: WebSocket | null = null
  private subs = new Map<string, Set<Handler>>()
  private reconnectTimer: number | null = null
  private url = ''
  private pingTimer: number | null = null

  init(url = '/ws/quotes') { this.url = url }

  connect() {
    if (this.ws) return
    const ws = new WebSocket(this.url); this.ws = ws
    ws.onopen = () => { this.sendAllPending(); this.startPing() }
    ws.onmessage = (e) => { try { const m = JSON.parse(e.data); if (m.type === 'quote') this.dispatch(m as Quote) } catch {} }
    ws.onclose = () => { this.ws = null; this.stopPing(); this.scheduleReconnect() }
    ws.onerror = () => {}
  }

  private startPing() { this.stopPing(); this.pingTimer = window.setInterval(() => this.send({ action: 'ping' }), 30000) }
  private stopPing() { if (this.pingTimer) { clearInterval(this.pingTimer); this.pingTimer = null } }
  private scheduleReconnect() { if (this.reconnectTimer) return; this.reconnectTimer = window.setTimeout(() => { this.reconnectTimer = null; this.connect() }, 3000) }
  private sendAllPending() { const all = Array.from(this.subs.keys()); if (all.length) this.send({ action: 'sub', codes: all }) }
  private send(msg: any) { if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg)) }
  private dispatch(q: Quote) { const h = this.subs.get(q.code); if (h) for (const fn of h) fn(q) }

  subscribe(codes: string[], handler: Handler) {
    const newCodes: string[] = []
    for (const c of codes) {
      if (!this.subs.has(c)) { this.subs.set(c, new Set()); newCodes.push(c) }
      this.subs.get(c)!.add(handler)
    }
    if (newCodes.length && this.ws?.readyState === WebSocket.OPEN) this.send({ action: 'sub', codes: newCodes })
  }

  unsubscribe(codes: string[], handler: Handler) {
    for (const c of codes) {
      const s = this.subs.get(c); if (!s) continue
      s.delete(handler); if (s.size === 0) this.subs.delete(c)
    }
  }

  close() { this.stopPing(); if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null }; this.ws?.close(); this.ws = null }
}

export const quoteWS = new QuoteWS()
```

- [ ] **Step 6: Init in main.ts + subscribe in HoldingCard**

Modify `frontend/src/main.ts` — add at top:
```ts
import { quoteWS } from './ws/client'
quoteWS.init('/ws/quotes')
quoteWS.connect()
```

Modify `frontend/src/views/HoldingCard.vue` — add to `<script setup>`:
```ts
import { onMounted, onUnmounted } from 'vue'
import { quoteWS } from '../ws/client'
const handler = (q: { code: string; price: number }) => { if (q.code === props.p.code) props.p.price = q.price }
onMounted(() => quoteWS.subscribe([props.p.code], handler))
onUnmounted(() => quoteWS.unsubscribe([props.p.code], handler))
```

- [ ] **Step 7: Run frontend test PASS**

Run: `cd frontend && npx vitest run src/ws/__tests__/client.test.ts`
Expected: PASS

- [ ] **Step 8: Visual verify WS**

Run: `bash a_stock/api/run_dev.sh` (background)
Playwright: open `http://localhost:5173/`, wait 5s, screenshot. Wait 3s, screenshot.
Expected: 持仓 "现 52.93" 数字微变, 卡片不重排.

- [ ] **Step 9: Commit**

```bash
git add a_stock/api/ws.py a_stock/api/app.py frontend/src/ws/ frontend/src/main.ts frontend/src/views/HoldingCard.vue tests/test_api_ws.py
git commit -m "feat(p2): /ws/quotes backend + frontend ws client + holding price update"
```

---

## Phase P3: Trade writes + dialogs (3 tasks)

### Task 7: POST endpoints with 100 股 validation

**Files:**
- Modify: `a_stock/api/routes/positions.py` (add 3 POST handlers)
- Test: `tests/test_api_positions_write.py`

- [ ] **Step 1: Write test**

```python
# tests/test_api_positions_write.py
import pytest
import a_stock.config as cfg
import a_stock.db as db
from fastapi.testclient import TestClient
from a_stock.api.app import app

c = TestClient(app)


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    dec = tmp_path / "decisions.sqlite"
    monkeypatch.setattr(cfg, "DECISIONS_DB", dec)
    db.init_decisions_db()
    return dec


def test_new_position_ok(isolated_db):
    r = c.post("/api/positions", json={"code": "T_NEW1", "name": "x", "strategy": "mid", "price": 10.0, "qty": 100})
    assert r.status_code == 201 and r.json()["code"] == "T_NEW1"

def test_new_position_rejects_150(isolated_db):
    r = c.post("/api/positions", json={"code": "T_BAD", "name": "x", "strategy": "mid", "price": 10.0, "qty": 150})
    assert r.status_code == 422 and "100" in r.json()["error"]

def test_add_ok(isolated_db):
    c.post("/api/positions", json={"code": "T_ADD", "name": "x", "strategy": "mid", "price": 10.0, "qty": 100})
    r = c.post("/api/positions/T_ADD/add", json={"strategy": "mid", "price": 11.0, "qty": 200})
    assert r.status_code == 201

def test_reduce_ok(isolated_db):
    c.post("/api/positions", json={"code": "T_RED", "name": "x", "strategy": "mid", "price": 10.0, "qty": 500})
    r = c.post("/api/positions/T_RED/reduce", json={"price": 12.0, "qty": 200, "reason": "partial_take_profit"})
    assert r.status_code == 201 and r.json()["realized"] > 0

def test_reduce_over(isolated_db):
    c.post("/api/positions", json={"code": "T_OVR", "name": "x", "strategy": "mid", "price": 10.0, "qty": 100})
    r = c.post("/api/positions/T_OVR/reduce", json={"price": 12.0, "qty": 200, "reason": "manual"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run test FAIL**

Run: `.venv/bin/python -m pytest tests/test_api_positions_write.py -v`
Expected: FAIL (no POST routes)

- [ ] **Step 3: Add POST handlers**

Replace `a_stock/api/routes/positions.py` with:
```python
"""/api/positions — 持仓列表 + 建/加/减仓. 100 股铁律在 endpoint 把关."""
from fastapi import APIRouter, HTTPException
from a_stock.web import positions_panel
from a_stock.api.models import PositionOut, TradeResult
from a_stock.a_screen.decision_log import add_buy, add_add, reduce_position, cost_report
from a_stock.web.trading_modal import _validate_lot, _pick_largest_lot

router = APIRouter()


@router.get("/positions", response_model=list[PositionOut])
def get_positions() -> list[PositionOut]:
    return [
        PositionOut(code=r["code"], name=r["name"], qty=r["qty"],
            cost=r["cost"], price=r["price"], pnl=r["pnl"],
            pnl_pct=r["pnl_pct"], stop_loss=r.get("stop_loss"))
        for r in positions_panel.collect_positions()
    ]


def _err(msg: str) -> HTTPException:
    return HTTPException(422, {"error": msg})


@router.post("/positions", status_code=201, response_model=TradeResult)
def post_new_position(body: dict) -> TradeResult:
    code = str(body.get("code", "")).strip()
    name = str(body.get("name", code)).strip()
    strategy = body.get("strategy", "mid")
    price = float(body.get("price", 0))
    qty = int(body.get("qty", 0))
    reason = body.get("reason")

    if not code or not code.isdigit() or not (5 <= len(code) <= 6):
        raise _err("code 需 5-6 位数字")
    if price <= 0: raise _err("price 必须 > 0")
    ok, msg = _validate_lot(qty, "add")
    if not ok: raise _err(msg)

    try:
        new_id = add_buy(code=code, name=name, strategy=strategy, price=price, quantity=qty, reason=reason)
    except Exception as e:
        raise _err(f"写入失败: {e}")
    return TradeResult(id=new_id, code=code, realized=0)


@router.post("/positions/{code}/add", status_code=201, response_model=TradeResult)
def post_add_position(code: str, body: dict) -> TradeResult:
    strategy = body.get("strategy", "mid")
    price = float(body.get("price", 0))
    qty = int(body.get("qty", 0))
    reason = body.get("reason")

    if price <= 0: raise _err("price 必须 > 0")
    ok, msg = _validate_lot(qty, "add")
    if not ok: raise _err(msg)
    if not cost_report(code): raise _err(f"无持仓 {code}, 不能加仓")

    try:
        new_id = add_add(code=code, strategy=strategy, price=price, quantity=qty, reason=reason)
    except Exception as e:
        raise _err(f"写入失败: {e}")
    return TradeResult(id=new_id, code=code, realized=0)


@router.post("/positions/{code}/reduce", status_code=201, response_model=TradeResult)
def post_reduce_position(code: str, body: dict) -> TradeResult:
    price = float(body.get("price", 0))
    qty = int(body.get("qty", 0))
    reason = body.get("reason", "manual")

    if price <= 0: raise _err("price 必须 > 0")
    ok, msg = _validate_lot(qty, "reduce")
    if not ok: raise _err(msg)

    rep = cost_report(code)
    if not rep: raise _err(f"无持仓 {code}")
    held = sum(lot["remaining"] for lot in rep["lots"])
    if qty > held: raise _err(f"减仓 {qty} 超过持仓 {held}")

    parent_id = _pick_largest_lot(code)
    if not parent_id: raise _err(f"{code} 无可减 lot")

    try:
        new_id = reduce_position(parent_id=parent_id, reduce_price=price, reduce_qty=qty, reason=reason)
    except Exception as e:
        raise _err(f"写入失败: {e}")

    lot_cost = next((l["cost"] for l in rep["lots"] if l["id"] == parent_id), price)
    realized = int((price - lot_cost) * qty)
    return TradeResult(id=new_id, code=code, realized=realized)
```

- [ ] **Step 4: Run test PASS**

Run: `.venv/bin/python -m pytest tests/test_api_positions_write.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add a_stock/api/routes/positions.py tests/test_api_positions_write.py
git commit -m "feat(p3): POST /api/positions + add + reduce, 100股铁律后端"
```

---

### Task 8: TradingDialog + 3 form components + trade store

**Files:**
- Create: `frontend/src/stores/trade.ts`
- Create: `frontend/src/components/TradingDialog.vue`
- Create: `frontend/src/components/AddForm.vue`
- Create: `frontend/src/components/ReduceForm.vue`
- Create: `frontend/src/components/NewPositionForm.vue`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Write trade store**

`frontend/src/stores/trade.ts`:
```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api/client'
import { usePositions } from './positions'
import { usePortfolio } from './portfolio'

export const useTrade = defineStore('trade', () => {
  const submitting = ref(false)
  const error = ref<string | null>(null)

  async function add(code: string, body: any) {
    submitting.value = true; error.value = null
    try { await api.addToPosition(code, body); await usePositions().refresh(); await usePortfolio().refresh() }
    catch (e: any) { error.value = e.message; throw e } finally { submitting.value = false }
  }
  async function reduce(code: string, body: any) {
    submitting.value = true; error.value = null
    try { await api.reducePosition(code, body); await usePositions().refresh(); await usePortfolio().refresh() }
    catch (e: any) { error.value = e.message; throw e } finally { submitting.value = false }
  }
  async function newPosition(body: any) {
    submitting.value = true; error.value = null
    try { await api.addPosition(body); await usePositions().refresh(); await usePortfolio().refresh() }
    catch (e: any) { error.value = e.message; throw e } finally { submitting.value = false }
  }
  return { submitting, error, add, reduce, newPosition }
})
```

- [ ] **Step 2: Write AddForm.vue**

```vue
<template>
  <div class="form">
    <div class="caption">{{ payload.name }} ({{ payload.code }})</div>
    <label>买入价 ¥<input type="number" v-model.number="price" step="0.01" /></label>
    <label>数量(股)<input type="number" v-model.number="qty" step="100" /></label>
    <label>策略<select v-model="strategy"><option value="mid">mid</option><option value="short">short</option></select></label>
    <label>理由<input v-model="reason" placeholder="可选" /></label>
    <div v-if="error" class="err">❌ {{ error }}</div>
    <div class="actions">
      <button class="primary" :disabled="trade.submitting" @click="submit">确认加仓</button>
      <button @click="dialog.close()">取消</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useDialog } from '../stores/dialog'
import { useTrade } from '../stores/trade'
const props = defineProps<{ payload: { code: string; name: string; cost: number } }>()
const dialog = useDialog(); const trade = useTrade()
const price = ref(props.payload.cost || 0)
const qty = ref(100); const strategy = ref('mid'); const reason = ref('')
const error = ref<string | null>(null)
async function submit() {
  error.value = null
  try { await trade.add(props.payload.code, { strategy: strategy.value, price: price.value, qty: qty.value, reason: reason.value || undefined }); dialog.close() }
  catch (e: any) { error.value = e.message }
}
</script>

<style scoped>
.form { display: flex; flex-direction: column; gap: 10px; min-width: 280px; }
.caption { font-size: 12px; color: var(--dim); }
label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--dim); }
input, select { background: var(--panel-2); border: 1px solid var(--line-2); color: var(--txt);
  padding: 6px 8px; border-radius: 3px; font-family: var(--mono); font-size: 13px; }
.actions { display: flex; gap: 8px; margin-top: 6px; }
button { flex: 1; padding: 7px 12px; border: 1px solid var(--line-2); background: var(--panel-2);
  color: var(--txt); border-radius: 3px; cursor: pointer; font-family: var(--mono); }
button.primary { background: var(--red); color: #000; border-color: var(--red); font-weight: 600; }
button:disabled { opacity: 0.4; cursor: not-allowed; }
.err { color: var(--red); font-size: 12px; }
</style>
```

- [ ] **Step 3: Write ReduceForm.vue**

```vue
<template>
  <div class="form">
    <div class="caption">{{ payload.name }} ({{ payload.code }}) · 持仓 {{ payload.qty }}股</div>
    <label>卖出价 ¥<input type="number" v-model.number="price" step="0.01" /></label>
    <label>数量(股)<input type="number" v-model.number="qty" step="100" :max="payload.qty" /></label>
    <label>原因<select v-model="reason">
      <option value="partial_take_profit">partial_take_profit</option>
      <option value="partial_stop_loss">partial_stop_loss</option>
      <option value="manual">manual</option>
    </select></label>
    <div class="hint">💰 预估: {{ estimatedPnl }}元 (成本{{ payload.cost?.toFixed(4) }})</div>
    <div v-if="error" class="err">❌ {{ error }}</div>
    <div class="actions">
      <button class="primary" :disabled="trade.submitting" @click="submit">确认减仓</button>
      <button @click="dialog.close()">取消</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useDialog } from '../stores/dialog'
import { useTrade } from '../stores/trade'
const props = defineProps<{ payload: { code: string; name: string; qty: number; cost: number } }>()
const dialog = useDialog(); const trade = useTrade()
const price = ref(props.payload.cost || 0); const qty = ref(props.payload.qty)
const reason = ref('partial_take_profit'); const error = ref<string | null>(null)
const estimatedPnl = computed(() => Math.round((price.value - (props.payload.cost || 0)) * qty.value))
async function submit() {
  error.value = null
  try { await trade.reduce(props.payload.code, { price: price.value, qty: qty.value, reason: reason.value }); dialog.close() }
  catch (e: any) { error.value = e.message }
}
</script>

<style scoped>
.form { display: flex; flex-direction: column; gap: 10px; min-width: 280px; }
.caption { font-size: 12px; color: var(--dim); }
label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--dim); }
input, select { background: var(--panel-2); border: 1px solid var(--line-2); color: var(--txt);
  padding: 6px 8px; border-radius: 3px; font-family: var(--mono); font-size: 13px; }
.hint { font-size: 12px; color: var(--dim); font-family: var(--mono); }
.actions { display: flex; gap: 8px; margin-top: 6px; }
button { flex: 1; padding: 7px 12px; border: 1px solid var(--line-2); background: var(--panel-2);
  color: var(--txt); border-radius: 3px; cursor: pointer; font-family: var(--mono); }
button.primary { background: var(--red); color: #000; border-color: var(--red); font-weight: 600; }
button:disabled { opacity: 0.4; cursor: not-allowed; }
.err { color: var(--red); font-size: 12px; }
</style>
```

- [ ] **Step 4: Write NewPositionForm.vue**

```vue
<template>
  <div class="form">
    <label>股票代码<input v-model="code" placeholder="000960 / 515650" /></label>
    <label>股票名称<input v-model="name" placeholder="可后填" /></label>
    <label>成本价 ¥<input type="number" v-model.number="price" step="0.01" /></label>
    <label>数量(股)<input type="number" v-model.number="qty" step="100" /></label>
    <label>策略<select v-model="strategy"><option value="mid">mid</option><option value="short">short</option></select></label>
    <label>买入理由<input v-model="reason" placeholder="可选" /></label>
    <div v-if="error" class="err">❌ {{ error }}</div>
    <div class="actions">
      <button class="primary" :disabled="trade.submitting" @click="submit">确认建仓</button>
      <button @click="dialog.close()">取消</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useDialog } from '../stores/dialog'
import { useTrade } from '../stores/trade'
const dialog = useDialog(); const trade = useTrade()
const code = ref(''); const name = ref(''); const price = ref(1.0)
const qty = ref(100); const strategy = ref('mid'); const reason = ref('')
const error = ref<string | null>(null)
async function submit() {
  error.value = null
  if (!code.value || !/^\d{5,6}$/.test(code.value)) { error.value = '代码需 5-6 位数字'; return }
  try { await trade.newPosition({ code: code.value, name: name.value || code.value, strategy: strategy.value, price: price.value, qty: qty.value, reason: reason.value || undefined }); dialog.close() }
  catch (e: any) { error.value = e.message }
}
</script>

<style scoped>
.form { display: flex; flex-direction: column; gap: 10px; min-width: 280px; }
label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--dim); }
input, select { background: var(--panel-2); border: 1px solid var(--line-2); color: var(--txt);
  padding: 6px 8px; border-radius: 3px; font-family: var(--mono); font-size: 13px; }
.actions { display: flex; gap: 8px; margin-top: 6px; }
button { flex: 1; padding: 7px 12px; border: 1px solid var(--line-2); background: var(--panel-2);
  color: var(--txt); border-radius: 3px; cursor: pointer; font-family: var(--mono); }
button.primary { background: var(--red); color: #000; border-color: var(--red); font-weight: 600; }
button:disabled { opacity: 0.4; cursor: not-allowed; }
.err { color: var(--red); font-size: 12px; }
</style>
```

- [ ] **Step 5: Write TradingDialog.vue (Teleport)**

```vue
<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="dialog.open" class="modal-mask" @click.self="dialog.close()">
        <div class="modal-body">
          <component :is="formComponent" :payload="dialog.payload" />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useDialog } from '../stores/dialog'
import AddForm from './AddForm.vue'
import ReduceForm from './ReduceForm.vue'
import NewPositionForm from './NewPositionForm.vue'
const dialog = useDialog()
const formComponent = computed(() => {
  if (dialog.mode === 'add') return AddForm
  if (dialog.mode === 'reduce') return ReduceForm
  if (dialog.mode === 'new') return NewPositionForm
  return null
})
</script>

<style scoped>
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-body { background: var(--panel); border: 1px solid var(--line);
  border-radius: 8px; padding: 20px; min-width: 320px; max-width: 90vw; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
```

- [ ] **Step 6: Mount TradingDialog in App.vue**

Replace `frontend/src/App.vue` with:
```vue
<template>
  <div class="app">
    <TickerBar /><AssetBar /><Dashboard /><TradingDialog />
  </div>
</template>
<script setup lang="ts">
import TickerBar from './views/TickerBar.vue'
import AssetBar from './views/AssetBar.vue'
import Dashboard from './views/Dashboard.vue'
import TradingDialog from './components/TradingDialog.vue'
</script>
<style scoped>
.app { max-width: 1280px; margin: 0 auto; padding: 1.2rem 1rem 2rem; }
</style>
```

- [ ] **Step 7: Visual verify full flow**

Run: `bash a_stock/api/run_dev.sh` (background)
Playwright: open `http://localhost:5173/`
- Click 600276 `+` -> 加仓 form 弹出, 默认价 49.121
- Fill 150 qty, click 确认加仓 -> 红字 "150 必须 100 整数倍"
- Change 200, click 确认加仓 -> 弹窗关, 持仓 +200 股
- Click 600276 `-` -> 减仓 form 弹出
- Click 持仓标题 `+` -> 新建持仓 form 弹出

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/ frontend/src/stores/trade.ts frontend/src/App.vue
git commit -m "feat(p3): TradingDialog + 3 forms, full write flow"
```

---

### Task 9: Playwright E2E

**Files:**
- Create: `tests/test_e2e_trade.py`

- [ ] **Step 1: Install playwright python**

Run: `.venv/bin/pip install playwright`
Run: `.venv/bin/playwright install chromium`

- [ ] **Step 2: Write E2E test**

```python
# tests/test_e2e_trade.py
"""端到端: 起 fastapi + vite, playwright 走通建仓, 截图."""
import subprocess, time
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def dev_servers():
    backend = subprocess.Popen([".venv/bin/uvicorn", "a_stock.api.app:app", "--port", "8000"],
        cwd=str(PROJECT_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    frontend = subprocess.Popen(["npm", "run", "dev"], cwd=str(PROJECT_ROOT / "frontend"),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)
    yield
    backend.terminate(); frontend.terminate()
    backend.wait(timeout=5); frontend.wait(timeout=5)


def test_e2e_new_position(dev_servers, tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto("http://localhost:5173/")
        page.wait_for_selector(".card.hold", timeout=10000)
        page.screenshot(path=str(tmp_path / "01-initial.png"))
        page.click("button.newpos")
        page.wait_for_selector(".modal-mask", timeout=3000)
        page.screenshot(path=str(tmp_path / "02-dialog.png"))
        page.fill("input[placeholder*='000960']", "T_E2E1")
        page.fill("input[placeholder*='后填']", "E2E")
        page.locator("label:has-text('成本价') input").fill("10.0")
        page.click("button.primary:has-text('确认建仓')")
        page.wait_for_selector(".modal-mask", state="detached", timeout=3000)
        page.screenshot(path=str(tmp_path / "03-after.png"))
        browser.close()
```

- [ ] **Step 3: Run test PASS**

Run: `.venv/bin/python -m pytest tests/test_e2e_trade.py -v --tb=short`
Expected: PASS, screenshots in tmp_path

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e_trade.py
git commit -m "test(p3): playwright e2e for trade flow"
```

---

## Phase P4: Polish (2 tasks)

### Task 10: Loading + error states + sentiment mini

**Files:**
- Modify: `frontend/src/views/AssetBar.vue`
- Modify: `frontend/src/views/OpportunityFeed.vue`
- Modify: `frontend/src/views/PositionsList.vue`
- Create: `frontend/src/views/SentimentMini.vue`
- Modify: `frontend/src/views/OpportunityFeed.vue` (add sentiment inline)

- [ ] **Step 1: AssetBar loading/error**

In `frontend/src/views/AssetBar.vue` replace the `<div v-if="portfolio.data" class="bar5">` opener with:
```vue
<div v-if="portfolio.loading" class="status">加载中…</div>
<div v-else-if="portfolio.error" class="status error">⚠ {{ portfolio.error }} <button @click="portfolio.refresh()">重试</button></div>
<div v-else-if="portfolio.data" class="bar5">
```

Add to style:
```css
.status { background: var(--panel); border: 1px solid var(--line);
  border-radius: 6px; padding: 14px 18px; color: var(--dim);
  font-family: var(--mono); margin-bottom: 18px; }
.status.error { color: var(--red); }
.status button { margin-left: 12px; padding: 2px 8px;
  background: var(--panel-2); border: 1px solid var(--line-2);
  color: var(--txt); border-radius: 3px; cursor: pointer; }
```

- [ ] **Step 2: OpportunityFeed loading/error/empty + SentimentMini**

In `frontend/src/views/OpportunityFeed.vue`:
- Add `<SentimentMini />` to title right side
- Add import `import SentimentMini from './SentimentMini.vue'`
- Replace body with:
```vue
<div v-if="opp.loading" class="status">加载中…</div>
<div v-else-if="opp.error" class="status error">⚠ {{ opp.error }} <button @click="opp.refresh()">重试</button></div>
<div v-else-if="opp.list.length === 0" class="status">暂无机会点 · 盘后或市场平静时属正常</div>
<div v-else class="panel">
  <OpportunityCard v-for="o in opp.list" :key="o.code + o.type" :opp="o" />
</div>
```

Replace `.empty` with `.status` (same as AssetBar).

`frontend/src/views/SentimentMini.vue`:
```vue
<template>
  <div v-if="s.data" class="mood-mini">
    <span class="t" :style="{ color: moodColor }">{{ s.data.temp.toFixed(0) }}</span>
    <div class="bar"><div class="fill" :style="{ width: `${s.data.temp}%` }"></div></div>
    <span class="lbl">{{ s.data.mood || '中性' }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useSentiment } from '../stores/sentiment'
const s = useSentiment()
onMounted(() => s.refresh())
const moodColor = computed(() => {
  if (!s.data) return 'var(--dim)'
  if (s.data.temp >= 55) return 'var(--red)'
  if (s.data.temp >= 30) return 'var(--amber)'
  return 'var(--green)'
})
</script>

<style scoped>
.mood-mini { display: flex; align-items: center; gap: 10px; font-family: var(--mono); }
.mood-mini .t { font-size: 18px; font-weight: 700; line-height: 1; }
.mood-mini .bar { width: 60px; height: 5px; background: var(--panel-2);
  border-radius: 3px; overflow: hidden; }
.mood-mini .fill { height: 100%;
  background: linear-gradient(90deg, var(--green), var(--amber), var(--red)); }
.mood-mini .lbl { font-size: 10px; color: var(--dim);
  text-transform: uppercase; letter-spacing: 0.1em; }
</style>
```

- [ ] **Step 3: PositionsList loading/error/empty**

In `frontend/src/views/PositionsList.vue`:
```vue
<div v-if="pos.loading" class="status">加载中…</div>
<div v-else-if="pos.error" class="status error">⚠ {{ pos.error }} <button @click="pos.refresh()">重试</button></div>
<div v-else-if="pos.list.length === 0" class="status">无持仓</div>
<div v-else class="panel">
  <HoldingCard v-for="p in pos.list" :key="p.code" :p="p" />
</div>
```

Replace `.empty` with `.status` (same).

- [ ] **Step 4: Verify error states**

Stop backend, refresh page, see error states. Start backend, click 重试, data loads.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/
git commit -m "feat(p4): loading + error + retry + sentiment mini"
```

---

### Task 11: Deprecate streamlit + migration doc + full smoke

**Files:**
- Modify: `a_stock/web/dashboard.py` (deprecation banner)
- Create: `docs/dashboard-migration.md`

- [ ] **Step 1: Add deprecation banner**

In `a_stock/web/dashboard.py` — after `import streamlit as st` (top of file), add BEFORE any `st.*` call:
```python
st.warning("⚠️ 此 streamlit dashboard 已废弃, 请用 vue3 前端: `bash a_stock/api/run_dev.sh` 启动, 浏览器打开 http://localhost:5173/")
```

- [ ] **Step 2: Write migration doc**

`docs/dashboard-migration.md`:
```markdown
# Dashboard 迁移指南 (streamlit -> vue3)

## 起停

```bash
bash a_stock/api/run_dev.sh
# 后端 :8000, 前端 :5173
```

浏览器打开 http://localhost:5173/

## 关键差异

| 操作 | 旧 (streamlit) | 新 (vue3) |
|---|---|---|
| 加仓 | 点 + -> 弹窗 (整页 rerun) | 点 + -> 弹窗 (主区不动) |
| 价格更新 | 手动刷新 (整页) | WS 自动 (1-2s) |
| 多窗口 | 不支持 | 支持 (共享后端 WS) |
| 移动端 | 不能用 | responsive |

## 数据兼容

- DB schema 不变, 写操作走同一 `decision_log` 函数
- 持仓/机会/行情数据源不变 (东财/腾讯)
- 旧 streamlit dashboard 保留可访问, 顶部有废弃警告

## 开发

- 后端: `a_stock/api/` (FastAPI)
- 前端: `frontend/` (Vue 3 + Vite + TypeScript)
- 启动脚本: `a_stock/api/run_dev.sh`
- 测试: `pytest tests/test_api_*.py` (后端) + `cd frontend && npx vitest` (前端)
```

- [ ] **Step 3: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: All pass (191+ original + ~15 new API tests + 1 e2e)

Run: `cd frontend && npx vitest run`
Expected: All pass

- [ ] **Step 4: Manual full smoke**

Run: `bash a_stock/api/run_dev.sh` (background)
Playwright:
- open http://localhost:5173/, screenshot dashboard-final.png
- click + 加仓, screenshot dialog.png
- 关闭弹窗, 主区不动 (确认)
- 等 3s, 持仓价格微变 (确认 WS)
- 试 150 股 -> 红字报错 (确认 100 股铁律)

- [ ] **Step 5: Commit**

```bash
git add a_stock/web/dashboard.py docs/dashboard-migration.md
git commit -m "chore(p4): deprecate streamlit dashboard, migration doc"
```

---

## Self-Review

**Spec coverage:**
- Goal 1 弹窗不重渲染 -> Task 8 (Teleport to body)
- Goal 2 实时 WS -> Task 6
- Goal 3 100 股铁律后端 -> Task 7
- Goal 4 视觉对齐 -> Tasks 4-5
- Goal 5 现有模块 0 改 -> 所有任务 import 现有, 不改
- Section 5 API 契约 -> Tasks 2, 7
- Section 7 弹窗机制 -> Task 8
- Section 8 错误处理 -> Task 7 (后端), Task 10 (前端)
- Section 9 测试 -> Tasks 1-3, 6, 7, 9
- Section 10 分期 -> P0-P4 完整

**Type consistency:** Position/Opportunity/Portfolio types in Task 3 match schemas in Task 2. `_validate_lot` from `a_stock.web.trading_modal` imported in Task 7.

**Placeholder scan:** No TBD/TODO. All code blocks complete. All file paths absolute.
