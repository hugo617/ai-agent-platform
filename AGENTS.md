# AGENTS.md

> 这个文件是给 **AI 编码助手**(Claude Code / Cursor / ZCode 等)看的入口。
> 人类开发者请看 [README.md](README.md)。

---

## 项目简介

**多租户 AI 智能体 SaaS 平台** —— 可作为新 SaaS 产品的脚手架。
技术栈:FastAPI + SQLAlchemy 2.0(async)+ pycasbin + LangGraph + React 19 + PostgreSQL 16 + pgvector,
双轨认证(本地 bcrypt + Logto OIDC)统一过 `get_current_user` 管线。
详见 [`项目指南/00-总览/03-技术栈总览.md`](项目指南/00-总览/03-技术栈总览.md)(单点真相源)。

---

## 🚀 开工流程(每轮会话开始时,按顺序做)

> 这是 Harness 工程的入口。目的是让每轮会话结束后,下一轮能无猜测地继续。

1. `pwd` —— 确认在仓库根目录。
2. 读 [`progress.md`](progress.md) —— 恢复「现在做到哪了、下一步做什么」。
3. 读 [`feature_list.json`](feature_list.json) —— 选优先级最高的 `not_started` 功能(WIP=1,同时只能一个)。
4. `git log --oneline -5` —— 看最近发生了什么。
5. 运行 `./init.sh` —— 装依赖 + 跑基础验证(ruff + pytest,SQLite 内存库,秒级)。
6. **如果基础验证失败,先修基础,不要在坏起点上叠新功能。**

---

## 📚 第一件事:读文档

本项目有完整的**中文文档体系**,在 [`项目指南/`](项目指南/) 目录。
**AI 必读 [`项目指南/README-给AI.md`](项目指南/README-给AI.md)** ——
教你按任务渐进式读取文档(不塞满上下文),含「按任务选文档」表(10 个常见任务)+ CodeGraph 配合使用 + 容易踩的坑。

---

## ⚠️ 改代码前必知(项目铁律)

1. **依赖单向**:Controller → Service → Repository → Model,绝不能反向。
2. **多租户隔离**:写新的数据查询时,租户过滤必须在 Repository 层(用
   `TenantScopedRepository`),不要依赖 Service「记得加 where」。
3. **三种 token**:本地(HS256)、Logto(RS256)、开发(RS256),都走同一条验证管线。
4. **软删除 + 部分唯一索引**是惯例,查询要带 `is_deleted=False` 语义。
5. **引用代码用符号名**(如 `TenantScopedRepository`),不用行号(行号会变)。
6. **数据库表设计原则**:加新表前必读 `项目指南/02-后端架构/03-数据库与ORM.md` 的
   「新增表的设计原则」(8 条 checklist)。**按需加表,不预建空架子,不过度设计**;
   SCD2(`valid_from`/`valid_to`)仅授权链等合规刚需才上(见 `docs/auth-history-scd2-plan.md`)。

更多约定见 [`项目指南/README-给AI.md`](项目指南/README-给AI.md) 的「容易踩的坑」。

---

## 🤖 自动触发规则(task → skill 路由表)

agent 不再凭自觉用 skill,按任务状态变化硬触发(详见
[`harness/docs/task-workflow.md`](harness/docs/task-workflow.md) §7,含 mermaid 流程图):

| 任务状态变化 | 必调 skill |
|---|---|
| feature_list.json 新增任务 | `/grill-with-docs`(有 codebase)/ `/grill-me`(无) |
| 需求沟通清楚,要落 PRD | `/to-spec`(模板见 [`harness/docs/prd-template.md`](harness/docs/prd-template.md))|
| PRD 完成,要拆切片 | `/to-tickets` |
| 切片开始实施 | `/implement`(内部驱动 `/tdd`)|
| 实施完成 | `/code-review`(双轴 Standards + Spec)|
| bug 出现 | `/diagnosing-bugs`(流程见 [`harness/docs/bug-tracking.md`](harness/docs/bug-tracking.md))|
| 代码健康度巡检(每 10 feature / 重构前)| `/improve-codebase-architecture`(流程见 [`harness/docs/codebase-health-check.md`](harness/docs/codebase-health-check.md))|
| context 接近 60% | `/handoff` |

不确定用哪个?输入 `/harness-router` 让路由器推荐(阶段 3 后可用)。

---

## 📋 每次任务完成后:必须提供「文档影响评估」

**这是项目的长期约定,每个任务完成时都要做。** 详见
[`harness/docs/doc-impact-assessment.md`](harness/docs/doc-impact-assessment.md)
(触发时机 / 4 行格式模板 / 判断依据 / 示例)。

---

## 🔧 工作规则与完成定义

> Harness Stage 1 + Stage 3:防越界、防半成品、防假完成。详见
> [`harness/docs/task-workflow.md`](harness/docs/task-workflow.md)(状态机 / 完成定义 / 收尾清单全在这)。

**核心 4 条**(不可违反):
- **WIP=1**:一次只做一个功能,当前端到端验证通过前不开新功能
- **完成绑定证据**:状态 `in_progress` → `passing` 唯一方式是验证真跑过 + 证据写进 [`feature_list.json`](feature_list.json) `evidence`
- **不越界**:只做选定功能,不顺手重构/多改(除非窄范围 blocker 修复)
- **仓库是唯一事实来源**:脑子里的不算,决策/进度/约定都落到文件

**收尾**:对照 [`harness/clean-state-checklist.md`](harness/clean-state-checklist.md) 逐项打勾 + 更新 [`progress.md`](progress.md)。
