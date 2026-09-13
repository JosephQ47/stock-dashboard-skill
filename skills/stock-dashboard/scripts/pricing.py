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
    a, b = float(pe_percentile_25_price), float(pe_percentile_75_price)
    return {"low": min(a, b), "high": max(a, b)}


def technical_anchor(ma20, prior_low, boll_lower) -> dict:
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
        chosen, name = val, "估值锚"
    else:
        chosen, name = tech, "技术锚"
    note = (
        f"估值锚与技术锚无交集，取更靠下的{name}区间。"
        f"两者背离说明价格与基本面判断不一致，需人工复核"
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
    implied_pe = round(price / float(eps), 2) if eps else None
    return {"price": round(price, 2), "formula": formula, "implied_pe": implied_pe}


def stop_loss(entry, atr14, prior_low) -> dict:
    entry = float(entry)
    options = []
    if atr14 is not None:
        p = entry - ATR_MULTIPLE * float(atr14)
        options.append(("ATR", p, f"入场 {entry:.2f} 减 {ATR_MULTIPLE:g} 倍 ATR14 {float(atr14):.2f}"))
    if prior_low is not None:
        p = float(prior_low) * (1 - STRUCTURE_BUFFER)
        options.append(("结构", p, f"前低 {float(prior_low):.2f} 下方 {STRUCTURE_BUFFER:.0%}"))
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
