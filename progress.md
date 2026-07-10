# 进度日志(progress.md)

> 每轮会话开始时先读、收尾时更新。跨会话必须的关键信息写这里,脑子里的不算。

## 当前已验证状态

- **仓库根目录**: `/Users/star/hugo/3-项目代码/project/ai-agent-platform`
- **标准启动路径**: `./init.sh`(装依赖 + ruff + pytest)
- **标准验证路径**: `./init.sh`(同上,后端快速验证,SQLite 内存库)
- **完整验证路径**(需 docker): `alembic upgrade head && alembic check` + `cd frontend && npm run build`
- **当前最高优先级未完成功能**: `roles-crud`(角色管理 CRUD 全栈对齐)—— `validation-error-i18n` 已 passing
- **当前 blocker**: 无

## 已 passing 的地基能力(详见 feature_list.json)

| 功能 | 状态 | 验证依据 |
|------|------|---------|
| auth-local(本地密码登录) | passing | 8 tests |
| auth-logto(Logto OIDC) | passing | 4 tests |
| rbac-permission(RBAC 多租户) | passing | 29 tests |
| users-crud(用户管理 CRUD) | passing | 27 tests |
| db-migrations(迁移链) | passing | CI migrations job |
| scd2-history(授权链历史) | passing | 7 tests |

## 会话记录

### Session 001 — 2026-07-10
- **本轮目标**: 搭建 Harness 工程目录基础版(Stage 1 四件套 + clean-state)
- **已完成**:
  - 新建 `init.sh`(标准化启动+验证入口:ruff + pytest on SQLite)
  - 新建 `feature_list.json`(登记 6 个已 passing 地基 + 2 个 not_started 二开示例)
  - 新建 `progress.md`(本文件)
  - 新建 `harness/clean-state-checklist.md`(7 项收尾清单)
  - 增强 `AGENTS.md`(新增开工流程、工作规则 WIP=1、完成定义 4 条、收尾指引段落)
- **运行过的验证**: `./init.sh`(ruff check + pytest 全绿)
- **已知风险**: 无
- **下一步最佳动作**: 由用户决定是否开始二开(`global-rename`),或继续加 harness 工件(handoff/rubric/cleanup,按需)

### Session 002 — 2026-07-10
- **本轮目标**: 执行 `validation-error-i18n`(Pydantic 422 校验错误中文化)—— TDD 5 步,纯后端
- **已完成**(对照 plan §5 的 Step 0-5):
  - Step 0 基线确认:`./init.sh` → 82 passed(起点干净)
  - Step 1 写单测(RED):新建 `tests/test_validation_errors.py`(5 纯函数单测 + 1 集成)→ `ModuleNotFoundError`(预期)
  - Step 2 实现纯函数(GREEN):新建 `app/core/validation_errors.py`(`localize_message` + `_TYPE_TEMPLATES` + `_FIELD_LABELS`)→ 5 纯函数单测全绿
  - Step 3 注册 handler + 集成测试:`app/main.py` 加 `RequestValidationError` handler(紧邻 `PermissionError` handler)→ 6 passed(含端到端)
  - Step 4 全量回归:`./init.sh` → ruff `All checks passed!` + **88 passed**(82 + 6)
  - Step 5 手测:未单独跑 curl(需完整 docker 环境);集成测试已用 ASGITransport 以更强断言覆盖
- **运行过的验证**(全过):
  - `./init.sh` → ruff check passed + **88 tests passed**
  - `pytest tests/test_validation_errors.py -v` → 6 passed
- **已记录证据**: `feature_list.json` 的 `validation-error-i18n.evidence` 字段(6 条,含命令+结果+日期)
- **技术要点**(与 plan §3.2 的实现差异):
  - plan 骨架用 `try/except (KeyError, IndexError)` 处理 ctx 缺占位;实际发现 `str.format` 在 except 内再次调用仍会抛 `KeyError`(`{min_length}` 占位仍在模板里)
  - 改用 `_SafeDict`(`__missing__` 返回空串)+ `string.Formatter.vformat`,统一让缺失占位渲染为空串,永不抛异常,更稳健
  - `_FIELD_LABELS` 对齐当前 `app/schemas/user.py` 全部 10 个字段
  - 集成测试适配真实 schema:用 `username="a"`(1 字符 < `min_length=2`),断言 msg 含「用户名」与「2」(plan 原文写「3」是历史背景,schema 未改成 3)
  - 422 响应形状 `{detail:[{loc,msg,type,...}]}` 不变,前端 `client.ts` / 所有 `app/schemas/*.py` / `users.py` 零改动
- **提交记录**: `feat/validation-error-i18n` 分支(本次提交)
- **已知风险**: 无功能风险。`EmailStr` 格式错误在 Pydantic v2 落到 `value_error` type,会透传英文(plan §6 标注的可选增强,本任务范围外)
- **下一步最佳动作**: 由用户决定(a)合并 feat/validation-error-i18n 到 main;(b)开始下一个任务 `roles-crud`

---
<!--
会话记录模板(复制使用):
### Session 0XX — YYYY-MM-DD
- 本轮目标:
- 已完成:(含通过标准)
- 运行过的验证:
- 已记录证据:(feature_list 的 evidence 字段)
- 提交记录:
- 已知风险:
- 下一步最佳动作:
-->
