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

# 市场分组：A 股（沪/深/北）共用新浪源的中文报表列名；港股/美股共用 yfinance 的
# 英文报表科目名。两组字段名完全不同，但下游需要的十个 ratios 字段是一样的，
# 用一张按分组索引的字段名映射表来抽取，避免同一份「字段缺失就换个名字再试」
# 的回退链在多个函数里各写一份、日后改一个忘了改另一个。
_CN_MARKETS = ("CN_SH", "CN_SZ", "CN_BJ")


def _market_group(market):
    if market in _CN_MARKETS:
        return "CN"
    if market in ("HK", "US"):
        return "US"  # 港股/美股都走 yfinance，报表科目名一致
    return None


FIELD_MAP = {
    "CN": {
        "cfo": ("经营活动产生的现金流量净额",),
        "net_profit": ("净利润",),
        "total_assets": ("资产总计",),
        "goodwill": ("商誉",),
        "net_assets": ("所有者权益(或股东权益)合计", "归属于母公司股东权益合计"),
        "cash": ("货币资金",),
        "short_debt": ("短期借款",),
        "long_debt": ("长期借款",),
        "ar": ("应收账款", "应收票据及应收账款"),
        "revenue": ("营业收入", "营业总收入"),
    },
    "US": {
        "cfo": ("Operating Cash Flow",),
        "net_profit": ("Net Income",),
        "total_assets": ("Total Assets",),
        "goodwill": ("Goodwill",),
        "net_assets": ("Stockholders Equity", "Common Stock Equity"),
        "cash": ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
        "short_debt": ("Current Debt",),
        "long_debt": ("Long Term Debt",),
        "ar": ("Accounts Receivable", "Receivables"),
        "revenue": ("Total Revenue", "Operating Revenue"),
    },
}

# A 股财报季度、年度混杂在同一张表里，年报以「报告日」以 1231 结尾识别；
# 港股/美股走 yfinance 默认只返回年度数据（财年结束日不一定是 12-31，例如
# 苹果是 09-30），因此不按后缀筛选，全部当年度处理。
ANNUAL_FILTER = {
    "CN": lambda d: d.endswith("1231"),
    "US": None,
}


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))


def _D(v):
    """安全转 Decimal。None、空串、常见占位符（含浮点/Decimal 的 NaN）一律转为 None。

    pandas 的 NaN 经 json 往返后是 Python float('nan')；str(float('nan')) == 'nan'，
    而 Decimal('nan') 并不报错，会悄悄生成一个 NaN Decimal 而不是抛异常，一旦参与
    比较还会抛 InvalidOperation。ratios.py 的 D()/_is_missing() 已经在源头做了同样
    的拦截（NaN 不分市场，A 股新浪源和 yfinance 都用 NaN 表示「无此科目」），这里
    重复一遍是纵深防御：compute.py 自己也做 Decimal 运算（如权益比率、净利率、
    同比增速），不能假设所有输入都会先过一遍 ratios.check_red_flags。
    """
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, Decimal):
        return None if v.is_nan() else v
    s = str(v).strip()
    if not s or s.lower() in ("--", "nan", "none", "n/a"):
        return None
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError, AttributeError):
        return None
    return None if d.is_nan() else d


def _first_value(row, field_names):
    """按顺序尝试一组候选字段名，返回第一个非缺失的 Decimal 值。

    唯一的字段名回退实现——net_assets、cash、revenue 等「同一概念、不同报表
    版本里叫法不同」的字段，无论在 extract_derived 还是 derive_quality_dims
    里用，都调这一个函数，不允许两处各写一条回退链、日后改动只改了一处。
    """
    if not row:
        return None
    for name in field_names:
        v = _D(row.get(name))
        if v is not None:
            return v
    return None


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


