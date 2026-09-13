# -*- coding: utf-8 -*-
"""A 股取数。降级链来自 2026-09-13 实测，东财永远是最后一档。

限流边界提示：本模块只对经由 `HttpClient.get`/`HttpClient.post` 发出的请求施加
2 秒间隔、10 次调用上限与熔断保护。`fetch_market_extras` 与 `fetch_financials` 里
对 `akshare` 的调用（`stock_lhb_detail_em`、`stock_financial_analysis_indicator`、
`stock_financial_report_sina` 等）由 akshare 内部自行发起 HTTP 请求，完全绕开
`HttpClient`，因此不计入东财的调用上限、不受 2 秒间隔约束，其失败也不会触发熔断。
也就是说，即使 `client` 已经判定东财熔断，这些 akshare 调用仍可能持续向东财发起
请求。这是架构层面的限制，本任务范围内未做处理，留给后续任务收口。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import endpoints
from http_client import SourceDown


def _now():
    return datetime.now().isoformat(timespec="seconds")


def fetch_quote(client, norm) -> dict:
    errors = []
    try:
        r = client.get(endpoints.TENCENT_QUOTE.format(symbol=norm["tencent"]), source="tencent")
        try:
            parts = r.text.split("~")
            if len(parts) > 3:
                return {
                    "price": float(parts[3]),
                    "name": parts[1],
                    "source": "腾讯 qt.gtimg.cn",
                    "fetched_at": _now(),
                }
            errors.append("腾讯返回格式异常")
        except (ValueError, IndexError) as exc:
            errors.append(f"腾讯响应解析失败: {type(exc).__name__}: {exc}")
    except SourceDown as exc:
        errors.append(str(exc))

    try:
        r = client.get(endpoints.EM_QUOTE.format(secid=norm["eastmoney_secid"]), source="eastmoney")
        try:
            data = r.json().get("data") or {}
            if data.get("f43") is not None:
                return {
                    "price": float(data["f43"]) / 100.0,
                    "name": data.get("f58", ""),
                    "source": "东财 push2",
                    "fetched_at": _now(),
                }
            errors.append("东财返回空数据")
        except (ValueError, TypeError) as exc:
            errors.append(f"东财响应解析失败: {type(exc).__name__}: {exc}")
    except SourceDown as exc:
        errors.append(str(exc))

    raise SourceDown("行情取数全部失败: " + "; ".join(errors))


def fetch_kline(client, norm, days=250) -> dict:
    end = datetime.now()
    start = end - timedelta(days=int(days * 1.6))
    baostock_skip_reason = None

    try:
        import baostock as bs

        bs.login()
        rows = []
        try:
            rs = bs.query_history_k_data_plus(
                norm["baostock"],
                "date,high,low,close,volume",
                start_date=start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="2",
            )
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
            if not rows and rs.error_code != "0":
                baostock_skip_reason = (
                    f"baostock 查询返回错误码 {rs.error_code}: {getattr(rs, 'error_msg', '')}"
                )
        finally:
            bs.logout()
        if rows:
            return {
                "dates": [r[0] for r in rows],
                "high": [float(r[1]) for r in rows],
                "low": [float(r[2]) for r in rows],
                "close": [float(r[3]) for r in rows],
                "volume": [float(r[4]) for r in rows],
                "source": "baostock",
                "fetched_at": _now(),
                "baostock_skip_reason": None,
            }
        if baostock_skip_reason is None:
            baostock_skip_reason = "baostock 登录/查询未报错，但未返回任何行情行"
    except Exception as exc:
        baostock_skip_reason = f"baostock 不可用: {type(exc).__name__}: {str(exc)[:120]}"

    url = endpoints.EM_KLINE.format(
        secid=norm["eastmoney_secid"],
        beg=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )
    r = client.get(url, source="eastmoney")
    klines = (r.json().get("data") or {}).get("klines") or []
    if not klines:
        raise SourceDown(f"K 线取数全部失败（baostock 跳过原因: {baostock_skip_reason}）")
    dates, highs, lows, closes, vols = [], [], [], [], []
    for line in klines:
        f = line.split(",")
        dates.append(f[0])
        closes.append(float(f[2]))
        highs.append(float(f[3]))
        lows.append(float(f[4]))
        vols.append(float(f[5]))
    return {
        "dates": dates, "high": highs, "low": lows, "close": closes, "volume": vols,
        "source": "东财 push2his", "fetched_at": _now(),
        "baostock_skip_reason": baostock_skip_reason,
    }


def _slice_with_annuals(df, min_annuals=3, date_col="报告日"):
    """按 `date_col` 取从最新往回数、至少覆盖 `min_annuals` 个年报（以 1231 结尾）的行。

    数据按新浪源约定为新→旧排列。返回 (切片后的 df, 覆盖的期数, 其中年报数)。
    若全表年报数不足 `min_annuals`，则返回全表并如实报告实际年报数。
    """
    if df is None or len(df) == 0 or date_col not in df.columns:
        return df, 0, 0
    dates = df[date_col].astype(str)
    annual_idxs = [i for i, d in enumerate(dates) if d.endswith("1231")]
    if len(annual_idxs) >= min_annuals:
        cutoff = annual_idxs[min_annuals - 1] + 1
        annuals_included = min_annuals
    else:
        cutoff = len(df)
        annuals_included = len(annual_idxs)
    return df.head(cutoff), cutoff, annuals_included


def fetch_financials(norm) -> dict:
    fetched_at = _now()
    market_value = norm["market"].value

    if market_value == "CN_BJ":
        return {
            "source": "akshare 新浪源",
            "fetched_at": fetched_at,
            "available": False,
            "reason": (
                "新浪财务报表源（stock_financial_report_sina）不覆盖北交所：无论拼 "
                "bj 前缀还是 sz 前缀均返回 TypeError('NoneType' object is not "
                "subscriptable)，本函数不再对北交所代码发起该请求"
            ),
            "manual_check": "https://www.bse.cn",
        }

    import akshare as ak

    if market_value == "CN_SH":
        prefix = "sh"
    elif market_value == "CN_SZ":
        prefix = "sz"
    else:
        # 本函数按设计只服务 A 股（沪/深/北），北交所已在上面提前返回；
        # 落到这里说明调用方传入了非 A 股 norm，明确兜底为 sz 而不是隐式穿透。
        prefix = "sz"
    stock = f"{prefix}{norm['code']}"
    out = {"source": "akshare 新浪源", "fetched_at": fetched_at, "available": False}
    try:
        balance = ak.stock_financial_report_sina(stock=stock, symbol="资产负债表")
        income = ak.stock_financial_report_sina(stock=stock, symbol="利润表")
        cashflow = ak.stock_financial_report_sina(stock=stock, symbol="现金流量表")

        balance_slice, balance_periods, balance_annuals = _slice_with_annuals(balance)
        income_slice, income_periods, income_annuals = _slice_with_annuals(income)
        cashflow_slice, cashflow_periods, cashflow_annuals = _slice_with_annuals(cashflow)

        out.update({
            "available": True,
            "balance_rows": len(balance),
            "income_rows": len(income),
            "cashflow_rows": len(cashflow),
            "balance": balance_slice.to_dict("records"),
            "income": income_slice.to_dict("records"),
            "cashflow": cashflow_slice.to_dict("records"),
            "balance_periods_included": balance_periods,
            "balance_annuals_included": balance_annuals,
            "income_periods_included": income_periods,
            "income_annuals_included": income_annuals,
            "cashflow_periods_included": cashflow_periods,
            "cashflow_annuals_included": cashflow_annuals,
        })
    except Exception as exc:
        out["reason"] = f"{type(exc).__name__}: {str(exc)[:80]}"
        return out

    try:
        ind = ak.stock_financial_analysis_indicator(symbol=norm["code"], start_year="2023")
        out["indicators"] = ind.head(4).to_dict("records")
    except Exception as exc:
        out["indicators"] = None
        out["indicators_reason"] = f"{type(exc).__name__}"
    return out


def fetch_market_extras(client, norm) -> dict:
    if client.is_tripped("eastmoney"):
        return {
            "available": False,
            "reason": "东财已熔断，龙虎榜与两融未获取到",
            "manual_check": "http://www.sse.com.cn 或 http://www.szse.cn",
            "source": "akshare 东财源",
            "fetched_at": _now(),
        }
    import akshare as ak

    out = {"available": True, "fetched_at": _now(), "source": "akshare 东财源"}
    try:
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        lhb = ak.stock_lhb_detail_em(start_date=start, end_date=end)
        if "代码" in lhb.columns:
            hits = lhb[lhb["代码"] == norm["code"]]
            out["lhb_count"] = int(len(hits))
        else:
            out["lhb_count"] = None
            out["lhb_reason"] = "东财龙虎榜接口返回结果缺少'代码'列，无法按代码过滤，非真实零命中"
    except Exception as exc:
        out["lhb_count"] = None
        out["lhb_reason"] = f"{type(exc).__name__}"
    return out
