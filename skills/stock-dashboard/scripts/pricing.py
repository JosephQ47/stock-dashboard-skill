# -*- coding: utf-8 -*-
"""三价位推导。每个价位都必须带推导式，禁止直接报数字。"""
from __future__ import annotations

RSI_CEILING = 80.0
BIAS_CEILING = 5.0
ATR_MULTIPLE = 2.0
STRUCTURE_BUFFER = 0.01


class PricingBlocked(Exception):
    """输入不足以推导价位，调用方应说明原因而不是编造数字。"""


def valuation_anchor(pe_percentile_25_price, pe_percentile_75_price) -> dict:
    """估值锚：根据 PE 分位数推导价格区间。

    返回中间值，不直接呈现给用户，不需要公式。
    """
    if pe_percentile_25_price is None or pe_percentile_75_price is None:
        raise PricingBlocked("PE 分位数价格缺失，无法构造估值锚")
    a, b = float(pe_percentile_25_price), float(pe_percentile_75_price)
    return {"low": min(a, b), "high": max(a, b)}


def technical_anchor(ma20, prior_low, boll_lower) -> dict:
    """技术锚：根据移动平均线、结构支撑推导价格区间。

    返回中间值，不直接呈现给用户，不需要公式。
    """
    vals = [float(v) for v in (ma20, prior_low, boll_lower) if v is not None]
    if not vals:
        raise PricingBlocked("MA20、前低、布林下轨全部缺失，无法构造技术锚")
    return {"low": min(vals), "high": max(vals)}


def buy_range(val: dict, tech: dict) -> dict:
    lo = max(val["low"], tech["low"])
    hi = min(val["high"], tech["high"])
    formula = (
        f"估值锚 [{val['low']:.2f}, {val['high']:.2f}] 与 "
        f"技术锚 [{tech['low']:.2f}, {tech['high']:.2f}] 取交集"
    )
    if lo <= hi:
        return {"low": round(lo, 2), "high": round(hi, 2), "formula": formula, "note": None}

    val_mid = (val["low"] + val["high"]) / 2
    tech_mid = (tech["low"] + tech["high"]) / 2
    if val_mid <= tech_mid:
        chosen = val
        note = (
            "估值锚与技术锚无交集，取更靠下的估值锚。"
            "等待更深的技术回调以与基本面对齐，这是保守的做法。"
            "两者背离说明价格与基本面判断不一致，需人工复核"
        )
    else:
        chosen = tech
        note = (
            "估值锚与技术锚无交集，取更靠下的技术锚。"
            "价格已跌破技术支撑但基本面评估（基于滞后财务数据）未同步。"
            "在趋势不确定时介入，两者背离说明价格与基本面判断不一致，需人工复核"
        )
    return {
        "low": round(chosen["low"], 2),
        "high": round(chosen["high"], 2),
        "formula": formula,
        "note": note,
    }


def target_price(val_high, resistance, eps) -> dict:
    candidates = [("估值区间上沿", float(val_high))] if val_high is not None else []
    if resistance is not None:
        candidates.append(("前高阻力位", float(resistance)))
    if not candidates:
        raise PricingBlocked("估值上沿与阻力位均缺失，无法推导目标价")
    name, price = min(candidates, key=lambda x: x[1])
    parts = " 与 ".join(f"{n} {v:.2f}" for n, v in candidates)
    formula = f"{parts} 取较低者，得 {name} {price:.2f}"
    implied_pe = round(price / float(eps), 2) if eps is not None and float(eps) > 0 else None
    return {"price": round(price, 2), "formula": formula, "implied_pe": implied_pe}


def stop_loss(entry, atr14, prior_low) -> dict:
    entry = float(entry)
    options = []
    if atr14 is not None:
        p = entry - ATR_MULTIPLE * float(atr14)
        if p < entry:
            options.append(("ATR", p, f"入场 {entry:.2f} 减 {ATR_MULTIPLE:g} 倍 ATR14 {float(atr14):.2f}"))
        else:
            raise PricingBlocked(f"ATR14 过小（{float(atr14):.2f}），计算得止损 {p:.2f} 不低于入场 {entry:.2f}，无法形成有效止损")
    if prior_low is not None:
        p = float(prior_low) * (1 - STRUCTURE_BUFFER)
        if p < entry:
            options.append(("结构", p, f"前低 {float(prior_low):.2f} 下方 {STRUCTURE_BUFFER:.0%}"))
        else:
            raise PricingBlocked(f"前低 {float(prior_low):.2f} 高于入场 {entry:.2f}，结构止损无法有效保护头寸，需等前低回落至入场下方")
    if not options:
        raise PricingBlocked("ATR14 与前低均缺失，无法推导止损价")
    method, price, formula = max(options, key=lambda x: x[1])
    return {"price": round(price, 2), "formula": formula, "method": method}


def gate_check(rsi14, bias_ma5) -> list[str]:
    gates = []
    if rsi14 is not None and float(rsi14) > RSI_CEILING:
        gates.append(f"RSI14 为 {float(rsi14):.1f}，超过 {RSI_CEILING:.0f}，不给买入信号，只能等回调")
    if bias_ma5 is not None and float(bias_ma5) > BIAS_CEILING:
        gates.append(f"价格相对 MA5 乖离 {float(bias_ma5):.1f}%，超过 {BIAS_CEILING:.0f}%，不给追高建议")
    return gates
