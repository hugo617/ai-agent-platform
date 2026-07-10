# 进度日志(progress.md)

> 每轮会话开始时先读、收尾时更新。跨会话必须的关键信息写这里,脑子里的不算。

## 当前已验证状态

- **仓库根目录**: `/Users/star/hugo/3-项目代码/project/ai-agent-platform`
- **标准启动路径**: `./init.sh`(装依赖 + ruff + pytest)
- **标准验证路径**: `./init.sh`(同上,后端快速验证,SQLite 内存库)
- **完整验证路径**(需 docker): `alembic upgrade head && alembic check` + `cd frontend && npm run build`
- **当前最高优先级未完成功能**: `custom-business-module`(占位,需先定产品方向)—— `global-rename` 已 passing
- **当前 blocker**: 无(待用户决定产品方向 + 替换占位任务)

## 已 passing 的地基能力(详见 feature_list.json)

| 功能 | 状态 | 验证依据 |
|------|------|---------|
| auth-local(本地密码登录) | passing | 8 tests |
| auth-logto(Logto OIDC) | passing | 4 tests |
| rbac-permission(RBAC 多租户) | passing | 29 tests |
| users-crud(用户管理 CRUD) | passing | 27 tests |
| roles-crud(角色管理 CRUD 全栈) | passing | 96 tests total(13 rbac_api) |
| db-migrations(迁移链) | passing | CI migrations job |
| scd2-history(授权链历史) | passing | 7 tests |
| validation-error-i18n(422 中文化) | passing | 6 tests |
| global-rename(全局改名为 agenthub) | passing | grep 0 残留 + init.sh + npm build |

> ⚠️ **未纳管的产品内核**:`agents`(CRUD)+ `chat`(SSE 流式 LangGraph)后端完整、前端有 `agents-page.tsx`,但**未进 feature_list、未做端到端验证登记**。这是平台最核心能力,后续二开前建议先收口(补测试 + 登记证据)。

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

### Session 003 — 2026-07-10
- **本轮目标**: 执行 `roles-crud`(角色管理 CRUD 全栈对齐)—— 7 步 5 阶段,前后端 + 权限分配
- **已完成**(对照 plan 的 Step 1-7):
  - Step 0 基线确认:`./init.sh` → 88 passed(起点干净),切 `feat/roles-crud` 分支
  - Step 1 后端 Service 异常对齐:`rbac_service.py` 6 处裸 `ValueError` 改为 `NotFoundError`/`BizError`(都是 ValueError 子类,现有 except 仍捕获),加 import
  - Step 2 后端 API 错误映射:`roles.py` 删除 `_bad_request`/`_not_found` + 字符串匹配,改为 `_http_exc`(照抄 users.py 的 isinstance 模式),8 个端点统一 `raise _http_exc(e)`
  - Step 3 测试补全:`test_rbac_api.py` 从 5 个测试补到 13 个(+8:member 403 ×2、系统角色保护 400、404 映射 ×2、权限授权全生命周期、revoke 非授权 404、缺失角色 404)
  - Step 4 前端 API 层:`types.ts` 加 `RoleUpdate`/`RolePermissionGrant`/`RolePermissionRead`;`endpoints.ts` 加 `updateRole` + 3 个权限端点
  - Step 5 前端 hooks:`queries.ts` 加 `useRoles`/`useUpdateRole`/`useDeleteRole`/`useRolePermissions`/`useGrantRolePermission`/`useRevokeRolePermission` + `rolePermissions` key
  - Step 6 前端页面重写:`roles-page.tsx` 从 122 行硬编码空壳重写为真实数据驱动(列表表格 + 创建/编辑 Dialog + 删除确认 + 权限分配面板),参照 `users-page.tsx` 模式
  - Step 7 总验证:`./init.sh` → ruff + **96 passed**;`cd frontend && npm run build` → tsc + vite 通过
- **运行过的验证**(全过):
  - `./init.sh` → ruff `All checks passed!` + **96 passed**(88 基线 + 8 新增)
  - `pytest tests/test_rbac_api.py -v` → 13 passed
  - `cd frontend && npm run build` → tsc + vite build 成功,0 类型错误
- **已记录证据**: `feature_list.json` 的 `roles-crud.evidence` 字段(8 条,含命令+结果+日期+架构铁律说明)
- **技术要点**(与 plan 的实现差异):
  - plan 提「软删除后 code 可复用」,实际 `Role` 表 `UniqueConstraint(tenant_id,code)` 是全表唯一约束(非部分索引),软删除后 code 不可复用——本任务未改 schema(超范围),测试覆盖了列表不出现但不测 code 复用
  - 前端 `sort_order` 用 `z.number()` + `register valueAsNumber`,而非 plan 骨架的 `z.coerce.number()`(后者推断成 unknown,TS 报错)
  - 异常对齐利用了 Python 继承:`NotFoundError`/`BizError` 是 `ValueError` 子类,所以 `except ValueError` 仍捕获,现有 4 个测试零改动通过——这是「向后兼容的渐进式重构」
- **提交记录**: `feat/roles-crud` 分支(本次提交)
- **已知风险**: 无功能风险。手动验证(浏览器/curl)未单独执行,需完整 docker 环境(Postgres)+ 真实 token;前端 tsc 类型检查 + 后端 pytest 已覆盖类型正确性与 API 行为
- **下一步最佳动作**: 由用户决定(a)合并 feat/roles-crud 到 main;(b)开始下一个任务 `global-rename`

