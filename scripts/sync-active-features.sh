#!/usr/bin/env bash
# 同步 feature_list.json → feature_list.active.json + features-passing-archive.json
# 触发时机:feature 状态变化后(可配 ZCode hook 自动跑,见 plan §3.7.5)
#
# v3.1 修订(回应第二轮评审 opus+sonnet+haiku):
#   1. 保留的「最近 N 个 passing」改为精简字段(只留 id/priority/area/title/status)
#      —— 避免 active.json 反被 passing 的 evidence 字段撑大(实测 169 行 → 59 行)
#   2. 脚本必须放在 <repo>/scripts/ 下(脚本用 BASH_SOURCE/.. 推断 ROOT_DIR)
#   3. 「priority 大 = 新」依赖本仓 priority 单调递增约定(见 feature_list.json 现有分配,
#      priority 1-60 与 60 features 一一对应);若未来改变 priority 语义,需同步改此处排序逻辑
#   4. active.json 每次全量重写(非增量),milestone 记录每次刷新时间戳
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python3 <<'PY'
import json
from datetime import datetime
from pathlib import Path

root = Path.cwd()
full_path = root / "feature_list.json"
active_path = root / "feature_list.active.json"
archive_dir = root / "harness" / "docs" / "archive"
archive_path = archive_dir / "features-passing-archive.json"

if not full_path.exists():
    raise SystemExit("feature_list.json not found")

with open(full_path, encoding="utf-8") as f:
    data = json.load(f)

features = data.get("features", [])
active = [f for f in features if f["status"] in ("not_started", "in_progress", "blocked")]
passing = [f for f in features if f["status"] == "passing"]

# 最近 N 个 passing 作最近活动参考(按 priority 倒序,priority 大 = 新)
# ⚠️ 依赖本仓 priority 单调递增约定(见脚本头注释)
RECENT_PASSING_KEEP = 5
SLIM_FIELDS = ("id", "priority", "area", "title", "status")  # v3.1:精简字段,丢弃 evidence/verification/notes

def slim(f):
    """精简保留的 passing,只留 agent 决策需要的字段(其余字段查 archive/feature_list.json)"""
    return {k: f.get(k) for k in SLIM_FIELDS}

recent_passing_full = sorted(passing, key=lambda x: x.get("priority", 0), reverse=True)[:RECENT_PASSING_KEEP]
recent_passing_slim = [slim(f) for f in recent_passing_full]

# 需要归档的 passing(超出阈值的部分,完整字段)
to_archive = sorted(passing, key=lambda x: x.get("priority", 0), reverse=True)[RECENT_PASSING_KEEP:]

# 里程碑摘要(1 条聚合代替 N 条历史 passing)
milestone = None
if to_archive:
    milestone = {
        "id": "_milestone_archived",
        "priority": 0,
        "area": "里程碑",
        "title": f"[已归档 {len(to_archive)} 条 passing,见 archive/features-passing-archive.json]",
        "status": "passing",
    }

# 写 active.json(v3.1:每次全量重写,非增量)
active_data = dict(data)
active_data.pop("status_legend", None)  # 精简:agent 不需要图例
active_features = active + recent_passing_slim
if milestone:
    active_features.append(milestone)
active_data["features"] = active_features
active_data["_active_view_note"] = (
    "⚠️ 派生视图(自动生成,禁止手动编辑)。只含活跃任务 + 最近 5 个 passing(精简字段)+ 里程碑摘要。"
    "完整数据见 feature_list.json;历史归档见 harness/docs/archive/features-passing-archive.json。"
    "feature 状态变化后跑 scripts/sync-active-features.sh 刷新。"
)
with open(active_path, "w", encoding="utf-8") as f:
    json.dump(active_data, f, indent=2, ensure_ascii=False)

# 写/合并 archive.json(幂等:按 id 去重)
archive_dir.mkdir(parents=True, exist_ok=True)
existing_archived = {}
if archive_path.exists():
    try:
        existing = json.load(open(archive_path, encoding="utf-8"))
        for f in existing.get("features", []):
            existing_archived[f["id"]] = f
    except Exception:
        pass
for f in to_archive:
    existing_archived[f["id"]] = f  # 完整字段保留,审计用

archive_data = {
    "project": data.get("project"),
    "description": "已 passing feature 的历史归档(完整字段保留,审计用)",
    "count": len(existing_archived),
    "features": list(existing_archived.values()),
}
with open(archive_path, "w", encoding="utf-8") as f:
    json.dump(archive_data, f, indent=2, ensure_ascii=False)

# 统计
now = datetime.now().isoformat(timespec="seconds")
print(f"[{now}] ✅ active: {len(active)} 活跃 + {len(recent_passing_slim)} 最近 passing(精简)+ "
      f"{1 if milestone else 0} 里程碑 = {len(active_features)} 条", flush=True)
print(f"✅ archive: 新增 {len(to_archive)} 条,累计 {len(existing_archived)} 条", flush=True)
print(f"📁 active: {active_path.relative_to(root)}", flush=True)
print(f"📁 archive: {archive_path.relative_to(root)}", flush=True)
PY