def _yoy_growth_pct(rows, current_date, field_names):
    """同比增速（百分比数字，如 12.3 代表 12.3%）。

    必须用去年同一期（同月同日）对比，而不是相邻两期（例如二季度对一季度），
    否则会把环比误当同比，产生没有意义的增速。找不到同期数据就返回 None。
    `field_names` 是一组候选科目名，按顺序尝试，两期都要能用同一个候选名取到
    值才算数（不允许今年用「应收账款」、去年用「应收票据及应收账款」拼出增速，
    那样的同比没有实际意义）。
    """
    prior_date = _prior_year_date(current_date)
    cur_row = _find_by_date(rows, current_date)
    prior_row = _find_by_date(rows, prior_date)
    if cur_row is None or prior_row is None:
        return None
    for field in field_names:
        cur = _D(cur_row.get(field))
        prior = _D(prior_row.get(field))
        if cur is not None and prior is not None and prior != 0:
            return (cur - prior) / prior * Decimal(100)
    return None


def _cash_to_profit_history(cashflow, income, cfo_field, net_profit_field, annual_filter=None):
    """最近两个年度期的净现比历史，供 check_red_flags 判定「连续两年净现比低于
    0.5」的一票否决用。

    与主净现比指标（只需最新一期 cfo、net_profit 均非缺失）不同的地方：这里如果
    两期年报中有一期缺 cfo 或 net_profit 为零，只丢弃那一期，仍然把另一期的有效
    值返回——因为 check_red_flags 只有在 len(history) >= 2 时才会判定「连续两年」
    偏低，只给 1 个数不会误触发否决；比因为一期数据有问题就把另一期也一起扔掉更
    诚实：应该如实反映「只查到一期」，而不是「什么都没有」。
    """
    if annual_filter:
        cf_rows = [r for r in cashflow if annual_filter(str(r.get("报告日", "")))]
        inc_rows = [r for r in income if annual_filter(str(r.get("报告日", "")))]
    else:
        cf_rows = cashflow
        inc_rows = income
    cf_by_date = {str(r.get("报告日")): r for r in cf_rows}
    inc_by_date = {str(r.get("报告日")): r for r in inc_rows}
    common = sorted(set(cf_by_date) & set(inc_by_date), reverse=True)[:2]
    if not common:
        return None
    history = []
    for d in common:
        cfo = _D(cf_by_date[d].get(cfo_field))
        np_ = _D(inc_by_date[d].get(net_profit_field))
        if cfo is not None and np_ is not None and np_ != 0:
            history.append(cfo / np_)
    return history or None


