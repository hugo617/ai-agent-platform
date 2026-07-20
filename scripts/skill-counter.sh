#!/usr/bin/env bash
# Skill 使用计数器 —— 监听 PostToolUse(Skill) hook,自动 +1 到 .skill-counters.json
#
# ──────────────────────────────────────────────────────────────────────────
# 部署位置变更说明(plan v2 §5.1 实测发现的真实缺陷,详见 progress.md Session 115):
# ──────────────────────────────────────────────────────────────────────────
# 原设计 (plan v2):workspace 级 <repo>/.zcode/config.json
#   ❌ 实测失败:ZCode 3.3.6 安全策略默认拦截 workspace hooks
#      证据:日志 event=config.project_hooks.ignored × 20+ 次
#      diagnosticMessage: "Project hooks were ignored by the security policy"
#      diagnosing-hooks SKILL.md / zcode-configuration-guide SKILL.md 均未提及
#      用户在 Settings 界面也未找到「项目 hook 信任」开关
#
# 现方案:用户级 ~/.zcode/cli/config.json + 本脚本自带 cwd 守卫
#   ✅ 不被 security policy 拦截
#   ✅ cwd 守卫等价实现「仅本项目生效」(其他项目静默 exit 0,零噪音零失败)
#   ✅ 满足 plan v2 §5.1「仅本项目生效、可入库」的核心初衷
#   ⚠️ 代价:hook 配置本身在 ~/.zcode/ 不入库(但脚本本身在 scripts/ 入库)
#      团队成员各自复制 hooks 段到自己的用户级配置即可
#
# ──────────────────────────────────────────────────────────────────────────
# 字段路径(2026-07-20 实测确认,回应 plan v2 硬约束 #3):
# ──────────────────────────────────────────────────────────────────────────
# PostToolUse hook stdin payload 结构(实测样本):
#   {
#     "cwd": "...", "mode": "...", "hookEventName": "PostToolUse",
#     "sessionId": "sess_xxx", "session_id": "sess_xxx",     # 双命名冗余
#     "toolName": "Skill",       "tool_name": "Skill",        # 双命名冗余
#     "toolInput": { "args": "...", "skill": "find-skills" }, # camelCase
#     "tool_input": { "args": "...", "skill": "find-skills" },# snake_case
#     "toolResultPreview": "...", "toolCallId": "...",
#     "traceId": "...", "turnId": "...", "timestamp": "..."
#   }
#
# 字段路径结论:
#   主路径:   tool_input.skill      (snake_case)
#   fallback: toolInput.skill       (camelCase)
#   plan v2 §5.2 候选 2 "tool_input.skill_name" 实测不存在
#   plan v2 §5.2 候选 3 "tool_name" 实测是 "Skill"(工具名)非 skill 名
#
# ──────────────────────────────────────────────────────────────────────────
# 关键加固(回应 review C-5 / O-1 / diagnosing-hooks 陷阱 8):
# ──────────────────────────────────────────────────────────────────────────
#   1. stdout 必须为空(hook 输出 schema 严格,非 JSON 内容判 failed)
#   2. 所有诊断信息走 stderr → 落盘 .skill-counters.log
#   3. heredoc 用 <<'PY' 禁止 shell 展开 + 环境变量传参(防注入)
#   4. 永远 exit 0,绝不阻断主流程
#   5. cwd 守卫:非本项目静默退出(用户级 hook 会拦所有项目,需自屏蔽)
#   6. 异常永不向上抛:计数文件损坏 → 重置;写失败 → 静默
set -uo pipefail

# ─── cwd 守卫(等价 workspace 级效果)───
# 只在 ai-agent-platform 项目记录,其他项目静默退出
if ! pwd | grep -q 'ai-agent-platform'; then
  exit 0
fi

# ─── 无 stdin(tty)直接退出(避免 unknown 计数污染)───
if [ -t 0 ]; then
  exit 0
fi

# ─── 路径 ───
# ZCODE_PROJECT_DIR 由 hook 注入(实测确认),fallback pwd
PROJECT_DIR="${ZCODE_PROJECT_DIR:-$(pwd)}"
COUNTER_FILE="${PROJECT_DIR}/.skill-counters.json"
DEBUG_LOG="${PROJECT_DIR}/.skill-counters.log"

# 抓 stdin(stdin 是一次性流)
INPUT=$(cat)

# ─── Python 提取 skill 名 ───
# 字段路径已实测确认(见文件头注释):tool_input.skill 主,toolInput.skill 备
export COUNTER_FILE
export DEBUG_LOG
SKILL_NAME=$(printf '%s' "$INPUT" | SKILL_INPUT="$INPUT" python3 -c '
import json, os, sys
try:
    d = json.loads(os.environ.get("SKILL_INPUT", "{}"))
    # 字段路径已实测确认:snake_case 主,camelCase 备
    name = (
        d.get("tool_input", {}).get("skill")         # 主路径(实测有效)
        or d.get("toolInput", {}).get("skill")        # fallback(camelCase)
        or ""
    )
    print(name)
except Exception as e:
    # 诊断走 stderr(不污染 stdout)
    sys.stderr.write(f"parse_error:{type(e).__name__}:{e}\n")
    print("")
' 2>>"$DEBUG_LOG")

# 提取失败 → 不计数,但不阻断
if [ -z "$SKILL_NAME" ]; then
  printf '[%s] empty skill name, skip\n' "$(date -u +%FT%TZ)" >> "$DEBUG_LOG" 2>/dev/null
  exit 0
fi

# ─── 写入计数文件 ───
export SKILL_NAME
python3 <<'PY' 2>>"$DEBUG_LOG"
import json, os, sys
from datetime import datetime, timezone

path = os.environ["COUNTER_FILE"]
skill = os.environ["SKILL_NAME"]
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# 读已有数据(损坏则重置)
data = {"skills": {}, "total_calls": 0, "first_call": now, "last_updated": now}
if os.path.exists(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        sys.stderr.write(f"counter file corrupted, reset: {e}\n")
        data = {"skills": {}, "total_calls": 0, "first_call": now, "last_updated": now}

# 更新计数
skills = data.setdefault("skills", {})
entry = skills.setdefault(skill, {"count": 0, "first_used": None, "last_used": None})
entry["count"] += 1
entry["last_used"] = now
if not entry.get("first_used"):
    entry["first_used"] = now

data["total_calls"] = data.get("total_calls", 0) + 1
data["last_updated"] = now

# 写入(失败永不阻断主流程)
try:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
except Exception as e:
    sys.stderr.write(f"failed to write counter: {e}\n")
    sys.exit(0)  # 永不阻断
PY

# stdout 必须为空(hook schema 严格)
exit 0
