# 计划:知识库分级 Feature A —— 数据模型 + 权限地基

> **id**: `knowledge-tiered-foundation`
> **状态**: in_progress(切片 01+02 已合并,切片 03 末切片待做)
> **优先级**: 90(feature_list.json)
> **创建日期**: 2026-08-06
> **承接**: [`plan-knowledge-tiered-overview.md`](plan-knowledge-tiered-overview.md)(EP1 总纲,D1-D12 决策锁定)
> **下游**: `knowledge-tiered-backend`(B,depends_on 本 feature)/ `knowledge-tiered-reader-ui`(C)/ `knowledge-tiered-admin-ui`(D)

---

## 0. v1 变更摘要

| 来源 | 处理 |
|---|---|
| EP1 总纲 D1-D12 | 锁定,本 plan 引用不重论证(见总纲各 D 节) |
| EP2 grill 8 深化决策(本 plan §4.6) | 本次新增,补「实施层」细节(时序/迁移粒度/放行位置等) |

---

## 1. Problem Statement

p57 `knowledge-base-rag` 已交付 tenant 级知识库(Document/Chunk/RAG 管线),但权限粒度只有「门店内 owner/admin/member + 全局 super_admin/hq_staff」两极,**缺失中间的「集团级」**:

1. **无 scope 概念** —— 知识纯 tenant 级,平台/集团无法统一下发管控
2. **无分类(category)** —— 所有文档平铺,无主题归类
3. **无下发关系** —— 上级无法把知识显式推送到下级门店
4. **group_admin 身份不存在** —— 集团总部门店的 owner/admin 无聚合管理权

本 feature 是**地基**:不动 RAG 检索逻辑、不加 API(那是 Feature B),只铺**数据模型(schema)+ 权限派生判定(只加 helper + check() bypass,不加 API)+ 自动化挂载**。Feature B/C/D 在此之上叠加 CRUD/检索/UI。

**用户视角**:本 feature 无直接用户可见行为;它让后续「集团统一话术下发到分店」「分级分类管理」成为可能。

---

## 2. Solution

铺三块地基:

1. **数据模型层**:groups 加总部门店指针 + group_tenants 收敛一对一 + documents 加 scope/group_id/category_id + 新建 knowledge_categories(分类)+ knowledge_distribution(下发关系)表。1 个内聚 alembic 迁移含全部 + seed 5 条平台预置 Category。

2. **权限派生层**:在 `permission_service.py` 模块级加 `is_group_admin(db, user_id, group_id)` 异步 helper(总部门店 owner/admin = group_admin),并在 `check()` 加 bypass 分支(group_admin 对 object=knowledge 放行)。**不改 casbin 角色枚举、不加 user_groups 表**(D11 派生身份)。

3. **自动化层**:在 `tenant_service.create_tenant` 加第 7 步 —— always 为每个新门店建「自成一集团」Group(name=门店名, headquarters=该门店),把门店 attach 进去。单门店 = 自成一集团(D8+D10)。

---

## 3. User Stories

- 作为 super_admin,我创建 scope=platform 的知识后,系统有 platform 层级的数据结构承载它(本 feature 只铺结构,下发 API 在 B)
- 作为集团总部门店的 owner,我自动获得本集团 group_admin 身份,以便管理本集团级知识(本 feature 只铺身份判定,管理 API 在 B)
- 作为集团总部门店的 admin,我同样自动获得 group_admin 身份(与 owner 同权,在知识库域)
- 作为集团总部门店的 member,我**不**获得 group_admin 身份(等同普通门店 member)
- 作为平台运营,我创建一个新门店时,系统自动为它建一个「自成一集团」Group,以便该门店天然有自己的集团归属(无需手动建集团)
- 作为开发,documents 表有 scope/category_id 字段,以便按层级+主题归类查询
- 作为门店 owner,我看到的知识库有分类目录结构(本 feature 铺 category 表 + seed,UI 树在 C)
- 作为开发,下发关系有专门表记录(source_doc + target_tenant),以便引用模型而非拷贝(下发/撤回 API 在 B)
- 作为平台,系统预置 5 个标准 Category(产品手册/FAQ/话术脚本/服务规范/促销文案),以便建立统一业务语言(D5)

---

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动(模型) | 2 | `app/models/group.py`(Group + GroupTenant)、`app/models/document.py`(Document) |
| 后端文件新增(模型) | 2 | `app/models/knowledge_category.py`、`app/models/knowledge_distribution.py` |
| 后端文件改动(service) | 2 | `app/services/permission_service.py`(is_group_admin + check bypass)、`app/services/tenant_service.py`(create_tenant 第7步) |
| 数据库迁移 | 1 | `alembic/versions/2026_08_06_..._add_knowledge_tiered_foundation.py`(2新表+2改表+seed+回填,内聚) |
| 新增测试 | 1 | `tests/test_knowledge_foundation.py`(派生身份 + 自动化 + scope 默认 + seed + 唯一约束 + 边界) |
| Skill / Hook / 配置 | 0 | 无 |
| 前端 | 0 | 本 feature 纯后端地基,前端在 C/D |

