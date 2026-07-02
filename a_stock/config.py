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

# Mac弹窗开关 (默认关: mac推送不好用, 改用会话内心跳通知).
# cron数据管道照跑(落盘candidate_history/industry_flow), 只不弹窗.
# 临时开: NOTIFY_ENABLED=1
NOTIFY_ENABLED = os.environ.get("NOTIFY_ENABLED", "0") == "1"

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