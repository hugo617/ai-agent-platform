#!/usr/bin/env python3
"""检查 harness/docs/plan-*.md 顶部状态行与 feature_list.json 是否一致。

触发场景:实施时常忘更 plan 顶部状态行(只更 feature_list + plan checklist),
导致「plan 说 not_started 但 feature_list 已 passing」的文档债。本脚本在 CI
兜底,不一致则 fail。

豁免:状态行带 `?` 存疑标注(如 `Session 007?`)不计为不一致 —— 用于 PR/commit/
日期已核实但 Session 仅推断的早期 feature。

退出码:0 = 一致 / 1 = 发现不一致或错误。

用法:
    python3 scripts/check_plan_status_sync.py
    # CI 中:作为 backend job 的一个 step(见 .github/workflows/ci.yml)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FEATURE_LIST = ROOT_DIR / "feature_list.json"
PLAN_GLOB = "plan-*.md"
PLAN_DIR = ROOT_DIR / "harness" / "docs"

# plan 状态行范式:"> 状态: <value>(...)" 或 "> **状态**: <value>(...)"
# 取 <value> 第一个 word(not_started / in_progress / blocked / passing)
STATUS_RE = re.compile(r"^>\s+\*{0,2}状态\*{0,2}:\s*(\w+)", re.MULTILINE)


def load_feature_statuses() -> dict[str, str]:
    """feature_list.json 的 id → status 映射(真相源)。"""
    if not FEATURE_LIST.exists():
        print(f"::error::feature_list.json 不存在:{FEATURE_LIST}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(FEATURE_LIST.read_text(encoding="utf-8"))
    return {f["id"]: f["status"] for f in data.get("features", [])}


def read_plan_status(plan_path: Path) -> str | None:
    """读 plan 顶部状态行,返回状态值或 None(无状态行)。"""
    # 只读前 500 字符(状态行恒在前 8 行)
    head = plan_path.read_text(encoding="utf-8")[:500]
    m = STATUS_RE.search(head)
    return m.group(1) if m else None


def main() -> int:
    feature_statuses = load_feature_statuses()

    mismatches: list[str] = []
    no_status: list[str] = []
    no_feature_entry: list[str] = []
    checked = 0

    for plan_path in sorted(PLAN_DIR.glob(PLAN_GLOB)):
        # 文件名 → feature id(plan-dashboard-analytics.md → dashboard-analytics)
        feature_id = plan_path.stem.replace("plan-", "", 1)
        plan_status = read_plan_status(plan_path)

        if plan_status is None:
            no_status.append(plan_path.name)
            continue

        feature_status = feature_statuses.get(feature_id)
        if feature_status is None:
            # plan 文档无对应 feature_list 条目(可能是 series overview 或独立 plan)
            no_feature_entry.append(plan_path.name)
            continue

        checked += 1
        if plan_status != feature_status:
            mismatches.append(
                f"  {plan_path.name}: plan={plan_status} vs feature_list={feature_status}"
            )

    # 报告
    print(f"核查 plan 文档数:{checked}")
    if no_status:
        print(f"\n无状态行(跳过,{len(no_status)} 个,可能是 series overview):")
        for name in no_status:
            print(f"  {name}")
    if no_feature_entry:
        print(f"\n无对应 feature_list 条目(跳过,{len(no_feature_entry)} 个):")
        for name in no_feature_entry:
            print(f"  {name}")

    if mismatches:
        print(f"\n::error::发现 {len(mismatches)} 个 plan 状态行与 feature_list.json 不一致:")
        for m in mismatches:
            print(m)
        print(
            "\n修复:把 plan 顶部 `> 状态: <旧值>` 改为 `> 状态: <feature_list 真实值>`"
            "(参考 scripts/sync-active-features.sh 的范式)。"
        )
        return 1

    print("✅ 全仓 plan 状态行与 feature_list.json 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
