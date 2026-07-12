# 计划:数据权限(data_scope 角色级数据范围)(权限重构系列 3/4)

> 对应 feature_list.json 的 `id`: `permission-data-scope`
> 状态: not_started
> 优先级: 41
> 前置: `permission-unified-model`(目录统一后,data_scope 作为角色属性接入)
> 系列总纲: [`plan-permission-redesign-overview.md`](plan-permission-redesign-overview.md)

---

## 背景:数据权限无显式建模

### 现状(2026-07-12 核实)

数据权限(「能看到哪些数据行」)目前靠**特例补丁**,无统一模型：

| 现有机制 | 位置 | 局限 |
|---|---|---|
| 租户过滤 | `TenantScopedRepository` 所有查询带 `tenant_id` | 只到「租户级」,租户内所有人看同样的数据 |
| 跨租户只读 | `hq_staff`/`super_admin` 的 bypass | 平台级,租户内角色用不了 |
| Group 归属 | `GroupTenant` 关联 | 只表达「门店属于哪个组织」,不驱动查询过滤 |

**典型未覆盖场景**:
- 「业务员只能看自己创建的客户」(self)
- 「店长只能看本店(本租户)的客户」(tenant,现状已覆盖,但无显式配置)
- 「区域经理能看本组织(Group)内所有门店的客户」(group,未覆盖)

### 目标

给角色加 `data_scope` 字段(四档),Repository 层按角色 data_scope **自动注入数据范围过滤**:

| data_scope | 含义 | 谁用 | 查询过滤逻辑 |
|---|---|---|---|
| `all` | 平台级全部 | super_admin / hq_staff(平台角色,不配) | 不过滤 |
| `tenant` | 本租户全部 | owner / admin / member(默认) | `WHERE tenant_id = current` |
| `group` | 本组织(Group)内 | 区域经理类自定义角色 | `WHERE tenant_id IN (Group 内门店)` |
| `self` | 只看自己的数据 | 业务员类自定义角色 | `WHERE created_by = current_user` |

### 关键设计决策

1. **data_scope 挂在角色上,不是权限项上**——一个角色一种数据范围(角色 = 一组权限 + 一个数据范围)。避免「每个权限单独配数据范围」的爆炸复杂度。
2. **super_admin/hq_staff 仍走 bypass**——它们的 `platform_role` 已表达平台级,不进 data_scope 系统。
3. **group 范围依赖现有 Group 模型**——Group + GroupTenant 已有(任务 groups-api),复用。
4. **self 范围需要业务表有 `created_by` 列**——核实哪些表有,缺失的要补(主要 customers/conversations/agents)。

---

## 前置条件

- `permission-unified-model` 完成
- `groups-api` 完成(Group + GroupTenant 已有)✅

---

## 实施步骤

### 第一阶段:模型 + 迁移

#### Step 1:Role 加 data_scope 字段

- **改什么**(`app/models/rbac.py` Role 模型):
  ```python
  data_scope: Mapped[str] = mapped_column(String(20), default="tenant")
  # 取值:all / tenant / group / self;默认 tenant(向后兼容)
  ```
- **迁移**(`alembic` autogenerate):加列 `data_scope` default 'tenant'
- **检查**:`alembic upgrade head && alembic check` 无 drift;现有角色 data_scope = tenant(默认值回填)

#### Step 2:系统角色 seed 设默认 data_scope

- **改什么**(`app/services/permission_service.py` / `rbac_service.py` seed):
  - owner/admin/member → `data_scope="tenant"`(默认,本租户全量)
  - 自定义角色创建时由创建者选(`RbacService.create` 入参加 data_scope,默认 tenant)
- **检查**:新建租户三角色 data_scope = tenant

### 第二阶段:Repository 层数据范围过滤(核心)

#### Step 3:设计 DataScopeResolver 工具

- **新建**(`app/repositories/data_scope.py` 或并入 `app/core/`):
  ```python
  class DataScopeResolver:
      """根据角色的 data_scope 返回查询过滤条件。"""
      def resolve(self, user, tenant_id, roles) -> FilterCondition:
          # all → 无过滤
          # tenant → tenant_id == current
          # group → tenant_id IN (user 所属 Group 的全部门店)
          # self → created_by == user.user_id
  ```
- **输入**:当前 user、tenant_id、user 的角色列表(取最宽 data_scope,即多角色取并集)
- **输出**:一个可叠加到 SQLAlchemy 查询的过滤条件(如 `or_(tenant_id.in_(...), created_by == ...)`)
- **多角色聚合规则**:用户有多个角色时,data_scope 取**最宽**的(有 tenant 也有 self → 按 tenant)。避免「加了个 self 角色反而看不到原来数据」。
- **检查**:单元测试覆盖四档 + 多角色聚合

#### Step 4:业务 Repository 接入 DataScopeResolver

- **改什么**(需要数据范围过滤的 Repository,首批):
  - `CustomerRepository`(customers 域,最典型 self/group 场景)
  - `ConversationRepository`(业务员只看自己会话)
  - `AgentRepository`(可选,agent 通常租户共享)
