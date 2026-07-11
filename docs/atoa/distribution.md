# AtoA 分发与安装

> 如何让外部 AI Agent 获取并使用 agenthub CLI + Skill。

## 分发模型

agenthub AtoA 采用**四件套分发**,每件有不同的分发路径:

| 件 | 分发方式 | 状态 |
|----|---------|------|
| **CLI**(`agenthub` 命令) | pip / pipx 安装(源码或 PyPI 包) | ✅ 源码安装可用;PyPI 发版待定 |
| **Skill**(`SKILL.md` 等) | 随仓库分发 / 手动复制到 skills 目录 | ✅ 当前方式 |
| **授权**(API Token) | 用户在平台 UI 自行颁发 | ✅(UI 管理待 `atoa-admin-ui`) |
| **约定**(JSON/exit code) | 内建在 CLI,无需分发 | ✅ |

---

## 安装方式

### 1. CLI 安装

#### 源码安装(开发 / 内部部署)

```bash
git clone <仓库地址> && cd ai-agent-platform
pip install -e .          # 注册 agenthub 命令
```

依赖见 `requirements-cli.txt`(typer / rich / httpx),`init.sh` 会自动安装。

#### pipx 安装(推荐,隔离环境)

> ⚠️ 需先发布到 PyPI。当前未发版,暂用源码安装。

```bash
pipx install agenthub
```

pipx 的好处:为 agenthub 创建独立虚拟环境,不污染系统 Python,升级也方便(`pipx upgrade agenthub`)。

#### 验证

```bash
agenthub --help           # 显示命令清单
agenthub whoami           # 登录后显示身份
```

### 2. Skill 安装

Skill 是纯文本目录(`SKILL.md` + 可选子文件),分发给 Agent 就是复制到对应目录。

#### 各 Agent 的 skills 目录约定

| Agent | 项目级 | 全局级 |
|-------|--------|--------|
| Claude Code | `<project>/.agents/skills/` | `~/.agents/skills/` |
| Cursor | `<project>/.cursor/skills/` | `~/.cursor/skills/` |
| Codex | `<project>/.codex/skills/` | `~/.codex/skills/` |
| VS Code Copilot | `<project>/.github/skills/` | `~/.vscode/skills/` |

> Agent Skills 是 2025 年事实标准,各 Agent 目录约定略有差异但格式统一(YAML frontmatter + Markdown 正文)。

#### 安装命令(以 Claude Code 全局为例)

```bash
mkdir -p ~/.agents/skills
cp -r .agents/skills/agenthub ~/.agents/skills/
```

#### 验证 Skill 被识别

```bash
# 启动你的 Agent(Claude Code 等),问一个会命中 description 的问题:
# 「帮我用 agenthub 列出所有智能体」
# Agent 应识别 Skill 并执行 agenthub agents list
```

---

## 后续分发增强(未实现)

以下方式留作后续,当前不阻塞使用:

### npm 包分发(对标 Apifox / google/agents-cli)

```bash
npx skills add agenthub     # 一键安装 Skill(对标 npx skills add)
```

需做:把 SKILL.md 打包成 npm 包发布,提供 `add` 命令复制到各 Agent 目录。

### Skill 版本管理

Skill 与 CLI 版本联动(CLI 升级后 Skill 同步更新)。可加 CI 一致性检查:Skill 里的命令清单 vs CLI `--help` 输出。

### 远程 Skill 仓库

集中式 Skill 市场(类似 npm registry),`agenthub skill install <name>` 拉取。

---

## 安全注意事项

1. **Token 是敏感凭证**:不要提交到仓库、打印到日志、写进聊天摘要。Skill 里也没有硬编码 token,只教 Agent 让用户提供。
2. **最小权限原则**:为每个 Agent 颁发独立 token,用最小够用的角色(member 能做的别用 owner token)。
3. **Token 吊销**:发现泄露立即吊销(`DELETE /api/v1/api-tokens/<id>` 或后续 UI)。
4. **Skill 信任**:Skill 是指令文档,Agent 会按其执行。只安装来源可信的 Skill(本仓库的 Skill 随代码走,可审计)。

---

## 给平台管理员的分发清单

如果你要让团队里的多个 AI Agent 接入你的 agenthub 平台:

1. **部署平台**:后端 + 数据库,确保外部可达(或 Agent 所在环境可达)
2. **准备 CLI 安装源**:内部 PyPI / 直接给源码仓库 / 打包 wheel
3. **准备 Skill 分发**:把 `.agents/skills/agenthub/` 放到团队可获取的位置(内部 git / 共享盘)
4. **文档化颁发 token 流程**:告诉用户去哪颁发 token(平台 URL + 路径)
5. **写一份团队内部指南**:基于 [getting-started.md](getting-started.md) 改写,填入实际的平台 URL 和安装方式
