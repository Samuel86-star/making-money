"""Mac 本地通知: 用 osascript 弹窗, 落通知中心. 不需 key, 不需安装."""
import argparse
import subprocess
import time
from pathlib import Path
import a_stock.config as cfg

LOG_FILE = cfg.DATA_DIR / "notifier.log"


def push(title: str, body: str, subtitle: str = "",
         sound: bool = False, group: str = "a-stock") -> bool:
    """弹 Mac 通知. 返回是否成功."""
    # 转义双引号
    title_esc = title.replace('"', "'")
    body_esc = body.replace('"', "'")
    sub_esc = subtitle.replace('"', "'") if subtitle else ""

    script_parts = [f'display notification "{body_esc}" with title "{title_esc}"']
    if sub_esc:
        script_parts[0] += f' subtitle "{sub_esc}"'
    if sound:
        script_parts[0] += ' sound name "default"'

    script = " ".join(script_parts)

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5
        )
        ok = result.returncode == 0
        _log(title, body, ok, result.stderr)
        return ok
    except Exception as e:
        _log(title, body, False, str(e))
        return False


def _log(title: str, body: str, ok: bool, err: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    status = "✓" if ok else "✗"
    line = f"[{ts}] {status} {title} | {body}"
    if not ok and err:
        line += f" | err={err.strip()}"
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def test() -> None:
    """测试推送: 弹3条不同优先级."""
    push("🟢 A股监控测试", "低优先级通知, 不响铃",
         subtitle="smoke test")
    time.sleep(0.5)
    push("🟡 测试", "普通通知", subtitle="smoke test", sound=True)
    time.sleep(0.5)
    push("🔴 测试", "重要通知, 响铃", subtitle="smoke test", sound=True)
    print(f"✓ 已发送 3 条测试通知. log: {LOG_FILE}")


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
