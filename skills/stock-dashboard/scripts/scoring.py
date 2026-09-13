# -*- coding: utf-8 -*-
"""双轴评分与矩阵映射。

Q 轴回答「值不值得拿」，T 轴回答「现在是不是时候」。
两轴不合并成单一数字，矛盾时必须显式报出，不允许调和成模糊的持有。
"""
from __future__ import annotations

QUALITY_WEIGHTS = {
    "statement": 30,
    "profitability": 25,
    "health": 15,
    "moat": 15,
    "valuation": 15,
}

TIMING_WEIGHTS = {
    "trend": 30,
    "momentum": 25,
    "volume": 20,
    "position": 15,
    "catalyst": 10,
}

VETO_CAP = 40.0
HIGH = 60.0
SPECULATION_FLOOR = 45.0

VERDICT_BUY = "重点关注，可建仓"
VERDICT_WATCH = "加入候选池，等技术面转好"
VERDICT_SPEC = "短线博弈，不是投资"
VERDICT_AVOID = "回避"


def _weighted(dims, weights):
    present = {k: v for k, v in (dims or {}).items() if k in weights and v is not None}
    missing = [k for k in weights if k not in present]
    if not present:
        return {"score": 0.0, "breakdown": {}, "missing": list(weights)}
    total_weight = sum(weights[k] for k in present)
    raw = sum(float(present[k]) * weights[k] for k in present)
    score = raw / total_weight
    breakdown = {k: float(present[k]) * weights[k] / total_weight for k in present}
    return {"score": round(score, 2), "breakdown": breakdown, "missing": missing}


def quality_score(dims: dict) -> dict:
    return _weighted(dims, QUALITY_WEIGHTS)


def timing_score(dims: dict) -> dict:
    return _weighted(dims, TIMING_WEIGHTS)


def apply_veto(q: float, veto: bool) -> float:
    if not veto:
        return q
    return min(float(q), VETO_CAP)


def map_matrix(q: float, t: float, veto: bool) -> dict:
    if veto:
        return {"verdict": VERDICT_AVOID, "conflict": "触发一票否决，无论评分高低一律回避"}

    q, t = float(q), float(t)
    q_high, t_high = q >= HIGH, t >= HIGH

    if q_high and t_high:
        verdict = VERDICT_BUY
    elif q_high and not t_high:
        verdict = VERDICT_WATCH
    elif not q_high and t_high:
        verdict = VERDICT_SPEC if q >= SPECULATION_FLOOR else VERDICT_AVOID
    else:
        verdict = VERDICT_AVOID

    conflict = None
    if q_high and not t_high:
        conflict = f"基本面达标（Q {q:.0f}）但技术面未转好（T {t:.0f}），等趋势确认再谈"
    elif t_high and not q_high:
        if q >= SPECULATION_FLOOR:
            conflict = f"技术面强势（T {t:.0f}）但基本面不达标（Q {q:.0f}），是博弈不是投资"
        else:
            conflict = f"技术面强势（T {t:.0f}）但基本面太弱不足投资（Q {q:.0f}），坚决回避"

    return {"verdict": verdict, "conflict": conflict}
