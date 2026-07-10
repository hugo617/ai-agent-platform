# 进度日志(progress.md)

> 每轮会话开始时先读、收尾时更新。跨会话必须的关键信息写这里,脑子里的不算。

## 当前已验证状态

- **仓库根目录**: `/Users/star/hugo/3-项目代码/project/ai-agent-platform`
- **标准启动路径**: `./init.sh`(装依赖 + ruff + pytest)
- **标准验证路径**: `./init.sh`(同上,后端快速验证,SQLite 内存库)
- **完整验证路径**(需 docker): `alembic upgrade head && alembic check` + `cd frontend && npm run build`
- **当前最高优先级未完成功能**: `global-rename`(二开第 1 步)—— 但取决于你是否要二开
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
