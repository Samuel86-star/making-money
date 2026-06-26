"""AI 代理手递手集成测试：模拟从快照生成到 AI 分析注入的全流程。"""
import py.config as cfg
from py.a_screen.snapshot import save_snapshot, update_ai_analysis
from py.a_screen.brief_builder import render_markdown


def _mock_snapshot(code: str, date: str) -> dict:
    """返回一个无网络调用的最小快照 dict。"""
    return {
        "meta": {"code": code, "name": "神州数码", "generated_at": f"{date}T10:00:00", "trigger": "manual"},
        "snapshot_date": date,
        "fundamentals": {
            "price": 30.0, "change_pct": -0.5, "pe_ttm": 18, "pb": 2.1,
            "mcap_yi": 200, "float_mcap_yi": 150, "industry": "IT服务",
            "limit_up": 33.0, "limit_down": 27.0, "turnover_pct": 3.5,
        },
        "membership": {"industries": [{"name": "计算机"}], "concepts": [{"name": "信创"}], "regions": []},
        "fund_flow": {"today": {}, "5d_cumulative": -5e7, "20d_cumulative": 1.2e8},
        "research": {"report_count_30d": 2, "reports": [
            {"date": "2026-06-24", "org": "华泰", "rating": "买入", "title": "国产化替代加速"},
        ]},
        "consensus": {"eps_forecasts": []},
        "hot_signal": {"is_today_hot": False, "reason": None},
        "dragon_tiger": {"30d_count": 0, "last_appearance": None},
        "northbound": {"5d_net_inflow": 0},
        "screener_score": {"short": 65, "mid": 58, "scan_date": date},
        "risks": ["PE 18 合理", "近5日主力净流出 0.50 亿"],
        "ai_analysis": None,
    }


def test_ai_handoff_placeholder_then_filled(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "BRIEFS_DIR", tmp_path)

    code, date = "000034", "2026-06-26"
    snap = _mock_snapshot(code, date)
    save_snapshot(snap)

    # 阶段 1：快照刚生成，MD 含占位注释
    md = render_markdown(snap)
    assert "AI 跨信号分析" in md
    assert "等分析" in md
    assert "AI 建议" not in md

    # 阶段 2：模拟 AI（Claude Code）写回分析
    ai_text = "AI 建议:观望,等待回调至28元附近。关注华为昇腾生态中标进展。"
    update_ai_analysis(code, date, ai_text)

    # 重新从磁盘加载，再渲染 — 此时 AI 段应填充
    from py.a_screen.snapshot import load_snapshot
    reloaded = load_snapshot(code, date)
    assert reloaded is not None
    assert reloaded["ai_analysis"] == ai_text

    md2 = render_markdown(reloaded)
    assert "等分析" not in md2  # 占位消失
    assert "AI 建议:观望" in md2
    assert "华为昇腾" in md2
    assert "ai_analysis_meta" in reloaded
    assert "analyzed_at" in reloaded["ai_analysis_meta"]