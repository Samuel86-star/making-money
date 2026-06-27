"""多因子评分: 技术35% + 资金35% + 基本面10% + 板块10% + 事件10%.
抄 KHunter 权重, 改归一化 (每因子先 clamp [0,100] 再加权, 修 KHunter 缺陷).
只抄3类真veto: 技术/资金/事件 (不抄 KHunter 死代码 veto)."""
from dataclasses import dataclass, field
from typing import Optional

# 权重 (抄 KHunter stock_score_models.py:24-33, 属实)
SCORE_WEIGHTS = {
    "technical": 0.35,
    "moneyflow": 0.35,
    "fundamental": 0.10,
    "sector": 0.10,
    "event": 0.10,
}
VETO_SCORE = -100


@dataclass
class FactorScore:
    """单因子评分结果."""
    score: float = 50.0          # 0-100, 先 clamp 再加权 (修KHunter不归一化)
    veto: bool = False
    veto_reason: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class TotalScore:
    code: str
    name: str
    technical: FactorScore = field(default_factory=FactorScore)
    moneyflow: FactorScore = field(default_factory=FactorScore)
    fundamental: FactorScore = field(default_factory=FactorScore)
    sector: FactorScore = field(default_factory=FactorScore)
    event: FactorScore = field(default_factory=FactorScore)
    total: float = 50.0
    level: str = ""
    veto: bool = False
    veto_reason: str = ""

    def calculate(self) -> None:
        """加权求和. 任一veto→-100."""
        vetoed = [f for f in [self.technical, self.moneyflow, self.fundamental,
                              self.sector, self.event] if f.veto]
        if vetoed:
            self.veto = True
            self.veto_reason = " | ".join(f.veto_reason for f in vetoed if f.veto_reason)
            self.total = VETO_SCORE
            self.level = "❌ 否决"
            return

        # 关键改进: 每因子 clamp [0,100] 再加权 (修 KHunter 不归一化)
        t = max(0, min(100, self.technical.score))
        m = max(0, min(100, self.moneyflow.score))
        f_ = max(0, min(100, self.fundamental.score))
        s = max(0, min(100, self.sector.score))
        e = max(0, min(100, self.event.score))

        self.total = round(
            t * SCORE_WEIGHTS["technical"]
            + m * SCORE_WEIGHTS["moneyflow"]
            + f_ * SCORE_WEIGHTS["fundamental"]
            + s * SCORE_WEIGHTS["sector"]
            + e * SCORE_WEIGHTS["event"],
            1,
        )
        self.level = self._level(self.total)

    @staticmethod
    def _level(score: float) -> str:
        """评级 (8档, 抄 UZI v3.4.1 细分)."""
        if score >= 80:
            return "★★★ 重仓"
        if score >= 70:
            return "★★ 可以蹲"
        if score >= 65:
            return "★★ 偏弱可蹲"
        if score >= 60:
            return "★ 观望偏多"
        if score >= 55:
            return "★ 观望中性"
        if score >= 50:
            return "观望偏空"
        if score >= 35:
            return "谨慎"
        return "回避"


def score_to_position_scale(score: float) -> float:
    """评分→仓位缩放系数. 用于 position_sizer.
    <40: 0 (不买)
    40-60: 0.5 (半仓)
    60-80: 1.0 (满仓×Kelly)
    >=80: 1.2 (超配, 受单仓30%上限约束)"""
    if score < 40:
        return 0.0
    if score < 60:
        return 0.5
    if score < 80:
        return 1.0
    return 1.2