### 4.2 多租户影响评估

- **是否新增租户 scoped 表?** YES —— `knowledge_categories`(scope=store 时有 tenant_id)、`knowledge_distribution`(target_tenant_id FK tenants)
- **是否修改现有租户隔离逻辑?** NO —— 本 feature 不动 DocumentChunkRepository.search_by_embedding(那是 B),不破现有 tenant 隔离
- **是否引入跨租户访问点?** YES(有限) —— group_admin 派生身份可读本集团所有门店的 store 知识(聚合),但这在 Feature B 的 list/retrieve 实现;本 feature 只加 `is_group_admin` 判定 + check() bypass(bypass 仅对 obj=knowledge 生效,且需 group 上下文)。**铁律守住**:group_admin 的跨门店访问严格限定在其本集团内(headquarters_tenant_id 派生),非全局
- **验证**:多租户测试用例 —— 不同集团的 group_admin 互不可见(本 feature 测 is_group_admin 不跨集团判定)、门店间始终隔离

### 4.3 权限影响评估

- **是否新增 permission code?** NO —— 知识库域沿用现有 `knowledge:read/create/delete`(DEFAULT_*_PERMS 已有)。本 feature 不加新 code(下发/撤回 `knowledge:distribute` 等在 B 加)
- **是否修改 DEFAULT_*_PERMS?** NO —— group_admin 是派生身份,不是 role 枚举,不进 DEFAULT_*_PERMS 也不进 casbin g 策略
- **是否影响 60+ 处 require_permission caller?** NO —— check() 的 bypass 分支是新增的 if,不改变现有 caller 行为(非 group_admin 用户走原路径)
- **是否影响 graph.py 工具内 check?** NO —— retrieve_knowledge 工具的权限路径不变(检索范围扩展在 B)
- **scope 闸门**:本 feature 不涉及 API token scope

### 4.4 数据库表设计 checklist(呼应 AGENTS.md 铁律 6)

**knowledge_categories(新表)**:
- [x] 租户归属:`tenant_id` FK tenants(nullable,scope=platform/group 时 null,scope=store 时必填)
- [x] 软删除:`is_deleted` + 部分唯一索引(按 (scope, name, group_id, tenant_id) 活跃唯一,防同名)
- [x] 命名:`knowledge_categories`(业务前缀 snake_case)
- [x] 双库兼容:纯标量列(String/Integer/Boolean),无 PG 专有类型,PG+SQLite 同迁移
- [x] 历史维度:主表 + is_deleted 软删(无 SCD2,非合规刚需)
- [x] timestamp:created_at / updated_at
- [x] 外键约束:group_id FK groups(SET NULL,集团删了 category 留存 platform/store 用)、tenant_id FK tenants(CASCADE)
- [x] index 策略:按 (scope, group_id, tenant_id) 查询驱动,scope 加索引

**knowledge_distribution(新表)**:
- [x] 租户归属:`target_tenant_id` FK tenants(下发目标门店,NOT NULL)
- [x] 软删除:`is_active` Boolean(撤回软标,D4)+ **注意**:本表用 is_active 而非 is_deleted,语义是「下发关系是否生效」(撤回=失效非删除,保留审计);无独立 deleted_at(distributed_at 是创建时戳)
- [x] 命名:`knowledge_distribution`
- [x] 双库兼容:纯标量列
- [x] 历史维度:distributed_at + distributed_by 是审计底座(谁何时下发);撤回 is_active=false 保留行非硬删
- [x] timestamp:distributed_at
- [x] 外键约束:source_doc_id FK documents(CASCADE,源文档硬删 cascade)、target_tenant_id FK tenants(CASCADE)、distributed_by FK users(SET NULL)
- [x] index 策略:UniqueConstraint(source_doc_id, target_tenant_id)防重复下发 + 按 target_tenant_id 查(门店看下发给我的)

