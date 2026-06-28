"""共用 helper:em_get 防封、限流、缓存、ticker 归一化、retry。"""
import hashlib
import json
import random
import re
import time
from pathlib import Path
import requests
import a_stock.config as cfg

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
    """读缓存:返回缓存数据或 None(过期或不存在)。"""
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
    if code.startswith(("5", "6", "9")):
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