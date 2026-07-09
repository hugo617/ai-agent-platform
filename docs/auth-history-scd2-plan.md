# 权限历史回溯改造计划(SCD2 + 关系统一)

> 状态:**需求触发参考(现阶段不实施)**。本文档是当业务**真的出现**「任意时间点还原」合规
> 需求时,给执行者的完整施工图。现阶段「权限表 + 基础属性表」已够用,SCD2 属于按需增强,
> **不是当前行动项**——别一上来就照这个改表。
> 这是 [表设计原则第 6 条](../项目指南/02-后端架构/03-数据库与ORM.md) 的具体展开;
> 设计背景见 [06-权限模型RBAC](../项目指南/02-后端架构/06-权限模型RBAC.md) 的「权限变更的历史回溯(SCD2)」节。

---

## 1. 背景与目标

当前 RBAC 是**双层结构**:`roles / permissions / role_permissions` 是显示层,`casbin_rule` 是执行层(权威)。问题有二:

1. **没有历史**:角色/权限一旦改了,旧值丢失。无法回答「张三在 3 月 1 日是什么角色?」「admin 角色当时的权限集是什么?」这类**任意时间点还原**的合规诉求。
2. **双层职责模糊**:改权限时「该改哪张表」不清晰,执行层与显示层两条路并存,改动牵连不可知(用户反馈的核心痛点)。

**目标**:在不推翻现有架构的前提下,给**授权链**加上时间维度,并定死双层职责边界,使得:
- 任意时间点可还原单成员角色(场景 i)与单角色权限集(场景 ii);
- 实时鉴权仍由 casbin 负责,毫秒级、不变;
- 改动牵连清晰可查。

**非目标(明确不做)**:全租户权限拓扑快照(场景 iii)、事件溯源、agent 模型扩展、SaaS 商业层(计费/配额)——见第 9 节。

---

## 2. 设计总纲(一句话)

> **方案三(主表 + 变更日志)做骨架;在 `user_tenants` 和 `role_permissions` 两张表上局部叠加方案二(SCD2 时态表);casbin 只管「现在能不能」,SCD2 的当前态是 casbin 的同步源;`system_logs` 是所有变更的审计底座。**

### 数据流地图

```
┌──────────────────────────────────────────────────────────────┐
│ 实时鉴权(高频,每请求)                                        │
│   请求 → PermissionService.check → casbin_rule(当前态) → 放行/拒绝 │
│   ★ casbin 永远只回答「现在」,不管历史                         │
├──────────────────────────────────────────────────────────────┤
│ 当前态来源(中频,管理员界面)                                  │
│   user_tenants / role_permissions 的 WHERE valid_to IS NULL    │
├──────────────────────────────────────────────────────────────┤
│ 历史回溯(低频,合规/事故复盘)                                 │
│   同两张表的 valid_from/valid_to 时间区间查询 → 还原 (i)(ii)    │
├──────────────────────────────────────────────────────────────┤
│ 全量审计(所有变更底座)                                       │
│   system_logs:谁、何时、把什么从 X 改成了 Y(append-only)       │
└──────────────────────────────────────────────────────────────┘
```

### 双层职责「宪法」(必须落到代码注释 + 文档)

> **历史回溯看 SCD2 表;实时鉴权看 casbin;SCD2 当前态是 casbin 的同步源。**
> 管理员改权限 → 写 SCD2(关旧行/插新行)→ 用 SCD2 当前态同步 casbin → 写 system_logs。
> 永远不要让 casbin 兼顾历史,casbin 不存历史。

这条宪法顺带治好了「双层谁为准」的断裂:`role_permissions` 从死表变为「角色权限历史还原的唯一数据源」,当前态同步给 casbin。

---

## 3. 范围声明:本计划覆盖什么、不覆盖什么

| 评审发现的问题 | 处置 | 说明 |
|---|---|---|
| **B. RBAC 双层 display↔casbin 断裂** | ✅ 本计划覆盖 | 宪法定死「以谁为准」;`role_permissions` 经 SCD2 激活为历史源 |
| **E(部分). 软引用散落** | ✅ 本计划覆盖(b 线) | `role_permissions.tenant_id` 等 3 处软引用统一 |
| **A. 多租户隔离无 RLS 兜底** | ⏭️ 后续 | 不在本计划。隔离仍靠 `TenantScopedRepository`,单独议题 |
| **C. agent 模型单薄** | ⏭️ 后续 | 依赖产品形态定义,另立计划 |
| **D. SaaS 商业层缺失** | ⏭️ 后续 | 计费/配额/邀请,另立计划 |
| **E(其余). 字段级问题** | ⏭️ 后续 | `verification_codes` 只有 phone、`users.created_by` 无 ondelete、`system_logs` 无分区等 |