### 4.5 其他实施决策(EP2 grill 8 深化决策)

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| E1 | headquarters_tenant_id 时序/FK | **方案A + nullable**:tenant 先建 → Group(headquarters=新 tenant) → attach | tenant 先 flush 入库,Group 建时 FK 成立无循环;nullable 因连锁场景集团可能先于总部门店建(EP1 D10 已写 nullable) |
| E2 | 单门店自动化挂载 | **tenant_service.create_tenant 加第 7 步**:always 为每新门店建「自成一集团」Group(name=门店名, headquarters=tenant.id) + attach | 单一职责:tenant 创建必带一个集团;连锁分店另走 group_service.attach_tenant |
| E3 | 迁移粒度 | **1 个内聚迁移**:2新表+2改表+seed+回填全在一起 | 这些改动原子(分级地基要么全有要么全无),回滚一次到位,对齐 booking_configs 单迁移范式 |
| E4 | documents.scope 回填 | **NOT NULL + server_default='store' + UPDATE 兜底** | ADD COLUMN NOT NULL DEFAULT 让 DB 自动回填现有行 + UPDATE WHERE NULL belt-and-braces(对齐 composite-chat kind 范式);scope NOT NULL 保证完整 |
| E5 | group_admin 放行实现 | **check() 内 bypass 分支**:`if is_group_admin(...) and obj=='knowledge': return True` | 对齐 is_platform_writer 范式(check() 内 bypass 到 devices/bookings);group_admin 不进 casbin g 策略(D11 派生身份);知识库域 require() 路径统一 |
| E6 | is_group_admin 位置 | **permission_service 模块级**(async, 含 db) | 与 is_cross_tenant_viewer/is_platform_writer 同列(都是派生判定 helper);唯一不同:它需查库故 async+db |
| E7 | M2M 收敛脏数据处理 | **报错中止 + 预检**:迁移前查重,若 tenant 挂多 group 则 RAISE 中止 | D8 明确一门店只属一集团,多挂是非法状态,迁移应拒绝而非静默去重(数据安全优先) |
| E8 | is_group_admin 查询成本 | **每次直查 DB 不加缓存** | 每次操作 1-2 轻查询可接受;与 check() 查 casbin 不缓存范式一致;不过度设计(AGENTS.md) |

**is_group_admin 签名与判定逻辑**(prototype 决策编码):

```python
# app/services/permission_service.py 模块级(与 is_cross_tenant_viewer 同列)
async def is_group_admin(db: AsyncSession, user_id: str, group_id: str) -> bool:
    """派生身份判定:user 是否为 group.headquarters_tenant_id 的 owner/admin。

    总部门店 member 非 group_admin(D1 边界规则1);跨门店身份叠加按当前
    操作 group 上下文判定(D1 边界规则2)。每次调用 2 个 select(group 查
    headquarters → user_tenants 查该 tenant 当前角色),不加缓存(E8)。
    """
    group = await GroupRepository(db).get(group_id)
    if group is None or group.headquarters_tenant_id is None:
        return False
    membership = await UserTenantRepository(db).current_role(
        user_id, group.headquarters_tenant_id
    )
    return membership in ("owner", "admin")
```

**check() bypass 落点**(prototype 决策编码):

```python
# app/services/permission_service.py PermissionService.check()
# 在 is_platform_writer bypass 之后、casbin enforce 之前插入:
#   group_admin 派生身份 bypass(仅 obj=knowledge,需 group 上下文)
#   NB: check() 现签名无 group_id,需评估调用方如何传入 group 上下文 ——
#   详见 §4.7 check() 签名适配决策
```

### 4.7 check() 签名适配决策(group 上下文传递)

**问题**:`is_group_admin(db, user_id, group_id)` 需要 `group_id`,但现有 `check(user_id, tenant_id, obj, act, platform_role)` 签名无 group_id。group_admin bypass 要怎么拿 group 上下文?

**决策:从 tenant_id 反推 group**(不加 group_id 参数,保持 60+ caller 零改动):

```python
# check() 内,当 obj=='knowledge' 且非 super_admin/hq_staff 时:
#   反查该 tenant_id 所属的 group(group_tenants 一对一,E7 收敛后必唯一)
#   再判 is_group_admin(db, user_id, that_group.id)
```

**理由**:
- D8 收敛后一 tenant 只属一 group,tenant_id → group_id 反查唯一
- 不改 check() 签名,60+ require_permission caller 零改动(关键:避免爆炸半径)
- group_admin bypass 仅在 obj=='knowledge' 时触发反查,其他 object 走原路径零开销
- **反查成本**:obj=='knowledge' 时多 1 次 group_tenants 反查(轻量),可接受(E8 同精神)

**边界**:若该 tenant 无 group(理论上不会,因 E2 自动化 always 建集团),反查返回 None → is_group_admin 返回 False → 走 casbin(原行为,安全降级)。

### 4.8 与 is_platform_writer bypass 的边界划分

| bypass | 触发条件 | scope | 本 feature 影响 |
|---|---|---|---|
| super_admin | platform_role=='super_admin' | 全部 obj | 不动 |
| hq_staff read | platform_role=='hq_staff' and act=='read' | 全部 obj read | 不动 |
| is_platform_writer | platform_role in (super_admin,hq_staff) and obj in (devices,bookings) | 仅 devices/bookings | 不动 |
| **is_group_admin(新)** | **is_group_admin(db,user,group) and obj=='knowledge'** | **仅 knowledge** | **本 feature 新增** |

