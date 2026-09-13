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
    norm = normalize(code)
    cn = _is_cn(norm["market"])
    mod = sources_cn if cn else sources_hk_us

    payload = {
        "code": norm["code"],
        "raw": norm["raw"],
        "market": norm["market"].value,
        "currency": norm["currency"],
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
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
        except (SourceDown, Exception) as exc:
            payload[key] = None
            payload["errors"][key] = f"{type(exc).__name__}: {str(exc)[:100]}"

    if cn:
        try:
            payload["extras"] = sources_cn.fetch_market_extras(client, norm)
        except Exception as exc:
            payload["extras"] = {"available": False, "reason": f"{type(exc).__name__}"}
    else:
        payload["extras"] = {"available": False, "reason": "A 股专属项，当前市场不适用"}

    payload["completeness"] = completeness(payload)
    if payload["completeness"] < COMPLETENESS_FLOOR:
        payload["blocked"] = True
        payload["missing"] = [k for k in ("quote", "kline", "financials") if not payload.get(k)]
        payload["manual_check"] = (
            "http://www.cninfo.com.cn" if cn else "https://www.sec.gov/edgar/searchedgar/companysearch"
        )
    else:
        payload["blocked"] = False
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

    for code in args.codes:
        payload = fetch_one(code, client)
        path = out_dir / f"{payload['code']}_raw.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        status = "完备率不足，已阻断" if payload["blocked"] else "就绪"
        print(f"{payload['code']} 完备率 {payload['completeness']:.0%} {status} -> {path}")
        if payload["errors"]:
            for k, v in payload["errors"].items():
                print(f"  {k} 失败: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
