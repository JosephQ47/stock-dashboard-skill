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

    # 证据单薄却给出「基本面达标」这类自信结论：VERDICT_BUY/VERDICT_WATCH
    # 都要求 Q 轴过了 HIGH 门槛，但 renormalize 之后一两个维度就能把分数
    # 顶到 100。
    #
    # 判定条件用「或」而不是「且」：只要质量维度数、或红旗真实判定数，
    # 任一低于下限（2）就判定为「证据单薄」。这是本次刻意调整过的口径——
    # 旧版本要求两者同时低于下限才报，比 scoring.map_matrix 自己在
    # `q_dims_present < QUALITY_MIN_DIMS_FOR_CLAIM` 时就已经软化措辞的判据
    # 还要窄：会出现「Q 轴只由 1 个维度撑起来、conflict 文案已经在说证据
    # 单薄，但 selfcheck 仍判 ok: True」这种自检结论比它要backup的措辞规则
    # 更宽松的情况，等于自检对自己已经识别出的风险视而不见。
    # 两个方向都要考虑：放宽判定条件确实会多出一些误报（本来正常的报告因为
    # 单一信号偏薄被多标一句注意），但漏掉一次真正的单薄证据——尤其是「统计
    # 上只有 statement 一个维度在场，其它维度全靠没人核实的红旗撑住」这类
    # 情形——恰恰是这道自检存在的意义：宁可让读者多看一句「证据单薄」的提示
    # 去自行判断，也不能让自检对已知的薄弱信号保持沉默。真实 600519 一次
    # 正常跑下来是 3 个质量维度、3 条红旗有真实判定，两个数都比下限 2 多
    # 出 1 的余量，无论用「且」还是「或」都不会被误伤。
    # 任一字段缺失（旧格式 computed，没有 dims_present/flags_evidence）
    # 时不做判断，保持向后兼容。
    verdict = (computed.get("matrix") or {}).get("verdict")
    if verdict in (scoring.VERDICT_BUY, scoring.VERDICT_WATCH):
        dims_present = (computed.get("quality") or {}).get("dims_present")
        known_flags = (computed.get("flags_evidence") or {}).get("known")
        if (
            dims_present is not None and known_flags is not None
            and (
                dims_present < scoring.QUALITY_MIN_DIMS_FOR_CLAIM
                or known_flags < scoring.KNOWN_FLAGS_MIN_FOR_CLAIM
            )
        ):
            issues.append(
                f"结论「{verdict}」建立在单薄证据上：仅 {dims_present} 个质量维度、"
                f"{known_flags} 条红旗有真实数据支撑，不足以断言基本面达标"
            )

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