---

## 4. Schema 改造

### 4.1 `user_tenants`(场景 i:某成员当时的角色)

**现状**:`PK (user_id, tenant_id)`,`role`,`created_at`。无任何表 FK 引用它(已确认),改主键安全。

**改造**:

```text
id          varchar(32)  PK  新增代理主键(default uuid4().hex)
user_id     varchar(128)     FK→users.id, CASCADE  (放开唯一,变业务键)
tenant_id   varchar(32)      FK→tenants.id, CASCADE (放开唯一,变业务键)
role        varchar(64)  NN
valid_from  timestamptz  NN  新增,生效时间
valid_to    timestamptz  NULL 新增,失效时间;NULL = 当前生效
created_at  timestamptz  NN
```

**约束**:
- 删除原 `PRIMARY KEY (user_id, tenant_id)`,改为 `id` 主键。
- 新增 partial unique(参考 `users` 表已有的 `uq_users_username_active` 写法,PG 用 `postgresql_where`、SQLite 用 `sqlite_where`):
  - `UNIQUE (user_id, tenant_id) WHERE valid_to IS NULL` —— 保证「每个成员当前只有一行生效」。

**查询语义**:
- 当前态:`WHERE valid_to IS NULL`
- 时间点还原(i):`WHERE user_id=? AND tenant_id=? AND valid_from <= ts AND (valid_to IS NULL OR valid_to > ts)`
- 「移除成员」:`UPDATE ... SET valid_to = now()`(历史保留,不再物理删行)

### 4.2 `role_permissions`(场景 ii:某角色当时的权限集)

**现状**:`id PK`,`UNIQUE (tenant_id, role_id, permission_id)`。

**改造**:

```text
id            varchar(32) PK  不变
tenant_id     varchar(32) NN
role_id       varchar(32) FK→roles.id CASCADE
permission_id varchar(32) FK→permissions.id CASCADE
valid_from    timestamptz NN  新增
valid_to      timestamptz NULL 新增
created_at    timestamptz NN
```

**约束**:
- 把原 `UNIQUE (tenant_id, role_id, permission_id)` 改成 partial unique:
  - `UNIQUE (tenant_id, role_id, permission_id) WHERE valid_to IS NULL`

**查询语义**:
- 当前态:`WHERE role_id=? AND tenant_id=? AND valid_to IS NULL`
- 时间点还原(ii):`WHERE role_id=? AND tenant_id=? AND valid_from <= ts AND (valid_to IS NULL OR valid_to > ts)` → 当时该角色的完整权限集。

---

## 5. Repository 封装(命脉)

SCD2 的写路径必须封装,业务代码**绝不**直接操作 `valid_from/valid_to`,否则一定会有人忘了关旧行,数据就脏了。

### `UserTenantRepository` 新增方法

- `assign_role(user_id, tenant_id, role, *, at=None)` —— 关闭该成员当前生效行(`valid_to=at`)→ 插入新行(`valid_from=at, valid_to=NULL`)→ 全程一个事务。`at` 缺省取 `now()`。
- `remove_member(user_id, tenant_id, *, at=None)` —— 关闭当前生效行(不再物理删除)。
- `current_members(tenant_id)` —— `WHERE tenant_id=? AND valid_to IS NULL`(替代原 `list_for_tenant`)。
- `member_role_at(user_id, tenant_id, ts)` —— 场景 i 还原。
- `current_role(user_id, tenant_id)` —— 当前态角色(给鉴权/sync 用)。

### `RolePermissionRepository` 新增方法

- `grant(role_id, permission_id, tenant_id, *, at=None)` —— 关旧行 + 插新行。
- `revoke(role_id, permission_id, tenant_id, *, at=None)` —— 关旧行。
- `current_permissions(role_id, tenant_id)` —— 当前态权限集。
- `permissions_at(role_id, tenant_id, ts)` —— 场景 ii 还原。

> 约定:`at` 参数主要为**测试确定性**传入(避免依赖 `now()` 的不可重现)。生产路径用默认 `now()`。

---

## 6. casbin 同步(改动控制在最小面)

现有 `PermissionService.set_role_for_user_in_domain` 已在「改角色时同步 casbin」。SCD2 后,`assign_role` 内部在写完 SCD2 行后调用它即可——**casbin 侧代码几乎不动**,数据来源从扁平表变成 SCD2 当前态。

- 成员角色变更:`UserTenantRepository.assign_role` → `permission_service.set_role_for_user_in_domain`。
- 角色权限集变更:需要新增「按 role 重建该 domain 下受影响用户的 casbin 策略」——初版可简化为「改 role_permissions 后,该 tenant 内所有持有该 role 的用户重新同步」。注意这条是**新增逻辑**,要在计划里显式标注,别漏。

