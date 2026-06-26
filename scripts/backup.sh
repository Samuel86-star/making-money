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