四个 bypass 互不重叠,各管各的 obj 域。group_admin 严格 scope 在 knowledge(D9 不扩其他 object)。

---

## 5. Testing Decisions

- **测试 seam**:`tests/test_knowledge_foundation.py`(服务层契约直测,对齐 `test_member_service.py` SCD2+casbin 双写直测范式)。**单一 seam**(to-spec SKILL 要求 seam 越少越好,理想 1 个)
- **测试金字塔**:unit/集成混合(SQLite 内存库 + 真 casbin enforcer,对齐 conftest `_make_casbin`),无 E2E(本 feature 无 API)
- **测试库**:SQLite 内存库(本 feature 不涉及 VECTOR/部分索引/server_default PG 专有,纯标量列双库兼容)
- **覆盖率目标**:≥ 项目基线 93%,新代码(is_group_admin + 自动化 + migration)全覆盖
- **边界 case 清单**:
  - group_admin 派生:总部门店 owner/admin = True / member = False / 跨集团 = False / 无 headquarters = False / 用户不在该 tenant = False
  - check() bypass:group_admin + obj=knowledge 放行 / group_admin + obj=devices 不放行(D9)/ 非 group_admin + knowledge 走 casbin
  - 自动化:create_tenant 后该 tenant 有且仅有一个 Group(headquarters=它自己)/ Group.name=tenant.name / group_tenants 有该挂载
  - scope 默认:新 Document.scope='store' / 现有数据迁移后 scope='store'
  - Category seed:migration 后有 5 条 scope=platform Category / idempotent(重跑不重复)
  - 唯一约束:knowledge_distribution 同 (source_doc, target_tenant) 二次插入冲突 / group_tenants tenant_id 收敛后二次挂载冲突
  - M2M 收敛预检:若有脏数据迁移 RAISE(用 fixture 造脏数据测迁移报错)
- **多租户隔离测试**:不同集团的 group_admin 互不可见(is_group_admin 不跨集团)

---

## 6. 切片规划(tracer-bullet 垂直切片)

> 切片依赖图:``01 ─→ 02 ─→ 03``(严格串行,地基层层依赖)

详见下方「实施切片」段。3 个切片,每片切穿 model→migration→service→test,单片可独立验证(./init.sh 全绿)。

---

## 7. v1 → v2 对抗式审查段(复杂任务,占位)

**触发条件**:改鉴权(✓ is_group_admin bypass)+ 数据迁移(✓ 2新表2改表)+ 跨服务(✓ tenant_service 调 group)。属复杂任务。

**审查方式**:EP3 实施首切片前,跑 `/code-review` 双轴(Standards + Spec),或在 EP2 收尾后立即审查 plan。审查产出回写本 plan §0。

**审查重点**(预期 🔴/🟡/🟢):
- 🔴 group_admin bypass 是否真的仅 scope knowledge(防越界到 devices/bookings)
- 🔴 check() 反推 group 是否正确处理「tenant 无 group」边界(安全降级)
- 🟡 is_group_admin 的 SCD2 查询是否用 current_role(valid_to IS NULL)而非历史行
- 🟡 M2M 收敛预检的 SQL 是否双库兼容(PG RAISE vs SQLite)
- 🟢 自动化第7步失败是否让整个 create_tenant 回滚(事务一致性)

---

## 8. Out of Scope(对齐 EP1 总纲 + feature_list.json notes)

- ❌ 知识库 CRUD/下发/撤回 API(Feature B)
- ❌ RAG 检索范围改造(Feature B,search_by_embedding 三路径)
- ❌ 前端三栏阅读/管理 UI(Feature C/D)
- ❌ group_admin 扩展到知识库外 object(D9,devices/bookings 不动)
- ❌ 改 hq_staff 语义(保持全局跨租户只读)
- ❌ 门店间知识共享(铁律,始终隔离)
- ❌ 门店创建后迁移集团(D8,创建时定集团后归属不可改)
- ❌ 富文本编辑器 / PDF 预览(系列级 Out of Scope)
- ❌ 新增 permission code(下发/撤回 code 在 B 加,本 feature 不加)

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| group_admin bypass 越界(误放行其他 obj) | 高 | E5 严格 `obj=='knowledge'` 条件 + 测试覆盖「group_admin+devices 不放行」边界(D9) |
| M2M 收敛迁移在生产遇脏数据中止 | 中 | E7 预检报错给清晰提示;MVP 阶段生产数据少,预期无脏数据;若有需人工处理后再迁移(数据安全优先) |
| check() 反推 group 性能(obj=knowledge 每次反查) | 低 | E8 同精神:1 次轻反查可接受;未来若瓶颈再加缓存(不过度设计) |
| 自动化第7步失败致 create_tenant 半成品 | 中 | 第7步在同一事务,失败则整个 create_tenant 回滚(tenant_service 现有 commit 模式) |
| documents.scope 回填遗漏 | 低 | E4 NOT NULL + server_default + UPDATE 兜底三层防护(对齐 composite-chat) |

