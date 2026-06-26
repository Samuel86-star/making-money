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