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

# 一个轴上参与打分的维度数——renormalize 之后，分数可能完全由一两个维度
# 撑起来（例如仅 statement 一项缺席其余四项时，Q 照样能算出 100 分）。
# 少于 2 个维度在场时，不允许 map_matrix 把这个分数断言成「基本面达标」
# 或「基本面太弱」，只能如实说证据不足。选 2 而不是更高，是因为真实
# 600519 这类正常跑一次的报告通常有 3 个维度在场（statement/health/
# profitability），卡在 2 不会误伤正常报告，同时能挡住「只有 statement
# 一项」的注入场景。
QUALITY_MIN_DIMS_FOR_CLAIM = 2

# 红旗里「真正基于实际数据判定」的条数——同样的道理，用于 selfcheck 判断
# 结论是否建立在薄证据之上。真实 600519 跑一次通常有 3 条（CASH_PROFIT/
# ACCRUAL/RECEIVABLE）基于数据判定，其余 7 条因为没有数据源而标「未获取
# 到」；卡在 2 不会误伤正常报告，能挡住「10 条只判了 1 条」的注入场景。
KNOWN_FLAGS_MIN_FOR_CLAIM = 2


def _weighted(dims, weights):
    present = {k: v for k, v in (dims or {}).items() if k in weights and v is not None}
    missing = [k for k in weights if k not in present]
    total_possible = sum(weights.values())
    if not present:
        return {
            "score": 0.0, "breakdown": {}, "missing": list(weights),
            "evidence": 0.0, "dims_present": 0, "dims_total": len(weights),
        }
    total_weight = sum(weights[k] for k in present)
    raw = sum(float(present[k]) * weights[k] for k in present)
    score = raw / total_weight
    breakdown = {k: float(present[k]) * weights[k] / total_weight for k in present}
    # evidence：实际在场的权重占该轴满额权重的比例（0~1），比 missing 列表
    # 更进一步——不仅说哪些维度缺，还说这些缺席的维度原本值多少分量。一个
    # 30 分权重的维度单独在场（evidence=0.3）和三个共 70 分权重的维度在场
    # （evidence=0.7）都可能让 missing 只列出「两三个名字」，但可信度天差
    # 地别，只有 evidence 能把这个差异带到 scoring 层之外。
    evidence = round(total_weight / total_possible, 4) if total_possible else 0.0
    return {
        "score": round(score, 2), "breakdown": breakdown, "missing": missing,
        "evidence": evidence, "dims_present": len(present), "dims_total": len(weights),
    }


def quality_score(dims: dict) -> dict:
    return _weighted(dims, QUALITY_WEIGHTS)


def timing_score(dims: dict) -> dict:
    return _weighted(dims, TIMING_WEIGHTS)


def apply_veto(q: float, veto: bool) -> float:
    if not veto:
        return q
    return min(float(q), VETO_CAP)


def map_matrix(q: float, t: float, veto: bool, q_dims_present: int | None = None) -> dict:
    """双轴矩阵映射。

    `q_dims_present` 是 Q 轴实际参与打分的维度数（来自 `quality_score(...)
    ["dims_present"]`），可选——调用方不传时（例如既有测试直接手写 q/t 数值）
    完全保持旧行为。传了之后，一旦维度数低于 `QUALITY_MIN_DIMS_FOR_CLAIM`，
    conflict 里就不再断言「基本面达标」或「基本面太弱」，只如实说证据不足；
    verdict 本身不变——用哪个判定分区仍按 q/t 数值走，被纠正的只是措辞，不
    是结论本身该不该给。
    """
    if veto:
        return {"verdict": VERDICT_AVOID, "conflict": "触发一票否决，无论评分高低一律回避"}

    q, t = float(q), float(t)
    q_high, t_high = q >= HIGH, t >= HIGH
    q_thin = q_dims_present is not None and q_dims_present < QUALITY_MIN_DIMS_FOR_CLAIM

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
        if q_thin:
            conflict = (
                f"质量分 Q {q:.1f} 仅由 {q_dims_present} 个维度支撑，证据单薄，"
                "无法判断基本面是否达标；技术面也未转好，等基本面数据补齐或趋势确认再谈"
            )
        else:
            conflict = f"基本面达标（Q {q:.1f}）但技术面未转好（T {t:.1f}），等趋势确认再谈"
    elif t_high and not q_high:
        if q_thin:
            conflict = (
                f"技术面强势（T {t:.1f}），但质量分 Q {q:.1f} 仅由 {q_dims_present} 个维度支撑，"
                "证据不足以判断基本面强弱，不构成任何投资依据"
            )
        elif q >= SPECULATION_FLOOR:
            conflict = f"技术面强势（T {t:.1f}）但基本面不达标（Q {q:.1f}），是博弈不是投资"
        else:
            conflict = f"技术面强势（T {t:.1f}）但基本面太弱不足投资（Q {q:.1f}），坚决回避"

    return {"verdict": verdict, "conflict": conflict}
