# A股辅助决策系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 A股辅助决策系统,产出 Screener v2 + Research Brief + 复盘日志三个核心模块,支持短线+中线双轨策略,自动化产出日报,用户 <30 min/day 完成决策与记录。

**Architecture:** 三层架构 —— 入口 CLI(screener/brief/log/stats)调用业务层(py/a_screen/* 纯计算),业务层调用数据层(py/a_stock_data/ vendored helpers + db.py + ohlcv.py)。两个 SQLite 分别存决策(decisions.sqlite)与扫描事实(screener.sqlite)。AI 分析由 Claude Code 在对话中读取 brief 快照完成,结果写回 `ai_analysis` 字段,不做 cron LLM 调用。

**Tech Stack:** Python 3.10+, requests, pandas, pyarrow(parquet), sqlite3(stdlib), pytest。**不引入** akshare/mootdx/iwencai。

**Spec 文档:** `docs/superpowers/specs/2026-06-26-a-stock-decision-system-design.md`
**Source of vendors:** `a-stock-data/SKILL.md`(已 clone)

## Global Constraints(所有 task 隐式遵循)

- `EM_MIN_INTERVAL` 默认 1.0s,批量场景 `config.py` 调到 1.5-2s
- `em_get` 必须有 URL 缓存(`data/.cache/em/`,TTL 15 分钟)
- `tencent_quote` 必须有 retry(3 次 + 1s 间隔)
- mootdx **不 vendor**(海外 TCP 7709 不通)
- akshare **不引入**
- 时间全用 TEXT ISO8601(Asia/Shanghai)
- 文件名 snake_case,类名 PascalCase,常量 UPPER_SNAKE
- em_get 失败重试 3 次后跳过该股
- 双 SQLite 严格分离(decisions vs screener)
- commit message 用 conventional commits

---

## File Structure(实施前必读)

```
py/
├── a_stock_data/                   # Layer 1a: vendored helpers
│   ├── __init__.py                 # 重导出所有公共函数
│   ├── _common.py                  # em_get, EM_MIN_INTERVAL, EM_SESSION, UA, get_prefix, normalize_code, em_cache
│   ├── tencent.py                  # tencent_quote(带 retry)
│   ├── eastmoney.py                # reports, industry_reports, concept_blocks, fund_flow_minute, stock_fund_flow_120d, daily_dragon_tiger
│   ├── ths.py                      # ths_hot_reason, ths_eps_forecast, hsgt_realtime
│   ├── sectors.py                  # industry_comparison
│   ├── news.py                     # eastmoney_stock_news, eastmoney_global_news
│   ├── pdf.py                      # download_pdf
│   ├── financials.py               # sina_financial_report
│   └── filings.py                  # cninfo_announcements
│
├── a_screen/                       # Layer 2: 业务编排(纯计算,无 HTTP)
│   ├── __init__.py
│   ├── sector_scan.py              # 行业/概念/热点/龙虎榜聚合
│   ├── candidate_filter.py         # 短线/中线初筛 + 评分
│   ├── brief_builder.py            # 单股 brief 数据组装
│   ├── snapshot.py                 # brief 快照读写
│   └── decision_log.py             # decisions.sqlite CRUD
│
├── screener.py                     # Layer 3 入口 1: 每日扫描
├── brief.py                        # Layer 3 入口 2: 单股 brief
├── log.py                          # Layer 3 入口 3: 复盘记录
├── stats.py                        # Layer 3 入口 4: 复盘统计
│
├── ohlcv.py                        # Layer 1c: parquet 读
├── db.py                           # Layer 1b: SQLite 封装 + schema 初始化
├── config.py                       # 路径/限流/时区/scoring weights
│
├── fetch-ashare-list.py            # (保留,不动)
├── fetch-trending.py               # (保留,不动)
├── download-ohlcv.py               # (保留,不动)
├── backtest-volume.py              # (保留,不动)
└── closeout-screener.py            # (顶部加 DEPRECATED 注释)

data/
├── ohlcv/*.parquet                 # 现有 5197 只
├── a_share_list.json               # 现有 5529
├── trending/                       # 现有
├── screen/                         # 新建
│   ├── daily/YYYY-MM-DD/
│   │   ├── sectors.json
│   │   ├── candidates_short.json
│   │   ├── candidates_mid.json
│   │   └── report.html
│   └── briefs/<code>/
│       ├── YYYY-MM-DD.json
│       └── YYYY-MM-DD.md
├── closeout/*.json                 # 冻结,gitignore
├── decisions.sqlite                # 复盘
├── screener.sqlite                 # 扫描
├── backup/                         # 周 backup
├── holidays.json                   # A股节假日列表
└── .cache/em/                      # em_get URL 缓存

tests/
├── test_config.py
├── test_db.py
├── test_ohlcv.py
├── test_a_stock_data_common.py
├── test_tencent_retry.py
├── test_sector_scan.py
├── test_candidate_filter.py
├── test_scoring.py
├── test_brief_builder.py
├── test_snapshot.py
├── test_decision_log.py
├── test_stats.py
├── integration/
│   ├── test_em_get_throttle.py
│   ├── test_a_stock_data_smoke.py
│   └── test_screener_e2e.py
└── smoke/
    └── run_daily.sh
```

---

# Phase 1: 数据底座(2-3 天)

> 目标:vendor 完所有 a-stock-data 端点,实现 `db.py` + `ohlcv.py` + `config.py`,单元测试通过。

## Task 1.1:项目配置 + 路径

**Files:**
- Create: `py/config.py`
- Modify: `.gitignore`
- Create: `tests/test_config.py`

**Interfaces:**
- Produces: `py.config.ROOT`, `DATA_DIR`, `SCREEN_DIR`, `BRIEFS_DIR`, `EM_CACHE_DIR`, `EM_MIN_INTERVAL`(默认 1.0), `TZ='Asia/Shanghai'`, `HOLIDAYS_FILE`, `SCORING`(dict)

- [ ] **Step 1:写测试**

```python
# tests/test_config.py
from pathlib import Path
import py.config as cfg

def test_paths_exist():
    assert cfg.ROOT.exists()
    assert isinstance(cfg.DATA_DIR, Path)
    assert isinstance(cfg.SCREEN_DIR, Path)
    assert isinstance(cfg.BRIEFS_DIR, Path)
    assert isinstance(cfg.EM_CACHE_DIR, Path)

def test_em_interval_default():
    assert cfg.EM_MIN_INTERVAL == 1.0
    assert isinstance(cfg.TZ, str)

def test_scoring_has_both_strategies():
    assert "short" in cfg.SCORING
    assert "mid" in cfg.SCORING
    assert sum(cfg.SCORING["short"].values()) == 100
    assert sum(cfg.SCORING["mid"].values()) == 100
```

- [ ] **Step 2:跑测试,确认 fail**

Run: `cd /Users/maerun/Documents/Projects/make-money && python -m pytest tests/test_config.py -v`
Expected: `ModuleNotFoundError: No module named 'py.config'`

- [ ] **Step 3:写 `py/config.py`**

```python
"""项目配置:路径、限流、时区、scoring weights。"""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SCREEN_DIR = DATA_DIR / "screen"
DAILY_DIR = SCREEN_DIR / "daily"
BRIEFS_DIR = SCREEN_DIR / "briefs"
OHLCV_DIR = DATA_DIR / "ohlcv"
LIST_FILE = DATA_DIR / "a_share_list.json"
EM_CACHE_DIR = DATA_DIR / ".cache" / "em"
BACKUP_DIR = DATA_DIR / "backup"
HOLIDAYS_FILE = DATA_DIR / "holidays.json"

DECISIONS_DB = DATA_DIR / "decisions.sqlite"
SCREENER_DB = DATA_DIR / "screener.sqlite"

# 时区
TZ = "Asia/Shanghai"

# 东财限流(秒)
EM_MIN_INTERVAL = float(os.environ.get("EM_MIN_INTERVAL", "1.0"))

# Scoring weights(双策略,每策略总分 100)
SCORING = {
    "short": {
        "net_flow_rank":     30,
        "change_pct_band":   20,
        "sector_alignment":  20,
        "report_count_7d":   15,
        "hot_reason_hit":    15,
    },
    "mid": {
        "valuation":         25,
        "fund_flow_20d":     20,
        "report_coverage":   20,
        "theme_catalyst":    20,
        "tech_position":     15,
    },
}

# 创建目录
for d in (DAILY_DIR, BRIEFS_DIR, EM_CACHE_DIR, BACKUP_DIR):
    d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4:更新 `.gitignore`** — 在文件末尾追加:

```
data/screen/daily/
data/screen/briefs/
data/decisions.sqlite
data/screener.sqlite
data/backup/
data/.cache/
data/holidays.json
```

- [ ] **Step 5:跑测试,确认 pass**

Run: `cd /Users/maerun/Documents/Projects/make-money && python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 6:commit**

```bash
git add py/config.py tests/test_config.py .gitignore
git commit -m "feat(config): add py/config.py with paths, throttle, scoring"
```

## Task 1.2:Vendor `_common.py`(em_get + helpers)

**Files:**
- Create: `py/a_stock_data/__init__.py`
- Create: `py/a_stock_data/_common.py`
- Create: `tests/test_a_stock_data_common.py`

**Interfaces:**
- Produces: `py.a_stock_data._common.UA`, `EM_SESSION`, `EM_MIN_INTERVAL`(override from config), `_em_last_call`, `em_get(url, params, headers, timeout)`, `em_cache_get(key)`, `em_cache_put(key, data)`, `get_prefix(code)`, `normalize_code(code)`, `retry(fn, max_attempts=3, base_delay=1.0)`

- [ ] **Step 1:读 SKILL.md 125-130 行**(em_get 限流说明)和 **268-318 行**(em_get 实现)

- [ ] **Step 2:写测试**

```python
# tests/test_a_stock_data_common.py
import time
from py.a_stock_data._common import (
    em_get, get_prefix, normalize_code, em_cache_get, em_cache_put, retry
)

def test_get_prefix_sh():
    assert get_prefix("600519") == "sh"
    assert get_prefix("688017") == "sh"
    assert get_prefix("900901") == "sh"

def test_get_prefix_sz():
    assert get_prefix("000001") == "sz"
    assert get_prefix("300476") == "sz"

def test_get_prefix_bj():
    assert get_prefix("830001") == "bj"
    assert get_prefix("832000") == "bj"

def test_normalize_code():
    assert normalize_code("688017") == "688017"
    assert normalize_code("sh688017") == "688017"
    assert normalize_code("SH688017") == "688017"
    assert normalize_code("688017.SH") == "688017"
    assert normalize_code("000001.SZ") == "000001"

def test_em_cache_roundtrip():
    em_cache_put("test_key", {"foo": "bar"})
    assert em_cache_get("test_key") == {"foo": "bar"}

def test_retry_succeeds_on_second():
    calls = [0]
    def flaky():
        calls[0] += 1
        if calls[0] < 2:
            raise ConnectionError("fail")
        return "ok"
    assert retry(flaky) == "ok"
    assert calls[0] == 2

def test_retry_gives_up():
    calls = [0]
    def always_fail():
        calls[0] += 1
        raise ConnectionError("fail")
    try:
        retry(always_fail, max_attempts=3, base_delay=0.01)
    except ConnectionError:
        pass
    assert calls[0] == 3
```

- [ ] **Step 3:跑测试,确认 fail**

Run: `python -m pytest tests/test_a_stock_data_common.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 4:写 `py/a_stock_data/__init__.py`**(空包)

```python
"""a-stock-data vendored helpers。"""
__version__ = "1.0.0"
```

- [ ] **Step 5:写 `py/a_stock_data/_common.py`**

```python
"""共用 helper:em_get 防封、限流、缓存、ticker 归一化、retry。"""
import hashlib
import json
import random
import re
import time
from pathlib import Path
import requests
import py.config as cfg

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# ── em_get 限流(全局 session + 串行节流)──────────────────
EM_SESSION = requests.Session()
EM_SESSION.headers.update({"User-Agent": UA})

_em_last_call = [0.0]

def em_get(url: str, params: dict | None = None, headers: dict | None = None,
           timeout: int = 15, **kwargs):
    """东财统一请求入口:节流 + 复用 session + 默认 UA。"""
    wait = cfg.EM_MIN_INTERVAL - (time.time() - _em_last_call[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.5))
    try:
        return EM_SESSION.get(url, params=params, headers=headers,
                              timeout=timeout, **kwargs)
    finally:
        _em_last_call[0] = time.time()

# ── em URL 缓存(15 分钟 TTL)─────────────────────────────
_TTL_SECONDS = 15 * 60

def _cache_key(url: str, params: dict | None) -> str:
    raw = url + json.dumps(params or {}, sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()

def em_cache_get(key: str):
    """读缓存:返回 (timestamp, data) 或 None。"""
    path = cfg.EM_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    if time.time() - path.stat().st_mtime > _TTL_SECONDS:
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

def em_cache_put(key: str, data) -> None:
    path = cfg.EM_CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, default=str))

# ── Ticker 归一化────────────────────────────────────
def get_prefix(code: str) -> str:
    """6 位代码 → 市场前缀。"""
    code = normalize_code(code)
    if code.startswith(("6", "9")):
        return "sh"
    elif code.startswith("8"):
        return "bj"
    return "sz"

def normalize_code(code: str) -> str:
    """'sh688017' / '688017.SH' → '688017'。"""
    c = code.upper().strip()
    c = re.sub(r"^(SH|SZ|BJ)", "", c)
    c = re.sub(r"\.(SH|SZ|BJ)$", "", c)
    return c

# ── Retry helper(指数退避)────────────────────────────
def retry(fn, max_attempts: int = 3, base_delay: float = 1.0):
    """fn() 失败时按 base_delay * 2^attempt 退避重试,最多 max_attempts 次。"""
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < max_attempts - 1:
                time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.3))
    raise last_exc
```

- [ ] **Step 6:跑测试,确认 pass**

Run: `python -m pytest tests/test_a_stock_data_common.py -v`
Expected: 7 passed

- [ ] **Step 7:commit**

```bash
git add py/a_stock_data/ tests/test_a_stock_data_common.py
git commit -m "feat(a_stock_data): add _common.py with em_get, cache, retry, ticker utils"
```

## Task 1.3:Vendor `tencent.py`(行情层唯一)

**Files:**
- Create: `py/a_stock_data/tencent.py`
- Create: `tests/test_tencent_retry.py`

**Interfaces:**
- Produces: `py.a_stock_data.tencent.tencent_quote(codes: list[str]) -> dict[str, dict]`
- 调用: `py.a_stock_data._common.retry` 包住 `urllib.request.urlopen`

- [ ] **Step 1:读 SKILL.md 352-453 行**(tencent_quote 实现)

- [ ] **Step 2:写测试**

```python
# tests/test_tencent_retry.py
import pytest
from unittest.mock import patch, MagicMock
from py.a_stock_data.tencent import tencent_quote

def _mock_resp(text: str):
    m = MagicMock()
    m.read.return_value = text.encode("gbk")
    m.__enter__ = lambda s: s
    m.__exit__ = lambda s, *a: None
    return m

VALID = 'v_sh600519="1~贵州茅台~600519~1685.00~1670.00~1690.00~' + '~' * 50 + '22.5~3.2~18000~65432.1~63201.3~4.8~1853.50~1516.50~1.5~24.0";'

def test_tencent_quote_parses_basic():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _mock_resp(VALID)
        out = tencent_quote(["600519"])
    assert "600519" in out
    s = out["600519"]
    assert s["name"] == "贵州茅台"
    assert s["price"] == 1685.0
    assert s["pe_ttm"] == 22.5
    assert s["mcap_yi"] == 65432.1
    assert s["limit_up"] == 1853.5

def test_tencent_quote_retries_on_failure():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [
            TimeoutError("first"),
            TimeoutError("second"),
            _mock_resp(VALID),
        ]
        with patch("time.sleep"):  # 加速
            out = tencent_quote(["600519"])
    assert "600519" in out

def test_tencent_quote_handles_empty():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value = _mock_resp("")
    out = tencent_quote(["600519"])
    assert out == {}
```

- [ ] **Step 3:跑测试,确认 fail**

Run: `python -m pytest tests/test_tencent_retry.py -v`
Expected: `ModuleNotFoundError`

- [ ] **Step 4:写 `py/a_stock_data/tencent.py`**

```python
"""腾讯财经 API:PE/PB/市值/换手/涨跌停/指数/ETF。带 retry。"""
import random
import time
import urllib.request
from py.a_stock_data._common import get_prefix, retry

UA = "Mozilla/5.0"


def _fetch_raw(codes: list[str]) -> str:
    """单次 HTTP 调用,带 3 次 retry。"""
    prefixed = [f"{get_prefix(c)}{c}" for c in codes]
    url = "https://qt.gtimg.cn/q=" + ",".join(prefixed)
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.read().decode("gbk")


def _parse(raw: str) -> dict[str, dict]:
    result = {}
    for line in raw.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        key = line.split("=")[0].split("_")[-1]
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        code = key[2:]
        result[code] = {
            "name":            vals[1],
            "price":           float(vals[3]) or 0,
            "last_close":      float(vals[4]) or 0,
            "open":            float(vals[5]) or 0,
            "change_amt":      float(vals[31]) or 0,
            "change_pct":      float(vals[32]) or 0,
            "high":            float(vals[33]) or 0,
            "low":             float(vals[34]) or 0,
            "amount_wan":      float(vals[37]) or 0,
            "turnover_pct":    float(vals[38]) or 0,
            "pe_ttm":          float(vals[39]) or 0,
            "amplitude_pct":   float(vals[43]) or 0,
            "mcap_yi":         float(vals[44]) or 0,
            "float_mcap_yi":   float(vals[45]) or 0,
            "pb":              float(vals[46]) or 0,
            "limit_up":        float(vals[47]) or 0,
            "limit_down":      float(vals[48]) or 0,
            "vol_ratio":       float(vals[49]) or 0,
            "pe_static":       float(vals[52]) or 0,
        }
    return result


def tencent_quote(codes: list[str]) -> dict[str, dict]:
    """批量拉取实时行情。失败 3 次后抛 ConnectionError。"""
    def do():
        return _fetch_raw(codes)
    raw = retry(do, max_attempts=3, base_delay=1.0)
    return _parse(raw)
```

- [ ] **Step 5:跑测试,确认 pass**

Run: `python -m pytest tests/test_tencent_retry.py -v`
Expected: 3 passed

- [ ] **Step 6:commit**

```bash
git add py/a_stock_data/tencent.py tests/test_tencent_retry.py
git commit -m "feat(a_stock_data): add tencent.py with retry"
```

## Task 1.4:Vendor `eastmoney.py`(Tier 1, 6 函数)

**Files:**
- Create: `py/a_stock_data/eastmoney.py`

**Interfaces:**
- Produces:
  - `eastmoney_reports(code: str, max_pages: int = 1) -> list[dict]`
  - `eastmoney_industry_reports(industry_code: str = "*", max_pages: int = 1) -> list[dict]`
  - `eastmoney_concept_blocks(code: str) -> dict`
  - `eastmoney_fund_flow_minute(code: str) -> list[dict]`
  - `stock_fund_flow_120d(code: str) -> list[dict]`
  - `daily_dragon_tiger(trade_date: str | None = None) -> dict`

- [ ] **Step 1:读 SKILL.md 509-1307 行**,提取 6 个函数的实现

- [ ] **Step 2:写 `py/a_stock_data/eastmoney.py`**

将 SKILL.md 的 6 个函数(行号见上)原样复制到该文件,顶部加:

```python
"""东财数据层:研报列表/板块归属/资金流/龙虎榜。"""
import json
import time
from py.a_stock_data._common import em_get, em_cache_get, em_cache_put, _cache_key

# ── 2.1 个股研报列表 ─────────────────────────────────
REPORTAPI_URL = "https://reportapi.eastmoney.com/report/list"

def eastmoney_reports(code: str, max_pages: int = 1) -> list[dict]:
    """拉个股研报列表(标题/机构/评级/日期)。"""
    cache_key = _cache_key(REPORTAPI_URL, {"code": code, "max_pages": max_pages})
    cached = em_cache_get(cache_key)
    if cached is not None:
        return cached

    all_reports = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "50", "industry": "*",
            "rating": "*", "ratingChange": "*", "beginTime": "",
            "endTime": "", "pageNo": str(page), "fields": "",
            "qType": "0", "orgCode": "*", "code": code,
            "rcode": "", "_": str(int(time.time() * 1000)),
        }
        r = em_get(REPORTAPI_URL, params=params, timeout=15)
        d = r.json()
        if not d.get("data") or not d["data"].get("dataList"):
            break
        for item in d["data"]["dataList"]:
            all_reports.append({
                "title":       item.get("title", ""),
                "org":         item.get("orgSName", ""),
                "rating":      item.get("emRatingName", ""),
                "industry":    item.get("industryName", ""),
                "date":        item.get("publishDate", "")[:10],
                "report_id":   item.get("infoCode", ""),
            })
    em_cache_put(cache_key, all_reports)
    return all_reports


def eastmoney_industry_reports(industry_code: str = "*", max_pages: int = 1) -> list[dict]:
    """行业研报列表(同端点,qType=1)。"""
    cache_key = _cache_key(REPORTAPI_URL, {"industry": industry_code, "max_pages": max_pages, "type": "industry"})
    cached = em_cache_get(cache_key)
    if cached is not None:
        return cached

    all_reports = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": industry_code, "pageSize": "50", "industry": "*",
            "rating": "*", "ratingChange": "*", "beginTime": "",
            "endTime": "", "pageNo": str(page), "fields": "",
            "qType": "1", "orgCode": "*", "code": "",
            "rcode": "", "_": str(int(time.time() * 1000)),
        }
        r = em_get(REPORTAPI_URL, params=params, timeout=15)
        d = r.json()
        if not d.get("data") or not d["data"].get("dataList"):
            break
        for item in d["data"]["dataList"]:
            all_reports.append({
                "title":     item.get("title", ""),
                "org":       item.get("orgSName", ""),
                "rating":    item.get("emRatingName", ""),
                "industry":  item.get("industryName", ""),
                "date":      item.get("publishDate", "")[:10],
                "report_id": item.get("infoCode", ""),
            })
    em_cache_put(cache_key, all_reports)
    return all_reports


# ── 3.3 个股板块归属 ─────────────────────────────────
SLIST_URL = "https://push2.eastmoney.com/api/qt/stock/get"

def eastmoney_concept_blocks(code: str) -> dict:
    """返回 {industries: [...], concepts: [...], regions: [...]}。"""
    secid_map = {"sh": "1.", "sz": "0.", "bj": "0."}
    from py.a_stock_data._common import get_prefix
    secid = secid_map[get_prefix(code)] + code

    cache_key = _cache_key(SLIST_URL, {"secid": secid})
    cached = em_cache_get(cache_key)
    if cached is not None:
        return cached

    params = {
        "fields": "f12,f14,f128,f136,f152",
        "secid": secid,
        "_": str(int(time.time() * 1000)),
    }
    r = em_get(SLIST_URL, params=params, timeout=15)
    d = r.json().get("data", {})

    out = {"industries": [], "concepts": [], "regions": []}
    if d.get("f128"):  # 行业板块代码
        out["industries"].append({
            "code": d["f128"], "name": d.get("f12", ""),
        })
    # 概念/地域需另调接口(SKILL.md 934-980 详述),简化先返回基础
    em_cache_put(cache_key, out)
    return out


# ── 3.4 分钟资金流 ─────────────────────────────────
FUND_FLOW_MIN_URL = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"

def eastmoney_fund_flow_minute(code: str) -> list[dict]:
    """返回 60 分钟级别资金流 dict 列表。"""
    secid_map = {"sh": "1.", "sz": "0.", "bj": "0."}
    from py.a_stock_data._common import get_prefix
    secid = secid_map[get_prefix(code)] + code

    params = {
        "fields": "f1,f2,f3,f7",
        "secid": secid,
        "klt": "1", "lmt": "60",  # 1 分钟 K, 60 根
    }
    r = em_get(FUND_FLOW_MIN_URL, params=params, timeout=15)
    d = r.json().get("data", {})
    klines = d.get("klines", [])
    return [
        {"time": k.split(",")[0], "main": float(k.split(",")[1] or 0),
         "large": float(k.split(",")[2] or 0), "small": float(k.split(",")[3] or 0)}
        for k in klines if len(k.split(",")) >= 4
    ]


# ── 4.5 120 日资金流 ─────────────────────────────────
FUND_FLOW_120D_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

def stock_fund_flow_120d(code: str) -> list[dict]:
    """日级 120 日资金流,返回 [{"date": "2026-06-25", "main": 123.45, ...}]。"""
    cache_key = _cache_key(FUND_FLOW_120D_URL, {"code": code, "type": "120d"})
    cached = em_cache_get(cache_key)
    if cached is not None:
        return cached

    params = {
        "reportName": "RPT_MUTUAL_STOCK_HOLDRANKS",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
        "pageNumber": "1", "pageSize": "120",
        "sortColumns": "TRADE_DATE", "sortTypes": "-1",
        "source": "WEB", "client": "WEB",
    }
    r = em_get(FUND_FLOW_120D_URL, params=params, timeout=15)
    d = r.json()
    rows = d.get("result", {}).get("data", []) if d.get("result") else []
    out = []
    for row in rows:
        out.append({
            "date":   row.get("TRADE_DATE", "")[:10],
            "main":   row.get("MAIN_NET_INFLOW", 0) or 0,
            "large":  row.get("LARGE_NET_INFLOW", 0) or 0,
            "medium": row.get("MEDIUM_NET_INFLOW", 0) or 0,
            "small":  row.get("SMALL_NET_INFLOW", 0) or 0,
        })
    em_cache_put(cache_key, out)
    return out


# ── 3.8 全市场龙虎榜 ─────────────────────────────────
DRAGON_TIGER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"

def daily_dragon_tiger(trade_date: str | None = None, min_net_buy: float = None) -> dict:
    """返回 {"data": [{...龙虎榜记录...}], "total": N}。"""
    if trade_date is None:
        from datetime import date
        trade_date = date.today().isoformat()

    params = {
        "reportName": "RPT_DAILYBILLBOARD_DETAILS",
        "columns": "ALL",
        "filter": f'(TRADE_DATE=\'{trade_date}\')',
        "pageNumber": "1", "pageSize": "100",
        "sortColumns": "NET_BUY_AMT", "sortTypes": "-1",
        "source": "WEB", "client": "WEB",
    }
    r = em_get(DRAGON_TIGER_URL, params=params, timeout=15)
    d = r.json()
    rows = d.get("result", {}).get("data", []) if d.get("result") else []
    if min_net_buy is not None:
        rows = [row for row in rows if (row.get("NET_BUY_AMT") or 0) >= min_net_buy]
    return {"data": rows, "total": len(rows), "date": trade_date}
```

- [ ] **Step 3:创建占位模块**(让 import 路径完整,后续 task 填充)

```bash
mkdir -p py/a_stock_data
```

每个文件用函数 stub 抛 NotImplementedError,让 import 成功但调用时显式 fail:

`py/a_stock_data/ths.py`:
```python
def ths_hot_reason(*args, **kwargs):
    raise NotImplementedError("在 Task 1.5 填充")
def ths_eps_forecast(*args, **kwargs):
    raise NotImplementedError("在 Task 1.5 填充")
def hsgt_realtime(*args, **kwargs):
    raise NotImplementedError("在 Task 1.5 填充")
```

`py/a_stock_data/sectors.py`:
```python
def industry_comparison(*args, **kwargs):
    raise NotImplementedError("在 Task 1.6 填充")
```

`py/a_stock_data/news.py`:
```python
def eastmoney_stock_news(*args, **kwargs):
    raise NotImplementedError("在 Task 1.7 填充")
def eastmoney_global_news(*args, **kwargs):
    raise NotImplementedError("在 Task 1.7 填充")
```

`py/a_stock_data/pdf.py`:
```python
def download_pdf(*args, **kwargs):
    raise NotImplementedError("在 Task 1.7 填充")
```

`py/a_stock_data/financials.py`:
```python
def sina_financial_report(*args, **kwargs):
    raise NotImplementedError("在 Task 1.7 填充")
```

`py/a_stock_data/filings.py`:
```python
def cninfo_announcements(*args, **kwargs):
    raise NotImplementedError("在 Task 1.7 填充")
```

- [ ] **Step 4:写 `py/a_stock_data/__init__.py`** 重导出

```python
"""a-stock-data vendored helpers。"""
from py.a_stock_data._common import (
    em_get, em_cache_get, em_cache_put, get_prefix, normalize_code, retry,
    EM_SESSION, EM_MIN_INTERVAL, UA,
)
from py.a_stock_data.tencent import tencent_quote
from py.a_stock_data.eastmoney import (
    eastmoney_reports, eastmoney_industry_reports,
    eastmoney_concept_blocks, eastmoney_fund_flow_minute,
    stock_fund_flow_120d, daily_dragon_tiger,
)
from py.a_stock_data.ths import ths_hot_reason, ths_eps_forecast, hsgt_realtime
from py.a_stock_data.sectors import industry_comparison
from py.a_stock_data.news import eastmoney_stock_news, eastmoney_global_news
from py.a_stock_data.pdf import download_pdf
from py.a_stock_data.financials import sina_financial_report
from py.a_stock_data.filings import cninfo_announcements

__version__ = "1.0.0"
```

- [ ] **Step 5:语法检查**

Run: `python -c "import py.a_stock_data.eastmoney; print('OK')"`
Expected: `OK`

- [ ] **Step 6:commit**

```bash
git add py/a_stock_data/
git commit -m "feat(a_stock_data): add eastmoney.py with 6 tier-1 functions"
```

## Task 1.5:Vendor `ths.py`(3 函数)

**Files:**
- Create: `py/a_stock_data/ths.py`(填充)

- [ ] **Step 1:读 SKILL.md 778-925 行**,提取 `ths_hot_reason`、`ths_eps_forecast`、`hsgt_realtime` 实现

- [ ] **Step 2:写 `py/a_stock_data/ths.py`**(完整 vendor,见 SKILL.md,顶部加 `from py.a_stock_data._common import em_get, em_cache_get, em_cache_put, _cache_key`)

- [ ] **Step 3:语法检查**

Run: `python -c "import py.a_stock_data.ths; print('OK')"`

- [ ] **Step 4:commit**

```bash
git add py/a_stock_data/ths.py
git commit -m "feat(a_stock_data): add ths.py with hot_reason, eps_forecast, hsgt"
```

## Task 1.6:Vendor `sectors.py`

**Files:**
- Create: `py/a_stock_data/sectors.py`(填充)

- [ ] **Step 1:读 SKILL.md 1202-1257 行**,提取 `industry_comparison`

- [ ] **Step 2:写 `py/a_stock_data/sectors.py`**(vendor,顶部加 em_get 导入)

- [ ] **Step 3:commit**

```bash
git add py/a_stock_data/sectors.py
git commit -m "feat(a_stock_data): add sectors.py with industry_comparison"
```

## Task 1.7:Vendor `news.py`、`pdf.py`、`financials.py`、`filings.py`(Tier 2)

**Files:**
- Create: `py/a_stock_data/news.py`
- Create: `py/a_stock_data/pdf.py`
- Create: `py/a_stock_data/financials.py`
- Create: `py/a_stock_data/filings.py`

- [ ] **Step 1:读 SKILL.md 对应章节**:
  - news: 1548-1677 行
  - pdf: 532-560 行
  - financials: 1757-1816 行
  - filings: 1817-1914 行

- [ ] **Step 2:分别填充 4 个文件**,每个顶部加 em_get 导入

- [ ] **Step 3:语法检查**

Run: `python -c "from py.a_stock_data import eastmoney_stock_news, eastmoney_global_news, download_pdf, sina_financial_report, cninfo_announcements; print('OK')"`

- [ ] **Step 4:commit**

```bash
git add py/a_stock_data/news.py py/a_stock_data/pdf.py py/a_stock_data/financials.py py/a_stock_data/filings.py
git commit -m "feat(a_stock_data): add tier-2 modules (news, pdf, financials, filings)"
```

## Task 1.8:`db.py` —— SQLite 封装 + schema 初始化

**Files:**
- Create: `py/db.py`
- Create: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `init_decisions_db() -> None`(创建 decisions.sqlite + 表)
  - `init_screener_db() -> None`(创建 screener.sqlite + 表)
  - `conn(db_path) -> sqlite3.Connection`(上下文管理器)
  - `insert_decision(...) -> int`(返回新 id)
  - `update_decision_close(id, close_date, close_price, close_reason, pnl_pct) -> None`
  - `insert_candidate(...) -> None`(UPSERT by (date, strategy, code))
  - `insert_sector(...) -> None`(UPSERT by (date, type, name))
  - `upsert_daily_summary(...) -> None`

- [ ] **Step 1:写测试**

```python
# tests/test_db.py
import tempfile
from pathlib import Path
import py.db as db
import py.config as cfg
import sqlite3

def test_init_creates_tables():
    db.init_decisions_db()
    db.init_screener_db()
    with db.conn(cfg.DECISIONS_DB) as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r[0] for r in rows}
        assert "decisions" in names
        assert "watchlist" in names
    with db.conn(cfg.SCREENER_DB) as c:
        rows = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = {r[0] for r in rows}
        assert "candidate_history" in names
        assert "sector_history" in names
        assert "daily_summary" in names

def test_insert_and_query_decision():
    db.init_decisions_db()
    new_id = db.insert_decision(
        code="000858", name="五粮液", strategy="short", action="buy",
        decision_date="2026-06-26", price=168.5, quantity=100,
        reason="板块共振", brief_snapshot_path="data/screen/briefs/000858/2026-06-26.md",
        plan_stop_loss=160, plan_target=185, plan_hold_days=5,
    )
    with db.conn(cfg.DECISIONS_DB) as c:
        row = c.execute("SELECT code, name, strategy, price FROM decisions WHERE id=?", (new_id,)).fetchone()
        assert row[0] == "000858"
        assert row[1] == "五粮液"
        assert row[2] == "short"
        assert row[3] == 168.5

def test_close_decision_updates_pnl():
    db.init_decisions_db()
    new_id = db.insert_decision(
        code="000858", name="五粮液", strategy="short", action="buy",
        decision_date="2026-06-26", price=100.0, quantity=100,
    )
    db.update_decision_close(new_id, "2026-06-30", 110.0, "target", 10.0)
    with db.conn(cfg.DECISIONS_DB) as c:
        row = c.execute("SELECT close_price, close_reason, pnl_pct FROM decisions WHERE id=?", (new_id,)).fetchone()
        assert row[0] == 110.0
        assert row[1] == "target"
        assert row[2] == 10.0
```

- [ ] **Step 2:跑测试,确认 fail**

Run: `python -m pytest tests/test_db.py -v`

- [ ] **Step 3:写 `py/db.py`**

```python
"""SQLite 封装:schema 初始化 + CRUD helper。"""
import sqlite3
from contextlib import contextmanager
import py.config as cfg

DECISIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT NOT NULL,
    name            TEXT,
    strategy        TEXT NOT NULL CHECK(strategy IN ('short', 'mid')),
    action          TEXT NOT NULL CHECK(action IN ('buy', 'add', 'sell', 'close')),
    decision_date   TEXT NOT NULL,
    decision_time   TEXT,
    price           REAL NOT NULL,
    quantity        INTEGER NOT NULL,
    amount          REAL,
    reason          TEXT,
    brief_snapshot_path TEXT,
    plan_stop_loss      REAL,
    plan_target         REAL,
    plan_hold_days      INTEGER,
    plan_max_position_pct REAL,
    close_date      TEXT,
    close_price     REAL,
    close_reason    TEXT CHECK(close_reason IN ('stop_loss', 'target', 'manual', 'expired')),
    pnl_pct         REAL,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_code ON decisions(code);
CREATE INDEX IF NOT EXISTS idx_strategy_date ON decisions(strategy, decision_date);
CREATE INDEX IF NOT EXISTS idx_open ON decisions(close_date);
CREATE TABLE IF NOT EXISTS watchlist (
    code        TEXT PRIMARY KEY,
    name        TEXT,
    theme       TEXT,
    note        TEXT,
    added_at    TEXT DEFAULT (datetime('now'))
);
"""

SCREENER_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_history (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date           TEXT NOT NULL,
    strategy            TEXT NOT NULL CHECK(strategy IN ('short', 'mid')),
    code                TEXT NOT NULL,
    name                TEXT,
    sector              TEXT,
    concept_primary     TEXT,
    net_flow            REAL,
    change_pct          REAL,
    pe_ttm              REAL,
    pb                  REAL,
    mcap_yi             REAL,
    turnover_pct        REAL,
    report_count_7d     INTEGER,
    hot_reason          TEXT,
    on_dragon_tiger     INTEGER DEFAULT 0,
    score               REAL,
    raw_data_path       TEXT,
    UNIQUE(scan_date, strategy, code)
);
CREATE INDEX IF NOT EXISTS idx_strategy_date ON candidate_history(strategy, scan_date);
CREATE INDEX IF NOT EXISTS idx_code ON candidate_history(code);
CREATE TABLE IF NOT EXISTS sector_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date       TEXT NOT NULL,
    sector_type     TEXT NOT NULL CHECK(sector_type IN ('industry', 'concept')),
    name            TEXT NOT NULL,
    change_pct      REAL,
    net_flow        REAL,
    leader_name     TEXT,
    leader_code     TEXT,
    rank            INTEGER,
    UNIQUE(scan_date, sector_type, name)
);
CREATE INDEX IF NOT EXISTS idx_sector_date ON sector_history(scan_date);
CREATE TABLE IF NOT EXISTS daily_summary (
    date                TEXT PRIMARY KEY,
    generated_at        TEXT NOT NULL,
    short_count         INTEGER,
    mid_count           INTEGER,
    sector_count        INTEGER,
    report_path         TEXT,
    brief_snapshots     INTEGER,
    status              TEXT DEFAULT 'ok'
);
"""


@contextmanager
def conn(db_path):
    c = sqlite3.connect(str(db_path))
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_decisions_db() -> None:
    with conn(cfg.DECISIONS_DB) as c:
        c.executescript(DECISIONS_SCHEMA)


def init_screener_db() -> None:
    with conn(cfg.SCREENER_DB) as c:
        c.executescript(SCREENER_SCHEMA)


def insert_decision(*, code, name, strategy, action, decision_date, price, quantity,
                    reason=None, brief_snapshot_path=None,
                    plan_stop_loss=None, plan_target=None, plan_hold_days=None,
                    plan_max_position_pct=None) -> int:
    amount = price * quantity
    with conn(cfg.DECISIONS_DB) as c:
        cur = c.execute("""
            INSERT INTO decisions
            (code, name, strategy, action, decision_date, price, quantity, amount,
             reason, brief_snapshot_path, plan_stop_loss, plan_target,
             plan_hold_days, plan_max_position_pct)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (code, name, strategy, action, decision_date, price, quantity, amount,
              reason, brief_snapshot_path, plan_stop_loss, plan_target,
              plan_hold_days, plan_max_position_pct))
        return cur.lastrowid


def update_decision_close(decision_id, close_date, close_price, close_reason, pnl_pct) -> None:
    with conn(cfg.DECISIONS_DB) as c:
        c.execute("""
            UPDATE decisions SET close_date=?, close_price=?, close_reason=?, pnl_pct=?,
                updated_at=datetime('now')
            WHERE id=?
        """, (close_date, close_price, close_reason, pnl_pct, decision_id))


def upsert_candidate(scan_date, strategy, code, **fields) -> None:
    cols = ["scan_date", "strategy", "code"] + list(fields.keys())
    placeholders = ",".join("?" * len(cols))
    update_cols = ",".join(f"{k}=excluded.{k}" for k in fields.keys())
    values = [scan_date, strategy, code] + list(fields.values())
    with conn(cfg.SCREENER_DB) as c:
        c.execute(f"""
            INSERT INTO candidate_history ({",".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(scan_date, strategy, code) DO UPDATE SET {update_cols}
        """, values)


def upsert_sector(scan_date, sector_type, name, **fields) -> None:
    cols = ["scan_date", "sector_type", "name"] + list(fields.keys())
    placeholders = ",".join("?" * len(cols))
    update_cols = ",".join(f"{k}=excluded.{k}" for k in fields.keys())
    values = [scan_date, sector_type, name] + list(fields.values())
    with conn(cfg.SCREENER_DB) as c:
        c.execute(f"""
            INSERT INTO sector_history ({",".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(scan_date, sector_type, name) DO UPDATE SET {update_cols}
        """, values)


def upsert_daily_summary(date, **fields) -> None:
    cols = ["date"] + list(fields.keys())
    placeholders = ",".join("?" * len(cols))
    update_cols = ",".join(f"{k}=excluded.{k}" for k in fields.keys())
    values = [date] + list(fields.values())
    with conn(cfg.SCREENER_DB) as c:
        c.execute(f"""
            INSERT INTO daily_summary ({",".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT(date) DO UPDATE SET {update_cols}
        """, values)
```

- [ ] **Step 4:跑测试,确认 pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: 3 passed

- [ ] **Step 5:commit**

```bash
git add py/db.py tests/test_db.py
git commit -m "feat(db): add SQLite wrapper with schema and CRUD helpers"
```

## Task 1.9:`ohlcv.py` —— parquet 读

**Files:**
- Create: `py/ohlcv.py`
- Create: `tests/test_ohlcv.py`

**Interfaces:**
- Produces:
  - `load_ohlcv(code: str) -> pd.DataFrame`(从 `data/ohlcv/<code>.parquet`)
  - `list_available_codes() -> list[str]`

- [ ] **Step 1:写测试**

```python
# tests/test_ohlcv.py
import py.ohlcv as ohlcv

def test_load_ohlcv_existing():
    df = ohlcv.load_ohlcv("000001")  # 已知存在
    assert not df.empty
    assert "close" in df.columns
    assert "date" in df.columns or df.index.name is not None

def test_load_ohlcv_missing():
    try:
        ohlcv.load_ohlcv("999999")
    except FileNotFoundError:
        pass
    else:
        assert False, "should have raised"

def test_list_available_codes():
    codes = ohlcv.list_available_codes()
    assert len(codes) > 5000
    assert "000001" in codes
```

- [ ] **Step 2:写 `py/ohlcv.py`**

```python
"""parquet OHLCV 数据读取。"""
from pathlib import Path
import pandas as pd
import py.config as cfg


def load_ohlcv(code: str) -> pd.DataFrame:
    """读 <code>.parquet,返回标准化 DataFrame(date, open, high, low, close, volume)。"""
    path = cfg.OHLCV_DIR / f"{code}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"no parquet for {code}")
    df = pd.read_parquet(path)
    # 标准化列名(原始可能是 DateTime/index)
    df.columns = [c.lower() for c in df.columns]
    if "date" not in df.columns and df.index.name:
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
    if "volume" not in df.columns and "vol" in df.columns:
        df = df.rename(columns={"vol": "volume"})
    return df


def list_available_codes() -> list[str]:
    return sorted([p.stem for p in cfg.OHLCV_DIR.glob("*.parquet")])
```

- [ ] **Step 3:跑测试,确认 pass**

Run: `python -m pytest tests/test_ohlcv.py -v`
Expected: 3 passed

- [ ] **Step 4:commit**

```bash
git add py/ohlcv.py tests/test_ohlcv.py
git commit -m "feat(ohlcv): add parquet loader"
```

## Task 1.10:集成 smoke —— 验证 vendor 完的端点至少 import 成功

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_a_stock_data_smoke.py`

- [ ] **Step 1:写集成测试**(默认 skip)

```python
# tests/integration/test_a_stock_data_smoke.py
import pytest
from py.a_stock_data import (
    tencent_quote, industry_comparison, ths_hot_reason,
    daily_dragon_tiger,
)

pytestmark = pytest.mark.integration


@pytest.mark.skip(reason="需要网络;手动跑")
def test_tencent_quote_600519():
    out = tencent_quote(["600519"])
    assert "600519" in out


@pytest.mark.skip(reason="需要网络;手动跑")
def test_industry_comparison():
    out = industry_comparison(top_n=5)
    assert "data" in out or isinstance(out, list)
```

- [ ] **Step 2:跑(默认 skip)**

Run: `python -m pytest tests/integration/ -v`
Expected: 跳过 2 个

- [ ] **Step 3:commit**

```bash
git add tests/integration/
git commit -m "test: add a-stock-data smoke tests (skip by default)"
```

**Phase 1 完成验收**:
- `python -m pytest tests/ -v` 全 pass(集成测试默认 skip)
- `python -c "from py.a_stock_data import *"` 无错
- `python -c "import py.db; py.db.init_decisions_db(); py.db.init_screener_db()"` 创建 SQLite 文件
- `python -c "import py.ohlcv; print(len(py.ohlcv.list_available_codes()))"` 输出 >5000

---

# Phase 2: 业务层(2-3 天)

> 目标:`py/a_screen/` 五个模块全实现 + 单元测试,纯计算无 HTTP,所有数据层调用 mock。

## Task 2.1:`sector_scan.py` —— 板块聚合

**Files:**
- Create: `py/a_screen/__init__.py`
- Create: `py/a_screen/sector_scan.py`
- Create: `tests/test_sector_scan.py`

**Interfaces:**
- Produces:
  - `scan_sectors(trade_date: str) -> dict`
    - 返回 `{"industry": [...], "concept": [...], "hot": [...], "dragon_tiger": [...]}`

- [ ] **Step 1:写测试**

```python
# tests/test_sector_scan.py
from unittest.mock import patch, MagicMock
from py.a_screen.sector_scan import scan_sectors


def test_scan_sectors_combines_sources():
    with patch("py.a_screen.sector_scan.industry_comparison") as m1, \
         patch("py.a_screen.sector_scan.ths_hot_reason") as m2, \
         patch("py.a_screen.sector_scan.daily_dragon_tiger") as m3:
        m1.return_value = {"industry": [{"name": "白酒", "change_pct": 1.0}]}
        m2.return_value = [{"code": "600519", "name": "贵州茅台", "reason": "白酒提价"}]
        m3.return_value = {"data": [{"code": "000858", "name": "五粮液", "net_buy": 1e8}]}

        result = scan_sectors("2026-06-26")

    assert "industry" in result
    assert "hot" in result
    assert "dragon_tiger" in result
    assert result["industry"][0]["name"] == "白酒"
```

- [ ] **Step 2:写 `py/a_screen/sector_scan.py`**

```python
"""板块聚合:行业/概念/热点/龙虎榜。"""
from typing import Any
from py.a_stock_data import industry_comparison, ths_hot_reason, daily_dragon_tiger


def scan_sectors(trade_date: str) -> dict[str, Any]:
    # industry_comparison 返回结构需在实施时对齐 SKILL.md 1209-1257
    # 预期: {"industry": [{name, change_pct, net_flow, ...}], "concept": [...]}
    # 若实际是 {"data": [...]},需调整下面 .get 调用
    ic = industry_comparison(top_n=30)
    return {
        "industry":    ic.get("industry", []),
        "concept":     ic.get("concept", []),
        "hot":         _safe_ths_hot(trade_date),
        "dragon_tiger": daily_dragon_tiger(trade_date).get("data", []),
    }


def _safe_ths_hot(trade_date: str):
    try:
        df = ths_hot_reason(trade_date)
        return df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    except Exception:
        return []
```

- [ ] **Step 3:跑测试**

Run: `python -m pytest tests/test_sector_scan.py -v`
Expected: 1 passed

- [ ] **Step 4:commit**

```bash
git add py/a_screen/ tests/test_sector_scan.py
git commit -m "feat(a_screen): add sector_scan with mocked tests"
```

## Task 2.2:`candidate_filter.py` —— 初筛 + 评分

**Files:**
- Create: `py/a_screen/candidate_filter.py`
- Create: `tests/test_candidate_filter.py`
- Create: `tests/test_scoring.py`

**Interfaces:**
- Produces:
  - `initial_filter(stocks: list[dict], strategy: str) -> list[dict]`
  - `score_candidate(c: dict, strategy: str, sector_data: dict) -> float`

- [ ] **Step 1:写测试(test_candidate_filter.py)**

```python
from py.a_screen.candidate_filter import initial_filter

def test_short_filter_picks_1_to_7_pct_gain():
    stocks = [
        {"code": "A", "change_pct": 0.5, "net_flow": 1e7},
        {"code": "B", "change_pct": 3.0, "net_flow": 2e7},
        {"code": "C", "change_pct": 8.0, "net_flow": 5e7},
        {"code": "D", "change_pct": 2.0, "net_flow": -1e6},
    ]
    out = initial_filter(stocks, "short")
    codes = {s["code"] for s in out}
    assert "A" in codes
    assert "B" in codes
    assert "C" not in codes  # 涨幅过高
    assert "D" not in codes  # 净流出

def test_mid_filter_picks_pe_in_range():
    stocks = [
        {"code": "A", "pe_ttm": 15, "mcap_yi": 100, "fund_flow_20d": 1e8},
        {"code": "B", "pe_ttm": 80, "mcap_yi": 100, "fund_flow_20d": 1e8},
        {"code": "C", "pe_ttm": 25, "mcap_yi": 30,  "fund_flow_20d": 1e8},
    ]
    out = initial_filter(stocks, "mid")
    codes = {s["code"] for s in out}
    assert "A" in codes
    assert "B" not in codes  # PE 过高
    assert "C" not in codes  # 市值过小
```

- [ ] **Step 2:写测试(test_scoring.py)**

```python
import py.config as cfg
from py.a_screen.candidate_filter import score_candidate

def test_short_score_in_range():
    c = {"code": "X", "change_pct": 3.0, "net_flow": 1e8,
         "sector_alignment": 0.8, "report_count_7d": 5, "hot_reason_hit": True}
    sector_data = {"industry": [{"name": "白酒", "codes": ["X"]}]}
    s = score_candidate(c, "short", sector_data)
    assert 0 <= s <= 100

def test_mid_score_uses_valuation():
    c = {"code": "X", "pe_ttm": 15, "pb": 2.0, "fund_flow_20d": 1e8,
         "report_count_30d": 10, "theme_catalyst": 0.7, "tech_position": 0.6}
    s = score_candidate(c, "mid", {})
    assert 0 <= s <= 100
    assert s > 50  # 全正面
```

- [ ] **Step 3:写 `py/a_screen/candidate_filter.py`**

```python
"""初筛 + 评分(短线/中线)。"""
import py.config as cfg


def initial_filter(stocks: list[dict], strategy: str) -> list[dict]:
    if strategy == "short":
        return [
            s for s in stocks
            if s.get("net_flow", 0) > 0
            and 0 <= s.get("change_pct", 0) <= 7
        ]
    elif strategy == "mid":
        return [
            s for s in stocks
            if 0 < s.get("pe_ttm", 0) <= 50
            and s.get("mcap_yi", 0) >= 50
            and s.get("fund_flow_20d", 0) > 0
        ]
    return []


def score_candidate(c: dict, strategy: str, sector_data: dict) -> float:
    """返回 0-100 评分。"""
    weights = cfg.SCORING[strategy]
    if strategy == "short":
        return _score_short(c, weights, sector_data)
    return _score_mid(c, weights)


def _score_short(c, w, sector_data) -> float:
    s = 0.0
    # net_flow_rank:用 net_flow 简单归一化(>1e8 = 满分)
    nf = c.get("net_flow", 0) or 0
    s += min(nf / 1e8, 1.0) * w["net_flow_rank"]
    # change_pct_band:1-5% 最优
    pct = c.get("change_pct", 0) or 0
    if 1 <= pct <= 5:
        s += w["change_pct_band"]
    elif 0 <= pct < 1 or 5 < pct <= 7:
        s += w["change_pct_band"] * 0.5
    # sector_alignment:是否在强势板块
    align = c.get("sector_alignment", 0) or 0
    s += min(align, 1.0) * w["sector_alignment"]
    # report_count_7d:研报热度(0-10 归一)
    rc = c.get("report_count_7d", 0) or 0
    s += min(rc / 10, 1.0) * w["report_count_7d"]
    # hot_reason_hit
    if c.get("hot_reason_hit"):
        s += w["hot_reason_hit"]
    return min(s, 100.0)


def _score_mid(c, w) -> float:
    s = 0.0
    # valuation:PE 0-30 线性,>30 衰减
    pe = c.get("pe_ttm", 0) or 0
    if 0 < pe <= 30:
        s += w["valuation"]
    elif 30 < pe <= 50:
        s += w["valuation"] * (50 - pe) / 20
    # fund_flow_20d
    ff = c.get("fund_flow_20d", 0) or 0
    s += min(ff / 5e8, 1.0) * w["fund_flow_20d"]
    # report_coverage
    rc = c.get("report_count_30d", 0) or 0
    s += min(rc / 20, 1.0) * w["report_coverage"]
    # theme_catalyst(0-1)
    s += min(c.get("theme_catalyst", 0) or 0, 1.0) * w["theme_catalyst"]
    # tech_position(0-1)
    s += min(c.get("tech_position", 0) or 0, 1.0) * w["tech_position"]
    return min(s, 100.0)
```

- [ ] **Step 4:跑测试**

Run: `python -m pytest tests/test_candidate_filter.py tests/test_scoring.py -v`
Expected: 4 passed

- [ ] **Step 5:commit**

```bash
git add py/a_screen/candidate_filter.py tests/test_candidate_filter.py tests/test_scoring.py
git commit -m "feat(a_screen): add candidate_filter with short/mid screening and scoring"
```

## Task 2.3:`brief_builder.py` —— brief 数据组装

**Files:**
- Create: `py/a_screen/brief_builder.py`
- Create: `tests/test_brief_builder.py`

**Interfaces:**
- Produces:
  - `build_snapshot(code: str, trade_date: str) -> dict` —— 拉所有数据,组装 spec 8.2 的 snapshot 结构
  - `render_markdown(snapshot: dict) -> str` —— 输出 spec 8.2 模板的 markdown

- [ ] **Step 1:写测试**

```python
# tests/test_brief_builder.py
from unittest.mock import patch
from py.a_screen.brief_builder import build_snapshot, render_markdown

def test_build_snapshot_combines_sources():
    with patch("py.a_screen.brief_builder.tencent_quote") as m_t, \
         patch("py.a_screen.brief_builder.eastmoney_concept_blocks") as m_c, \
         patch("py.a_screen.brief_builder.stock_fund_flow_120d") as m_f, \
         patch("py.a_screen.brief_builder.eastmoney_reports") as m_r, \
         patch("py.a_screen.brief_builder.ths_eps_forecast") as m_e:
        m_t.return_value = {"000858": {"name": "五粮液", "price": 168.5, "pe_ttm": 22.5, "pb": 4.8, "mcap_yi": 6543, "industry": "白酒"}}
        m_c.return_value = {"industries": [{"name": "白酒"}], "concepts": [{"name": "消费"}], "regions": []}
        m_f.return_value = [{"date": "2026-06-20", "main": 1e8}]
        m_r.return_value = [{"title": "高端白酒景气", "org": "中信", "rating": "买入", "date": "2026-06-20"}]
        m_e.return_value = [{"year": "2026E", "eps": 8.5, "org_count": 23}]

        snap = build_snapshot("000858", "2026-06-26")

    assert snap["meta"]["code"] == "000858"
    assert snap["fundamentals"]["price"] == 168.5
    assert "白酒" in [i["name"] for i in snap["membership"]["industries"]]
    assert len(snap["research"]["reports"]) == 1


def test_render_markdown_contains_key_sections():
    snap = {
        "meta": {"code": "000858", "name": "五粮液"},
        "snapshot_date": "2026-06-26",
        "fundamentals": {"price": 168.5, "pe_ttm": 22.5, "pb": 4.8, "mcap_yi": 6543, "industry": "白酒"},
        "membership": {"industries": [{"name": "白酒"}], "concepts": [], "regions": []},
        "fund_flow": {"today": {}, "5d_cumulative": 0, "20d_cumulative": 0},
        "research": {"report_count_30d": 0, "reports": []},
        "consensus": {},
        "risks": ["test risk"],
        "ai_analysis": None,
    }
    md = render_markdown(snap)
    assert "五粮液" in md
    assert "000858" in md
    assert "基础面" in md
    assert "AI 跨信号分析" in md
```

- [ ] **Step 2:写 `py/a_screen/brief_builder.py`**

```python
"""单股 brief 数据组装 + markdown 渲染。"""
from datetime import datetime
from py.a_stock_data import (
    tencent_quote, eastmoney_concept_blocks, stock_fund_flow_120d,
    eastmoney_reports, ths_eps_forecast, hsgt_realtime,
    ths_hot_reason,
)
import py.config as cfg


def build_snapshot(code: str, trade_date: str, trigger: str = "manual") -> dict:
    code = code.strip()
    # 基本面
    tq = tencent_quote([code]).get(code, {})

    # 板块
    blocks = eastmoney_concept_blocks(code)

    # 资金流 120 日
    flows = stock_fund_flow_120d(code)

    # 研报
    reports = eastmoney_reports(code, max_pages=1)
    reports_7d = [r for r in reports if r.get("date", "") >= _date_offset(trade_date, -7)]

    # 一致预期
    try:
        eps_df = ths_eps_forecast(code)
        eps_list = eps_df.to_dict("records") if hasattr(eps_df, "to_dict") else []
    except Exception:
        eps_list = []

    # 北向(容错)
    try:
        nb = hsgt_realtime()
    except Exception:
        nb = None

    # 5d/20d 累计资金
    fund_5d = sum(r.get("main", 0) for r in flows[:5])
    fund_20d = sum(r.get("main", 0) for r in flows[:20])

    # 风险点(脚本级,数据驱动)
    risks = []
    pe = tq.get("pe_ttm", 0) or 0
    if pe > 50:
        risks.append(f"PE {pe} 偏高")
    if fund_5d < 0:
        risks.append(f"近 5 日主力净流出 {abs(fund_5d)/1e8:.2f} 亿")
    if len(reports_7d) == 0:
        risks.append("近 7 日无研报覆盖")

    return {
        "meta": {
            "code": code, "name": tq.get("name", ""),
            "generated_at": datetime.now().isoformat(),
            "trigger": trigger,
        },
        "snapshot_date": trade_date,
        "fundamentals": {
            "price": tq.get("price", 0), "change_pct": tq.get("change_pct", 0),
            "yesterday_close": tq.get("last_close", 0),
            "pe_ttm": pe, "pb": tq.get("pb", 0),
            "mcap_yi": tq.get("mcap_yi", 0),
            "float_mcap_yi": tq.get("float_mcap_yi", 0),
            "turnover_pct": tq.get("turnover_pct", 0),
            "limit_up": tq.get("limit_up", 0),
            "limit_down": tq.get("limit_down", 0),
            "industry": tq.get("industry", ""),
        },
        "membership": blocks,
        "fund_flow": {
            "today": {},  # 简化为不取分钟,等 brief 单独触发时再拉
            "5d_cumulative": fund_5d,
            "20d_cumulative": fund_20d,
        },
        "research": {
            "report_count_30d": len(reports),
            "reports": reports[:10],
        },
        "consensus": {"eps_forecasts": eps_list[:5]},
        "hot_signal": {"is_today_hot": False, "reason": None},
        "dragon_tiger": {"30d_count": 0, "last_appearance": None},
        "northbound": {"5d_net_inflow": 0},
        "screener_score": {"short": None, "mid": None, "scan_date": None},
        "risks": risks,
        "ai_analysis": None,
    }


def render_markdown(snap: dict) -> str:
    """按 spec 8.2 模板输出 markdown。"""
    m = snap["meta"]
    f = snap["fundamentals"]
    mem = snap["membership"]
    ff = snap["fund_flow"]
    res = snap["research"]
    cons = snap["consensus"]

    industries = ", ".join(i.get("name", "") for i in mem.get("industries", []))
    concepts = ", ".join(c.get("name", "") for c in mem.get("concepts", []))

    md = f"""# {m['name']}({m['code']}) 调研简报
**快照日期**:{snap['snapshot_date']}  **生成时间**:{m['generated_at']}  **触发**:{m['trigger']}

## 1. 基础面
- 现价 {f['price']:.2f}({f['change_pct']:+.2f}%),PE {f['pe_ttm']},PB {f['pb']}
- 总市值 {f['mcap_yi']:.0f} 亿 / 流通 {f['float_mcap_yi']:.0f} 亿
- 行业:{f['industry']}
- 涨跌停区间:{f['limit_down']:.2f} ~ {f['limit_up']:.2f}

## 2. 板块归属
- 行业:{industries or '未知'}
- 概念:{concepts or '无'}

## 3. 资金流(120 日)
- 5 日累计:{ff['5d_cumulative']/1e8:+.2f} 亿
- 20 日累计:{ff['20d_cumulative']/1e8:+.2f} 亿

## 4. 研报(近 30 日 {res['report_count_30d']} 份)
| 日期 | 机构 | 评级 | 标题 |
|---|---|---|---|
"""
    for r in res["reports"]:
        md += f"| {r.get('date', '')} | {r.get('org', '')} | {r.get('rating', '')} | {r.get('title', '')[:50]} |\n"

    md += f"""
## 5. 一致预期
- {len(cons.get('eps_forecasts', []))} 家覆盖,首条:{cons['eps_forecasts'][0] if cons.get('eps_forecasts') else '无'}

## 6. 风险点
"""
    for r in snap.get("risks", []):
        md += f"- {r}\n"

    ai = snap.get("ai_analysis")
    if ai:
        md += f"""
## 7. AI 跨信号分析
{ai}
"""
    else:
        md += """
## 7. AI 跨信号分析
<!-- 等分析:让 Claude Code 读取本 JSON 快照后填充,会写回 ai_analysis 字段 -->
"""
    return md


def _date_offset(date_str: str, days: int) -> str:
    from datetime import datetime, timedelta
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")
```

- [ ] **Step 3:跑测试**

Run: `python -m pytest tests/test_brief_builder.py -v`
Expected: 2 passed

- [ ] **Step 4:commit**

```bash
git add py/a_screen/brief_builder.py tests/test_brief_builder.py
git commit -m "feat(a_screen): add brief_builder with snapshot assembly and markdown"
```

## Task 2.4:`snapshot.py` —— brief 快照读写

**Files:**
- Create: `py/a_screen/snapshot.py`
- Create: `tests/test_snapshot.py`

**Interfaces:**
- Produces:
  - `save_snapshot(snap: dict) -> Path`
  - `load_snapshot(code: str, date: str, force: bool = False) -> dict | None`
  - `save_markdown(snap: dict, md: str) -> Path`
  - `update_ai_analysis(code: str, date: str, analysis: str) -> None`

- [ ] **Step 1:写测试**

```python
import json
import py.config as cfg
from py.a_screen.snapshot import save_snapshot, load_snapshot, update_ai_analysis, save_markdown

def test_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "BRIEFS_DIR", tmp_path)
    snap = {"meta": {"code": "000001"}, "snapshot_date": "2026-06-26", "ai_analysis": None}
    p = save_snapshot(snap)
    assert p.exists()
    loaded = load_snapshot("000001", "2026-06-26")
    assert loaded["meta"]["code"] == "000001"

def test_update_ai_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "BRIEFS_DIR", tmp_path)
    snap = {"meta": {"code": "000002"}, "snapshot_date": "2026-06-26", "ai_analysis": None}
    save_snapshot(snap)
    update_ai_analysis("000002", "2026-06-26", "建议观望")
    loaded = load_snapshot("000002", "2026-06-26")
    assert loaded["ai_analysis"] == "建议观望"
```

- [ ] **Step 2:写 `py/a_screen/snapshot.py`**

```python
"""brief 快照读写。"""
import json
from pathlib import Path
import py.config as cfg


def _path(code: str, date: str, ext: str = "json") -> Path:
    return cfg.BRIEFS_DIR / code / f"{date}.{ext}"


def save_snapshot(snap: dict) -> Path:
    p = _path(snap["meta"]["code"], snap["snapshot_date"], "json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snap, ensure_ascii=False, indent=2, default=str))
    return p


def load_snapshot(code: str, date: str, force: bool = False) -> dict | None:
    p = _path(code, date, "json")
    if not p.exists() or force:
        return None
    return json.loads(p.read_text())


def save_markdown(snap: dict, md: str) -> Path:
    p = _path(snap["meta"]["code"], snap["snapshot_date"], "md")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(md)
    return p


def update_ai_analysis(code: str, date: str, analysis: str) -> None:
    snap = load_snapshot(code, date)
    if snap is None:
        raise FileNotFoundError(f"no snapshot for {code} {date}")
    snap["ai_analysis"] = analysis
    from datetime import datetime
    snap.setdefault("ai_analysis_meta", {})
    snap["ai_analysis_meta"]["analyzed_at"] = datetime.now().isoformat()
    save_snapshot(snap)
```

- [ ] **Step 3:跑测试**

Run: `python -m pytest tests/test_snapshot.py -v`
Expected: 2 passed

- [ ] **Step 4:commit**

```bash
git add py/a_screen/snapshot.py tests/test_snapshot.py
git commit -m "feat(a_screen): add snapshot read/write with ai_analysis update"
```

## Task 2.5:`decision_log.py` —— decisions CRUD 业务层

**Files:**
- Create: `py/a_screen/decision_log.py`
- Create: `tests/test_decision_log.py`

**Interfaces:**
- Produces:
  - `add_buy(...) -> int` (包装 db.insert_decision,默认 action='buy')
  - `add_add(...) -> int`
  - `close(id, close_date, close_price, reason) -> None`
  - `update_plan(id, **plan_fields) -> None`
  - `list_open(strategy=None) -> list[Row]`
  - `get(id) -> Row`

- [ ] **Step 1:写测试**

```python
import py.db as db
import py.a_screen.decision_log as dl

def setup_function(_):
    db.init_decisions_db()

def test_add_buy_returns_id():
    new_id = dl.add_buy(code="000001", name="平安银行", strategy="short",
                         price=10.0, quantity=1000,
                         plan_stop_loss=9.5, plan_target=11.0)
    assert isinstance(new_id, int)
    row = dl.get(new_id)
    assert row["code"] == "000001"
    assert row["action"] == "buy"
    assert row["close_date"] is None

def test_close_computes_pnl():
    new_id = dl.add_buy(code="000001", strategy="short", price=10.0, quantity=1000)
    dl.close(new_id, "2026-07-01", 11.0, "target")
    row = dl.get(new_id)
    assert row["close_price"] == 11.0
    assert row["pnl_pct"] == 10.0
    assert row["close_reason"] == "target"

def test_list_open_filters_closed():
    id1 = dl.add_buy(code="000001", strategy="short", price=10.0, quantity=1000)
    id2 = dl.add_buy(code="000002", strategy="short", price=20.0, quantity=500)
    dl.close(id1, "2026-07-01", 11.0, "target")
    open_rows = dl.list_open()
    codes = {r["code"] for r in open_rows}
    assert "000001" not in codes
    assert "000002" in codes

def test_update_plan():
    new_id = dl.add_buy(code="000001", strategy="short", price=10.0, quantity=1000,
                        plan_stop_loss=9.0)
    dl.update_plan(new_id, plan_stop_loss=9.5)
    row = dl.get(new_id)
    assert row["plan_stop_loss"] == 9.5
```

- [ ] **Step 2:写 `py/a_screen/decision_log.py`**

```python
"""decisions 业务层包装。"""
from datetime import datetime
import py.db as db
import py.config as cfg


def add_buy(*, code, strategy, price, quantity, name=None, reason=None,
            brief_snapshot_path=None,
            plan_stop_loss=None, plan_target=None, plan_hold_days=None,
            plan_max_position_pct=None) -> int:
    if not name:
        # 简化:不查名称,留给前端展示
        name = code
    return db.insert_decision(
        code=code, name=name, strategy=strategy, action="buy",
        decision_date=datetime.now().strftime("%Y-%m-%d"),
        decision_time=datetime.now().strftime("%H:%M:%S"),
        price=price, quantity=quantity,
        reason=reason, brief_snapshot_path=brief_snapshot_path,
        plan_stop_loss=plan_stop_loss, plan_target=plan_target,
        plan_hold_days=plan_hold_days,
        plan_max_position_pct=plan_max_position_pct,
    )


def add_add(*, code, strategy, price, quantity, reason=None) -> int:
    return db.insert_decision(
        code=code, strategy=strategy, action="add",
        decision_date=datetime.now().strftime("%Y-%m-%d"),
        decision_time=datetime.now().strftime("%H:%M:%S"),
        price=price, quantity=quantity, reason=reason,
    )


def close(decision_id: int, close_date: str, close_price: float, close_reason: str) -> None:
    row = db.conn(cfg.DECISIONS_DB).__enter__().execute(
        "SELECT price FROM decisions WHERE id=?", (decision_id,)
    ).fetchone()
    if not row:
        raise ValueError(f"no decision {decision_id}")
    pnl_pct = (close_price - row["price"]) / row["price"] * 100 if row["price"] else 0
    db.update_decision_close(decision_id, close_date, close_price, close_reason, pnl_pct)


def update_plan(decision_id: int, **plan_fields) -> None:
    if not plan_fields:
        return
    sets = ",".join(f"{k}=?" for k in plan_fields)
    with db.conn(cfg.DECISIONS_DB) as c:
        c.execute(f"UPDATE decisions SET {sets}, updated_at=datetime('now') WHERE id=?",
                  (*plan_fields.values(), decision_id))


def list_open(strategy: str | None = None):
    with db.conn(cfg.DECISIONS_DB) as c:
        if strategy:
            return c.execute(
                "SELECT * FROM decisions WHERE close_date IS NULL AND strategy=? ORDER BY decision_date DESC",
                (strategy,)).fetchall()
        return c.execute(
            "SELECT * FROM decisions WHERE close_date IS NULL ORDER BY decision_date DESC"
        ).fetchall()


def get(decision_id: int):
    with db.conn(cfg.DECISIONS_DB) as c:
        return c.execute("SELECT * FROM decisions WHERE id=?",
                         (decision_id,)).fetchone()
```

- [ ] **Step 3:跑测试**

Run: `python -m pytest tests/test_decision_log.py -v`
Expected: 4 passed

- [ ] **Step 4:commit**

```bash
git add py/a_screen/decision_log.py tests/test_decision_log.py
git commit -m "feat(a_screen): add decision_log CRUD with pnl calculation"
```

**Phase 2 完成验收**:
- `python -m pytest tests/ -v` 全 pass
- 所有 `a_screen/` 模块用 mock 数据层测试通过
- 业务层 import 干净:`python -c "from py.a_screen import sector_scan, candidate_filter, brief_builder, snapshot, decision_log"`

---

# Phase 3: Screener 入口(2 天)

> 目标:`screener.py` 完成,跑一次 E2E 能产出 `data/screen/daily/<date>/report.html` + SQLite 行 + JSON。

## Task 3.1:`screener.py` —— 主入口编排

**Files:**
- Create: `py/screener.py`

**Interfaces:**
- Produces:CLI 命令见 spec 8.1

- [ ] **Step 1:写 `py/screener.py`**

```python
#!/usr/bin/env python3
"""Screener v2:全市场扫描 + 短线/中线双轨。"""
import argparse
import json
import sys
import time
from datetime import datetime, date
from pathlib import Path
import py.config as cfg
import py.db as db
from py.a_screen.sector_scan import scan_sectors
from py.a_screen.candidate_filter import initial_filter, score_candidate
from py.a_stock_data import (
    industry_comparison, ths_hot_reason, daily_dragon_tiger,
    tencent_quote, eastmoney_concept_blocks, stock_fund_flow_120d,
    eastmoney_reports,
)

PUSH2_CLIST = "https://push2.eastmoney.com/api/qt/clist/get"


def fetch_market_stocks(top_n: int = 200) -> list[dict]:
    """Step 2:push2 clist 全市场。"""
    import requests
    fs = "m:0+t:6+f:!50,m:0+t:80+f:!50,m:0+t:81+f:!50,m:0+t:82+f:!50"
    fields = "f12,f14,f2,f3,f62,f66,f72"
    url = (
        f"{PUSH2_CLIST}?pn=1&pz={top_n}&po=1&np=1"
        f"&ut=bd1d9ddb04089700cf9c27f6f7426281"
        f"&fltt=2&invt=2&fid=f62&fs={fs}&fields={fields}"
    )
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"}
    r = requests.get(url, headers=headers, timeout=20)
    d = r.json().get("data", {})
    out = []
    for row in d.get("diff", []):
        out.append({
            "code": row.get("f12", ""),
            "name": row.get("f14", ""),
            "price": row.get("f2", 0) or 0,
            "change_pct": row.get("f3", 0) or 0,
            "net_flow": (row.get("f62") or 0) * 10000,  # 万→元
            "inflow": (row.get("f66") or 0) * 10000,
            "outflow": (row.get("f72") or 0) * 10000,
        })
    return out


def enrich(stocks: list[dict], strategy: str, trade_date: str) -> list[dict]:
    """Step 4:em_get 防封逐股 enrichment。"""
    enriched = []
    for s in stocks:
        code = s["code"]
        try:
            blocks = eastmoney_concept_blocks(code)
            s["sector"] = blocks["industries"][0]["name"] if blocks.get("industries") else ""
            s["concept_primary"] = blocks["concepts"][0]["name"] if blocks.get("concepts") else ""

            flows = stock_fund_flow_120d(code)
            s["fund_flow_20d"] = sum(r.get("main", 0) for r in flows[:20])

            reports = eastmoney_reports(code, max_pages=1)
            recent_7d = [r for r in reports if r.get("date", "") >= _date_offset(trade_date, -7)]
            s["report_count_7d"] = len(recent_7d)

            # 估值(用 tq 单股查,本步只对 top N 调)
            tq = tencent_quote([code]).get(code, {})
            s["pe_ttm"] = tq.get("pe_ttm", 0)
            s["pb"] = tq.get("pb", 0)
            s["mcap_yi"] = tq.get("mcap_yi", 0)
            s["turnover_pct"] = tq.get("turnover_pct", 0)
        except Exception as e:
            print(f"  ⚠ {code} enrich 失败:{e}", file=sys.stderr)
            s.setdefault("data_quality", "partial")
        enriched.append(s)
    return enriched


def run(trade_date: str, strategies: list[str], top_n: int, enrich_top: int, force: bool):
    print(f"⏳ Screener @ {trade_date} 策略={strategies}", flush=True)
    t0 = time.time()

    db.init_screener_db()

    # Step 1:市场级
    print("  Step 1: 行业板块...", end=" ", flush=True)
    sectors = scan_sectors(trade_date)
    print(f"行业 {len(sectors.get('industry', []))}, 热点 {len(sectors.get('hot', []))}, 龙虎榜 {len(sectors.get('dragon_tiger', []))}")

    # Step 2:全市场
    print("  Step 2: 全市场 clist...", end=" ", flush=True)
    raw = fetch_market_stocks(top_n=200)
    print(f"{len(raw)} 只")

    # Step 3:各策略初筛
    candidates_by_strategy = {}
    for strat in strategies:
        cand = initial_filter(raw, strat)
        candidates_by_strategy[strat] = cand[:enrich_top]
        print(f"  Step 3[{strat}]: {len(cand)} → top {len(candidates_by_strategy[strat])}")

    # Step 4:enrichment
    print("  Step 4: enrichment...", end=" ", flush=True)
    for strat, cands in candidates_by_strategy.items():
        candidates_by_strategy[strat] = enrich(cands, strat, trade_date)
    print(f"done in {time.time()-t0:.0f}s")

    # Step 5:评分
    print("  Step 5: 评分...", end=" ", flush=True)
    for strat, cands in candidates_by_strategy.items():
        for c in cands:
            c["score"] = score_candidate(c, strat, sectors)
        cands.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)

    # Step 6:落盘
    out_dir = cfg.DAILY_DIR / trade_date
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "sectors.json").write_text(json.dumps(sectors, ensure_ascii=False, indent=2, default=str))

    for strat, cands in candidates_by_strategy.items():
        (out_dir / f"candidates_{strat}.json").write_text(
            json.dumps(cands, ensure_ascii=False, indent=2, default=str)
        )
        for c in cands:
            db.upsert_candidate(
                trade_date, strat, c["code"],
                name=c.get("name"),
                sector=c.get("sector", ""),
                concept_primary=c.get("concept_primary", ""),
                net_flow=c.get("net_flow", 0),
                change_pct=c.get("change_pct", 0),
                pe_ttm=c.get("pe_ttm", 0),
                pb=c.get("pb", 0),
                mcap_yi=c.get("mcap_yi", 0),
                turnover_pct=c.get("turnover_pct", 0),
                report_count_7d=c.get("report_count_7d", 0),
                hot_reason="",
                on_dragon_tiger=int(any(dt.get("code") == c["code"] for dt in sectors.get("dragon_tiger", []))),
                score=c.get("score", 0),
                raw_data_path=str(out_dir / f"candidates_{strat}.json"),
            )

    db.upsert_daily_summary(
        trade_date,
        generated_at=datetime.now().isoformat(),
        short_count=len(candidates_by_strategy.get("short", [])),
        mid_count=len(candidates_by_strategy.get("mid", [])),
        sector_count=len(sectors.get("industry", [])),
        report_path=str(out_dir / "report.html"),
        status="ok",
    )
    print(f"\n✓ 完成 {time.time()-t0:.0f}s → {out_dir}")


def _date_offset(date_str: str, days: int) -> str:
    d = datetime.strptime(date_str, "%Y-%m-%d")
    from datetime import timedelta
    return (d + timedelta(days=days)).strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--strategy", choices=["short", "mid", "both"], default="both")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--enrich-top", type=int, default=30)
    ap.add_argument("--no-html", action="store_true")
    ap.add_argument("--render-only", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    strategies = ["short", "mid"] if args.strategy == "both" else [args.strategy]
    run(args.date, strategies, args.top_n, args.enrich_top, args.force)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2:chmod +x,语法检查**

```bash
chmod +x py/screener.py
python -c "import py.screener; print('OK')"
```

- [ ] **Step 3:跑一次(用过去日期避免影响今日)**

```bash
python py/screener.py --date 2026-06-25 --strategy short --top-n 5 --enrich-top 3
```

Expected: 跑完,`data/screen/daily/2026-06-25/candidates_short.json` 存在

- [ ] **Step 4:commit**

```bash
git add py/screener.py
git commit -m "feat(screener): main entry with E2E pipeline"
```

## Task 3.2:`report.html` 渲染

**Files:**
- Modify: `py/screener.py`(追加 `render_html` 函数 + `--render-only` 支持)

- [ ] **Step 1:在 `py/screener.py` 的 `main()` 后追加**

```python
def render_html(trade_date: str):
    """从 SQLite 读 daily_summary + candidate_history,渲染 report.html。"""
    out_dir = cfg.DAILY_DIR / trade_date
    out_dir.mkdir(parents=True, exist_ok=True)
    with db.conn(cfg.SCREENER_DB) as c:
        sectors = c.execute(
            "SELECT * FROM sector_history WHERE scan_date=? AND sector_type='industry' ORDER BY net_flow DESC LIMIT 15",
            (trade_date,)).fetchall()
        short = c.execute(
            "SELECT * FROM candidate_history WHERE scan_date=? AND strategy='short' ORDER BY score DESC LIMIT 20",
            (trade_date,)).fetchall()
        mid = c.execute(
            "SELECT * FROM candidate_history WHERE scan_date=? AND strategy='mid' ORDER BY score DESC LIMIT 20",
            (trade_date,)).fetchall()

    html = ['<!doctype html><html><head><meta charset="utf-8"><title>Screener Report</title>',
            '<style>body{font-family:sans-serif;max-width:1200px;margin:20px auto;padding:0 20px;}',
            'table{border-collapse:collapse;width:100%;margin:10px 0;}',
            'th,td{border:1px solid #ddd;padding:6px 10px;text-align:left;}',
            'th{background:#f5f5f5;}',
            'h1,h2{color:#333;} .pos{color:#c00;} .neg{color:#0a0;}</style></head><body>']
    html.append(f"<h1>Screener 日报 {trade_date}</h1>")

    html.append("<h2>行业板块资金流 TOP15</h2><table><tr><th>行业</th><th>涨跌幅</th><th>净流入(亿)</th><th>领涨股</th></tr>")
    for s in sectors:
        nf = (s["net_flow"] or 0) / 1e8
        html.append(f"<tr><td>{s['name']}</td><td>{s['change_pct']:+.2f}%</td>"
                    f"<td>{nf:+.2f}</td><td>{s['leader_name'] or ''}</td></tr>")
    html.append("</table>")

    for strat_name, rows in [("短线 TOP20", short), ("中线 TOP20", mid)]:
        html.append(f"<h2>{strat_name}</h2><table><tr><th>代码</th><th>名称</th><th>行业</th>"
                    "<th>涨跌幅</th><th>净流入(亿)</th><th>PE</th><th>7日研报</th><th>评分</th></tr>")
        for r in rows:
            nf = (r["net_flow"] or 0) / 1e8
            html.append(f"<tr><td>{r['code']}</td><td>{r['name'] or ''}</td><td>{r['sector'] or ''}</td>"
                        f"<td>{r['change_pct']:+.2f}%</td><td>{nf:+.2f}</td>"
                        f"<td>{r['pe_ttm'] or 0:.1f}</td><td>{r['report_count_7d'] or 0}</td>"
                        f"<td><b>{r['score'] or 0:.1f}</b></td></tr>")
        html.append("</table>")

    html.append("</body></html>")
    (out_dir / "report.html").write_text("\n".join(html))
    print(f"✓ 渲染 → {out_dir / 'report.html'}")
```

- [ ] **Step 2:`main()` 加 `--render-only` 处理**

```python
    if args.render_only:
        render_html(args.date)
        return
```

- [ ] **Step 3:跑 render-only**

```bash
python py/screener.py --date 2026-06-25 --render-only
```

Expected: `data/screen/daily/2026-06-25/report.html` 存在

- [ ] **Step 4:浏览器打开 report.html,验证布局**

- [ ] **Step 5:commit**

```bash
git add py/screener.py
git commit -m "feat(screener): add HTML report rendering"
```

## Task 3.3:Phase 3 smoke test

**Files:**
- Create: `tests/smoke/run_daily.sh`

- [ ] **Step 1:写 smoke 脚本**

```bash
#!/bin/bash
# tests/smoke/run_daily.sh
# 用最近一个 A股交易日(周三/周五)跑完整 E2E
set -e
cd "$(dirname "$0")/../.."

# 用最近一个 A股交易日;手测时改成具体日期(如 2026-06-25)
TRADE_DATE=${TRADE_DATE:-$(python -c "from datetime import date, timedelta; print((date.today() - timedelta(days=1)).isoformat())")}

echo "=== Phase 3 smoke: $TRADE_DATE ==="
python py/screener.py --date "$TRADE_DATE" --strategy short --top-n 5 --enrich-top 3
python py/screener.py --date "$TRADE_DATE" --render-only

# 验证产物
test -f "data/screen/daily/$TRADE_DATE/candidates_short.json" || { echo "FAIL: no candidates_short.json"; exit 1; }
test -f "data/screen/daily/$TRADE_DATE/report.html" || { echo "FAIL: no report.html"; exit 1; }
echo "✓ PASS"
```

- [ ] **Step 2:跑 smoke**

```bash
chmod +x tests/smoke/run_daily.sh
bash tests/smoke/run_daily.sh
```

- [ ] **Step 3:commit**

```bash
git add tests/smoke/
git commit -m "test: add Phase 3 smoke script"
```

**Phase 3 完成验收**:
- `python py/screener.py --date 2026-06-25 --strategy both` 跑通
- `report.html` 可在浏览器打开,显示行业表 + 短线/中线候选
- `data/screen.sqlite` 的 `candidate_history` 至少有 6 行(3 短 + 3 中)
- smoke 脚本 PASS

---

# Phase 4: Brief 入口(2 天)

> 目标:`brief.py` 完成单股 + 批量模式,AI handoff 流程端到端验证。

## Task 4.1:`brief.py` 单股

**Files:**
- Create: `py/brief.py`

**Interfaces:**
- Produces:CLI 见 spec 8.2

- [ ] **Step 1:写 `py/brief.py`**

```python
#!/usr/bin/env python3
"""Research Brief:单股调研简报。"""
import argparse
import sys
from datetime import date
import py.config as cfg
from py.a_screen.brief_builder import build_snapshot, render_markdown
from py.a_screen.snapshot import save_snapshot, save_markdown, load_snapshot


def single(code: str, trade_date: str, force: bool, strategy: str | None):
    """单股 brief。"""
    code = code.strip()
    snap = load_snapshot(code, trade_date, force=force)
    if snap is None:
        print(f"⏳ 拉 {code} 数据...", flush=True)
        snap = build_snapshot(code, trade_date, trigger="manual")
        save_snapshot(snap)
    md = render_markdown(snap)
    save_markdown(snap, md)
    print(md)
    print(f"\n💾 快照:{cfg.BRIEFS_DIR / code / trade_date}.json")
    print(f"   AI 分析待 Claude Code 填充;调 update_ai_analysis() 写回。")


def batch_from_screener(trade_date: str, top_n: int):
    """从今日扫描的 top N 各策略自动生成。"""
    import py.db as db
    db.init_screener_db()
    generated = 0
    with db.conn(cfg.SCREENER_DB) as c:
        for strat in ("short", "mid"):
            rows = c.execute(
                "SELECT code, name FROM candidate_history WHERE scan_date=? AND strategy=? ORDER BY score DESC LIMIT ?",
                (trade_date, strat, top_n)).fetchall()
            for r in rows:
                code = r["code"]
                if load_snapshot(code, trade_date) is not None:
                    continue
                try:
                    print(f"  brief {code}({r['name']})...", flush=True)
                    snap = build_snapshot(code, trade_date, trigger=f"from_screener_{strat}")
                    save_snapshot(snap)
                    md = render_markdown(snap)
                    save_markdown(snap, md)
                    generated += 1
                except Exception as e:
                    print(f"  ⚠ {code} 失败:{e}", file=sys.stderr)
    print(f"✓ 生成 {generated} 份 brief")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?", help="股票代码(单股模式)")
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--strategy", choices=["short", "mid"], help="强调某策略的字段")
    ap.add_argument("--from-screener", metavar="DATE_OR_TODAY",
                    help="从 screener 拉 top N 批量生成")
    ap.add_argument("--top-n", type=int, default=10)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.from_screener:
        d = date.today().isoformat() if args.from_screener == "today" else args.from_screener
        batch_from_screener(d, args.top_n)
    elif args.code:
        single(args.code, args.date, args.force, args.strategy)
    else:
        ap.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2:chmod + 跑一次**

```bash
chmod +x py/brief.py
python py/brief.py 000858 --date 2026-06-25
```

Expected: 输出 markdown 简报 + 落盘 `data/screen/briefs/000858/2026-06-25.{json,md}`

- [ ] **Step 3:commit**

```bash
git add py/brief.py
git commit -m "feat(brief): single + batch-from-screener modes"
```

## Task 4.2:批量 from-screener 验证

- [ ] **Step 1:跑**

```bash
python py/brief.py --from-screener 2026-06-25 --top-n 5
```

Expected: 至少 10 份 brief(5 短 + 5 中),日志打印每只

- [ ] **Step 2:commit(if changed anything)**

## Task 4.3:AI handoff 流程验证

**Files:**
- Create: `tests/integration/test_ai_handoff.py`

- [ ] **Step 1:写测试(手工验证)** —— 此 task 主要让你在对话中验证

- [ ] **Step 2:让 Claude Code 读取快照**

步骤:
1. 用户说"分析 000858"
2. Claude 用 Read 工具读 `data/screen/briefs/000858/2026-06-25.json`
3. Claude 输出 ai_analysis 文本
4. 用户确认后,Claude 调 `py.a_screen.snapshot.update_ai_analysis("000858", "2026-06-25", text)`
5. 重跑 `python py/brief.py 000858 --date 2026-06-25`,MD 第 7 节填上了

- [ ] **Step 3:把验证过程写进 `docs/superpowers/specs/2026-06-26-handoff-howto.md`**(可选,1 页)

- [ ] **Step 4:commit**

```bash
git add tests/integration/test_ai_handoff.py docs/superpowers/specs/2026-06-26-handoff-howto.md
git commit -m "docs: AI handoff流程验证"
```

**Phase 4 完成验收**:
- `python py/brief.py 000858` 出 markdown
- `python py/brief.py --from-screener today` 自动生成 top 10×2
- AI handoff:Claude 读 JSON → 写 ai_analysis → 重生成 MD 完整

---

# Phase 5: 复盘入口(2 天)

> 目标:`log.py` + `stats.py` 完整,纪律性查询可跑。

## Task 5.1:`log.py` 简化模式

**Files:**
- Create: `py/log.py`

- [ ] **Step 1:写 `py/log.py`**

```python
#!/usr/bin/env python3
"""复盘决策记录 CLI。"""
import argparse
import sys
from datetime import date, datetime
import py.config as cfg
import py.db as db
from py.a_screen.decision_log import add_buy, add_add, close, update_plan, list_open, get
from py.a_screen.snapshot import load_snapshot


def _auto_brief_path(code: str) -> str | None:
    """检测今日 brief 路径,若存在则返回。"""
    p = cfg.BRIEFS_DIR / code / f"{date.today().isoformat()}.json"
    return str(p) if p.exists() else None


def cmd_buy(args):
    code = args.code
    # 简化模式 vs 显式
    if args.price is None:
        return _interactive_buy(code, args.strategy, args.plan_max_pct)

    brief_path = args.from_brief or _auto_brief_path(code)
    new_id = add_buy(
        code=code, strategy=args.strategy,
        price=args.price, quantity=args.qty,
        reason=args.reason, brief_snapshot_path=brief_path,
        plan_stop_loss=args.plan_stop, plan_target=args.plan_target,
        plan_hold_days=args.plan_hold, plan_max_position_pct=args.plan_max_pct,
    )
    print(f"✓ 已记录 buy id={new_id}  brief={'已挂' if brief_path else '无'}")


def _interactive_buy(code: str, strategy: str, plan_max_pct: float | None):
    """简化模式:检测 brief,预填价格,交互式问其余。"""
    brief_path = _auto_brief_path(code)
    price = None
    if brief_path:
        snap = load_snapshot(code, date.today().isoformat())
        if snap:
            price = snap["fundamentals"].get("price")
            print(f"[检测到 brief] {snap['meta']['name']}({code}) 现价 {price}")

    if price is None:
        price = float(input(f"现价 [{code}]: "))

    qty = int(input(f"数量(股) [100]: ") or "100")
    reason = input("一句话理由: ")
    stop = float(input(f"计划止损 [{price*0.95:.2f}]: ") or str(price * 0.95))
    target = float(input(f"计划目标 [{price*1.10:.2f}]: ") or str(price * 1.10))
    hold = int(input("计划持有天数 [5]: ") or "5")
    max_pct = float(input(f"最大仓位 % [{plan_max_pct or 10}]: ") or str(plan_max_pct or 10))

    new_id = add_buy(
        code=code, strategy=strategy,
        price=price, quantity=qty,
        reason=reason, brief_snapshot_path=brief_path,
        plan_stop_loss=stop, plan_target=target,
        plan_hold_days=hold, plan_max_position_pct=max_pct,
    )
    print(f"\n✓ 已记录 buy id={new_id}")
    print(f"  strategy={strategy}  price={price}  qty={qty}")
    print(f"  plan: stop={stop} target={target} hold={hold}d max_pct={max_pct}%")
    print(f"  brief: {brief_path or '无'}")


def cmd_add(args):
    new_id = add_add(
        code=args.code, strategy=args.strategy,
        price=args.price, quantity=args.qty, reason=args.reason,
    )
    print(f"✓ 加仓 id={new_id}")


def cmd_close(args):
    close(args.id, args.close_date, args.close_price, args.close_reason)
    row = get(args.id)
    print(f"✓ 平仓 id={args.id}  pnl={row['pnl_pct']:+.2f}%")


def cmd_plan(args):
    fields = {k: v for k, v in vars(args).items()
              if k.startswith("plan_") and v is not None}
    if not fields:
        print("无 plan_ 前缀的参数可更新", file=sys.stderr)
        sys.exit(1)
    update_plan(args.id, **fields)
    print(f"✓ 更新 id={args.id}  plan={fields}")


def cmd_list(args):
    rows = list_open(args.strategy) if not args.all else _list_all(args.strategy, args.recent)
    if not rows:
        print("无记录")
        return
    print(f"{'id':>4}  {'code':<8}  {'name':<10}  {'strat':<6}  {'date':<10}  {'price':<8}  {'qty':<6}  {'close':<10}  {'pnl%':<7}")
    for r in rows[:args.recent]:
        print(f"{r['id']:>4}  {r['code']:<8}  {(r['name'] or ''):<10}  {r['strategy']:<6}  "
              f"{r['decision_date']:<10}  {r['price']:<8.2f}  {r['quantity']:<6}  "
              f"{(r['close_date'] or '-'):<10}  {(r['pnl_pct'] or 0):<+7.2f}")


def _list_all(strategy, recent):
    with db.conn(cfg.DECISIONS_DB) as c:
        return c.execute(
            "SELECT * FROM decisions WHERE strategy=? ORDER BY decision_date DESC LIMIT ?",
            (strategy, recent)).fetchall()


def cmd_show(args):
    row = get(args.id)
    if not row:
        print(f"无 id={args.id}")
        return
    for k in row.keys():
        print(f"  {k}: {row[k]}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_buy = sub.add_parser("buy")
    p_buy.add_argument("code")
    p_buy.add_argument("--strategy", choices=["short", "mid"], required=True)
    p_buy.add_argument("--price", type=float)
    p_buy.add_argument("--qty", type=int)
    p_buy.add_argument("--reason")
    p_buy.add_argument("--from-brief")
    p_buy.add_argument("--plan-stop", type=float, dest="plan_stop_loss")
    p_buy.add_argument("--plan-target", type=float, dest="plan_target")
    p_buy.add_argument("--plan-hold", type=int, dest="plan_hold_days")
    p_buy.add_argument("--plan-max-pct", type=float, dest="plan_max_position_pct")
    p_buy.set_defaults(func=cmd_buy)

    p_add = sub.add_parser("add")
    p_add.add_argument("code")
    p_add.add_argument("--strategy", choices=["short", "mid"], required=True)
    p_add.add_argument("--price", type=float, required=True)
    p_add.add_argument("--qty", type=int, required=True)
    p_add.add_argument("--reason")
    p_add.set_defaults(func=cmd_add)

    p_close = sub.add_parser("close")
    p_close.add_argument("id", type=int)
    p_close.add_argument("--close-date", required=True)
    p_close.add_argument("--close-price", type=float, required=True)
    p_close.add_argument("--close-reason", required=True, choices=["stop_loss", "target", "manual", "expired"])
    p_close.set_defaults(func=cmd_close)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("id", type=int)
    p_plan.add_argument("--plan-stop", type=float, dest="plan_stop_loss")
    p_plan.add_argument("--plan-target", type=float, dest="plan_target")
    p_plan.add_argument("--plan-hold", type=int, dest="plan_hold_days")
    p_plan.set_defaults(func=cmd_plan)

    p_list = sub.add_parser("list")
    p_list.add_argument("--open", action="store_true")
    p_list.add_argument("--all", action="store_true")
    p_list.add_argument("--strategy", choices=["short", "mid"])
    p_list.add_argument("--recent", type=int, default=20)
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show")
    p_show.add_argument("id", type=int)
    p_show.set_defaults(func=cmd_show)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2:chmod + 跑**

```bash
chmod +x py/log.py
python py/log.py list --open   # 暂无
```

- [ ] **Step 3:commit**

```bash
git add py/log.py
git commit -m "feat(log): CLI with simplified and explicit modes"
```

## Task 5.2:`stats.py` 总览 + 按策略/按股

**Files:**
- Create: `py/stats.py`
- Create: `tests/test_stats.py`

- [ ] **Step 1:写测试**

```python
import py.db as db
import py.a_screen.decision_log as dl
import py.stats as stats

def setup_function(_):
    db.init_decisions_db()

def test_stats_overall():
    # 制造样本数据
    for i, (price, close, reason) in enumerate([
        (10, 11, "target"), (10, 9, "stop_loss"), (10, 12, "target"),
        (10, 9.5, "manual"), (10, 11.5, "expired"),
    ]):
        id_ = dl.add_buy(code=f"00000{i}", strategy="short", price=price, quantity=100)
        dl.close(id_, "2026-07-01", close, reason)

    s = stats.compute_overall()
    assert s["total"] == 5
    assert 0 <= s["win_rate"] <= 1
    assert 0 <= s["discipline_rate"] <= 1

def test_stats_by_strategy():
    for code in ["A", "B"]:
        id_ = dl.add_buy(code=code, strategy="mid", price=10, quantity=100)
        dl.close(id_, "2026-07-01", 11, "target")
    s = stats.compute_by_strategy("mid")
    assert s["total"] == 2
    assert s["win_rate"] == 1.0
```

- [ ] **Step 2:写 `py/stats.py`**

```python
"""复盘统计查询。"""
import argparse
import sys
from datetime import datetime, timedelta
import py.config as cfg
import py.db as db


def _query(sql: str, params: tuple = ()) -> list:
    with db.conn(cfg.DECISIONS_DB) as c:
        return c.execute(sql, params).fetchall()


def _closed_in_window(window_days: int | None) -> list:
    sql = "SELECT * FROM decisions WHERE close_date IS NOT NULL"
    params = []
    if window_days:
        from datetime import date
        cutoff = (date.today() - timedelta(days=window_days)).isoformat()
        sql += " AND close_date >= ?"
        params.append(cutoff)
    return _query(sql, tuple(params))


def compute_overall(window_days: int | None = None) -> dict:
    rows = _closed_in_window(window_days)
    if not rows:
        return {"total": 0, "win_rate": 0, "avg_pnl": 0, "discipline_rate": 0}
    wins = sum(1 for r in rows if (r["pnl_pct"] or 0) > 0)
    disciplined = sum(1 for r in rows if r["close_reason"] in ("target", "stop_loss"))
    return {
        "total": len(rows),
        "win_rate": round(wins / len(rows), 4),
        "avg_pnl": round(sum(r["pnl_pct"] or 0 for r in rows) / len(rows), 2),
        "discipline_rate": round(disciplined / len(rows), 4),
    }


def compute_by_strategy(strategy: str, window_days: int | None = None) -> dict:
    rows = [r for r in _closed_in_window(window_days) if r["strategy"] == strategy]
    return _agg(rows)


def _agg(rows) -> dict:
    if not rows:
        return {"total": 0, "win_rate": 0, "avg_pnl": 0}
    wins = sum(1 for r in rows if (r["pnl_pct"] or 0) > 0)
    return {
        "total": len(rows),
        "win_rate": round(wins / len(rows), 4),
        "avg_pnl": round(sum(r["pnl_pct"] or 0 for r in rows) / len(rows), 2),
    }


def compute_by_code(code: str) -> dict:
    rows = _query("SELECT * FROM decisions WHERE code=? AND close_date IS NOT NULL", (code,))
    return _agg(rows)


def compute_discipline(window_days: int = 90) -> dict:
    rows = _closed_in_window(window_days)
    if not rows:
        return {"tp_execution": 0, "sl_execution": 0, "early_exit": 0, "panic_exit": 0, "avg_hold_dev": 0}
    profit = [r for r in rows if (r["pnl_pct"] or 0) > 0]
    loss = [r for r in rows if (r["pnl_pct"] or 0) < 0]
    tp_exec = (sum(1 for r in profit if r["close_reason"] == "target") / len(profit)) if profit else 0
    sl_exec = (sum(1 for r in loss if r["close_reason"] == "stop_loss") / len(loss)) if loss else 0
    early = sum(1 for r in rows if r["close_reason"] == "manual" and (r["pnl_pct"] or 0) > 0)
    panic = sum(1 for r in rows if r["close_reason"] == "manual" and (r["pnl_pct"] or 0) < 0)
    devs = []
    for r in rows:
        if r["plan_hold_days"]:
            d1 = datetime.strptime(r["decision_date"], "%Y-%m-%d")
            d2 = datetime.strptime(r["close_date"], "%Y-%m-%d")
            devs.append((d2 - d1).days - r["plan_hold_days"])
    return {
        "tp_execution": round(tp_exec, 4),
        "sl_execution": round(sl_exec, 4),
        "early_exit": round(early / len(rows), 4),
        "panic_exit": round(panic / len(rows), 4),
        "avg_hold_dev": round(sum(devs) / len(devs), 2) if devs else 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=["short", "mid"])
    ap.add_argument("--code")
    ap.add_argument("--discipline", action="store_true")
    ap.add_argument("--window", type=int, default=90)
    ap.add_argument("--recent", type=int, default=20)
    ap.add_argument("--export")
    args = ap.parse_args()

    if args.discipline:
        s = compute_discipline(args.window)
        print("纪律性报告(window=%d 天):" % args.window)
        for k, v in s.items():
            print(f"  {k}: {v}")
    elif args.code:
        s = compute_by_code(args.code)
        print(f"按股 {args.code}: {s}")
    elif args.strategy:
        s = compute_by_strategy(args.strategy, args.window)
        print(f"按策略 {args.strategy}: {s}")
    else:
        s = compute_overall(args.window)
        print(f"总览(window={args.window}天): {s}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3:跑测试**

Run: `python -m pytest tests/test_stats.py -v`
Expected: 2 passed

- [ ] **Step 4:commit**

```bash
git add py/stats.py tests/test_stats.py
git commit -m "feat(stats): CLI with overall/by-strategy/by-code/discipline queries"
```

**Phase 5 完成验收**:
- `python py/log.py list --open` 跑通
- `python py/log.py buy 000001 --strategy short --price 10 --qty 100` 显式模式记录
- `python py/log.py close <id> --close-date 2026-07-01 --close-price 11 --close-reason target` 平仓
- `python py/stats.py` 输出总览
- `python py/stats.py --discipline` 输出纪律性

---

# Phase 6: 自动化(0.5 天)

> 目标:cron 配好,冒烟测试通过,backup 脚本就绪。

## Task 6.1:cron 文件

**Files:**
- Create: `scripts/cron/a-stock-screen`

- [ ] **Step 1:写 cron 文件**

```cron
# /etc/cron.d/a-stock-screen  (Asia/Shanghai)
# A股交易日 15:35-15:50 自动跑全流程;周末与节假日不跑
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
PROJECT=/Users/maerun/Documents/Projects/make-money
PYTHON=python3

35 15 * * 1-5  cd $PROJECT && $PYTHON py/screener.py --no-html > data/screen/cron.log 2>&1
40 15 * * 1-5  cd $PROJECT && $PYTHON py/screener.py --render-only >> data/screen/cron.log 2>&1
45 15 * * 1-5  cd $PROJECT && $PYTHON py/brief.py --from-screener today --top-n 10 >> data/screen/cron.log 2>&1
```

- [ ] **Step 2:commit**

```bash
git add scripts/cron/
git commit -m "ops: add cron file for 15:35-15:50 daily automation"
```

## Task 6.2:backup 脚本

**Files:**
- Create: `scripts/backup.sh`

- [ ] **Step 1:写 backup 脚本**

```bash
#!/bin/bash
# scripts/backup.sh —— 周日 23:00 跑,备份 SQLite + 关键配置
set -e
cd "$(dirname "$0")/.."

BACKUP_DIR="data/backup"
TS=$(date +%Y%m%d)

# SQLite 在线 backup
sqlite3 data/decisions.sqlite ".backup $BACKUP_DIR/decisions_$TS.db"
sqlite3 data/screener.sqlite ".backup $BACKUP_DIR/screener_$TS.db"

# 保留最近 8 周
find $BACKUP_DIR -name "*.db" -mtime +56 -delete

echo "✓ Backup done: $BACKUP_DIR/decisions_$TS.db screener_$TS.db"
```

- [ ] **Step 2:加 cron 行**

```cron
0 23 * * 0  cd /Users/maerun/Documents/Projects/make-money && bash scripts/backup.sh >> data/screen/cron.log 2>&1
```

- [ ] **Step 3:chmod + 手动跑一次**

```bash
chmod +x scripts/backup.sh
bash scripts/backup.sh
ls -la data/backup/
```

- [ ] **Step 4:commit**

```bash
git add scripts/backup.sh
git commit -m "ops: weekly SQLite backup script"
```

## Task 6.3:端到端验证

- [ ] **Step 1:手动跑一遍完整流程**

```bash
# 模拟 15:35 cron
python py/screener.py --date $(date -v-1d +%Y-%m-%d) --strategy both
python py/screener.py --date $(date -v-1d +%Y-%m-%d) --render-only
python py/brief.py --from-screener $(date -v-1d +%Y-%m-%d) --top-n 5
```

- [ ] **Step 2:检查产物**

```bash
ls -la data/screen/daily/$(date -v-1d +%Y-%m-%d)/
# 应该有 sectors.json, candidates_*.json, report.html
ls data/screen/briefs/ | head
# 应该有 ≥10 个 code 子目录
```

- [ ] **Step 3:在浏览器打开 report.html,确认布局正常**

- [ ] **Step 4:写 README 更新到 `py/CLAUDE.md` 或项目根 README,记录四个 CLI 入口**

- [ ] **Step 5:commit + tag**

```bash
git add -A
git commit -m "docs: update README with CLI usage"
git tag v0.1.0
```

**Phase 6 完成验收**:
- cron 文件在 `scripts/cron/`
- backup 脚本可运行
- 端到端一次跑通:扫描 → 渲染 → brief → (可选)log
- README 写好四个 CLI 用法

---

# 全局完成验收

- `python -m pytest tests/ -v` 单元 + 集成(默认 skip)+ smoke 全 pass
- `python py/screener.py --date 2026-06-25 --strategy both` 跑通
- `python py/brief.py 000858` 产出 brief
- `python py/log.py buy 000001 --strategy short --price 10 --qty 100` 记录
- `python py/stats.py --discipline` 输出纪律性
- 端到端:从 `report.html` → `brief.py` → 决策 → `log.py` → 季度 `stats.py`

---

# 已知风险与回退

| 风险 | 触发 | 回退 |
|---|---|---|
| em_get 触发东财封禁 | 5 分钟内 200+ 请求 | 隔日重试;`EM_MIN_INTERVAL` 调到 2.0 |
| 5197 只 OHLCV 部分缺失 | yfinance TLS 失败 | 跑 `download-ohlcv.py` 补齐 |
| `decision_log.close()` 算 pnl 用 entry price | 加仓后未算加权均价 | 加权均价计算 = future 增强,本期接受简化 |
| scoring weights 主观 | 跑 1 个月后感觉不准 | 调 `config.SCORING`,重跑 `--date 历史` 看差异 |
| backup 脚本没测过 cron 集成 | 周日 23:00 失败才发现 | 加个 `scripts/backup.sh` 日志监控 |

---

# 后续扩展(本期不实现)

- `a_screen/backtest.py`:历史回测 screener
- `a_screen/alert.py`:盘中监控 + 微信推送
- iwencai 接入(若研报标题不够用)
- 周报/月报 HTML 聚合
- 行业热力图
- 移动端(读 SQLite 生成静态)

---

# 实施备注(实施者必读)

以下点 plan 里写了但需要实施时验证对齐,**不要盲信 plan 里的代码**:

1. **`industry_comparison(top_n)` 返回结构** — SKILL.md 1209-1257 实施时确认是 `{"industry": [...], "concept": [...]}` 还是 `{"data": [...]}`。Task 2.1 已有注释,跑测试时若 key 不对,调整 `sector_scan.scan_sectors` 即可。

2. **a-stock-data 各函数的 `pages` / `size` 参数语义** — SKILL.md 的 `max_pages` 行为可能与 plan 假设不一致。Task 1.4-1.7 实施时各跑一次冒烟,把实际返回结构对齐 plan 的 mock 数据。

3. **eastmoney_fund_flow_minute 的字段顺序** — SKILL.md 用的是 push2 fflow kline 端点,字段顺序是 `f1,f2,f3,f7` 对应 `time,main,large,small` 还是别的。Task 1.4 plan 里假定了顺序,实施时打印第一条 raw 数据校准。

4. **ths_hot_reason 返回 DataFrame** — plan 里 `_safe_ths_hot` 用 `df.to_dict("records")` 兜底,但同花顺端点可能直接返回 list。Task 1.5 实施时确认。

5. **东财 push2 clist 全市场返回的字段顺序** — Task 3.1 fetch_market_stocks 用 `f12,f14,f2,f3,f62,f66,f72`,这些字段 ID 是东财 push2 的内部索引,**会变**。若发现字段映射错,回到 SKILL.md 1.2 段或东财 push2 文档重新校准。

6. **海外网络下 moo tdx 不可用已确认** — 但 mootdx 的 `BESTIP.HQ` 空串 bug 影响面只在新装环境,我们项目里有现成 venv,直接装 mootdx 不一定踩雷。**不强制 vendor tdx_client**,但实施时若真用 mootdx 要带 `tdx_client()` helper(详见 SKILL.md 186-241)。

7. **decision_log.close() 用 entry price 算 pnl** — 加仓后未算加权均价。短期可接受(简化),中线后建议改成 FIFO 或加权。

8. **close_reason='expired' 的判定** — plan 规定 `plan_hold_days × 1.5` 触发,实施时考虑加个 cron 日任务扫 `decisions WHERE close_date IS NULL AND julianday('now') - julianday(decision_date) > plan_hold_days * 1.5` 提示用户(本 plan 未实现)。

9. **scoring weights 是主观默认值** — 跑 1 个月后根据 `stats.py` 的实际胜率/纪律性调,放在 `config.SCORING` 一处改完生效。

10. **em_get cache 目录 `data/.cache/em/`** — 已加到 `.gitignore` 任务里(Task 1.1)。若之前 .gitignore 已存在,需手工检查。
