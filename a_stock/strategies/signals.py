"""策略信号数据结构 + 聚合.
Signal: 单策略对单标的的信号.
SignalVote: 同标的多策略信号聚合, 按 total_confidence 排序."""
from dataclasses import dataclass, field


@dataclass
class Signal:
    code: str
    name: str
    action: str            # buy / sell / hold
    confidence: float      # 0.0 ~ 1.0
    strategy: str          # 来源策略名
    reason: str
    meta: dict = None


@dataclass
class SignalVote:
    code: str
    name: str
    total_confidence: float
    strategies: list = field(default_factory=list)
    signals: list = field(default_factory=list)
    top_reason: str = ""


def aggregate(signals: list) -> list:
    """按 code 聚合 buy 信号, total_confidence 降序."""
    by_code: dict[str, SignalVote] = {}
    for s in signals:
        if s.action != "buy":
            continue
        if s.code not in by_code:
            by_code[s.code] = SignalVote(
                code=s.code, name=s.name, total_confidence=0.0,
                strategies=[], signals=[], top_reason=s.reason,
            )
        v = by_code[s.code]
        v.total_confidence += s.confidence
        v.strategies.append(s.strategy)
        v.signals.append(s)
        # top_reason 取当前最高 confidence 那条
        if s.confidence >= max(sig.confidence for sig in v.signals):
            v.top_reason = s.reason
    return sorted(by_code.values(), key=lambda v: -v.total_confidence)
