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


def buy_range_technical_only(tech: dict, reason: str) -> dict:
    """估值锚缺失或被阻断（PE 亏损、港股/美股无五年 PE 历史等）时的退化买入区间：
    只用技术锚构造，绝不回退到「现价百分比」这类伪估值锚。`reason` 必须写清楚
    估值锚为什么缺失，让读者知道这不是「估值支持了这个区间」，只是技术面的
    区间。
    """
    formula = (
        f"估值锚缺失（{reason}），买入区间仅取技术锚 "
        f"[{tech['low']:.2f}, {tech['high']:.2f}]"
    )
    return {
        "low": round(tech["low"], 2),
        "high": round(tech["high"], 2),
        "formula": formula,
        "note": f"估值锚不可用：{reason}。本买入区间不包含基本面估值判断，仅代表技术面支撑/压力位。",
    }


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
    # val 可能带一个 formula 字段（来自 compute.derive_valuation_anchor，展示
    # 当前 PE、分位 PE、历史天数与换算价格的完整推导），有就展示真实推导过程，
    # 没有就退回到只报区间数字的旧行为，保持对老调用方（测试里直接传
    # {"low","high"} 的裸字典）的兼容。
    val_formula = val.get("formula")
    val_desc = f"估值锚（{val_formula}）" if val_formula else f"估值锚 [{val['low']:.2f}, {val['high']:.2f}]"
    formula = f"{val_desc}；技术锚 [{tech['low']:.2f}, {tech['high']:.2f}] 取交集"
    if lo <= hi:
        return {"low": round(lo, 2), "high": round(hi, 2), "formula": formula, "note": None}

    val_mid = (val["low"] + val["high"]) / 2
    tech_mid = (tech["low"] + tech["high"]) / 2
    if val_mid <= tech_mid:
        # 估值锚整体更低：按历史 PE 分位算出的合理区间落在当前技术区间之下，
        # 基本面显示偏贵。这里只能断言「两个锚不一致」这一件事——不能断言价
        # 格相对哪个锚做了什么动作，那需要额外的价格位置信息，不是这两个区
        # 间本身能证明的。
        chosen = val
        note = (
            "估值锚与技术锚无交集，取更靠下的估值锚（更保守）。"
            "按历史 PE 分位推算的合理区间低于当前技术区间，基本面显示偏贵。"
            "两者背离，需人工复核"
        )
    else:
        # 估值锚整体更高：按历史 PE 分位算出的合理区间落在当前技术区间之上，
        # 基本面显示偏便宜，但仍然取更保守的技术锚，而不是因为估值乐观就把
        # 入场价抬高去够估值锚。这个组合本身不能说明技术支撑被跌破、也不能
        # 说明趋势不确定——那些都需要额外信息（如价格相对技术锚的实际位
        # 置），仅凭两个锚的相对高低无法判断，不得断言。
        chosen = tech
        note = (
            "估值锚与技术锚无交集，取更靠下的技术锚（更保守）。"
            "按历史 PE 分位推算的合理区间高于当前技术区间，基本面显示偏便宜，"
            "但仍以更保守的技术锚为准，不因估值乐观而抬高入场价。"
            "两者背离，需人工复核；此结构本身不代表技术支撑被跌破，也不代表趋势不确定"
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
    candidates = []
    dropped = []

    if atr14 is not None:
        atr_val = float(atr14)
        p = entry - ATR_MULTIPLE * atr_val
        formula = f"入场 {entry:.2f} 减 {ATR_MULTIPLE:g} 倍 ATR14 {atr_val:.2f}"
        if 0 < p < entry:
            candidates.append(("ATR", p, formula))
        else:
            if p <= 0:
                dropped.append(("ATR", f"计算得止损 {p:.2f}，不大于零"))
            else:
                dropped.append(("ATR", f"计算得止损 {p:.2f}，不低于入场 {entry:.2f}"))

    if prior_low is not None:
        prior_val = float(prior_low)
        p = prior_val * (1 - STRUCTURE_BUFFER)
        formula = f"前低 {prior_val:.2f} 下方 {STRUCTURE_BUFFER:.0%}"
        if 0 < p < entry:
            candidates.append(("结构", p, formula))
        else:
            if p <= 0:
                dropped.append(("结构", f"计算得止损 {p:.2f}，不大于零"))
            else:
                dropped.append(("结构", f"计算得止损 {p:.2f}，不低于入场 {entry:.2f}"))

    if not candidates:
        if dropped:
            reasons = "；".join(f"{method}：{reason}" for method, reason in dropped)
            raise PricingBlocked(f"所有止损方法均无效：{reasons}")
        else:
            raise PricingBlocked("ATR14 与前低均缺失，无法推导止损价")

    method, price, formula = max(candidates, key=lambda x: x[1])
    result = {"price": round(price, 2), "formula": formula, "method": method}

    if dropped:
        dropped_text = "；".join(f"{m}被舍弃（{r}）" for m, r in dropped)
        result["note"] = dropped_text

    return result


def gate_check(rsi14, bias_ma5) -> list[str]:
    gates = []
    if rsi14 is not None and float(rsi14) > RSI_CEILING:
        gates.append(f"RSI14 为 {float(rsi14):.1f}，超过 {RSI_CEILING:.0f}，不给买入信号，只能等回调")
    if bias_ma5 is not None and float(bias_ma5) > BIAS_CEILING:
        gates.append(f"价格相对 MA5 乖离 {float(bias_ma5):.1f}%，超过 {BIAS_CEILING:.0f}%，不给追高建议")
    return gates