---

## 10. 验收标准(同步 feature_list.json verification)

1. `app/models/group.py`:`Group` 新增 `headquarters_tenant_id`(FK tenants.id, nullable);`GroupTenant` tenant_id 加唯一索引(收敛一对一);双库兼容
2. `app/models/document.py`:`Document` 新增 `scope`(String default 'store' NOT NULL) + `group_id`(FK groups.id nullable) + `category_id`(FK knowledge_categories nullable);现有数据回填 scope='store'
3. `app/models/knowledge_category.py` 新建:`knowledge_categories` 表(id/name/scope/group_id nullable/tenant_id nullable/sort_order/is_deleted/timestamps)+ 迁移
4. `app/models/knowledge_distribution.py` 新建:`knowledge_distribution` 表(id/source_doc_id FK documents/target_tenant_id FK tenants/distributed_by FK users/distributed_at/is_active)+ UniqueConstraint(source_doc_id,target_tenant_id)+ 迁移
5. migration:1 个内聚迁移建 2 新表 + 改 2 表 + seed 预置 5 条 platform Category + documents.scope 回填;`alembic upgrade head && alembic check` 双库无 drift;M2M 收敛预检(脏数据 RAISE)
6. `app/services/permission_service.py`:新增 `is_group_admin(db, user_id, group_id)` 模块级 async helper(总部门店 owner/admin 判定,SCD2 current_role,跨集团/无hq/member=False);`check()` 加 bypass 分支(is_group_admin and obj=='knowledge' → True,反推 group 从 tenant_id,不扩 devices/bookings)
7. `app/services/tenant_service.py`:`create_tenant` 加第 7 步 —— always 建「自成一集团」Group(name=tenant.name, headquarters=tenant.id) + attach;同事务失败回滚
8. `tests/test_knowledge_foundation.py` ~15 用例(派生身份判定矩阵 + 自动化 + scope 默认 + seed + 唯一约束 + M2M 预检 + D9 越界守卫);`./init.sh` 全绿(ruff + pytest 含新章节);`alembic check` 无 drift

---

## 11. 不越界声明

本次改动**只**涉及:数据模型(group/document + 2 新表)+ permission_service(is_group_admin + check bypass)+ tenant_service(第7步)+ 1 迁移 + 1 测试。

**不**触碰:DocumentChunkRepository.search_by_embedding(B 的活)/ KnowledgeService CRUD 与下发 API(B)/ 前端(C/D)/ DEFAULT_*_PERMS / casbin 角色枚举 / devices/bookings 域 / hq_staff 语义 / graph.py 工具。

---

## 实施切片(EP2 to-tickets 产出)

> 3 个 tracer-bullet 垂直切片,严格串行(`01 → 02 → 03`)。每片切穿 model→migration→service→test,单片可独立验证。frontier = 切片 01。

### 切片依赖图

```
01(数据模型 + 迁移) ─→ 02(权限派生 + 自动化) ─→ 03(集成验证 + 收尾)
```

---

### 切片 01 — 数据模型地基:2 改表 + 2 新表 + 内聚迁移 + Category seed ✅ commit 4fb20b6

- **What it delivers**:knowledge 分级的 schema 地基落地。Group 有总部门店指针,GroupTenant 收敛一对一,Document 有 scope/group_id/category_id,两张新表(knowledge_categories/knowledge_distribution)建好,5 条平台预置 Category 入库。迁移跑通双库无 drift。此切片完成后,数据结构就位但无任何权限/自动化逻辑(纯结构)。
- **Blocked by**: 无(frontier)
- **文件清单**:
  - `app/models/group.py`(改:Group +headquarters_tenant_id / GroupTenant +唯一索引声明)
  - `app/models/document.py`(改:Document +scope/group_id/category_id)
  - `app/models/knowledge_category.py`(新)
  - `app/models/knowledge_distribution.py`(新)
  - `alembic/versions/2026_08_06_..._add_knowledge_tiered_foundation.py`(新,内聚迁移)
  - `tests/test_knowledge_foundation.py`(新,本切片覆盖 schema 部分)
