# Hook 计数器安装指南(团队成员)

> 本文档指导团队成员如何在本地启用 Skill 使用计数器(`scripts/skill-counter.sh`)。
> 这是 [Session 115 阶段 1](../../progress.md) 的衍生文档 —— 因 ZCode 3.3.6 安全策略默认拦截 workspace hook,改用用户级配置 + 脚本 cwd 守卫。

---

## 1. 它是干什么的

每次 agent 调用 Skill 工具(grill-with-docs / to-spec / to-tickets / implement / code-review 等),自动 +1 到 `.skill-counters.json`,记录:

```json
{
  "skills": {
    "grill-with-docs": { "count": 3, "first_used": "...", "last_used": "..." },
    "to-spec": { "count": 2 }
  },
  "total_calls": 6,
  "last_updated": "..."
}
```

**用途**:统计哪些 skill 用得多 / 哪些从没用过 → 优化 harness 工作流。

---

## 2. 安装步骤(每个团队成员 1 次)

### 步骤 1:确认仓库已就位

```bash
cd /path/to/ai-agent-platform
ls scripts/skill-counter.sh   # 应存在且可执行
```

若不可执行:`chmod +x scripts/skill-counter.sh`

### 步骤 2:编辑用户级 ZCode 配置

打开 `~/.zcode/cli/config.json`(不存在则创建),在顶层对象加 `hooks` 字段:

```json
{
  "mcp": {
    "servers": { /* 你已有的 MCP 配置,保留 */ }
  },
  "hooks": {
    "enabled": true,
    "events": {
      "PostToolUse": [
        {
          "matcher": "^Skill$",
          "hooks": [
            {
              "type": "command",
              "command": "bash \"${ZCODE_PROJECT_DIR}/scripts/skill-counter.sh\"",
              "timeout": 3
            }
          ]
        }
      ]
    }
  }
}
```

> 关键点:
> - `hooks.enabled: true` 必须显式设置(默认禁用)
> - `matcher: "^Skill$"` 大小写敏感(必须 `Skill` 不是 `skill`)
> - `timeout: 3` 是秒(command 类型用秒,不是毫秒)
> - `${ZCODE_PROJECT_DIR}` 由 ZCode 自动注入

### 步骤 3:重启 ZCode

用户级配置变更必须重启 ZCode 才生效。

### 步骤 4:验证

调一次任意 skill(如 `/find-skills test`),然后:

```bash
cat .skill-counters.json   # 应有内容,刚调的 skill count=1
cat .skill-counters.log    # 应为空(0 错误)
```

---

## 3. 为什么不用 workspace 级配置

**实测发现**(2026-07-20,ZCode 3.3.6):

- workspace 级 `<repo>/.zcode/config.json` 的 hooks 段被安全策略默认拦截
- 日志 event:`config.project_hooks.ignored`,diagnosticMessage:`"Project hooks were ignored by the security policy"`
- 官方 `diagnosing-hooks/SKILL.md` / `zcode-configuration-guide/SKILL.md` **均未提及**(文档盲区)
- Settings 界面也未找到「项目 hook 信任」开关

**降级方案**:用户级配置 + 脚本 cwd 守卫。

---

## 4. cwd 守卫(为什么不会污染其他项目)

用户级 hook 会拦截所有 ZCode 项目的 Skill 调用,但 `scripts/skill-counter.sh` 自带 cwd 守卫:

```bash
if ! pwd | grep -q 'ai-agent-platform'; then
  exit 0   # 静默退出,其他项目零感知
fi
```

其他项目调 Skill 时:
- hook 触发(脚本被调用)
- 脚本检查 cwd,发现不在 `ai-agent-platform`
- 立即 `exit 0`(0 噪音、0 失败、0 阻断)

**等价效果**:仅 ai-agent-platform 项目记录,与 workspace 级配置的本意一致。

---

## 5. 卸载

不想要时,删掉 `~/.zcode/cli/config.json` 里的 `hooks` 字段(保留 mcp 等),重启 ZCode。

`.skill-counters.json` / `.skill-counters.log` 已在 `.gitignore` 里,不会污染仓库。

---

## 6. 调试

| 症状 | 排查 |
|---|---|
| `.skill-counters.json` 不生成 | ① 用户级配置 `hooks.enabled: true` 设了吗?② 重启 ZCode 了吗?③ cwd 在 ai-agent-platform 吗?④ `scripts/skill-counter.sh` 可执行吗? |
| `.skill-counters.log` 有 `parse_error` | skill 名提取失败,看 [scripts/skill-counter.sh](../../scripts/skill-counter.sh) 文件头注释的字段路径说明 |
| 其他项目 Skill 调用变慢/报错 | 不应该发生(cwd 守卫静默 exit 0);若发生查脚本 `pwd | grep` 是否误匹配 |

---

## 7. 相关文件

| 文件 | 入库? | 说明 |
|---|---|---|
| [scripts/skill-counter.sh](../../scripts/skill-counter.sh) | ✅ 入库 | 计数器脚本(可执行,带 cwd 守卫) |
| `.gitignore` 的 `.skill-counters.*` 条目 | ✅ 入库 | 计数文件不入库(每人本地) |
| `~/.zcode/cli/config.json` 的 hooks 段 | ❌ 用户私有 | 每个成员各自配置(本文档指导) |
| `.zcode/config.json`(仓库内) | ❌ 被 .zcode/ 忽略 | workspace 占位(待 ZCode 放开信任后切换回 workspace) |
