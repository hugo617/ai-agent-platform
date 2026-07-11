# AtoA 快速上手(5 分钟)

> 假设你已有一个运行中的 agenthub 平台实例(后端 + 数据库)。如果没有,先按 [README.md](../../README.md) 的「快速开始」启动。

本指南带你从零接入 AtoA:让一个外部 AI Agent(Claude Code)能操作你的 agenthub 平台。

---

## 第 1 步:颁发 API Token

在 agenthub 平台的 Web UI 中:

1. 用 owner 或 admin 账号登录
2. 进入 **设置(Settings)→ API Token**
3. 点击「创建 Token」,填写名称(如 `claude-code-agent`)
4. **复制生成的 token**(`ahp_xxxxxxxx` 格式)

> ⚠️ **明文 token 仅显示一次**,关闭弹窗后不可再见。请立即保存到安全位置(密码管理器等)。

> 📌 token 继承颁发者的角色权限(owner 能做的它都能做),建议为不同 Agent 颁发独立 token 便于审计和吊销。`atoa-admin-ui` 任务完成后,UI 管理界面会更完善(列表 / 吊销 / 最后使用时间)。

如果你更习惯用 API 颁发(需已登录的会话 token):

```bash
curl -X POST http://localhost:8000/api/v1/api-tokens/ \
  -H "Authorization: Bearer <你的会话token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "claude-code-agent"}'
# 响应里的 plaintext 字段就是 ahp_ token(仅此一次)
```

---

## 第 2 步:安装 agenthub CLI

### 方式 A:从源码安装(开发场景)

```bash
git clone <你的仓库地址> && cd ai-agent-platform
pip install -e .                # 注册 agenthub 命令
```

### 方式 B:pipx 安装(推荐生产用,后续发版后)

```bash
pipx install agenthub
```

### 验证安装

```bash
agenthub --help
# 应显示 login / whoami / agents / conversations 命令
```

---

## 第 3 步:登录

```bash
agenthub login ahp_xxxxxxxx --base-url http://localhost:8000
```

- `--base-url` 默认 `http://localhost:8000`,远程实例改成实际地址
- 登录成功会显示 `user_id` 和 `tenant`,凭证存到 `~/.agenthub/credentials`(权限 0600)

验证登录:

```bash
agenthub whoami
# 显示当前身份
```

---

## 第 4 步:安装 Skill(让 AI Agent 学会用)

### 给 Claude Code 用

将 `.agents/skills/agenthub/` 目录放到 Claude Code 能扫描的位置:

- **项目级**(推荐):复制到你的工作项目的 `.agents/skills/agenthub/`
- **全局级**:复制到 `~/.agents/skills/agenthub/`

```bash
# 全局安装(对所有项目生效)
mkdir -p ~/.agents/skills
cp -r .agents/skills/agenthub ~/.agents/skills/
```

### 验证 Skill 被识别

启动 Claude Code,问它:

> 帮我用 agenthub 列出所有智能体

Claude Code 应该会:
1. 识别到 agenthub Skill(因为描述命中了「agenthub」「列出智能体」)
2. 执行 `agenthub agents list --json`
3. 返回结果

如果没命中,检查:
- Skill 目录路径正确(`.agents/skills/agenthub/SKILL.md`)
- SKILL.md 的 frontmatter 格式合法(`name` + `description`)
- agenthub CLI 已安装且 `agenthub whoami` 能通过

### 兼容其他 Agent

Skill 遵循 Agent Skills 开放标准,Cursor / Codex / VS Code Copilot 同样支持。安装方式类似(各自的 skills 目录约定),详见各 Agent 的文档。

---

## 第 5 步:开始用

### 和智能体对话

```bash
agenthub agents list --json                    # 先找到要对话的 agent id
agenthub agents chat --agent <id> "你好"        # 流式对话
```

### 通过 AI Agent 用(装了 Skill 后)

直接用自然语言告诉 Claude Code:

- 「用 agenthub 创建一个叫"翻译助手"的智能体,model 用 deepseek-chat」
- 「用 agenthub 看看我和智能体的最近对话」
- 「用 agenthub 跟翻译助手说:把这句话翻成英文」

Claude Code 会自动调用对应的 `agenthub` 命令。

---

## 常见问题

### Q: token 过期了怎么办?
A: token 不会自动过期(除非设置了 expires_at 或被吊销)。如果 `whoami` 返回 401,重新到平台「设置 → API Token」颁发新 token,然后 `agenthub login <新token>`。

### Q: 如何续接之前的对话?
A: `agenthub conversations list` 找到会话 id,再 `agenthub agents chat --agent <id> "续聊" --conversation-id <conv-id>`。

### Q: Agent 提示「权限不足」(403)?
A: token 继承颁发者角色。如果是 member 角色的 token,无法执行写操作(创建/删除智能体)。用 owner/admin 账号重新颁发 token,或让 owner 调整你的角色权限。

### Q: 怎么吊销一个 token?
A: 当前需调 API:`DELETE /api/v1/api-tokens/<id>`。`atoa-admin-ui` 任务完成后可在 Web UI 吊销。

---

## 下一步

- 完整命令参考:见 [Skill 的 commands.md](../../.agents/skills/agenthub/commands.md)
- 分发与安装详情:见 [distribution.md](distribution.md)
- 架构原理:见本目录 README.md 的「架构设计」章节