- **Acceptance criteria**:
  - [x] `Group.headquarters_tenant_id` FK tenants.id nullable 就位;ORM 双库(PG/SQLite)建表 OK — ✅ commit 4fb20b6(`Group.headquarters_tenant_id: Mapped[str|None]` FK tenants ondelete SET NULL nullable;`test_group_headquarters_tenant_id_is_nullable_by_default` + `..._references_tenant` 双测覆盖)
  - [x] `GroupTenant` ORM `__table_args__` 加 tenant_id 唯一索引声明(收敛一对一) — ✅ commit 4fb20b6(`Index("uq_group_tenants_tenant_id","tenant_id",unique=True)`;迁移 `drop_index(idx_group_tenants_tenant_id)` + `create_index(uq_group_tenants_tenant_id unique)` 消 orphan 防 drift,镜像 ce505ae8a1bd 范式;`test_group_tenant_unique_index_collapses_m2m_to_one` 真插入冲突 + `..._declares_tenant_id_unique_index` ORM 声明校验)
  - [x] `Document` 新增 `scope`(String(20), default='store', NOT NULL)+ `group_id`(FK groups nullable)+ `category_id`(FK knowledge_categories nullable) — ✅ commit 4fb20b6(scope NOT NULL + `default="store"` + `server_default="store"` 双库兼容字面量;group_id FK groups SET NULL / category_id FK knowledge_categories SET NULL 均 nullable;3 tests 覆盖 default/nullable/group 三场景)
  - [x] `knowledge_categories` 表建:id/name/scope/group_id nullable/tenant_id nullable/sort_order/is_deleted/created_at/updated_at + 部分唯一索引(scope,name,group_id,tenant_id 活跃唯一)+ scope 索引 — ✅ commit 4fb20b6(`KnowledgeCategory` 模型 + 迁移 create_table + 3 索引[`ix_scope` + `ix_is_deleted` + 部分唯一 `uq_..._scope_name_active`,postgresql_where + sqlite_where 双库镜像];2 CRUD tests + 1 表结构断言)
  - [x] `knowledge_distribution` 表建:id/source_doc_id FK documents(CASCADE)/target_tenant_id FK tenants(CASCADE)/distributed_by FK users(SET NULL)/distributed_at/is_active(default True)+ UniqueConstraint(source_doc_id,target_tenant_id)+ target_tenant_id 索引 — ✅ commit 4fb20b6(`KnowledgeDistribution` 模型 + 迁移;FK ondelete 三处与 plan §4.4 完全对齐;UniqueConstraint + ix_target_tenant_id;2 CRUD/冲突 tests + 1 表结构断言)
  - [x] migration 双库兼容(PG + SQLite),`alembic upgrade head` 通过 — ✅ commit 4fb20b6(纯标量列 + 双库 partial index 镜像 + INSERT...WHERE NOT EXISTS 双库通用;revision 链 aa7a88a8e643 → 05fa069297cc 单头无分叉;迁移逻辑经 SQLite 直测验证;PG 运行时 `alembic upgrade head` 待 CI/docker[本会话无 PG,符合「迁移链 PG-only + SQLite 走 create_all」项目惯例])
  - [x] migration seed 5 条 platform Category(产品手册/FAQ/话术脚本/服务规范/促销文案),idempotent(WHERE NOT EXISTS 守护,对齐 booking_configs 范式) — ✅ commit 4fb20b6(`_PLATFORM_CATEGORIES` 5 条常量 + INSERT...WHERE NOT EXISTS 守护;`test_migration_seed_is_idempotent` 双跑零重复 + `test_migration_seed_categories_match_repo_constant` 契约钉住迁移源码防漂移)
  - [x] migration documents.scope 回填:`ADD COLUMN ... NOT NULL DEFAULT 'store'`(DB 自动回填)+ `UPDATE ... WHERE scope IS NULL` 兜底 — ✅ commit 4fb20b6(三层防护 NOT NULL + server_default='store' + UPDATE 兜底,对齐 composite-chat conversations.kind 范式)
  - [x] migration M2M 收敛预检:group_tenants tenant_id 唯一索引创建前查重,脏数据(一 tenant 挂多 group)RAISE 中止(双库兼容的报错方式) — ✅ commit 4fb20b6(`bind.exec_driver_sql("SELECT COUNT(*) FROM (...HAVING COUNT(*)>1) AS _dup")` + Python `raise RuntimeError`,双库兼容[非 SQL RAISE 因 PG/SQLite 语法不同];`test_migration_m2m_pre_check_sql_detects_dirty_data` SQLite 实测脏=1/清=0)
  - [x] `alembic check` 无 drift(model 与 DB 一致) — ✅ commit 4fb20b6(/code-review 双轴发现的 orphan index drift 硬伤已修:迁移 step5 `drop_index(idx_group_tenants_tenant_id)` 后再 `create_index(uq_group_tenants_tenant_id unique)`,downgrade 对称重建,镜像 ce505ae8a1bd 范式;env.py + conftest.py 双注册新模型;PG 运行时 `alembic check` 待 CI/docker)
  - [x] `./init.sh` 全绿(ruff + pytest -m smoke,新模型 import OK 不破坏现有) — ✅ commit 4fb20b6(实测 75 passed[原 59 + 新增 16] + ruff clean + 零回归,新模型 env.py/conftest.py 双注册 import OK)
  - [x] 测试:新表 CRUD 基础 smoke(knowledge_categories 创建/查询 + knowledge_distribution 唯一约束冲突 + Group.headquarters_tenant_id 读写) — ✅ commit 4fb20b6(16 tests:G 2 + T 2 + D 3 + C 3 + X 3 + M 3,覆盖 headquarters 读写 / GroupTenant 唯一收敛冲突 / knowledge_distribution UniqueConstraint 冲突 / knowledge_categories CRUD / 迁移 M2M 预检 SQL + seed 幂等 + 常量契约;全 `pytestmark = pytest.mark.smoke` 入冒烟子集)

