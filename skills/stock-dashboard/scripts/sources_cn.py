# -*- coding: utf-8 -*-
"""A 股取数。降级链来自 2026-09-13 实测，东财永远是最后一档。"""
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
        parts = r.text.split("~")
        if len(parts) > 3:
            return {
                "price": float(parts[3]),
                "name": parts[1],
                "source": "腾讯 qt.gtimg.cn",
                "fetched_at": _now(),
            }
        errors.append("腾讯返回格式异常")
    except SourceDown as exc:
        errors.append(str(exc))

    try:
        r = client.get(endpoints.EM_QUOTE.format(secid=norm["eastmoney_secid"]), source="eastmoney")
        data = r.json().get("data") or {}
        if data.get("f43") is not None:
            return {
                "price": float(data["f43"]) / 100.0,
                "name": data.get("f58", ""),
                "source": "东财 push2",
                "fetched_at": _now(),
            }
        errors.append("东财返回空数据")
    except SourceDown as exc:
        errors.append(str(exc))

    raise SourceDown("行情取数全部失败: " + "; ".join(errors))


def fetch_kline(client, norm, days=250) -> dict:
    end = datetime.now()
    start = end - timedelta(days=int(days * 1.6))

    try:
        import baostock as bs

        bs.login()
        try:
            rs = bs.query_history_k_data_plus(
                norm["baostock"],
                "date,high,low,close,volume",
                start_date=start.strftime("%Y-%m-%d"),
                end_date=end.strftime("%Y-%m-%d"),
                frequency="d",
                adjustflag="2",
            )
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
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
            }
    except Exception:
        pass

    url = endpoints.EM_KLINE.format(
        secid=norm["eastmoney_secid"],
        beg=start.strftime("%Y%m%d"),
        end=end.strftime("%Y%m%d"),
    )
    r = client.get(url, source="eastmoney")
    klines = (r.json().get("data") or {}).get("klines") or []
    if not klines:
        raise SourceDown("K 线取数全部失败")
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
    }


def fetch_financials(norm) -> dict:
    import akshare as ak

    prefix = "sh" if norm["market"].value == "CN_SH" else "sz"
    stock = f"{prefix}{norm['code']}"
    out = {"source": None, "fetched_at": _now(), "available": False}
    try:
        balance = ak.stock_financial_report_sina(stock=stock, symbol="资产负债表")
        income = ak.stock_financial_report_sina(stock=stock, symbol="利润表")
        cashflow = ak.stock_financial_report_sina(stock=stock, symbol="现金流量表")
        out.update({
            "source": "akshare 新浪源",
            "available": True,
            "balance_rows": len(balance),
            "income_rows": len(income),
            "cashflow_rows": len(cashflow),
            "balance": balance.head(3).to_dict("records"),
            "income": income.head(3).to_dict("records"),
            "cashflow": cashflow.head(3).to_dict("records"),
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
        }
    import akshare as ak

    out = {"available": True, "fetched_at": _now(), "source": "akshare 东财源"}
    try:
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")
        lhb = ak.stock_lhb_detail_em(start_date=start, end_date=end)
        hits = lhb[lhb["代码"] == norm["code"]] if "代码" in lhb.columns else lhb.head(0)
        out["lhb_count"] = int(len(hits))
    except Exception as exc:
        out["lhb_count"] = None
        out["lhb_reason"] = f"{type(exc).__name__}"
    return out
