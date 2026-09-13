# -*- coding: utf-8 -*-
"""统一取数入口。对话层不需要知道内部走了哪个源。"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from http_client import HttpClient, SourceDown
from market import Market, normalize
import sources_cn
import sources_hk_us

COMPLETENESS_FLOOR = 0.70


def _is_cn(market) -> bool:
    return market in (Market.CN_SH, Market.CN_SZ, Market.CN_BJ)


def fetch_one(code: str, client=None) -> dict:
    client = client or HttpClient()
    fetched_at = datetime.now().isoformat(timespec="seconds")

    try:
        norm = normalize(code)
    except Exception as exc:
        return {
            "code": code,
            "raw": code,
            "market": None,
            "currency": None,
            "fetched_at": fetched_at,
            "data_sources": {},
            "errors": {"normalize": f"{type(exc).__name__}: {exc}"},
            "quote": None,
            "kline": None,
            "financials": None,
            "extras": {
                "available": False,
                "reason": "代码无法识别，未发起任何取数",
                "source": "market.normalize",
                "fetched_at": fetched_at,
            },
            "completeness": 0.0,
            "blocked": True,
            "block_reasons": ["代码无法识别，市场未判定"],
            "missing": ["quote", "kline", "financials"],
            "manual_check": None,
        }

    cn = _is_cn(norm["market"])
    mod = sources_cn if cn else sources_hk_us

    payload = {
        "code": norm["code"],
        "raw": norm["raw"],
        "market": norm["market"].value,
        "currency": norm["currency"],
        "fetched_at": fetched_at,
        "data_sources": {},
        "errors": {},
    }

    for key, fn in (
        ("quote", lambda: mod.fetch_quote(client, norm)),
        ("kline", lambda: mod.fetch_kline(client, norm)),
        ("financials", lambda: mod.fetch_financials(norm)),
    ):
        try:
            value = fn()
            payload[key] = value
            payload["data_sources"][key] = value.get("source")
        except SourceDown as exc:
            payload[key] = None
            payload["errors"][key] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            # 非 SourceDown 的异常（例如我们自己代码里的 bug、格式解析错误）与真实数据源
            # 故障用不同前缀区分，读者不应把两者混为一谈。
            payload[key] = None
            payload["errors"][key] = f"BUG {type(exc).__name__}: {exc}"

    if cn:
        try:
            payload["extras"] = sources_cn.fetch_market_extras(client, norm)
        except Exception as exc:
            payload["extras"] = {
                "available": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "source": "akshare 东财源",
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
            }
    else:
        payload["extras"] = {
            "available": False,
            "reason": "A 股专属项，当前市场不适用",
            "source": "n/a",
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
        }

    payload["completeness"] = completeness(payload)

    quote_missing = not payload.get("quote")
    financials_val = payload.get("financials")
    financials_unavailable = not financials_val or not financials_val.get("available")

    block_reasons = []
    if payload["completeness"] < COMPLETENESS_FLOOR:
        block_reasons.append(
            f"完备率 {payload['completeness']:.0%} 低于阻断线 {COMPLETENESS_FLOOR:.0%}"
        )
    if quote_missing:
        block_reasons.append("行情缺失：现价、买入区间、目标价与止损价均无法给出")
    if financials_unavailable:
        block_reasons.append("财务数据缺失：红旗与否决条件无法评估")

    if block_reasons:
        payload["blocked"] = True
        payload["block_reasons"] = block_reasons
        payload["missing"] = [k for k in ("quote", "kline", "financials") if not payload.get(k)]
        payload["manual_check"] = (
            "http://www.cninfo.com.cn" if cn else "https://www.sec.gov/edgar/searchedgar/companysearch"
        )
    else:
        payload["blocked"] = False
        payload["block_reasons"] = []
    return payload


def completeness(payload) -> float:
    weights = {"quote": 0.30, "kline": 0.40, "financials": 0.30}
    got = 0.0
    for key, w in weights.items():
        value = payload.get(key)
        if not value:
            continue
        if key == "financials" and not value.get("available"):
            continue
        got += w
    return round(got, 2)


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="统一取数入口")
    ap.add_argument("codes", nargs="+", help="股票代码，1 到 3 个")
    ap.add_argument("--out", required=True, help="JSON 输出目录")
    args = ap.parse_args()

    if len(args.codes) > 3:
        print("单次最多 3 只，超出部分请分批运行")
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = HttpClient()

    any_blocked = False
    for code in args.codes:
        payload = fetch_one(code, client)
        if payload["blocked"]:
            any_blocked = True
        path = out_dir / f"{payload['code'] or code}_raw.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        status = "已阻断（" + "；".join(payload.get("block_reasons", [])) + "）" if payload["blocked"] else "就绪"
        print(f"{payload['code']} 完备率 {payload['completeness']:.0%} {status} -> {path}")
        if payload["errors"]:
            for k, v in payload["errors"].items():
                print(f"  {k} 失败: {v}")
    return 1 if any_blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
