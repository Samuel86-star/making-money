"""单股 brief 数据组装 + markdown 渲染。"""
from datetime import datetime
from a_stock.a_stock_data import (
    tencent_quote, eastmoney_concept_blocks, stock_fund_flow_120d,
    eastmoney_reports, ths_eps_forecast,
    ths_hot_reason,
)
import a_stock.config as cfg


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