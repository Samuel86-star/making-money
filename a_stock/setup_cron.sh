#!/usr/bin/env bash
# 安装/卸载 A股监控 cron 任务 (v1.0: monitor + scheduler)
# 用法: a_stock/setup_cron.sh [install|uninstall|status|test]

set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
LOG_DIR="$PROJECT_DIR/data/logs"

# v1.0: 双任务
# 1. monitor 每5分钟 (价格规则+异动) — 9-11, 13-14, 15:05
# 2. scheduler 每分钟检查到点任务 (早盘扫描9:35/9:50 + 盘后15:10) — 9-15
CRON_MONITOR_AM="*/5 9-11 * * 1-5"
CRON_MONITOR_PM="*/5 13-14 * * 1-5"
CRON_MONITOR_CLOSE="5 15 * * 1-5"
CRON_SCHEDULER="* 9-14 * * 1-5"
CRON_SCHEDULER_PM="* 15 * * 1-5"

CMD_MONITOR="cd $PROJECT_DIR && $PYTHON -m a_stock.monitor --heartbeat >> $LOG_DIR/monitor.log 2>&1"
CMD_SCHEDULER="cd $PROJECT_DIR && $PYTHON -m a_stock.scheduler run >> $LOG_DIR/scheduler.log 2>&1"

case "${1:-status}" in
  install)
    mkdir -p "$LOG_DIR"
    # 清旧任务 (兼容旧版只跑monitor的)
    crontab -l 2>/dev/null | grep -v "a_stock.monitor" | grep -v "a_stock.scheduler" | grep -v "a_stock.notifier.test" > /tmp/cron_clean || true
    # 装新任务
    (cat /tmp/cron_clean
     echo "$CRON_MONITOR_AM $CMD_MONITOR"
     echo "$CRON_MONITOR_PM $CMD_MONITOR"
     echo "$CRON_MONITOR_CLOSE $CMD_MONITOR"
     echo "$CRON_SCHEDULER $CMD_SCHEDULER"
     echo "$CRON_SCHEDULER_PM $CMD_SCHEDULER"
    ) | crontab -
    echo "✓ Cron v1.0 已安装:"
    echo "  monitor:  9-11/13-14 每5分钟 + 15:05 (价格规则+异动+💓心跳)"
    echo "  scheduler: 9-15 每分钟 (早盘扫描9:35/9:50 + 盘后15:10)"
    echo "  日志: $LOG_DIR/{monitor,scheduler}.log"
    echo ""
    crontab -l | grep "a_stock"
    ;;

  uninstall)
    crontab -l 2>/dev/null | grep -v "a_stock.monitor" | grep -v "a_stock.scheduler" > /tmp/cron_clean || true
    crontab /tmp/cron_clean
    echo "✓ Cron 已卸载"
    ;;

  status)
    echo "当前 cron 任务:"
    crontab -l 2>/dev/null | grep -E "(a_stock|sentiment|macro)" || echo "  (无相关任务)"
    echo ""
    echo "最近 monitor 日志:"
    [ -f "$LOG_DIR/monitor.log" ] && tail -5 "$LOG_DIR/monitor.log" || echo "  (无)"
    echo ""
    echo "最近 scheduler 日志:"
    [ -f "$LOG_DIR/scheduler.log" ] && tail -5 "$LOG_DIR/scheduler.log" || echo "  (无)"
    ;;

  test)
    echo "=== 测试 monitor (dry-run) ==="
    cd "$PROJECT_DIR"
    $PYTHON -m a_stock.monitor --dry-run
    echo ""
    echo "=== 测试 scheduler ==="
    $PYTHON -m a_stock.scheduler due
    ;;

  *)
    echo "用法: $0 [install|uninstall|status|test]"
    exit 1
    ;;
esac
