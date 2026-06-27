"""Mac 本地通知: osascript 弹窗 + 限流 + 重试 + 分段.
抄 a-share-quant-selector 的 RateLimiter 三闸门 + 重试骨架, 适配 osascript."""
import argparse
import subprocess
import time
from pathlib import Path
import a_stock.config as cfg

LOG_FILE = cfg.DATA_DIR / "notifier.log"

# 单条通知 body 上限 (osascript 无硬限, 但太长通知中心截断). 超长按行分段
MAX_BODY_LEN = 1500


class RateLimiter:
    """三闸门限流: 每分钟配额 + 最小间隔 + 限速锁定.
    抄 a-share-quant-selector/utils/dingtalk_notifier.py:30-94."""

    def __init__(self, max_per_minute: int = 20, min_interval: float = 0.5):
        self.max_per_minute = max_per_minute
        self.min_interval = min_interval
        self.send_times: list[float] = []
        self._lock_time: float = 0.0

    def acquire(self) -> float:
        now = time.time()
        self.send_times = [t for t in self.send_times if now - t < 60]

        # 闸0: 限速锁定 (状态化罚时, 一次错误阻塞后续所有)
        if now < self._lock_time:
            time.sleep(self._lock_time - now)
            now = time.time()

        # 闸1: 每分钟配额
        if len(self.send_times) >= self.max_per_minute:
            wait = 60 - (now - self.send_times[0]) + 0.1
            if wait > 0:
                time.sleep(wait)
                now = time.time()
                self.send_times = [t for t in self.send_times if now - t < 60]

        # 闸2: 最小间隔
        if self.send_times:
            elapsed = now - self.send_times[-1]
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
                now = time.time()

        self.send_times.append(now)
        return now

    def on_error(self, retry_count: int = 0) -> None:
        """osascript 失败退避 (无钉钉660026专属码, 统一退避)."""
        backoff = min(2 ** retry_count, 30)
        self._lock_time = time.time() + backoff
        time.sleep(backoff)


# 全局单例 (跨调用共享限流状态)
# min_interval=0.2: monitor 命中多条规则时累计延迟可控 (5条=1s)
_rate_limiter = RateLimiter(max_per_minute=30, min_interval=0.2)


def _osascript(title: str, body: str, subtitle: str = "", sound: bool = False) -> bool:
    """单次 osascript 调用. 返回是否成功."""
    title_esc = title.replace('"', "'")
    body_esc = body.replace('"', "'")
    sub_esc = subtitle.replace('"', "'") if subtitle else ""

    script = f'display notification "{body_esc}" with title "{title_esc}"'
    if sub_esc:
        script += f' subtitle "{sub_esc}"'
    if sound:
        script += ' sound name "default"'

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def push(title: str, body: str, subtitle: str = "",
         sound: bool = False, group: str = "a-stock",
         max_retries: int = 3) -> bool:
    """弹 Mac 通知, 带限流+重试. 返回是否成功.
    body 超长自动分段."""
    # 分段
    segments = _split_body(body, MAX_BODY_LEN)

    all_ok = True
    for i, seg in enumerate(segments):
        seg_title = title if len(segments) == 1 else f"{title} ({i+1}/{len(segments)})"
        ok = _push_single(seg_title, seg, subtitle, sound, max_retries)
        if not ok:
            all_ok = False
        # 分段间稍等
        if i < len(segments) - 1:
            time.sleep(0.3)

    _log(title, body, all_ok, "")
    return all_ok


def _push_single(title: str, body: str, subtitle: str, sound: bool,
                 max_retries: int) -> bool:
    """单条推送, 带重试 (1s→2s→4s→8s)."""
    for attempt in range(max_retries + 1):
        _rate_limiter.acquire()
        ok = _osascript(title, body, subtitle, sound)
        if ok:
            return True
        if attempt < max_retries:
            _rate_limiter.on_error(attempt)
    return False


def _split_body(body: str, max_len: int) -> list[str]:
    """按行切分, 超长行按字符 chunk (UTF-8 安全)."""
    if len(body) <= max_len:
        return [body]

    lines = body.split("\n")
    segments = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > max_len:
            if current:
                segments.append(current)
            # 单行超长, 按字符切
            while len(line) > max_len:
                segments.append(line[:max_len])
                line = line[max_len:]
            current = line
        else:
            current = current + "\n" + line if current else line
    if current:
        segments.append(current)
    return segments


def _log(title: str, body: str, ok: bool, err: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    status = "✓" if ok else "✗"
    line = f"[{ts}] {status} {title} | {body[:80]}"
    if not ok and err:
        line += f" | err={err.strip()}"
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def test() -> None:
    """测试: 限流 + 重试 + 分段."""
    print("=== 1. 单条测试 ===")
    push("🟢 A股监控测试", "低优先级通知, 不响铃", subtitle="smoke test")
    time.sleep(0.5)
    push("🟡 测试", "普通通知, 响铃", subtitle="smoke test", sound=True)
    time.sleep(0.5)
    push("🔴 测试", "重要通知, 响铃", subtitle="smoke test", sound=True)

    print("\n=== 2. 限流测试 (连发10条, 应被限流到2s间隔) ===")
    t0 = time.time()
    for i in range(10):
        push("🧪 限流测试", f"第{i+1}条", sound=False)
    elapsed = time.time() - t0
    print(f"  10条耗时 {elapsed:.1f}s (限流后预期 ~5s)")

    print("\n=== 3. 分段测试 (超长body) ===")
    long_body = "\n".join(f"第{i}行: " + "x" * 100 for i in range(30))
    push("🧩 分段测试", long_body, subtitle="超长body分段")

    print(f"\n✓ 测试完成. log: {LOG_FILE}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_push = sub.add_parser("push")
    p_push.add_argument("--title", required=True)
    p_push.add_argument("--body", required=True)
    p_push.add_argument("--subtitle", default="")
    p_push.add_argument("--sound", action="store_true")

    sub.add_parser("test")

    args = ap.parse_args()

    if args.cmd == "test":
        test()
    elif args.cmd == "push":
        ok = push(args.title, args.body, args.subtitle, args.sound)
        print(f"{'✓' if ok else '✗'} {args.title}")


if __name__ == "__main__":
    main()
