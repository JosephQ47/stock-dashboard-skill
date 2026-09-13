# -*- coding: utf-8 -*-
"""出报告前的自检。任何一项不通过都必须在看板中说明，不得静默放行。"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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

    for name, block in (computed.get("prices") or {}).items():
        if not block.get("formula"):
            issues.append(f"{name} 缺少推导式")

    if computed.get("gates") and computed["matrix"]["verdict"] == scoring.VERDICT_BUY:
        issues.append("存在买入禁令但结论仍为可建仓")

    if float(computed.get("completeness") or 0) < 0.70 and not computed.get("blocked"):
        issues.append("完备率低于 70% 但未标记阻断")

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
