# 计划:AtoA CLI 骨架 —— agenthub 命令行工具（登录 + 只读命令）

> 对应 feature_list.json 的 `id`: `atoa-cli-core`
> 状态: not_started
> 优先级: 20
> 前置: `atoa-api-token-auth` ✅（API Token 鉴权机制必须先就绪，CLI 才有凭证可用）

---

## 背景:为什么需要这个任务

API Token 鉴权机制（atoa-api-token-auth）建立后，外部 Agent 已能用 token 调 API。但当前**没有任何 CLI 工具**——仓库无 `click`/`typer`/`fire`,`pyproject.toml` 无 `console_scripts`。Agent 只能手写 HTTP 请求，不稳定且每个 Agent 都要重新学。

本任务建立 `agenthub` CLI 工具的**骨架**：让 Agent（或人类）装上 CLI、用 token 登录、跑通只读命令（`agents list` / `agents get`）。这是 Apifox CLI 打法的核心组件之一——一个 Agent-Ready 的命令行入口。

### 行业对标

- **[google/agents-cli](https://github.com/google/agents-cli)**：Google 出品，`uvx google-agents-cli setup` + `agents-cli login`，与本项目目标形态最贴近
- **[ComposioHQ/awesome-agent-clis](https://github.com/ComposioHQ/awesome-agent-clis)**：总结 Agent-Ready CLI 的 6 条准则（见下）
- **Apifox CLI**：`apifox` npm 包，`--json` 结构化输出

### Agent-Ready CLI 6 准则（设计硬指标）

| Trait | 为什么重要 | 本任务如何实现 |
|-------|-----------|---------------|
| 结构化输出 `--json` | Agent 解析 JSON，不解析 ASCII 表格 | 所有命令支持 `--json` flag |
| 非交互模式 `--no-interactive` | Agent 不能回答交互提示 | 全局 flag，跳过所有确认提示 |
| API key 认证(env var / config) | 不能跳浏览器 OAuth | `agenthub login <token>` 存本地文件 |
| 幂等性 | Agent 可安全重试 | 只读命令天然幂等 |
| 管道输出检测 | 自动从「漂亮」切到「机器可读」 | stdout 非 TTY 时自动输出 JSON |
| 有意义的 exit code | Agent 据此分支 | 0 成功 / 1 通用错误 / 2 认证失败 |

### 当前状态速查

| 能力 | 状态 | 位置 |
|------|------|------|
| 后端 API（/agents 等） | ✅ 已完成 | `app/api/v1/agents.py` |
| API Token 鉴权 | ✅ 前置任务交付 | `app/api/deps.py`（旁路） |
| CLI 工具 | ❌ 完全缺失 | 无 cli/ 目录，无 console_scripts |
| 本地凭证存储 | ❌ 完全缺失 | 无 |

---

## 目标

1. **新建 `cli/` 顶层目录**：与 `app/` 平级，不污染后端包
2. **`agenthub` 命令可安装**：`pipx install -e .` 或 `pip install -e .` 后 `agenthub` 命令可用
3. **登录 + 凭证存储**：`agenthub login <token> --base-url <url>`，存 `~/.agenthub/credentials`（权限 0600）
4. **只读命令跑通**：`whoami` / `agents list` / `agents get <id>`，支持 `--json`
5. **Agent-Ready 6 准则全满足**

### 已确认的决策（与用户对齐）

| 决策点 | 选择 |
|--------|------|
| CLI 技术栈 | **Python typer**（对齐后端技术栈，可直接复用 app/schemas；与 google/agents-cli 同款） |
| CLI 代码位置 | **`cli/` 顶层目录**（与 `app/` 平级，独立包，不污染后端） |
| 凭证存储 | `~/.agenthub/credentials`（JSON，权限 0600） |
| HTTP client | `httpx`（后端已依赖，复用） |
| 安装方式 | `pipx install -e .`（开发）/ `pipx install agenthub`（发布后） |

---

## 前置条件

- `atoa-api-token-auth` ✅（API Token 颁发端点 + 鉴权旁路就绪）
- 后端 `/agents` 端点可用（已 passing）
- 一个已颁发的 API Token（从前置任务的管理端点或 UI 拿）

---

## 实施步骤

### 第一阶段:工程结构

#### Step 1:`pyproject.toml` 加 CLI 依赖与入口

- **加依赖**（`pyproject.toml` 的 `[project] dependencies` 或 `requirements.txt`）：
  - `typer>=0.12,<1`（CLI 框架）
  - `httpx>=0.27,<1`（HTTP client，后端已用可复用）
  - `rich>=13,<14`（typer 依赖的终端美化，自动装）
- **加入口**（`pyproject.toml`）：
  ```toml
  [project.scripts]
  agenthub = "cli.main:app"
  ```
- **注意**：当前 `pyproject.toml` 无 `[project] dependencies` 段（依赖在 `requirements.txt`），需新增该段或加 `requirements-cli.txt` 分离

#### Step 2:`cli/` 目录结构（新建）

```
cli/
├── __init__.py
├── main.py            # typer app 入口 + 全局选项（--json/--no-interactive）
├── client.py          # HTTP client：读凭证、发请求、处理 401/错误
├── config.py          # 凭证存储（~/.agenthub/credentials，权限 0600）
├── errors.py          # CLI 异常 + exit code 映射
└── commands/
    ├── __init__.py
    ├── login.py       # agenthub login <token>
    ├── agents.py      # agenthub agents list/get
    └── whoami.py      # agenthub whoami（调 /api-tokens/verify）
```

---

### 第二阶段:核心模块

#### Step 3:`cli/config.py` —— 凭证存储

- **凭证文件**：`~/.agenthub/credentials`（JSON 格式）
  ```json
  {"token": "ahp_xxx", "base_url": "http://localhost:8000"}
  ```
- **权限控制**：写入时 `os.chmod(path, 0o600)`，读取时校验权限
- **环境变量覆盖**：`AGENTHUB_TOKEN` + `AGENTHUB_BASE_URL` 优先于文件（CI/容器场景）
- **函数**：`load_credentials() -> Credentials | None` / `save_credentials(token, base_url)` / `clear_credentials()`

#### Step 4:`cli/client.py` —— HTTP client

- 基于 `httpx.Client`，统一加 `Authorization: Bearer <token>` header
- **错误处理**：
  - 401 → exit code 2，提示「token 无效或已过期，请重新 `agenthub login`」
  - 403 → exit code 3，提示「权限不足」
  - 网络/超时 → exit code 1
- **响应解析**：JSON 响应直接返回 dict；SSE 响应交给 chat 命令处理（下个任务）
- **函数**：`request(method, path, **kwargs) -> dict | httpx.Response`

#### Step 5:`cli/main.py` —— typer 入口 + 全局选项

```python
import typer
app = typer.Typer(name="agenthub", help="agenthub 平台 CLI")

@app.callback()
def main(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="输出 JSON"),
    no_interactive: bool = typer.Option(False, "--no-interactive", help="非交互模式"),
):
    ctx.obj = {"json": json_output or not sys.stdout.isatty(), "no_interactive": no_interactive}
```

- **管道检测**：`not sys.stdout.isatty()` 时自动切 JSON 输出（准则 5）
- 注册子命令 app：`login` / `whoami` / `agents`

---

### 第三阶段:命令实现

#### Step 6:`cli/commands/login.py`

```bash
agenthub login <token> [--base-url http://localhost:8000]
```

- 存凭证到 `~/.agenthub/credentials`（权限 0600）
- 验证 token 有效（调 `/api-tokens/verify`）
- 成功输出「已登录为 <email>（租户 <tenant_id>）」

#### Step 7:`cli/commands/whoami.py`

```bash
agenthub whoami [--json]
```

- 调 `/api-tokens/verify`
- 默认：人类友好输出（email + tenant + token prefix）
- `--json`：`{"user_id": "...", "tenant_id": "...", "email": "...", "token_prefix": "ahp_***wxyz"}`

#### Step 8:`cli/commands/agents.py`

```bash
agenthub agents list [--json]
agenthub agents get <id> [--json]
```

- 调 `/agents` + `/agents/{id}`
- 默认：表格输出（rich Table）
- `--json`：原始 JSON 数组/对象

---

### 第四阶段:测试 + 验证

#### Step 9:CLI 测试

- **方案选择**（二选一，推荐 A）：
  - **A. `cli/tests/` 单测**：mock httpx，测命令逻辑（不依赖真实后端）。用 `typer.testing.CliRunner`
  - **B. 集成测试**：起后端 + CLI 真实调用（重，但更真实）
- 测试用例：
  - login 存凭证 + 权限 0600
  - whoami 正常 / 未登录报错（exit 2）
  - agents list 正常 / `--json` 输出格式 / 401 处理
- **注意**：CLI 测试不进 `tests/`（那是后端的），放 `cli/tests/`；`pyproject.toml` 的 `testpaths` 可能需扩展

#### Step 10:验证

- `pip install -e .`（装 CLI）→ `agenthub --help` 可用
- 起后端 → 颁发 token → `agenthub login <token>` → `agenthub whoami` → `agenthub agents list --json` 跑通
- `./init.sh` 全绿（确认 CLI 新增不破坏后端测试）

---

## 验收标准

1. `pipx install -e .` 后 `agenthub` 命令可用
2. `agenthub login <token>` + `agenthub whoami` + `agenthub agents list --json` 跑通
3. Agent-Ready 6 准则全满足（--json / --no-interactive / exit code / 管道检测）
4. 凭证文件权限 0600，支持 env var 覆盖
5. CLI 测试通过（`cli/tests/`）
6. `./init.sh` 全绿（后端不回归）
7. 证据已记录到 feature_list.json + progress.md 已更新

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| CLI 与后端共享 pyproject.toml 导致打包混乱 | CLI 独立 `cli/` 包，依赖分离（可选 `requirements-cli.txt`）；`[project.scripts]` 指向 `cli.main:app` |
| typer/rich 版本与现有依赖冲突 | 用 `>=x,<y` 范围约束；装后跑 `./init.sh` 确认不破坏 |
| 凭证文件泄露 | 写入强制 0600；env var 覆盖支持无文件场景 |
| 管道检测误判 | `isatty()` 检测 stdout 非 stdin；`--json` 显式覆盖 |
| CLI 测试与后端 testpaths 混 | CLI 测试放 `cli/tests/`，`pyproject.toml` testpaths 可加 `cli/tests` 或保持 `tests`（CLI 用单独命令跑） |

### 不做的事（边界）

- 不实现对话命令（atoa-cli-chat-admin 任务）
- 不实现 CRUD 写命令（atoa-cli-chat-admin 任务）
- 不实现 Skill（atoa-skill 任务）
- 不实现自动更新 / 版本检查
- 不实现多 profile（多租户切换）——本版一个凭证文件
- 不发布到 PyPI（本地 `pipx install -e .` 即可）

---

## 参考文件（实施时对照）

| 参照 | 路径 / 链接 |
|------|------------|
| pyproject.toml（加 scripts） | `pyproject.toml`（当前无 [project.scripts]） |
| requirements.txt（加依赖） | `requirements.txt` |
| 后端 /agents 端点 | `app/api/v1/agents.py` |
| API Token 验证端点 | `app/api/v1/api_tokens.py`（前置任务交付） |
| SSE 端点（下个任务对接） | `app/api/v1/chat.py` `POST /chat/stream` |
| 行业对标 google/agents-cli | https://github.com/google/agents-cli |
| Agent-Ready 6 准则 | https://github.com/ComposioHQ/awesome-agent-clis |
| typer 文档 | https://typer.tiangolo.com/ |
