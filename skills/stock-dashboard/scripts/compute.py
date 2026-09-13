# -*- coding: utf-8 -*-
"""计算总入口。不联网，只吃 fetch_data 的 JSON。"""
from __future__ import annotations

import argparse
import io
import json
import math
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import indicators
import pricing
import ratios
import scoring


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


def _D(v):
    """安全转 Decimal。None、空串、常见占位符（含浮点 NaN）一律转为 None。

    pandas 的 NaN 经 json 往返后是 Python float('nan')；str(float('nan')) == 'nan'，
    而 Decimal('nan') 并不报错，会悄悄生成一个 NaN Decimal 而不是抛异常。
    ratios.py 自己的 D() 有同样的隐患（对 NaN 不当作缺失处理），所以这里必须先把
    NaN 拦在 compute.py 这一层，绝不把 NaN 值放进 check_red_flags 的输入字典里，
    否则 fin.get(key) 非 None、_is_missing() 也认不出 NaN，红旗判定会被污染。
    """
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    if not s or s.lower() in ("--", "nan", "none", "n/a"):
        return None
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError, AttributeError):
        return None
    if d.is_nan():
        return None
    return d


def _find_by_date(rows, date_str):
    if not date_str:
        return None
    for r in rows:
        if str(r.get("报告日")) == date_str:
            return r
    return None


def _prior_year_date(date_str):
    if not date_str or len(date_str) != 8 or not date_str.isdigit():
        return None
    return f"{int(date_str[:4]) - 1}{date_str[4:]}"


def _yoy_growth_pct(rows, field, current_date):
    """同比增速（百分比数字，如 12.3 代表 12.3%）。

    必须用去年同一期（同月同日）对比，而不是相邻两期（例如二季度对一季度），
    否则会把环比误当同比，产生没有意义的增速。找不到同期数据就返回 None。
    """
    prior_date = _prior_year_date(current_date)
    cur_row = _find_by_date(rows, current_date)
    prior_row = _find_by_date(rows, prior_date)
    if cur_row is None or prior_row is None:
        return None
    cur = _D(cur_row.get(field))
    prior = _D(prior_row.get(field))
    if cur is None or prior is None or prior == 0:
        return None
    return (cur - prior) / prior * Decimal(100)


def _cash_to_profit_history(cashflow, income):
    """最近两个「年报」期（报告日以 1231 结尾）的净现比。

    任务 8 保证 balance/income/cashflow 各自的年报口径至少覆盖 3 期（如果公司历史
    够长），但不足两期年报时（新股、次新股），宁可整体不给这个 key，也不要拿一期
    凑数——那样会让 check_red_flags 里「连续两年低于 0.5」的判断失真。
    """
    annuals_cf = {str(r.get("报告日")): r for r in cashflow if str(r.get("报告日", "")).endswith("1231")}
    annuals_inc = {str(r.get("报告日")): r for r in income if str(r.get("报告日", "")).endswith("1231")}
    common = sorted(set(annuals_cf) & set(annuals_inc), reverse=True)[:2]
    if len(common) < 2:
        return None
    history = []
    for d in common:
        cfo = _D(annuals_cf[d].get("经营活动产生的现金流量净额"))
        np_ = _D(annuals_inc[d].get("净利润"))
        if cfo is None or np_ is None or np_ == 0:
            return None
        history.append(cfo / np_)
    return history if len(history) >= 2 else None