def extract_derived(market, fin_block: dict) -> dict:
    """把 fetch_financials 的原始三张报表（balance/income/cashflow，均为新→旧
    排列、`报告日` 为 YYYYMMDD 字符串的 list[dict]）映射成 ratios.check_red_flags
    需要的扁平字段。A 股（新浪源，中文列名）与港股/美股（yfinance，英文科目名）
    共用同一套抽取逻辑，只是 `FIELD_MAP`/`ANNUAL_FILTER` 按市场分组取不同的字段
    名与年报口径。

    能映射的字段：cfo、net_profit、total_assets、goodwill、net_assets、cash、
    interest_bearing_debt（短期借款+长期借款的代理指标，两项都非缺失才求和，
    只拿到一侧就整体省略——按 0 处理会系统性低估负债，比缺失更危险）、ar_growth、
    revenue_growth、cash_to_profit_history。

    没有来源、宁可缺失也不编造的字段：deducted_profit（无论 A 股新浪源还是
    yfinance 都没有确认存在扣非净利润科目）、audit_opinion、pledge_ratio、
    delisting_risk、under_investigation（当前流水线完全没有对接这四类数据源，
    与市场无关）。这些字段不写进返回字典，check_red_flags 会自然读到 None、
    判定为「未获取到」。
    """
    if not fin_block or not fin_block.get("available"):
        return {}
    group = _market_group(market)
    if group is None:
        return {}
    fields = FIELD_MAP[group]
    annual_filter = ANNUAL_FILTER[group]

    derived: dict = {}
    balance = fin_block.get("balance") or []
    income = fin_block.get("income") or []
    cashflow = fin_block.get("cashflow") or []

    bal0 = balance[0] if balance else None
    inc0 = income[0] if income else None
    cf0 = cashflow[0] if cashflow else None

    if cf0 is not None:
        cfo = _first_value(cf0, fields["cfo"])
        if cfo is not None:
            derived["cfo"] = cfo

    if inc0 is not None:
        net_profit = _first_value(inc0, fields["net_profit"])
        if net_profit is not None:
            derived["net_profit"] = net_profit

    if bal0 is not None:
        total_assets = _first_value(bal0, fields["total_assets"])
        if total_assets is not None:
            derived["total_assets"] = total_assets

        goodwill = _first_value(bal0, fields["goodwill"])
        if goodwill is not None:
            derived["goodwill"] = goodwill

        net_assets = _first_value(bal0, fields["net_assets"])
        if net_assets is not None:
            derived["net_assets"] = net_assets

        cash = _first_value(bal0, fields["cash"])
        if cash is not None:
            derived["cash"] = cash

        short_debt = _first_value(bal0, fields["short_debt"])
        long_debt = _first_value(bal0, fields["long_debt"])
        if short_debt is not None and long_debt is not None:
            derived["interest_bearing_debt"] = short_debt + long_debt

        cur_date = str(bal0.get("报告日") or "")
        ar_growth = _yoy_growth_pct(balance, cur_date, fields["ar"])
        if ar_growth is not None:
            derived["ar_growth"] = ar_growth

    if inc0 is not None:
        cur_date_inc = str(inc0.get("报告日") or "")
        revenue_growth = _yoy_growth_pct(income, cur_date_inc, fields["revenue"])
        if revenue_growth is not None:
            derived["revenue_growth"] = revenue_growth

    history = _cash_to_profit_history(
        cashflow, income, fields["cfo"][0], fields["net_profit"][0], annual_filter
    )
    if history is not None:
        derived["cash_to_profit_history"] = history

    return derived


