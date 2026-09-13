# -*- coding: utf-8 -*-
"""出报告前的自检。任何一项不通过都必须在看板中说明，不得静默放行。"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import compute
import scoring


def verify(computed: dict) -> dict:
    issues = []

    for axis in ("quality", "timing"):
        score = (computed.get(axis) or {}).get("score")
        if score is None or not (0.0 <= float(score) <= 100.0):
            issues.append(f"{axis} 分数越界: {score}")

    if computed.get("veto"):
        if float(computed["quality"]["score"]) > scoring.VETO_CAP:
            issues.append("触发否决但质量分超过封顶值 40")
        if computed["matrix"]["verdict"] != scoring.VERDICT_AVOID:
            issues.append("触发否决但结论不是回避")

    # `prices` 里混着两类子块：buy_range/target/stop_loss 这类用户要据以下单的
    # 价位，和 valuation 这个估值锚参数块（current_pe_ttm/pe25/pe75/low/high
    # 等）——后者的推导过程已经写进 buy_range 的 formula 里，本身不需要单独一份
    # 推导式。用 compute.NON_PRICE_LEVEL_PRICE_BLOCKS 白名单排除已知的参数块，
    # 而不是白名单收录已知的价位块：这样以后 compute.py 新增任何价位子块，
    # 默认就会被本检查覆盖，只有显式加入那个排除集合才会被跳过，不会静默漏检。
    for name, block in (computed.get("prices") or {}).items():
        if name in compute.NON_PRICE_LEVEL_PRICE_BLOCKS:
            continue
        if not block.get("formula"):
            issues.append(f"{name} 缺少推导式")

    if computed.get("gates") and computed["matrix"]["verdict"] == scoring.VERDICT_BUY:
        issues.append("存在买入禁令但结论仍为可建仓")

    if float(computed.get("completeness") or 0) < 0.70 and not computed.get("blocked"):
        issues.append("完备率低于 70% 但未标记阻断")

    # 反方向同样要查：数据已经被 compute.run() 判定为 blocked（行情缺失、财务
    # 缺失或完备率不足），却仍然给出一个非「回避」的自信结论，或者仍然带着价位——
    # 这正是本该被挡下、却漏网的那种「拿不完整数据装满仓」的报告。
    if computed.get("blocked"):
        verdict = (computed.get("matrix") or {}).get("verdict")
        if verdict != scoring.VERDICT_AVOID:
            issues.append(f"数据被阻断但结论不是回避: {verdict}")
        if computed.get("prices"):
            issues.append("数据被阻断但仍给出买入区间/目标价/止损价等价位")

    if not computed.get("data_sources"):
        issues.append("缺少数据来源记录")

    return {"ok": not issues, "issues": issues}


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="报告自检")
    ap.add_argument("--in", dest="src", required=True)
    args = ap.parse_args()

    computed = json.loads(Path(args.src).read_text(encoding="utf-8"))
    result = verify(computed)
    if result["ok"]:
        print(f"{computed.get('code')} 自检通过")
        return 0
    print(f"{computed.get('code')} 自检发现 {len(result['issues'])} 个问题:")
    for i in result["issues"]:
        print(f"  - {i}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