def extract_derived_cn(fin_block: dict) -> dict:
    """把 A 股 sources_cn.fetch_financials 的原始三张报表映射成 ratios.check_red_flags
    需要的扁平字段。sources_cn 只提供 balance/income/cashflow 三个列表（新→旧排列，
    `报告日` 为 YYYYMMDD 字符串），并不提供 `derived`，这一层的映射就是补上这个缺口。

    能映射的字段：cfo、net_profit、total_assets、goodwill、net_assets、cash、
    interest_bearing_debt（短期借款+长期借款的代理指标）、ar_growth、revenue_growth、
    cash_to_profit_history。

    没有来源、宁可缺失也不编造的字段：deducted_profit（新浪报表未确认有扣非净利润
    列）、audit_opinion、pledge_ratio、delisting_risk、under_investigation（当前流水
    线完全没有对接审计意见、质押、退市风险、立案调查的数据源）。这些字段不写进返回
    字典，check_red_flags 会自然读到 None、判定为「未获取到」。
    """
    derived: dict = {}
    balance = fin_block.get("balance") or []
    income = fin_block.get("income") or []
    cashflow = fin_block.get("cashflow") or []

    bal0 = balance[0] if balance else None
    inc0 = income[0] if income else None
    cf0 = cashflow[0] if cashflow else None

    if cf0 is not None:
        cfo = _D(cf0.get("经营活动产生的现金流量净额"))
        if cfo is not None:
            derived["cfo"] = cfo

    if inc0 is not None:
        net_profit = _D(inc0.get("净利润"))
        if net_profit is not None:
            derived["net_profit"] = net_profit

    if bal0 is not None:
        total_assets = _D(bal0.get("资产总计"))
        if total_assets is not None:
            derived["total_assets"] = total_assets

        goodwill = _D(bal0.get("商誉"))
        if goodwill is not None:
            derived["goodwill"] = goodwill

        net_assets = _D(bal0.get("所有者权益(或股东权益)合计"))
        if net_assets is None:
            net_assets = _D(bal0.get("归属于母公司股东权益合计"))
        if net_assets is not None:
            derived["net_assets"] = net_assets

        cash = _D(bal0.get("货币资金"))
        if cash is not None:
            derived["cash"] = cash

        # 有息负债不是单一列，短期借款+长期借款是合理代理指标（不含应付债券等其他
        # 有息负债形式）。两者必须都拿到才求和：只拿到一侧会系统性低估有息负债，
        # 比悄悄按 0 处理更危险，所以宁可整体缺失。
        short_debt = _D(bal0.get("短期借款"))
        long_debt = _D(bal0.get("长期借款"))
        if short_debt is not None and long_debt is not None:
            derived["interest_bearing_debt"] = short_debt + long_debt

        cur_date = str(bal0.get("报告日") or "")
        ar_growth = _yoy_growth_pct(balance, "应收账款", cur_date)
        if ar_growth is None:
            ar_growth = _yoy_growth_pct(balance, "应收票据及应收账款", cur_date)
        if ar_growth is not None:
            derived["ar_growth"] = ar_growth

    if inc0 is not None:
        cur_date_inc = str(inc0.get("报告日") or "")
        revenue_growth = _yoy_growth_pct(income, "营业收入", cur_date_inc)
        if revenue_growth is None:
            revenue_growth = _yoy_growth_pct(income, "营业总收入", cur_date_inc)
        if revenue_growth is not None:
            derived["revenue_growth"] = revenue_growth

    history = _cash_to_profit_history(cashflow, income)
    if history is not None:
        derived["cash_to_profit_history"] = history

    return derived


def extract_derived(market: str | None, fin_block: dict) -> dict:
    """按市场分派映射。A 股走 extract_derived_cn；港股/美股当前源头
    （sources_hk_us.fetch_financials）只记录报表行数与 yfinance info 的键名列表，
    并不保留资产负债表/利润表/现金流量表的具体数值，因此暂时没有可映射的字段，
    诚实返回空字典，让全部十项红旗如实显示「未获取到」，而不是编造数字。
    """
    if not fin_block or not fin_block.get("available"):
        return {}
    if market in ("CN_SH", "CN_SZ", "CN_BJ"):
        return extract_derived_cn(fin_block)
    return {}


def derive_timing_dims(tech: dict) -> dict:
    dims = {}
    close = tech.get("last_close")
    ma20, ma60, ma120 = tech.get("ma20"), tech.get("ma60"), tech.get("ma120")
    if close and ma20 and ma60:
        score = 50.0
        score += 20.0 if close > ma20 else -20.0
        score += 20.0 if close > ma60 else -20.0
        if ma120:
            score += 10.0 if close > ma120 else -10.0
        dims["trend"] = _clamp(score)

    rsi = tech.get("rsi14")
    macd = tech.get("macd")
    if rsi is not None:
        score = _clamp(float(rsi))
        if macd and macd.get("hist") is not None:
            score += 15.0 if macd["hist"] > 0 else -15.0
        dims["momentum"] = _clamp(score)

    vr = tech.get("vol_ratio")
    if vr is not None:
        dims["volume"] = _clamp(50.0 + (float(vr) - 1.0) * 40.0)

    boll = tech.get("boll")
    if boll and boll.get("pct_b") is not None:
        dims["position"] = _clamp(100.0 - float(boll["pct_b"]) * 100.0)

    return dims


