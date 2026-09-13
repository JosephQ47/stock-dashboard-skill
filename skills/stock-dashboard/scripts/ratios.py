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


def _is_missing(value):
    """检查值是否为缺失数据。

    缺失的值包括：None、空字符串、仅空格字符串、常见占位符。
    占位符包括: --, N/A, nan, None（不区分大小写）。
    """
    if value is None:
        return True
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if not cleaned:
            return True
        if cleaned in ('--', 'n/a', 'nan', 'none'):
            return True
    return False


def _parse_bool(value):
    """安全解析布尔值。

    Returns:
        True / False / None（缺失或无法解析）
    """
    if _is_missing(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ('true', '1', 'yes', '是', 'y'):
            return True
        if s in ('false', '0', 'no', '否', 'n'):
            return False
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

    cfo_val = fin.get("cfo")
    net_profit_val = fin.get("net_profit")
    if _is_missing(cfo_val) or _is_missing(net_profit_val):
        out.append(_flag("CASH_PROFIT", "净现比", False, MISSING))
    else:
        ctp = cash_to_profit(cfo_val, net_profit_val)
        if ctp is None:
            out.append(_flag("CASH_PROFIT", "净现比", False, "净利润为零"))
        else:
            history = [D(v) for v in (fin.get("cash_to_profit_history") or [])]
            history = [v for v in history if v is not None]
            two_year_low = len(history) >= 2 and all(v < Decimal("0.5") for v in history[-2:])
            hit = ctp < Decimal("0.7")
            detail = f"净现比 {ctp:.2f}" + ("，连续两年低于 0.5" if two_year_low else "")
            out.append(_flag("CASH_PROFIT", "净现比", hit, detail, veto=two_year_low))

    np_val = fin.get("net_profit")
    cfo_val = fin.get("cfo")
    ta_val = fin.get("total_assets")
    if _is_missing(np_val) or _is_missing(cfo_val) or _is_missing(ta_val):
        out.append(_flag("ACCRUAL", "总应计比率", False, MISSING))
    else:
        np_, cfo_, ta = D(np_val), D(cfo_val), D(ta_val)
        if np_ is None or cfo_ is None or ta is None:
            out.append(_flag("ACCRUAL", "总应计比率", False, MISSING))
        elif ta == 0:
            out.append(_flag("ACCRUAL", "总应计比率", False, "总资产为零"))
        else:
            ar = (np_ - cfo_) / ta
            out.append(_flag("ACCRUAL", "总应计比率", ar > Decimal("0.10"), f"应计比率 {ar:.3f}"))

    ar_growth_val = fin.get("ar_growth")
    revenue_growth_val = fin.get("revenue_growth")
    if _is_missing(ar_growth_val) or _is_missing(revenue_growth_val):
        out.append(_flag("RECEIVABLE", "应收增速超营收", False, MISSING))
    else:
        gap = receivable_gap(ar_growth_val, revenue_growth_val)
        if gap is None:
            out.append(_flag("RECEIVABLE", "应收增速超营收", False, MISSING))
        else:
            out.append(_flag("RECEIVABLE", "应收增速超营收", gap > Decimal("20"),
                             f"应收增速快于营收 {gap:.1f} 个百分点"))

    gw_val = fin.get("goodwill")
    na_val = fin.get("net_assets")
    if _is_missing(gw_val) or _is_missing(na_val):
        out.append(_flag("GOODWILL", "商誉占净资产", False, MISSING))
    else:
        gw = goodwill_ratio(gw_val, na_val)
        if gw is None:
            out.append(_flag("GOODWILL", "商誉占净资产", False, "净资产为零"))
        else:
            out.append(_flag("GOODWILL", "商誉占净资产", gw > Decimal("0.30"), f"商誉占比 {gw:.1%}"))

    dp_val = fin.get("deducted_profit")
    np_val = fin.get("net_profit")
    if _is_missing(dp_val) or _is_missing(np_val):
        out.append(_flag("RECURRING", "扣非占归母", False, MISSING))
    else:
        rec = recurring_ratio(dp_val, np_val)
        if rec is None:
            out.append(_flag("RECURRING", "扣非占归母", False, "归母净利润为零"))
        else:
            out.append(_flag("RECURRING", "扣非占归母", rec < Decimal("0.70"), f"扣非占比 {rec:.1%}"))

    cash_val = fin.get("cash")
    debt_val = fin.get("interest_bearing_debt")
    ta_val = fin.get("total_assets")
    if _is_missing(cash_val) or _is_missing(debt_val) or _is_missing(ta_val):
        out.append(_flag("BIG_DEPOSIT_LOAN", "大存大贷", False, MISSING))
    else:
        cash, debt = D(cash_val), D(debt_val)
        ta = D(ta_val)
        if cash is None or debt is None or ta is None:
            out.append(_flag("BIG_DEPOSIT_LOAN", "大存大贷", False, MISSING))
        elif ta == 0:
            out.append(_flag("BIG_DEPOSIT_LOAN", "大存大贷", False, "总资产为零"))
        else:
            hit = cash / ta > Decimal("0.30") and debt / ta > Decimal("0.30")
            out.append(_flag("BIG_DEPOSIT_LOAN", "大存大贷", hit,
                             f"货币资金占比 {cash / ta:.1%}，有息负债占比 {debt / ta:.1%}", veto=hit))

    opinion = fin.get("audit_opinion")
    if _is_missing(opinion):
        out.append(_flag("AUDIT_OPINION", "审计意见", False, MISSING))
    else:
        opinion_str = str(opinion).strip()
        # 清洁意见的特征：必须包含"无保留"
        # 五种审计意见类型：
        # 1. 标准无保留意见 - 包含"无保留" ✓
        # 2. 带强调事项段的无保留意见 - 包含"无保留" ✓
        # 3. 保留意见 - 不包含"无保留" ✗
        # 4. 否定意见 - 不包含"无保留" ✗
        # 5. 无法表示意见 - 不包含"无保留" ✗
        # 任何不是无保留的意见都应否决
        is_clean = "无保留" in opinion_str
        hit = not is_clean
        out.append(_flag("AUDIT_OPINION", "审计意见", hit, opinion_str, veto=hit))

    pledge_val = fin.get("pledge_ratio")
    if _is_missing(pledge_val):
        out.append(_flag("PLEDGE", "股权质押", False, MISSING))
    else:
        pledge = D(pledge_val)
        if pledge is None:
            out.append(_flag("PLEDGE", "股权质押", False, MISSING))
        else:
            hit = pledge > Decimal("50")
            out.append(_flag("PLEDGE", "股权质押", hit, f"质押比例 {pledge:.1f}%", veto=hit))

    dr = fin.get("delisting_risk")
    if _is_missing(dr):
        out.append(_flag("DELISTING_RISK", "退市风险", False, MISSING))
    else:
        dr_val = _parse_bool(dr)
        if dr_val is None:
            out.append(_flag("DELISTING_RISK", "退市风险", False, MISSING))
        else:
            out.append(_flag("DELISTING_RISK", "退市风险", dr_val,
                             "存在退市风险" if dr_val else "无", veto=dr_val))

    inv = fin.get("under_investigation")
    if _is_missing(inv):
        out.append(_flag("INVESTIGATION", "立案调查", False, MISSING))
    else:
        inv_val = _parse_bool(inv)
        if inv_val is None:
            out.append(_flag("INVESTIGATION", "立案调查", False, MISSING))
        else:
            out.append(_flag("INVESTIGATION", "立案调查", inv_val,
                             "存在立案调查" if inv_val else "无", veto=inv_val))

    return out


def veto_triggered(flags) -> bool:
    return any(f["veto"] for f in flags)