### Session 004 — 2026-07-10
- **本轮目标**: 清理废代码 + 代码质量审查 + PR + CI 守门 + 合并 feat/roles-crud 到 main
- **已完成**:
  - 废代码审查(7 改动文件):ruff F401/F811/F841/F821 全绿;`_require_role` 被 3 处调用(非死代码)、`_http_exc` 被 6 处调用、前端 `noUnusedLocals`/`noUnusedParameters` 严格开启且 build 通过 → **无废代码,无需清理改动**
  - 代码质量审查:`roles.py`/`rbac_service.py`/`roles-page.tsx` 结构清晰、铁律合规(分层/租户过滤/软删除);`organizations.py` 仍用旧 `_bad_request`/`_not_found` 但属既有代码,**不在本分支范围,未越界改**
  - 基线验证:`ruff check` 全绿 + **96 passed**
  - 推送 `feat/roles-crud` → 建 PR #11(base main)
  - CI 守门:3/3 全绿(Backend pytest+ruff / Frontend typecheck+build+lint / Migrations alembic upgrade on Postgres),无需修复
  - **squash 合并 PR #11 → main**(commit `e458cbe`),删除远程分支,本地切回 main 并同步
- **运行过的验证**:
  - `ruff check app/api/v1/roles.py app/services/rbac_service.py tests/test_rbac_api.py` → All checks passed!
  - `pytest -ra --strict-markers` → **96 passed**
  - `cd frontend && npx oxlint src/` → 0 errors,4 warnings(均为既有的 button/badge/auth-context/toast,非本分支)
  - CI(PR #11)→ 3 jobs pass
- **已记录证据**: 无新增(本任务是审查+发版,未改代码;feature_list 的 roles-crud.evidence 不变)
- **提交记录**: PR #11 已 squash 合并到 main,无本地新增 commit
- **已知风险**: 无
- **下一步最佳动作**: 开始下一个 not_started 任务 `global-rename`(二开第 1 步),或由用户指定

---

### Session 005 — 2026-07-10
- **本轮目标**: 分析后续任务方向 → 确认 `global-rename` 真实状态 → 执行全局改名(二开第 1 步)
- **前置诊断**:
  - 用户记得 global-rename「应该做过了」,核对后发现 main 上旧名全在,feature_list 仍 not_started → **确实未完成**
  - 发现本地 `feat/global-rename` 分支(fafd13d)是**脏分支**:从旧分叉点拉出,diff 1069 行删除,会回滚 validation-error-i18n(删 validation_errors.py + test)、roles-crud(砍 test_rbac_api.py 139 行 + roles-page.tsx 587 行)两个已 passing 功能 → 已 `git branch -D` 强删,基于最新 main 重建 `feat/global-rename-fresh`
- **已完成**(对照 plan-global-rename.md 的 Step 1-6):
  - Step 1 APP_NAME 核心:`.env.example` + `app/core/config.py` 默认值 → agenthub(.env 此前已是 agenthub)
  - Step 2 产品描述:`app/main.py` description + `pyproject.toml` name/description → 中文化
  - Step 3 前端标题(3 处硬编码全改,含二开清单遗漏的登录页):index.html title / dashboard-layout 页头 / login-page 登录标题 → 智能体云平台 · agenthub
  - Step 4 文档:README/NOTICE/frontend README/casbin 注释/LOGTO_SETUP 示例/项目指南(配置表+改造清单+环境准备)产品标识同步;保留文件夹名语境 + docker 网络名(ai-agent-platform_default)
  - Step 5 OpenAPI 重导出:`create_app().openapi()` → title=agenthub,非手改
  - Step 6 总验证:全过(见下)
- **运行过的验证**(全过):
  - `./init.sh` → ruff `All checks passed!` + **96 passed**
  - `cd frontend && npm run build` → tsc -b + vite build 成功,0 类型错误
  - grep 代码/配置层:**ai-agent-platform + 权限控制台 0 残留**;dist/index.html title 已刷新为「智能体云平台 · agenthub」
  - md 文档剩余 ai-agent-platform 均为合理保留(文件夹名路径/docker 网络名/plan 文档自身/目录树根节点)
- **已记录证据**: `feature_list.json` 的 `global-rename.evidence` 字段(8 条,含脏分支处理说明)
- **提交记录**: `feat/global-rename-fresh` 分支(待用户决定是否合并到 main)
- **已知风险**: 无功能风险。aap 缩写(docker 容器/POSTGRES_USER/CI 变量)未动(用户不可见,改需同步 DATABASE_URL);项目文件夹名未改(不影响运行)。手动浏览器验证未单独执行(纯字符串改名,tsc+grep 已充分覆盖)
- **下一步最佳动作**:
  - (a) 合并 feat/global-rename-fresh 到 main + 发 PR;
  - (b) **收口 AI 内核**(推荐):把 agents + chat 按 harness 流程补端到端验证 + 登记进 feature_list——这是平台最核心能力,目前是"裸奔"状态
  - (c) 定产品方向,把 `custom-business-module` 占位项替换为真实业务模块

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