def derive_quality_dims(fin: dict, flags: list) -> dict:
    """由财报红旗与真实报表数据推出 Q 轴维度分。

    statement：红旗命中率的反向映射，沿用既有逻辑。
    health：用权益比率（所有者权益合计 / 资产总计）代理财务健康度——权益占比越高，
        杠杆越低，抗风险能力越强，直接按百分比映射到 0~100 分。
    profitability：用净利率（净利润 / 营业收入）代理盈利能力，0% 记 50 分（中性），
        每 1 个百分点净利率对应 2 分浮动。

    两个维度只要输入数据（资产总计/所有者权益/净利润/营业收入）任一缺失，就整体
    不写入该维度——scoring.py 会对在场的维度重新加权归一，省略比编造一个 60 分的
    占位符更诚实。仅当财务数据完全不可用（fin 为空或 available=False）时才两者
    都缺失，例如当前港股/美股管线尚未保留报表明细的情况。
    """
    dims = {}
    hits = sum(1 for f in flags if f["hit"])
    known = sum(1 for f in flags if "未获取到" not in f["detail"])
    if known:
        dims["statement"] = _clamp(100.0 - hits * 100.0 / max(known, 1))

    balance = (fin or {}).get("balance") or []
    income = (fin or {}).get("income") or []
    bal0 = balance[0] if balance else None
    inc0 = income[0] if income else None

    if bal0 is not None:
        total_assets = _D(bal0.get("资产总计"))
        net_assets = _D(bal0.get("所有者权益(或股东权益)合计"))
        if net_assets is None:
            net_assets = _D(bal0.get("归属于母公司股东权益合计"))
        if total_assets is not None and net_assets is not None and total_assets != 0:
            equity_ratio = net_assets / total_assets
            dims["health"] = _clamp(float(equity_ratio) * 100.0)

    if inc0 is not None:
        net_profit = _D(inc0.get("净利润"))
        revenue = _D(inc0.get("营业收入"))
        if revenue is None:
            revenue = _D(inc0.get("营业总收入"))
        if net_profit is not None and revenue is not None and revenue != 0:
            net_margin = net_profit / revenue
            dims["profitability"] = _clamp(50.0 + float(net_margin) * 200.0)

    return dims


def run(raw: dict) -> dict:
    kline = raw.get("kline") or {}
    tech = indicators.compute_all(kline) if kline.get("close") else {}

    fin_block = raw.get("financials") or {}
    derived = extract_derived(raw.get("market"), fin_block)
    flags = ratios.check_red_flags(derived)
    veto = ratios.veto_triggered(flags)

    q = scoring.quality_score(derive_quality_dims(fin_block, flags))
    t = scoring.timing_score(derive_timing_dims(tech))
    q_score = scoring.apply_veto(q["score"], veto)
    matrix = scoring.map_matrix(q_score, t["score"], veto)

    gates = pricing.gate_check(tech.get("rsi14"), tech.get("bias_ma5"))

    prices, price_error = {}, None
    try:
        closes = kline.get("close") or []
        prior_low = min(closes[-60:]) if len(closes) >= 20 else None
        resistance = max(closes[-60:]) if len(closes) >= 20 else None
        last = tech.get("last_close")
        boll = tech.get("boll") or {}
        val = pricing.valuation_anchor(last * 0.85, last * 1.20) if last else None
        tech_anchor = pricing.technical_anchor(tech.get("ma20"), prior_low, boll.get("lower"))
        if val:
            prices["buy_range"] = pricing.buy_range(val, tech_anchor)
            prices["target"] = pricing.target_price(val["high"], resistance, None)
            entry = prices["buy_range"]["high"]
            prices["stop_loss"] = pricing.stop_loss(entry, tech.get("atr14"), prior_low)
    except pricing.PricingBlocked as exc:
        price_error = str(exc)

    return {
        "code": raw.get("code"),
        "market": raw.get("market"),
        "currency": raw.get("currency"),
        "completeness": raw.get("completeness"),
        "blocked": raw.get("blocked", False),
        "tech": tech,
        "flags": flags,
        "veto": veto,
        "quality": dict(q, score=q_score),
        "timing": t,
        "matrix": matrix,
        "gates": gates,
        "prices": prices,
        "price_error": price_error,
        "data_sources": raw.get("data_sources"),
    }


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="计算总入口")
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", dest="dst", required=True)
    args = ap.parse_args()

    raw = json.loads(Path(args.src).read_text(encoding="utf-8"))
    result = run(raw)
    Path(args.dst).write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(
        f"{result['code']} Q {result['quality']['score']:.0f} "
        f"T {result['timing']['score']:.0f} {result['matrix']['verdict']} -> {args.dst}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