---

## 7. 落地顺序(两条线分开做,严禁混在一起)

### 第 1 步 · b 线:宪法定稿 + 关系统一(改动小、先稳心智)

- [ ] 把第 2 节「宪法」写成代码注释,挂在 `permission_service.py` 顶部与 `rbac.py` 模块 docstring。
- [ ] 统一 3 处软引用:`role_permissions.tenant_id`(本计划 SCD2 后会带 tenant,自然消化)、`conversations.user_id`、`messages.tenant_id`——逐个决策「加 FK」或「登记为已知特例(在 `db-schema.mmd` 注释里集中标注)」。
- [ ] **验证标准**:再问「改权限改哪张表」,答案唯一且写在注释里。

### 第 2 步 · SCD2 schema 落地

- [ ] 改 `app/models/tenant.py` 的 `UserTenant`、`app/models/rbac.py` 的 `RolePermission`:加字段、改主键/约束。
- [ ] 写 Alembic 迁移(autogenerate 后手工校对):
  - 回填存量行:`valid_from = COALESCE(created_at, now())`,`valid_to = NULL`;
  - drop 旧主键/旧唯一约束,建新代理主键 + partial unique。
- [ ] Repository 封装(第 5 节方法),业务代码切到新方法。
- [ ] **验证标准**(可独立循环):单测——插一个成员、改三次角色,断言 `current_role` 与 `member_role_at(三个时间点)` 返回正确;`role_permissions` 同型测试。

### 第 3 步 · casbin 接线

- [ ] `assign_role` 接 `set_role_for_user_in_domain`;新增 role 权限集变更的同步逻辑(第 6 节)。
- [ ] **验证标准**:集成测试——改角色后,`permission_service.check` 的结果与 SCD2 当前态一致。

---

## 8. 风险与注意事项

1. **SCD2 引入新牵连点**:所有读这两张表当前态的查询都必须带 `WHERE valid_to IS NULL`,漏了就读到历史脏数据。**对策**:只通过 Repository 方法访问;加「当前态成员数 = 期望值」的回归测试兜底。
2. **写路径事务性**:「关旧行 + 插新行」必须在同一事务,中途失败要回滚。Repository 方法内 `flush`,由外层 Service/请求事务提交。
3. **SQLite 测试库差异**:partial unique 在 SQLite 用 `sqlite_where=text("valid_to IS NULL")`,PG 用 `postgresql_where`。已有 `users` 表先例可抄。注意 SQLite 对 `WHERE col IS NULL` 的 partial index 支持。
4. **`now()` 不可重现**:`valid_from` 默认用 `func.now()`;但**测试**显式传 `at` 参数,保证时间点断言稳定。
5. **不要顺手改 agent / 商业层**:它们是第 9 节的后续议题,混进本计划会让 review 失焦、回归测试爆炸。

---

## 9. 明确不在本计划范围(后续议题)

- **评审 A 多租户隔离 RLS 兜底**:建议作为下一个独立计划,给关键租户资源表加 PG Row-Level Security 做数据库层兜底 + 写跨租户泄漏渗透测试。
- **评审 C agent 模型**:provider/密钥、tools、RAG(pgvector 已装待接)、agent 级权限、版本/状态。**前置依赖:产品形态定义(Dify 式 / Coze 式 / AutoGen 式)**,形态不定不建模。
- **评审 D SaaS 商业层**:套餐/订阅/用量配额/token 计费/租户邀请(invitations)。
- **评审 E 其余字段级**:`verification_codes` 补 email 字段、`users.created_by/updated_by` 补 ondelete、`system_logs` 按月分区 + BRIN。

---

## 10. 关键文件清单(执行者入口)

| 关注点 | 文件 |
|---|---|
| 模型改造 | `app/models/tenant.py`(`UserTenant`)、`app/models/rbac.py`(`RolePermission`) |
| Repository 封装 | `app/repositories/tenant.py`、`app/repositories/rbac.py`、`app/repositories/base.py` |
| casbin 同步 | `app/services/permission_service.py`(`set_role_for_user_in_domain`、`seed_tenant_defaults`) |
| 业务调用方 | `app/services/user_service.py`、`app/services/rbac_service.py`、`app/services/member_service.py` |
| 迁移 | `alembic/versions/`(autogenerate + 手工校对) |
| Schema 文档 | `docs/db-schema.mmd`、`docs/db-schema.html`(改完同步) |
| 设计说明 | `项目指南/02-后端架构/06-权限模型RBAC.md`(已加 SCD2 节) |
| partial unique 先例 | `app/models/tenant.py` 的 `User`(`uq_users_username_active`) |
