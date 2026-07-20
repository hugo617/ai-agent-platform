# PRD / 切片 Design 模板

> 这是本项目的 **PRD 标准模板**。新任务立项写 plan 文档时,复制本文档结构。
> 它是 [`task-workflow.md`](./task-workflow.md) §5「附录:plan 文档模板」的强化版 —— 那个模板太简单,本文档补齐影响面清单 / 对抗式审查 / 差异段等工程刚需。
> 起步 skill:[`/grill-with-docs`](file:///Users/star/.agents/skills/grill-with-docs/SKILL.md) 烤清需求 → [`/to-spec`](file:///Users/star/.agents/skills/to-spec/SKILL.md) 落 PRD → [`/to-tickets`](file:///Users/star/.agents/skills/to-tickets/SKILL.md) 拆切片。

---

## 0. 使用说明

| 任务类型 | 用哪个模板 |
|---|---|
| 新功能 / 重构 / 复杂改动 | **本文档**(完整 PRD + 切片) |
| bug 修复 | [bug-tracking.md](./bug-tracking.md) §4 简化模板 |
| 小改动(1-2 文件,无 schema 变化) | [task-workflow.md](./task-workflow.md) §5 简单模板即可 |

**何时启动 PRD 流程**:改动文件 >5 / 涉及鉴权/权限/数据迁移/跨服务 / 需要技术选型 → 用本文档。

---

## 1. 完整 PRD 模板(复制即用)

```markdown
# 计划:<任务标题>

> **id**: <kebab-case,与 feature_list.json 同步>
> **状态**: draft v1 / draft v2(经对抗式审查)/ in_progress / passing
> **优先级**: <数字,从 feature_list.json>
> **创建日期**: YYYY-MM-DD
> **最后修订**: YYYY-MM-DD(v2+ 必填)

---

## 0. v1 → vN 变更摘要(若有修订,必填)
| v(N-1) 问题 | 严重度 | vN 处理 |
|---|---|---|
| <问题描述> | 🔴/🟡/🟢 | <修订动作> |

---

## 1. Problem Statement(对齐 to-spec)
<这个任务要解决什么问题?为什么现在做?用户痛点 / 业务诉求 / 技术债>

## 2. Solution(对齐 to-spec)
<总体方案,1-2 段。不要细节,细节在 §4 实施决策>

## 3. User Stories(对齐 to-spec)
- 作为 <角色>,我想 <动作>,以便 <价值>
- 作为 <角色>,我想 <动作>,以便 <价值>
(至少覆盖:owner / admin / member / super_admin / 平台运维 五种角色中的相关方)

---

## 4. Implementation Decisions(对齐 to-spec + 项目特化)

### 4.1 影响面清单(项目特化,必填)
| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | N | app/api/...、app/services/... |
| 数据库迁移 | M | alembic/versions/...(新增)/ ...(改) |
| 前端文件改动 | N | frontend/src/... |
| 新增测试类 | N | tests/test_xxx.py |
| Skill / Hook / 配置 | N | 若涉及 |

### 4.2 多租户影响评估(项目特化)
- 是否新增租户 scoped 表? YES/NO
- 是否修改现有租户隔离逻辑? YES/NO(若是,列文件)
- 是否引入跨租户访问点? YES/NO(若是,super_admin / hq_staff 等全局身份如何守卫)
- 验证:多租户测试用例 N 条(不同租户互不可见)

### 4.3 权限影响评估(项目特化)
- 是否新增 permission code? YES(列出,如 `customers:read`/`customers:update`)/ NO
- 是否修改 DEFAULT_*_PERMS? YES(哪个角色加什么)/ NO
- 是否影响 60+ 处 `require_permission` caller? YES(列出)/ NO
- 是否影响 graph.py 工具内 check(Agent 工具二次校验)? YES/NO
- scope 闸门(若涉及 API Token):read/write scope 如何收敛

### 4.4 数据库表设计 checklist(呼应 AGENTS.md 铁律 6)
加新表前 8 条:
- [ ] 租户归属(tenant_id FK + 索引)
- [ ] 软删除(is_deleted + 部分唯一索引)
- [ ] 命名(snake_case + 业务前缀)
- [ ] 双库兼容(PostgreSQL 生产 / SQLite 测试,VECTOR 等 PG 专有类型要方言守卫)
- [ ] 历史维度(主表 + system_logs 审计 / SCD2 仅合规刚需)
- [ ] timestamp(created_at / updated_at)
- [ ] 外键约束(SET NULL / CASCADE 选哪个,理由)
- [ ] index 策略(查询模式驱动)

> 详见 [项目指南/02-后端架构/03-数据库与ORM](../../项目指南/02-后端架构/03-数据库与ORM.md)「新增表的设计原则」。

### 4.5 其他实施决策
- 技术选型理由(为什么用 X 不用 Y)
- API 设计(RESTful? 新端点路径? )
- 错误处理(BizError 子类? HTTP 状态码?i18n)

---

## 5. Testing Decisions(对齐 to-spec)
- 测试金字塔:unit N / integration M / E2E K
- 测试用 SQLite 内存库还是真 PG?(涉及 VECTOR / 部分索引 / server_default 必须 PG)
- 覆盖率目标(项目基线 93%,本任务不低于)
- 边界 case 清单
- 多租户隔离测试(不同租户互不可见)

---

## 6. 切片规划(对齐 to-tickets tracer-bullet)

把任务拆成 N 个**垂直切片**(每片切穿 schema→API→UI→test 全栈,单片可独立验证),声明 blocking edges:

### Ticket 1: <切片名>
- **What to build**: <用户视角的端到端行为,非分层列表>
- **Blocked by**: <哪些 ticket 必须先完成>(无 = 可立即开始)
- **文件清单**: <估算>
- **验证命令**: <可执行>

### Ticket 2: <切片名>
- **What to build**: ...
- **Blocked by**: Ticket 1
- ...

> **例外:wide refactor 不切片**。若是「重命名列 / 改共享类型签名」等爆炸半径大的机械改动,用 expand–contract 序列(先加新形式并存 → 分批迁移 caller → 最后删旧形式)。详见 to-tickets SKILL.md。

---

## 7. v1 → v2 对抗式审查段(复杂任务必填)

**触发条件**(满足任一即复杂任务):
- 改动文件 >10
- 涉及鉴权 / 权限 / 数据迁移 / 跨服务调用
- 涉及安全敏感操作(token / 密钥 / 支付)
- 涉及不可逆操作(删表 / 删列 / 改列类型)

**审查方式**:
- 单模型双轴(Standards + Spec)—— 当前默认
- 多模型投票(模式 B)—— 未来态,见 [multi-model-voting.md](./multi-model-voting.md)

**审查产出**:
- 🔴 必修项(改完才能进实施)
- 🟡 建议项(影响落地质量)
- 🟢 打磨项(可选)
- 每项回写到本 plan 的 §0 v1→v2 变更摘要

> 范例:[plan-api-token-fine-grained-scopes.md](./plan-api-token-fine-grained-scopes.md) 的 v1→v2 段 + 配套 [review-harness-engineering-revamp.md](./review-harness-engineering-revamp.md)。

---

## 8. Out of Scope(对齐 to-spec)
- ❌ <明确不做的事>
- ❌ <推迟到后续任务的事>

---

## 9. 风险与缓解
| 风险 | 严重度 | 缓解 |
|---|---|---|
| <风险描述> | 高/中/低 | <缓解动作> |

---

## 10. 验收标准(同步 feature_list.json verification)
1. <可执行的检查>
2. <可执行的检查>
...

---

## 11. 不越界声明
本次改动**只**涉及 <X>;**不**触碰 <Y>(明确边界,防顺手改)。
```

---

## 2. 切片规则详解(tracer-bullet)

### 2.1 垂直切片(默认)

每个 ticket 切穿所有层,单片可独立 demo / verify:

```
Ticket 1: schema + migration + repository + API + UI + test(端到端打通最简路径)
Ticket 2: 加权限校验 + 权限测试(blocked by 1)
Ticket 3: 加多租户隔离 + 隔离测试(blocked by 1)
Ticket 4: 加 E2E + 文档(blocked by 1,2,3)
```

**反模式**:不要横向切片(「先做所有 schema,再做所有 API,再做所有 UI」)—— 每个 ticket 单独不可验证,WIP=1 时阻塞下游。

### 2.2 wide refactor 例外

机械改动 + 爆炸半径大(如重命名 `tenant_id` 列)用 expand–contract:

```
Ticket 1 (expand): 加新列 tenant_uuid 并存,代码读旧写新
Ticket 2..N (migrate batch): 分批迁移 reader,每批保持 CI 绿
Ticket N+1 (contract): 删旧列,blocked by 所有 migrate batch
```

详见 [to-tickets SKILL.md](file:///Users/star/.agents/skills/to-tickets/SKILL.md)。

---

## 3. 影响面清单怎么估

实操方法:

1. **后端**:`grep -r "<关键词>" app/` 数文件,分类(api/services/repositories/models/schemas)
2. **迁移**:是否加列/加表/改类型/加索引 → 算 1 个迁移文件
3. **前端**:`grep -r "<关键词>" frontend/src/` 数文件
4. **测试**:每改一个 service / API 至少 1 个测试文件
5. **配置**:改 `.env.example` / `config.py` / `docker-compose.yml` 算配置改动

---

## 4. 已有 plan 范例索引

| 任务 | 复杂度 | 看它的什么 |
|---|---|---|
| [plan-api-token-fine-grained-scopes.md](./plan-api-token-fine-grained-scopes.md) | 高 | v1→v2 对抗式审查段 + contextvar 范式 spike |
| [plan-chat-overflow-title-fix.md](./plan-chat-overflow-title-fix.md) | 低(bug) | bug 类简化模板 |
| [plan-permission-data-scope.md](./plan-permission-data-scope.md) | 中 | 多租户 + 权限 + 迁移 backfill |
| [plan-customers-api.md](./plan-customers-api.md) | 中 | 双表设计 + 全局身份跨店复用 |

---

## 5. 与 task-workflow.md 的关系

| 文档 | 角色 |
|---|---|
| [task-workflow.md](./task-workflow.md) | 任务管理规则(状态机 / WIP=1 / 完成定义)+ 简单 plan 模板 |
| 本文档 | PRD 强化模板(影响面 / 对抗式审查 / 切片) |
| [bug-tracking.md](./bug-tracking.md) | bug 专用简化模板 |

**写作顺序**:
1. 立项 → 先写本文档 §1-4(PRD 主体)
2. PRD 完成 → 写 §6 切片规划(可调 `/to-tickets`)
3. 复杂任务 → 写 §7 对抗式审查段 → 修订 → v2
4. 进 feature_list.json → 状态机走 task-workflow.md