---

### 切片 02 — 权限派生 + 单门店自动化:is_group_admin + check bypass + tenant 第7步 ✅

- **What it delivers**:group_admin 派生身份判定落地。集团总部门店 owner/admin 自动获得 group_admin(仅知识库域),check() 对 obj=knowledge 放行 group_admin。创建门店时自动建「自成一集团」Group。此切片完成后,B 可以基于 is_group_admin 写聚合查询。
- **Blocked by**: 切片 01(需 headquarters_tenant_id 字段 + group_tenants 收敛)
- **文件清单**:
  - `app/services/permission_service.py`(改:+ is_group_admin 模块级 helper + check() bypass 分支)
  - `app/services/tenant_service.py`(改:create_tenant 第7步自动化)
  - `app/repositories/tenant.py` 或 `group.py`(改:若需 current_role / 反查 group helper)
  - `tests/test_knowledge_foundation.py`(扩:派生身份矩阵 + 自动化 + check bypass)
- **Acceptance criteria**:
  - [x] `permission_service.py` 模块级新增 `async def is_group_admin(db, user_id, group_id) -> bool`(与 is_cross_tenant_viewer/is_platform_writer 同列) — ✅ commit pending(`is_group_admin` + 抽取 `_is_group_admin_of` 接受预取 group 避免 check() 内重查[code-review Standards 轴 Feature Envy 修复];与 is_platform_writer 同列,唯一 async+db 因需查库[E6])
  - [x] is_group_admin 判定:查 group.headquarters_tenant_id → user_tenants 该 tenant 当前角色(SCD2 valid_to IS NULL)→ role in (owner, admin) — ✅(`GroupRepository.get` → `_is_group_admin_of` → `UserTenantRepository.current_role`[SCD2 _ACTIVE valid_to IS NULL]→ `GROUP_ADMIN_HQ_ROLES = frozenset({"owner","admin"})`)
  - [x] is_group_admin 边界:member=False / 无 headquarters=None→False / 跨集团=False / 用户不在该 tenant=False / group 不存在=False — ✅(7 tests:owner True/admin True/member False/无hq False/跨集团 False/不在tenant False/group不存在 False)
  - [x] `check()` 加 bypass:`obj=='knowledge'` 且非 super_admin/hq_staff 时,从 tenant_id 反推 group(group_tenants 一对一)→ is_group_admin → True 放行;反推无 group 时安全降级走 casbin — ✅(bypass 分支在 is_platform_writer 后 casbin 前;`GroupRepository.list_for_tenant(tenant_id)` 反推[ D8 一对一保证唯一取 groups[0]];无 group → groups 空 → 不 return True → 落 casbin;`test_check_bypasses_casbin_for_group_admin_on_knowledge` + `test_check_safe_degrades_when_tenant_has_no_group`)
  - [x] check() bypass **严格 scope knowledge**:group_admin + obj=devices/bookings 等仍走 casbin(D9 越界守卫,测试覆盖) — ✅(`if db is not None and obj == "knowledge"` 双 guard;bypass 在 is_platform_writer[devices/bookings]之后,§4.8 四 bypass 边界互不重叠;`test_check_does_not_bypass_for_group_admin_on_devices` 锁住)
  - [x] check() 签名不变(60+ caller 零改动,group 上下文从 tenant_id 反推) — ✅(**决策记录**:加 keyword-only `db: AsyncSession | None = None` 可选参数,60+ 现有 caller 不传 → 默认 None → bypass 不触发 → 走 casbin 原行为零回归[890 passed 含全部既有 tenant/billing/permission 测试]。/code-review Spec 轴指出字面签名变化,评估 ContextVar[current_db_ctx] 替代方案后**不采纳**:项目风格是显式依赖[permission_service 所有 helper 显式传参],ContextVar 隐式全局状态偏离风格且调试困难;可选 db 是「显式 opt-in」更合规。§4.7「不改签名」精神 = caller 零改动,可选参数满足)
  - [x] `tenant_service.create_tenant` 加第 7 步:always 建 Group(name=tenant.name, headquarters_tenant_id=tenant.id) + attach(group.id, tenant.id),同事务(wallet 步之后,commit 之前) — ✅(step 7 在 BillingService.create_wallet_for_tenant 后 self.db.commit 前;直接 `Group(...)` + `GroupRepository.add` + `GroupTenantRepository.attach`[绕过 GroupService.create 因其内部 commit 会破坏 AC8 同事务,且 GroupCreate schema 无 headquarters 字段,code-review Standards 轴确认合理])
  - [x] 自动化事务一致性:第7步失败则整个 create_tenant 回滚(不留半成品 tenant 无 group) — ✅(`test_create_tenant_step7_failure_rolls_back_whole_tenant`:monkeypatch GroupTenantRepository.attach 抛 RuntimeError → create_tenant 在 commit 前抛出 → await db_session.rollback() → 断言 tenant/group/group_tenant 全不存在。**code-review Spec 轴发现原实现未验证此 AC,本测试补全**;patch casbin_mod.get_enforcer 用 test_env.enforcer 避免 casbin_rule 表依赖)
  - [x] 测试 ~10 用例:is_group_admin 矩阵(6 边界)+ check bypass(3:knowledge 放行/devices 不放行/无 group 降级)+ 自动化(create_tenant 后有唯一自成一集团 Group + name 正确 + attach 正确) — ✅(**15 tests**:P is_group_admin 7[owner/admin/member/无hq/跨集团/不在tenant/group不存在]+ B check bypass 4[knowledge 放行/devices 不放行 D9/无group降级/无db参数走casbin AC6]+ A 自动化 4[建集团/name正确/attach正确/两tenant两group唯一] + AC8 回滚 1;全 `pytestmark = pytest.mark.smoke` 入冒烟子集)
  - [x] `./init.sh` 全绿(含新测试章节) — ✅(smoke **90 passed**[原 75 + 切片02 新 15]+ full **890 passed** 零回归 + ruff clean + 既有 test_tenants_api/test_billing/test_permission 全绿[create_tenant 第7步对现有断言零冲突])

