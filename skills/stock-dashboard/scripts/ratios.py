# -*- coding: utf-8 -*-
"""财务比率与红旗判定。全部用 Decimal，禁止浮点直接比较。

数据缺失一律不判红旗，detail 写「未获取到」，不得推测填充。
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

MISSING = "未获取到"


def D(x):
    if x is None:
        return None
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _div(a, b):
    a, b = D(a), D(b)
    if a is None or b is None or b == 0:
        return None
    return a / b


def cash_to_profit(cfo, net_profit):
    return _div(cfo, net_profit)


def accrual_ratio(net_profit, cfo, total_assets):
    np_, cfo_, ta = D(net_profit), D(cfo), D(total_assets)
    if np_ is None or cfo_ is None or ta is None or ta == 0:
        return None
    return (np_ - cfo_) / ta


def receivable_gap(ar_growth, revenue_growth):
    a, b = D(ar_growth), D(revenue_growth)
    if a is None or b is None:
        return None
    return a - b


def goodwill_ratio(goodwill, net_assets):
    return _div(goodwill, net_assets)


def recurring_ratio(deducted_profit, net_profit):
    return _div(deducted_profit, net_profit)


def dupont(net_profit, revenue, total_assets, equity):
    nm = _div(net_profit, revenue)
    at = _div(revenue, total_assets)
    em = _div(total_assets, equity)
    roe = None if (nm is None or at is None or em is None) else nm * at * em
    return {"net_margin": nm, "asset_turnover": at, "equity_multiplier": em, "roe": roe}


def _flag(code, name, hit, detail, veto=False):
    return {"code": code, "name": name, "hit": bool(hit), "detail": detail, "veto": bool(veto)}


def check_red_flags(fin: dict) -> list[dict]:
    out = []

    ctp = cash_to_profit(fin.get("cfo"), fin.get("net_profit"))
    history = [D(v) for v in (fin.get("cash_to_profit_history") or [])]
    history = [v for v in history if v is not None]
    two_year_low = len(history) >= 2 and all(v < Decimal("0.5") for v in history[-2:])
    if ctp is None:
        out.append(_flag("CASH_PROFIT", "净现比", False, MISSING))
    else:
        hit = ctp < Decimal("0.7")
        detail = f"净现比 {ctp:.2f}" + ("，连续两年低于 0.5" if two_year_low else "")
        out.append(_flag("CASH_PROFIT", "净现比", hit, detail, veto=two_year_low))

    ar = accrual_ratio(fin.get("net_profit"), fin.get("cfo"), fin.get("total_assets"))
    if ar is None:
        out.append(_flag("ACCRUAL", "总应计比率", False, MISSING))
    else:
        out.append(_flag("ACCRUAL", "总应计比率", ar > Decimal("0.10"), f"应计比率 {ar:.3f}"))

    gap = receivable_gap(fin.get("ar_growth"), fin.get("revenue_growth"))
    if gap is None:
        out.append(_flag("RECEIVABLE", "应收增速超营收", False, MISSING))
    else:
        out.append(_flag("RECEIVABLE", "应收增速超营收", gap > Decimal("20"),
                         f"应收增速快于营收 {gap:.1f} 个百分点"))

    gw = goodwill_ratio(fin.get("goodwill"), fin.get("net_assets"))
    if gw is None:
        out.append(_flag("GOODWILL", "商誉占净资产", False, MISSING))
    else:
        out.append(_flag("GOODWILL", "商誉占净资产", gw > Decimal("0.30"), f"商誉占比 {gw:.1%}"))

    rec = recurring_ratio(fin.get("deducted_profit"), fin.get("net_profit"))
    if rec is None:
        out.append(_flag("RECURRING", "扣非占归母", False, MISSING))
    else:
        out.append(_flag("RECURRING", "扣非占归母", rec < Decimal("0.70"), f"扣非占比 {rec:.1%}"))

    cash, debt = D(fin.get("cash")), D(fin.get("interest_bearing_debt"))
    ta = D(fin.get("total_assets"))
    if cash is None or debt is None or ta is None or ta == 0:
        out.append(_flag("BIG_DEPOSIT_LOAN", "大存大贷", False, MISSING))
    else:
        hit = cash / ta > Decimal("0.30") and debt / ta > Decimal("0.30")
        out.append(_flag("BIG_DEPOSIT_LOAN", "大存大贷", hit,
                         f"货币资金占比 {cash / ta:.1%}，有息负债占比 {debt / ta:.1%}", veto=hit))

    opinion = fin.get("audit_opinion")
    if opinion is None:
        out.append(_flag("AUDIT_OPINION", "审计意见", False, MISSING))
    else:
        hit = "标准无保留" not in str(opinion)
        out.append(_flag("AUDIT_OPINION", "审计意见", hit, str(opinion), veto=hit))

    pledge = D(fin.get("pledge_ratio"))
    if pledge is None:
        out.append(_flag("PLEDGE", "股权质押", False, MISSING))
    else:
        hit = pledge > Decimal("50")
        out.append(_flag("PLEDGE", "股权质押", hit, f"质押比例 {pledge:.1f}%", veto=hit))

    dr = fin.get("delisting_risk")
    if dr is None:
        out.append(_flag("DELISTING_RISK", "退市风险", False, MISSING))
    else:
        out.append(_flag("DELISTING_RISK", "退市风险", bool(dr),
                         "存在退市风险" if dr else "无", veto=bool(dr)))

    inv = fin.get("under_investigation")
    if inv is None:
        out.append(_flag("INVESTIGATION", "立案调查", False, MISSING))
    else:
        out.append(_flag("INVESTIGATION", "立案调查", bool(inv),
                         "存在立案调查" if inv else "无", veto=bool(inv)))

    return out


def veto_triggered(flags) -> bool:
    return any(f["veto"] for f in flags)