- **改造模式**:Repository 的 list/query 方法加 `data_scope_filter` 可选参数,由 Service 层从当前 user 解析后传入
  ```python
  # Repository
  async def list(self, tenant_id, *, data_scope_filter=None):
      stmt = select(Customer).where(Customer.tenant_id == tenant_id, Customer.is_deleted == False)
      if data_scope_filter is not None:
          stmt = stmt.where(data_scope_filter)  # 叠加数据范围
      ...
  ```
- **Service 层**:`customer_service.list(...)` 调 `DataScopeResolver.resolve(user, ...)` 传给 Repository
- **检查**:业务员(self)登录 GET /customers 只看到自己创建的;店长(tenant)看到全店

#### Step 5:group 范围的门店解析

- **改什么**(`DataScopeResolver` group 分支):
  - 查 user 当前 tenant 所属的 Group → 取 Group 内全部 tenant_id → `WHERE tenant_id IN (...)`
  - 复用 `GroupRepository` 已有方法(查 Group 的门店列表)
  - 注意:一个 tenant 可能属于多个 Group → 取并集
- **边界**:如果 user 的 tenant 不属于任何 Group → group 降级为 tenant(只看自己门店)
- **检查**:区域经理(group)登录 → 看到本组织所有门店的客户

### 第三阶段:API + Schema

#### Step 6:角色 CRUD 暴露 data_scope

- **改什么**(`app/schemas/rbac.py`):
  - `RoleRead` / `RoleCreate` / `RoleUpdate` 加 `data_scope: str` 字段(默认 tenant)
  - 校验取值在 `{all, tenant, group, self}`
- **改什么**(`app/services/rbac_service.py`):create/update 写入 data_scope
- **改什么**(`app/api/v1/roles.py`):角色详情/编辑端点透传 data_scope
- **检查**:创建自定义角色时可选 data_scope;GET /roles 返回 data_scope 字段

### 第四阶段:测试 + 总验证

#### Step 7:补测试

- **新建** `tests/test_data_scope.py`:
  - self 范围:业务员只看自己客户(创建 2 个客户,1 个是别人的 → 只看到 1 个)
  - tenant 范围:owner 看到全租户客户
  - group 范围:区域经理看到 Group 内多门店客户
  - 多角色聚合:用户同时有 tenant 角色和 self 角色 → 按 tenant(最宽)
  - group 降级:tenant 不属于任何 Group → 降级 tenant
  - 跨租户隔离不变
- **检查**:`pytest tests/test_data_scope.py -v` 全过

#### Step 8:总验证

- **命令**:
  ```bash
  ./init.sh   # ruff + pytest 全绿
  cd frontend && npm run build   # schema 加字段不影响前端构建
  ```
- **通过标准**:
  - `./init.sh` 全绿(含 data_scope 测试)
  - alembic 无 drift
  - 手动验证:self 角色用户只看自己数据,tenant 角色看全店,group 角色看跨店
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

1. Role 表加 `data_scope` 字段(四档:all/tenant/group/self),默认 tenant
2. `DataScopeResolver` 实现四档过滤 + 多角色聚合(取最宽)
3. CustomerRepository / ConversationRepository 接入数据范围过滤
4. group 范围正确解析 Group 内门店(Group 不存在时降级 tenant)
5. 角色 CRUD 暴露 data_scope 字段
6. `./init.sh` + `npm run build` 全绿
7. 测试覆盖四档 + 多角色聚合 + 降级场景

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 业务表缺 `created_by` 列(self 范围用不了) | 核实 customers/conversations/agents 是否有 created_by;缺失的补列 + 迁移回填 |
| 多角色 data_scope 聚合规则复杂 | 简化为「取最宽」(all > group > tenant > self),单元测试覆盖 |
| group 查询性能(跨租户 IN) | Group 内门店数通常 <100,IN 查询可接受;超大规模再加缓存 |
| 现有查询漏接 data_scope | 首批只接 Customer/Conversation 两域;Agent 暂不接(租户共享语义);Repository 改造用 `data_scope_filter` 显式参数,不偷偷注入 |
| super_admin 范围冲突 | super_admin 走 bypass,不进 data_scope 解析(在 Resolver 入口判断 platform_role 直接返回 all) |

### 不做的事(边界)

- 不做列级数据权限(隐藏某列),只做行级
- 不做权限项粒度的 data_scope(只角色级)
- 不改 super_admin/hq_staff 的 bypass(platform_role 仍主导)
- 不做 data_scope 的 SCD2 历史(当前态即可,历史还原是按需项)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| 系列总纲 | `harness/docs/plan-permission-redesign-overview.md` |
| Role 模型(待改) | `app/models/rbac.py` Role |
| 租户隔离基类 | `app/repositories/base.py` `TenantScopedRepository` |
| Group 模型(复用) | `app/models/group.py` Group / GroupTenant |
| Group Repository(复用) | `app/repositories/group.py` |
| Customer Repository(待改) | `app/repositories/customer.py` |
| 多租户隔离文档 | `项目指南/02-后端架构/04-多租户隔离.md` |