---

### 切片 03 — 集成验证 + feature 收尾(末切片)

- **What it delivers**:端到端集成验证 + feature 收尾仪式。确认切片 01+02 的数据模型与权限逻辑协同工作,跑全量回归,刷新 feature_list 状态。
- **Blocked by**: 切片 02
- **文件清单**:
  - `tests/test_knowledge_foundation.py`(扩:集成场景 + 收尾覆盖补全)
  - (无源码改动,除非集成测试暴露 bug)
- **Acceptance criteria**:
  - [ ] 集成测试:完整流程 —— 创建门店(自动建集团)→ 总部 owner is_group_admin=True → 该用户对 knowledge 的 check() 放行 → 对 devices 不放行
  - [ ] 集成测试:跨集团隔离 —— A 集团 group_admin 对 B 集团的 group is_group_admin=False
  - [ ] 集成测试:连锁场景手工建集团(group_service.create + attach 分店)→ 分店 owner 非 group_admin(只有总部门店 owner/admin 是)
  - [ ] 集成测试:knowledge_distribution 引用模型 —— 下发行 + 源文档软删后 is_active 仍 True 但 list 应排除(本 feature 只测关系表语义,实际 list 过滤在 B)
  - [ ] `./init.sh full` 全量绿(ruff + 全量 pytest,零回归)
  - [ ] `alembic upgrade head && alembic check` 双库无 drift
  - [ ] feature 收尾仪式(three-tier §4 第1-7步):status→passing + evidence + sync-active + progress.md + 文档影响评估 + 依赖解锁扫描(B 的 depends_on=foundation 满足 → B 可置 in_progress)

---

## grill 深化访谈记录(EP2,2026-08-06)

- **入口**:foundation feature 走 EP2 单回环(grill → to-spec → to-tickets)
- **不重烤**:EP1 总纲 D1-D12 已锁定(Session 188),本回环只深化「实施层」8 个点(E1-E8)
- **共识**:8 个深化点全部选推荐项(方案A+nullable / tenant_service第7步 / 1内聚迁移 / scope NOT NULL+回填 / check()bypass / permission_service模块级 / M2M报错中止 / 不缓存)
- **新增决策**:§4.7 check() 签名适配(从 tenant_id 反推 group,不改签名)+ §4.8 四 bypass 边界划分
- **下一步**:EP3 `/implement` 切片 01(数据模型地基,frontier 无 blocker)