PE_PERCENTILE_TRADING_DAYS_5Y = 1220  # 与 sources_cn.PE_HISTORY_TRADING_DAYS_5Y 对应的口径常量


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """线性插值分位数（与 numpy.percentile 默认方法一致），入参须已排序。"""
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    k = (n - 1) * (pct / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _percentile_rank(sorted_vals: list[float], x: float) -> float:
    """x 在已排序序列中的分位排名（百分比），用于展示「当前 PE 处于历史第几分位」。"""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    count_le = sum(1 for v in sorted_vals if v <= x)
    return count_le / n * 100.0


def derive_valuation_anchor(pe_block: dict | None, current_price, market: str | None):
    """由 PE 五年历史推导估值锚（25/75 分位对应价格）。

    设计口径：当前 PE 除以分位 PE 等于当前价除以分位价（因为分位计算期间盈利
    不变），所以分位价 = 现价 × (分位 PE / 当前 PE)，不需要单独取 EPS。

    返回 (val, reason)：
    - val 非 None 时，是 {"low","high","formula"} 字典，formula 里带当前 PE、
      分位 PE、历史天数与换算价格，可核对算术；
    - val 为 None 时，reason 说明具体原因（亏损/PE 异常、历史缺失、港股/美股
      未接入等），调用方必须让买入区间退化为纯技术锚，而不是编造一个价格
      百分比式的假估值锚。

    港股/美股当前没有五年 PE 历史数据源，直接返回 (None, 原因)，不做任何替代
    近似——现价乘固定百分比正是本次要修复的缺陷本身，不能换个市场重犯。
    """
    group = _market_group(market)
    if group != "CN":
        return None, "港股/美股当前流水线未接入五年 PE 历史数据源，估值锚予以省略（不使用现价百分比近似）"

    if not pe_block or not pe_block.get("available"):
        reason = (pe_block or {}).get("reason") or "PE 历史数据未获取到"
        return None, f"PE 历史数据未获取到：{reason}"

    current_pe = pe_block.get("current_pe_ttm")
    if current_pe is None:
        return None, "当前 PE(TTM) 未获取到，无法构造估值锚"
    current_pe = float(current_pe)
    if current_pe <= 0:
        return None, (
            f"当前 PE(TTM) 为 {current_pe:.2f}（公司亏损或 PE 异常），估值分位数没有意义，不构造估值锚"
        )

    if current_price is None:
        return None, "现价缺失，无法把分位 PE 换算成分位价"
    current_price = float(current_price)

    raw_history = pe_block.get("pe_ttm_history") or []
    positive_history = sorted(float(v) for v in raw_history if v is not None and float(v) > 0)
    if not positive_history:
        return None, "PE 历史序列中没有有效（正值）样本，无法计算分位数"

    days_used = len(positive_history)
    pe25 = _percentile(positive_history, 25)
    pe75 = _percentile(positive_history, 75)
    rank = _percentile_rank(positive_history, current_pe)

    price_low = current_price * (pe25 / current_pe)
    price_high = current_price * (pe75 / current_pe)

    val = pricing.valuation_anchor(price_low, price_high)

    if days_used >= PE_PERCENTILE_TRADING_DAYS_5Y:
        coverage = f"{days_used} 个交易日"
    else:
        coverage = (
            f"{days_used} 个交易日（不足五年所需的约 {PE_PERCENTILE_TRADING_DAYS_5Y} 个交易日，"
            "本次按现有天数计算，不冒充完整五年分位）"
        )

    val["formula"] = (
        f"当前 PE(TTM) {current_pe:.2f}（处于历史 {rank:.1f} 分位），历史 {coverage} 中 "
        f"25 分位 PE {pe25:.2f}、75 分位 PE {pe75:.2f}，按现价 {current_price:.2f} × "
        f"(分位 PE / 当前 PE) 换算得 [{price_low:.2f}, {price_high:.2f}]"
    )
    val["meta"] = {
        "current_pe_ttm": round(current_pe, 2),
        "current_pe_percentile": round(rank, 1),
        "pe25": round(pe25, 2),
        "pe75": round(pe75, 2),
        "days_used": days_used,
        "days_required_for_5y": PE_PERCENTILE_TRADING_DAYS_5Y,
        "source": pe_block.get("source"),
        "fetched_at": pe_block.get("fetched_at"),
    }
    return val, None


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


def derive_quality_dims(fin: dict, flags: list, market: str | None = None) -> dict:
    """由财报红旗与真实报表数据推出 Q 轴维度分。

    statement：红旗命中率的反向映射，沿用既有逻辑。
    health：用权益比率（所有者权益 / 总资产）代理财务健康度——权益占比越高，
        杠杆越低，抗风险能力越强，直接按百分比映射到 0~100 分。
    profitability：用净利率（净利润 / 营业收入）代理盈利能力，0% 记 50 分
        （中性），每 1 个百分点净利率对应 2 分浮动。

    字段名回退链复用 `FIELD_MAP` + `_first_value`，与 `extract_derived` 共用
    同一份映射表，不再各写一份「先试这个名字，缺了再试那个名字」的逻辑——
    两处一旦各写一份，日后改字段名很容易只改一处、悄悄产生分歧。

    `market` 缺省（None）时按 A 股字段名读取，保持向后兼容；`run()` 会显式
    传入市场以支持港股/美股。

    两个维度只要输入数据任一缺失，就整体不写入该维度——scoring.py 会对在场
    的维度重新加权归一，省略比编造一个 60 分的占位符更诚实。
    """
    dims = {}
    hits = sum(1 for f in flags if f["hit"])
    known = sum(1 for f in flags if "未获取到" not in f["detail"])
    if known:
        dims["statement"] = _clamp(100.0 - hits * 100.0 / max(known, 1))

    group = _market_group(market) or "CN"
    fields = FIELD_MAP[group]

    balance = (fin or {}).get("balance") or []
    income = (fin or {}).get("income") or []
    bal0 = balance[0] if balance else None
    inc0 = income[0] if income else None

    if bal0 is not None:
        total_assets = _first_value(bal0, fields["total_assets"])
        net_assets = _first_value(bal0, fields["net_assets"])
        if total_assets is not None and net_assets is not None and total_assets != 0:
            equity_ratio = net_assets / total_assets
            dims["health"] = _clamp(float(equity_ratio) * 100.0)

    if inc0 is not None:
        net_profit = _first_value(inc0, fields["net_profit"])
        revenue = _first_value(inc0, fields["revenue"])
        if net_profit is not None and revenue is not None and revenue != 0:
            net_margin = net_profit / revenue
            dims["profitability"] = _clamp(50.0 + float(net_margin) * 200.0)

    return dims


def run(raw: dict) -> dict:
    kline = raw.get("kline") or {}
    tech = indicators.compute_all(kline) if kline.get("close") else {}

    market = raw.get("market")
    fin_block = raw.get("financials") or {}
    derived = extract_derived(market, fin_block)
    flags = ratios.check_red_flags(derived)
    veto = ratios.veto_triggered(flags)

    q = scoring.quality_score(derive_quality_dims(fin_block, flags, market))
    t = scoring.timing_score(derive_timing_dims(tech))
    q_score = scoring.apply_veto(q["score"], veto)
    matrix = scoring.map_matrix(q_score, t["score"], veto)

    gates = pricing.gate_check(tech.get("rsi14"), tech.get("bias_ma5"))

    blocked = bool(raw.get("blocked", False))
    block_reasons = raw.get("block_reasons") or []

    prices, price_error = {}, None
    if blocked:
        # 数据本身被 fetch_data 的硬性阻断线判了「不完整/不可信」（行情缺失、
        # 财务缺失或完备率不足），此时 kline 的收盘价可能是陈旧或片面的
        # last_close（indicators.compute_all 只看 kline，不看 quote 是否成功），
        # 绝不能拿它去推导一个看起来言之凿凿的买入区间/目标价/止损价。宁可不给
        # 价位，也不能让读者把「数据不全时算出来的数字」误当成「数据齐全时算出
        # 来的数字」。
        price_error = (
            "数据被阻断（" + "；".join(block_reasons) + "），不推导买入区间/目标价/止损价"
            if block_reasons
            else "数据被阻断，不推导买入区间/目标价/止损价"
        )
    else:
        try:
            closes = kline.get("close") or []
            prior_low = min(closes[-60:]) if len(closes) >= 20 else None
            resistance = max(closes[-60:]) if len(closes) >= 20 else None
            last = tech.get("last_close")
            boll = tech.get("boll") or {}
            tech_anchor = pricing.technical_anchor(tech.get("ma20"), prior_low, boll.get("lower"))

            val, val_reason = derive_valuation_anchor(raw.get("pe_history"), last, market)

            if val is not None:
                prices["buy_range"] = pricing.buy_range(val, tech_anchor)
                prices["valuation"] = dict(val.get("meta") or {}, low=val["low"], high=val["high"])
            else:
                prices["buy_range"] = pricing.buy_range_technical_only(tech_anchor, val_reason)
                prices["valuation"] = {"available": False, "reason": val_reason}

            val_high_for_target = val["high"] if val is not None else None
            prices["target"] = pricing.target_price(val_high_for_target, resistance, None)
            entry = prices["buy_range"]["high"]
            prices["stop_loss"] = pricing.stop_loss(entry, tech.get("atr14"), prior_low)
        except pricing.PricingBlocked as exc:
            price_error = str(exc)

    if blocked:
        # 同样的道理，矩阵结论也不能装作数据齐全——不管 Q/T 算出来是多少，一律
        # 强制回避，并把阻断原因带在 conflict 里，让读者看得到「为什么」，而不
        # 是只看到一个孤零零的「回避」。
        reason_text = "；".join(block_reasons) if block_reasons else "数据不完整或不可信"
        matrix = {
            "verdict": scoring.VERDICT_AVOID,
            "conflict": f"数据被阻断（{reason_text}），在数据补齐前一律回避，不构成任何买入或候选结论",
        }

    return {
        "code": raw.get("code"),
        "market": market,
        "currency": raw.get("currency"),
        "completeness": raw.get("completeness"),
        "blocked": blocked,
        "block_reasons": block_reasons,
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
