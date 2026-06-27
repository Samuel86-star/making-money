#!/usr/bin/env bash
# 安装/卸载 A股监控 cron 任务
# 用法: scripts/setup_cron.sh [install|uninstall|status]

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_DIR="$PROJECT_DIR/data/logs"

# 交易时段: 9:30-11:30, 13:00-15:00, 每 5 分钟
# 简化写法: 9:25-15:05 每 5 分钟 (覆盖盘前/盘后)
CRON_LINE_A="*/5 9-11 * * 1-5"
CRON_LINE_PM="*/5 13-14 * * 1-5"
CRON_LINE_CLOSE="5 15 * * 1-5"

CMD="cd $PROJECT_DIR && $PYTHON -m a_stock.monitor >> $LOG_DIR/monitor.log 2>&1"

case "${1:-status}" in
  install)
    mkdir -p "$LOG_DIR"
    # 先清掉旧任务
    crontab -l 2>/dev/null | grep -v "a_stock.monitor" | grep -v "a_stock.notifier.test" > /tmp/cron_clean || true
    # 装新任务
    (cat /tmp/cron_clean; echo "$CRON_LINE_A $CMD"; echo "$CRON_LINE_PM $CMD"; echo "$CRON_LINE_CLOSE $CMD") | crontab -
    echo "✓ Cron 已安装. 9-11, 13-14 点每 5 分钟, 15:05 收盘后各跑一次"
    echo "  日志: $LOG_DIR/monitor.log"
    crontab -l | grep "a_stock.monitor"
    ;;

  uninstall)
    crontab -l 2>/dev/null | grep -v "a_stock.monitor" > /tmp/cron_clean || true
    crontab /tmp/cron_clean
    echo "✓ Cron 已卸载"
    ;;

  status)
    echo "当前 cron 任务:"
    crontab -l 2>/dev/null | grep -E "(a_stock|sentiment|macro)" || echo "  (无相关任务)"
    echo ""
    echo "最近监控日志:"
    if [ -f "$LOG_DIR/monitor.log" ]; then
      tail -10 "$LOG_DIR/monitor.log"
    else
      echo "  (无日志)"
    fi
    ;;

  test)
    echo "测试运行 monitor (dry-run)..."
    cd "$PROJECT_DIR"
    $PYTHON -m a_stock.monitor --dry-run
    ;;

  *)
    echo "用法: $0 [install|uninstall|status|test]"
    exit 1
    ;;
esac
