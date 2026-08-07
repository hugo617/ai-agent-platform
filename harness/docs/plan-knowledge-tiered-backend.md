# 计划:知识库分级 Feature B —— 后端 CRUD + 下发 API + 检索改造

> **id**: `knowledge-tiered-backend`
> **状态**: draft v1(EP2 plan 自检后 → in_progress)
> **优先级**: 89(feature_list.json)
> **创建日期**: 2026-08-06
> **承接**: [`plan-knowledge-tiered-overview.md`](plan-knowledge-tiered-overview.md)(EP1 总纲,D1-D12 决策锁定)+ [`plan-knowledge-tiered-foundation.md`](plan-knowledge-tiered-foundation.md)(Feature A ✅ passing,数据模型 + 权限派生地基已交付)
> **下游**: `knowledge-tiered-reader-ui`(C)/ `knowledge-tiered-admin-ui`(D),均 depends_on 本 feature

---

## 0. v1 变更摘要

| 来源 | 处理 |
|---|---|
| EP1 总纲 D1-D12 | 锁定,本 plan 引用不重论证(见总纲各 D 节) |
| foundation 已交付 | 数据模型(Group.headquarters_tenant_id / GroupTenant 一对一收敛 / Document.scope+group_id+category_id / knowledge_categories / knowledge_distribution 五表)+ 权限派生(`is_group_admin` + `check()/require()` 加可选 `db` 参数 + obj=='knowledge' bypass)已就位。**本 feature 不重建,只消费** |
| EP2 grill 8 深化决策(本 plan §4.5) | 本次新增,补「实施层」细节(bypass 接通 / list 三路径落点 / 检索参数化 / 下发 API 形态 / 权限码 / Category 权限 / 一致性 / 切片粒度) |

---

## 1. Problem Statement

foundation Feature A 已铺好数据模型 + 权限派生地基,**但 group_admin 派生身份在 knowledge API 层目前是「死的」** —— `check()/require()` 虽加了可选 `db` 参数让 bypass 能触发,但 `KnowledgeService` 现有 6 处 `require()` 调用全没传 `db`,bypass 条件 `db is not None` 不满足,group_admin 调 knowledge API 仍走 casbin(被拒)。

同时,p57 `knowledge-base-rag` 交付的 RAG 管线是纯 tenant 级(`search_by_embedding` 只按 tenant_id 过滤),无法承载分级管理的三大核心诉求:

1. **list 按角色三路径过滤**:门店应看到「本店 store + 上级显式下发给我」;group_admin 应聚合看「本集团 group + 本集团所有门店 store」;super_admin 看全局。当前 list 只查本店,上级下发形同虚设。
2. **下发/撤回 API 缺失**:`knowledge_distribution` 表建好了,但没有端点能写入(下发)或软标失效(撤回)。集团统一管控门店的落地链路断了。
3. **Category CRUD 缺失**:`knowledge_categories` 表建好了 + 5 条平台预置 seed 入库,但没有端点让各级管理员扩展本级 Category,下级也无法 list 可见的上级 Category。

**用户视角**:本 feature 无直接前端,它让「集团统一话术下发到分店」和「分级分类管理」在后端真正跑通,为 Feature C(前端阅读)和 D(前端管理)提供 API 基石。

---

## 2. Solution

铺四块后端能力(都是消费 foundation 已建的表/权限,纯加法 + 改造,不重建地基):

1. **list/检索三路径改造**(核心):`DocumentRepository` 加 `list_visible_for(role, tenant_id, group_id, ...)` 封装三路径 WHERE(守「租户过滤在 Repository 层」铁律);`search_by_embedding` 加 `include_distributed` + 角色上下文参数,门店检索 LEFT JOIN distribution(只增不减,零负向回归),debug 页保持纯本店。
2. **group_admin bypass 接通**:`KnowledgeService` 6 处 `require()` 加 `db=self.db`,让 foundation 留的 bypass 真正生效(group_admin 在 knowledge 域放行)。
3. **下发/撤回 API**:`POST /knowledge/{doc_id}/distribute`(target_tenant_ids 或 target_group_id 二选一)+ `DELETE /knowledge/distribute/{dist_id}`(撤回=软删 is_active=false)。新权限码 `knowledge:distribute`(seed owner/admin,group_admin 经 bypass 放行)。
4. **Category CRUD + scope 分级**:`GET/POST/PUT/DELETE /knowledge/categories`,service 层按 payload.scope 校验角色(platform→super_admin / group→is_group_admin / store→本店 owner/admin),list 可见 = platform 全部 + 本集团 group + 本店 store。

---

## 3. User Stories

**下发/撤回(集团统一管控核心)**
- 作为 super_admin,我创建 scope=platform 的知识后,可下发到指定门店列表或整个集团,以便平台统一话术触达分店
- 作为 super_admin,我可撤回已下发的知识(软删 is_active=false 保留审计),以便门店侧该文档即时消失
- 作为集团总部门店的 owner(group_admin 派生),我创建 scope=group 的知识后,可下发到本集团分店,以便集团统一管控
- 作为 group_admin,我可撤回本集团级知识的下发关系
- 作为开发,下发到整个集团时,service 层自动展开成该集团所有 tenant_id 批量插 distribution 行(我不用前端逐个选)
- 作为平台运维,源文档被软删(Document.is_deleted=true)时,所有引用该文档的下发关系自动失效(门店 list/retrieve 同时排除),无需手动清理下发关系

**list 三路径(跨 scope 可见性)**
- 作为门店 owner/admin/member,我 list 知识时看到 = 本店自建(scope=store)+ 上级显式下发给我的,无需感知下发关系
- 作为 group_admin,我 list 知识时看到本集团级(scope=group)+ 本集团所有门店的 store 级(聚合管理视角)
- 作为 super_admin,我 list 知识时看到全部(全局无过滤)
- 作为门店 owner,我看不到其他门店的自建知识(门店间隔离铁律不破)
- 作为门店 owner,我看不到未显式下发给我的上级知识(严格显式下发语义 D3)

**检索三路径(RAG 兑现)**
- 作为门店 agent,我的 retrieve_knowledge 检索范围 = 本店 store + 上级下发给我的,集团下发的话术我能用
- 作为门店 owner,我在 retrieve 调试页检索时只看本店纯数据(include_distributed=False),避免下发数据干扰调试
- 作为门店 owner,门店视角检索对我「只增不减」(本店原命中保留 + 新增下发命中),现有 retrieve 行为零负向回归

**Category CRUD(预置+扩展 D5)**
- 作为 super_admin,我可创建 scope=platform 的 Category,以便建立全局统一业务语言
- 作为 group_admin,我可创建 scope=group 的 Category(补充本集团特有主题,如「理疗话术」)
- 作为门店 owner,我可创建 scope=store 的 Category(本店本地需求)
- 作为门店 owner,我 list Category 时看到 = platform 全部 + 本集团 group + 本店 store(下级能选用上级)
- 作为门店 member,我只能 read Category(不能创建/删除)

**权限边界(D9 守卫)**
- 作为 group_admin,我对 knowledge 域有管理权,但对 devices/bookings 等其他 object 无特殊权(派生身份仅知识库域)
- 作为平台运维,group_admin 派生身份不扩到其他 object,casbin 策略零回归

---

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动(service) | 1 | `app/services/knowledge_service.py`(6 处 require 加 db + retrieve/list 三路径调用改造) |
| 后端文件新增(service) | 1 | `app/services/category_service.py`(Category CRUD + scope 权限) |
| 后端文件改动(repository) | 1 | `app/repositories/document.py`(list_visible_for + search_by_embedding 三路径) |
| 后端文件新增(repository) | 1 | `app/repositories/knowledge_category.py`(Category repo,可选:若逻辑简单可内联 service) |
| 后端文件改动(repository) | 1 | `app/repositories/knowledge_distribution.py`(新:distribution repo,含 list_for_target/active filter) |
| 后端文件改动(api) | 1 | `app/api/v1/knowledge.py`(+ 下发/撤回端点 + Category CRUD 端点) |
| 后端文件改动(schema) | 1 | `app/schemas/document.py`(+ DistributeRequest / KnowledgeCategoryCreate/Read/Update / DocumentRead 加 scope/group_id/category_id) |
| 后端文件改动(agent) | 1 | `app/agents/graph.py`(retrieve_knowledge 适配新检索范围 + docstring 更新) |
| 后端文件改动(permission) | 1 | `app/services/permission_service.py`(DEFAULT_OWNER/ADMIN_PERMS 加 knowledge:distribute code + OBJ_CN/ACT_CN 加中文标签) |
| 数据库迁移 | 1 | `alembic/versions/2026_08_0X_..._add_knowledge_distribute_perm.py`(seed 新 permission code knowledge:distribute 到 owner/admin + casbin resync;**不建表不改列**,纯 permission seed) |
| 新增测试 | 1 | `tests/test_knowledge_backend.py`(三路径 list + 检索 + 下发/撤回 + Category CRUD + bypass 接通 + 跨租户隔离 + D9 越界守卫) |
| Skill / Hook / 配置 | 0 | 无 |
| 前端 | 0 | 本 feature 纯后端,前端在 C/D |

### 4.2 多租户影响评估

- **是否新增租户 scoped 表?** NO —— 表已在 foundation 建好(knowledge_categories / knowledge_distribution),本 feature 只读写
- **是否修改现有租户隔离逻辑?** YES —— `DocumentRepository.list_for_tenant` 当前只查本店;本 feature 新增 `list_visible_for` 按角色三路径。**关键**:门店视角永远包含「本店 store」(只增不减),跨租户访问仅限 group_admin 聚合(本集团内)和 super_admin(全局),门店间始终隔离(铁律)
- **是否引入跨租户访问点?** YES(受控) —— ① 门店读「上级下发给我」(通过 knowledge_distribution.target_tenant_id = 本店 join,只读下发给自己的,不能读其他门店);② group_admin 读本集团所有门店 store 级(通过 group_id 反查 group_tenants 取 tenant_ids,严格限定本集团);③ super_admin 全局。三路径都在 Repository 层 WHERE 显式约束,不靠 service「记得加过滤」
- **验证**:多租户测试用例 —— 门店 A 看不到门店 B 的 store 文档 / 门店 A 看不到未下发给自己的 platform 文档 / group_admin A 看不到 group B 的文档 / super_admin 看全部

### 4.3 权限影响评估

- **是否新增 permission code?** YES —— `knowledge:distribute`(下发/撤回用,撤回是下发的逆操作,复用同 code)。只 seed 给 owner/admin(member 无,门店 member 不能下发)
- **是否修改 DEFAULT_*_PERMS?** YES —— `DEFAULT_OWNER_PERMS` + `DEFAULT_ADMIN_PERMS` 加 `("knowledge", "distribute")`。member 不加
- **是否影响 60+ 处 require_permission caller?** NO —— 现有 knowledge 端点 read/create/delete 的 require 不变;新增的 distribute/categories 端点是新 require 调用点,不改老 caller
- **是否影响 graph.py 工具内 check?** YES(改造,非破坏) —— `retrieve_knowledge` 工具的 check 路径不变(仍 `check("knowledge", "read")`),但检索范围扩展(本店+下发)。group_admin bypass 经 G1 接通后,group_admin 调 retrieve_knowledge 也能放行(但 agent 工具主要门店用,bypass 是顺带生效)
- **scope 闸门**:本 feature 不涉及 API token scope(knowledge 端点沿用现有 token scope 收敛,不新增 scope 类型)
- **group_admin bypass 接通(G1)**:`KnowledgeService` 6 处 `require(...)` 调用加 `db=self.db`。这是 foundation 切片02 为此预留的设计(可选 db 参数),本 feature 补上「接通」这最后一步。零回归:非 group_admin 用户传 db 也走 casbin(bypass 条件 `is_group_admin and obj=='knowledge'` 不满足)

### 4.4 数据库表设计 checklist(呼应 AGENTS.md 铁律 6)

本 feature **不新建表**(foundation 已建好),只读写现有表。仅 1 个 permission seed 迁移(加 knowledge:distribute code)。故 8 条 checklist 不适用,但补充 distribution 查询的索引考量:

- `knowledge_distribution` 查询模式:① 门店视角 join(`target_tenant_id = :tenant AND is_active = true` → 已有 `ix_target_tenant_id` 索引,foundation 切片01 已建);② 下发列表(group_admin/super_admin 看 source_doc 的所有下发关系,按 source_doc_id 查 → UniqueConstraint(source_doc_id, target_tenant_id) 兼作覆盖,无需新索引)
- 软删过滤:list/retrieve 永远带 `doc.is_deleted=false AND dist.is_active=true`(源文档软删 → 下发关系自动失效,无需手动 flip is_active)

### 4.5 EP2 grill 8 深化决策

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| G1 | group_admin bypass 接通 | **KnowledgeService 6 处 require() 加 db=self.db** | foundation 切片02 为此预留可选 db 参数;实例属性已有;零新依赖;bypass 立即生效。非 group_admin 传 db 也走 casbin 零回归 |
| G2 | list 三路径落点 | **DocumentRepository 加 list_visible_for** | 守「租户过滤在 Repository 层」铁律(AGENTS.md 铁律2);三路径 WHERE 内聚不被 Service 拼凑;Service 只做角色判定 + 调 repo |
| G3 | search_by_embedding 三路径 | **加 include_distributed 参数 + 角色分支** | debug 页传 False(纯本店) / agent 工具传 True(本店+下发);门店检索 LEFT JOIN distribution 只增不减零负向回归(D6 审查补强);group_admin/super_admin 走聚合路径 |
| G4 | 下发 API 形态 | **target_tenant_ids + target_group_id 二选一(扁平 schema)** | 二选一校验(都传或都不传=400);target_group_id 时 service 层展开成该集团所有 tenant_id 批量插;对齐 feature_list.json verification + D3 显式下发语义 + 项目扁平 schema 风格(DocumentCreate) |
| G5 | 下发/撤回权限码 | **新增 knowledge:distribute code** | seed owner/admin;group_admin 经 G1 bypass 放行;语义清晰审计明确;撤回复用同 code(逆操作) |
| G6 | Category CRUD 权限 | **端点统一 require + service 层按 scope+角色校验** | 复用现有 knowledge:read/create/delete code 不加新 code;scope↔角色映射内聚 CategoryService(platform→super_admin / group→is_group_admin / store→本店 owner/admin) |
| G7 | 下发一致性 | **引用模型即时一致(D4)** | 共享 chunks 不拷贝;上级重新 ingest 后门店即时看最新;零额外同步逻辑;本 feature 不做版本快照 |
| G8 | 切片粒度 | **4 切片**(Category → list+检索 → 下发/撤回 → 集成验证) | 线性依赖图无环;每片可独立验证(./init.sh 全绿);blast radius 适中,WIP=1 下单片失败回滚成本可控 |

### 4.6 关键决策编码(prototype 级伪码)

**G2 list_visible_for 三路径**(决策编码,落 Repository):

```python
# app/repositories/document.py
async def list_visible_for(
    self,
    *,
    tenant_id: str,
    group_id: str | None = None,
    platform_role: str | None = None,
    is_group_admin: bool = False,
) -> list[Document]:
    """三路径按角色(super_admin 全局 / group_admin 聚合 / 门店本店+下发)。

    门店视角永远含「本店 store」(只增不减,G3 零负向回归同精神);
    上级下发给我通过 LEFT JOIN knowledge_distribution 扩展。
    """
    stmt = select(Document).where(Document.is_deleted.is_(False))
    if is_cross_tenant_viewer(platform_role):
        pass  # super_admin / hq_staff:全局无过滤
    elif is_group_admin and group_id is not None:
        # group_admin 聚合:本集团 group 级 + 本集团所有门店 store 级
        sibling_tenant_ids = await _sibling_tenants(self.db, group_id)
        stmt = stmt.where(
            or_(
                and_(Document.scope == "group", Document.group_id == group_id),
                and_(Document.scope == "store", Document.tenant_id.in_(sibling_tenant_ids)),
            )
        )
    else:
        # 门店:本店 store + 上级下发给我(LEFT JOIN distribution)
        stmt = stmt.where(
            or_(
                and_(Document.scope == "store", Document.tenant_id == tenant_id),
                Document.id.in_(
                    select(KnowledgeDistribution.source_doc_id).where(
                        KnowledgeDistribution.target_tenant_id == tenant_id,
                        KnowledgeDistribution.is_active.is_(True),
                    )
                ),
            )
        )
    stmt = stmt.order_by(Document.created_at.desc())
    return list((await self.db.execute(stmt)).scalars().all())
```

**G3 search_by_embedding 三路径**(决策编码,落 Repository):

```python
# app/repositories/document.py DocumentChunkRepository
async def search_by_embedding(
    self,
    *,
    tenant_id: str,
    query_embedding: list[float],
    top_k: int = 4,
    include_distributed: bool = False,   # G3:门店 agent True / debug 页 False
    group_id: str | None = None,         # group_admin 聚合视角
    platform_role: str | None = None,
    is_group_admin: bool = False,
) -> list[tuple[DocumentChunk, float]]:
    """Cosine-distance 向量检索,三路径按角色扩范围。

    Postgres only(pgvector <=>)。SQLite 测试 mock service 层。
    门店 include_distributed=True:本店 chunks + 下发给本店的文档的 chunks(只增不减)。
    """
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    stmt = select(DocumentChunk, distance.label("distance"))

    if is_cross_tenant_viewer(platform_role):
        pass  # super_admin/hq_staff:全局 chunks
    elif is_group_admin and group_id is not None:
        sibling_tenant_ids = await _sibling_tenants(self.db, group_id)
        stmt = stmt.where(
            or_(
                DocumentChunk.tenant_id.in_(sibling_tenant_ids),  # 本集团门店
                # group 级文档的 chunks(tenant_id 可能是 HQ 或 null,需 join document.scope='group')
                DocumentChunk.document_id.in_(
                    select(Document.id).where(
                        Document.scope == "group", Document.group_id == group_id
                    )
                ),
            )
        )
    else:
        # 门店:本店 chunks(永远含)
        tenant_filter = DocumentChunk.tenant_id == tenant_id
        if include_distributed:
            # 扩展:下发给我的文档的 chunks
            tenant_filter = or_(
                tenant_filter,
                DocumentChunk.document_id.in_(
                    select(KnowledgeDistribution.source_doc_id).where(
                        KnowledgeDistribution.target_tenant_id == tenant_id,
                        KnowledgeDistribution.is_active.is_(True),
                    )
                ),
            )
        stmt = stmt.where(tenant_filter)

    stmt = stmt.order_by(distance).limit(top_k)
    rows = (await self.db.execute(stmt)).all()
    return [(row[0], float(row[1])) for row in rows]
```

**G4 下发请求 schema**(决策编码,落 schemas/document.py):

```python
class DistributeRequest(BaseModel):
    """Payload for POST /knowledge/{doc_id}/distribute(G4 二选一)."""
    target_tenant_ids: list[str] | None = None   # 显式门店列表
    target_group_id: str | None = None            # 整个集团(service 层展开)

    @model_validator(mode="after")
    def _exactly_one(self) -> "DistributeRequest":
        has_tenants = bool(self.target_tenant_ids)
        has_group = self.target_group_id is not None
        if has_tenants == has_group:  # 都传或都不传
            raise ValueError("必须且只能指定 target_tenant_ids 或 target_group_id 之一")
        return self
```

### 4.7 与 foundation 已交付物的衔接

| foundation 交付 | 本 feature 如何消费 |
|---|---|
| `is_group_admin(db, user_id, group_id)` helper | service 层直接调,判定 group_admin 身份(下发权限 + list 聚合视角) |
| `check()/require()` 可选 `db` 参数 + obj=='knowledge' bypass | **G1 接通**:KnowledgeService 6 处 require 加 db=self.db,bypass 真正生效 |
| `Group.headquarters_tenant_id` + GroupTenant 一对一 | group_admin 判定 + 反推 group(从 tenant_id)已在 foundation 实现 |
| `Document.scope/group_id/category_id` | list/检索三路径按 scope 过滤;create 时按角色写 scope |
| `knowledge_categories` 表 + 5 条 platform seed | Category CRUD 读写;list 可见 = platform + 本集团 group + 本店 store |
| `knowledge_distribution` 表 + UniqueConstraint | 下发/撤回 API 写入;list/检索 LEFT JOIN |

---

## 5. Testing Decisions

- **测试 seam**:`tests/test_knowledge_backend.py`(服务层 + Repository 层契约直测,对齐 `test_knowledge_foundation.py` 范式)。**单一 seam**(to-spec SKILL 要求 seam 越少越好)
- **测试金字塔**:unit/集成混合(SQLite 内存库;检索用 mock embedding 范式,对齐现有 `retrieve` 的 SQLite-mock 约定)。无 E2E(本 feature 无前端)
- **测试库**:SQLite 内存库(list/Category/distribute 全用 SQLite;**检索测试 mock service 层**,因 pgvector `<=>` 无 SQLite 实现,沿用现有 `retrieve` 的 mock 约定)
- **覆盖率目标**:≥ 项目基线 93%,新代码(list_visible_for / search_by_embedding 三路径 / distribute / Category CRUD)全覆盖
- **边界 case 清单**:
  - **list 三路径矩阵**:门店看本店store+下发 / group_admin 看聚合 / super_admin 看全局 / 门店看不到其他门店store / 门店看不到未下发platform / group_admin 看不到其他group
  - **检索三路径**:门店 include_distributed=True 含下发 / =False 纯本店 / group_admin 聚合 / super_admin 全局 / 只增不减(本店原命中保留)
  - **下发**:target_tenant_ids 显式列表 / target_group_id 展开集团 / 二选一校验(都传或都不传=400) / 重复下发 UniqueConstraint 冲突 / 跨集团下发拒绝(group_admin 只能下发本集团)
  - **撤回**:撤回=软删 is_active=false / 撤回后门店 list/retrieve 排除 / 源文档软删后下发关系自动失效(不手动 flip is_active)
  - **Category CRUD**:platform 需 super_admin / group 需 is_group_admin / store 需本店 owner/admin / member 只读 / list 可见三路径(platform + 本集团group + 本店store) / 同 scope 同名唯一约束
  - **bypass 接通**:group_admin 调 knowledge API 放行(G1 生效) / 非 group_admin 传 db 走 casbin 零回归 / group_admin + devices 不放行(D9 守卫)
  - **一致性(G7)**:下发后上级改文档重新 ingest → 门店检索/list 即时看最新(引用模型)
- **多租户隔离测试**:门店间互不可见 / group_admin 严格本集团内 / 跨集团 group_admin 互不可见

---

## 6. 切片规划(tracer-bullet 垂直切片)

> 切片依赖图:`01 ─→ 02 ─→ 03 ─→ 04`(严格串行,核心层改造层层依赖)

详见下方「实施切片」段。4 个切片,每片切穿 schema→repository→service→api→test,单片可独立验证(./init.sh 全绿)。

---

## 7. v1 → v2 对抗式审查段(复杂任务,占位)

**触发条件**:改鉴权(✓ group_admin bypass 接通 G1)+ 跨服务(✓ KnowledgeService + CategoryService + graph.py)+ 权限码新增(✓ knowledge:distribute)。属复杂任务。

**审查方式**:EP3 实施首切片前,跑 `/code-review` 双轴(Standards + Spec),或在 EP2 收尾后立即审查 plan。审查产出回写本 plan §0。

**审查重点**(预期 🔴/🟡/🟢):
- 🔴 list_visible_for 三路径 WHERE 是否真的覆盖所有角色分支(防漏 group_admin 聚合 / 防门店误看其他门店)
- 🔴 search_by_embedding 改造是否破坏现有 retrieve 调用点(debug 页 / agent 工具 / seed_demo)
- 🔴 G1 bypass 接通后,group_admin 是否真的仅 scope knowledge(D9,防越界 devices/bookings)
- 🟡 distribute 的 target_group_id 展开逻辑是否正确处理「集团无门店」边界
- 🟡 源文档软删后下发关系自动失效的联合谓词(doc.is_deleted=false AND dist.is_active=true)是否在 list/retrieve 两处都落实
- 🟢 Category scope↔角色映射是否完整(super_admin/group_admin/store owner/admin/member 五角色)

---

## 8. Out of Scope(对齐 EP1 总纲 + feature_list.json notes)

- ❌ 前端三栏阅读/管理 UI(Feature C/D)
- ❌ 富文本/Markdown 文档**编辑器**(文档仍只 create/delete,无 update;feature_list.json notes 明示)
- ❌ PDF/Word 预览(系列级 Out of Scope)
- ❌ group_admin 扩展到知识库**外** object(D9,devices/bookings 不动)
- ❌ 改 hq_staff 语义(保持全局跨租户只读)
- ❌ 门店间知识共享(铁律,始终隔离)
- ❌ 版本控制 / 文档历史(G7 引用模型即时一致,不做版本树)
- ❌ 文档 update 路径(现有文档无 update act,本 feature 不补;重新 ingest 是 create+delete 替代)
- ❌ 下发定时/批量重新下发(单个操作即时下发,feature_list.json notes 明示)
- ❌ **门店创建后迁移集团**(D8,创建时定集团后归属不可改)
- ❌ Permission matrix UI 暴露 knowledge:distribute(本 feature 只加 code + seed,matrix 暴露归权限管理 feature;但 code 会自动出现在 matrix 因 OBJ_CN/ACT_CN 加标签)

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| search_by_embedding 改造破坏现有 retrieve 调用点(debug 页 / agent / seed_demo) | 高 | G3 加 include_distributed 参数向后兼容(默认 False = 原行为);debug 页显式传 False;agent 工具传 True;测试覆盖「只增不减」零负向回归 |
| list_visible_for 三路径 WHERE 漏角色分支(门店误看其他门店) | 高 | G2 三路径显式 WHERE 在 Repository 层;测试矩阵覆盖 6 角色边界;门店间隔离铁律用独立测试钉死 |
| G1 bypass 接通后 group_admin 越界到 devices/bookings | 高 | foundation 切片02 已锁 `obj=='knowledge'` 条件 + D9 测试;本 feature 补「group_admin + devices 不放行」回归测试 |
| distribute target_group_id 展开遇「集团无门店」边界 | 中 | service 层校验:集团无门店时返回空列表(下发 0 条,幂等不报错)或 BizError 提示;测试覆盖空集团 |
| 源文档软删后下发关系未自动失效(门店仍看到) | 中 | list/retrieve 两处联合谓词 `doc.is_deleted=false AND dist.is_active=true`;测试覆盖源文档软删后门店 list/retrieve 都排除 |
| knowledge:distribute code seed 迁移在已有库重复 | 低 | 迁移用 INSERT...WHERE NOT EXISTS 守护(对齐 foundation Category seed 范式),idempotent |

---

## 10. 验收标准(同步 feature_list.json verification)

1. `app/api/v1/knowledge.py`:新增端点 —— `POST /knowledge/{doc_id}/distribute`(下发到 target_tenant_ids 列表或 target_group_id 整个集团,G4 二选一)+ `DELETE /knowledge/distribute/{dist_id}`(撤回=软删 is_active=false,保留审计痕迹,非硬删)+ 源文档软删(Document.is_deleted=true)时所有引用该文档的下发关系自动失效(list/retrieve 同时排除 doc.is_deleted=false AND dist.is_active=true)+ `GET/POST/PUT/DELETE /knowledge/categories`(Category CRUD,按 scope 权限 G6)
2. `app/repositories/document.py`:list_visible_for 三路径(G2)+ search_by_embedding 改造(G3 三路径按角色:门店本店+下发 / group_admin 聚合 / super_admin 全局);retrieve_knowledge 工具传 include_distributed=True,retrieve 调试页传 include_distributed=False;门店视角检索「只增不减」零负向回归
3. `app/services/category_service.py` 新建:Category CRUD + scope 权限(super_admin 建 platform / group_admin 建 group / 门店建 store)+ 下级能 list 上级 Category(list 可见 = platform 全部 + 本集团 group + 本店 store)
4. `app/agents/graph.py`:`_build_tenant_tools` 的 retrieve_knowledge 适配新检索范围(本店 store + 下发),docstring 更新说明检索跨 scope
5. `app/services/knowledge_service.py`:6 处 require() 加 db=self.db(G1 接通 group_admin bypass)
6. `app/services/permission_service.py`:DEFAULT_OWNER/ADMIN_PERMS 加 knowledge:distribute code(G5)+ OBJ_CN/ACT_CN 加中文标签
7. `DataScope/Role.data_scope/DEFAULT_*_PERMS(除新增 distribute)/casbin policy 零回归(group_admin 派生身份仅知识库域);retrieve_knowledge 现有调用点零行为回归(门店 agent 检索范围只增不减)`
8. `tests/test_knowledge_backend.py` ~30+ 用例(三路径 list + 检索 + 下发/撤回 + Category CRUD + bypass 接通 + 跨租户隔离 + D9 越界守卫 + G7 一致性);`./init.sh full` 全绿(ruff + 全量 pytest 含新章节);`alembic upgrade head && alembic check` 无 drift

---

## 11. 不越界声明

本次改动**只**涉及:KnowledgeService(6 处 require 加 db + list/retrieve 三路径调用)+ DocumentRepository(list_visible_for + search_by_embedding 三路径)+ CategoryService(新建)+ DistributionRepository(新建/扩展)+ knowledge.py API(+ 下发/撤回 + Category CRUD 端点)+ schemas(+ DistributeRequest/Category schemas + DocumentRead 加 scope/group_id/category_id)+ graph.py(retrieve_knowledge 适配)+ permission_service(加 distribute code + 中文标签)+ 1 permission seed 迁移 + 1 测试。

**不**触碰:前端任何文件(C/D)/ Document 编辑路径(无 update)/ hq_staff 语义 / DEFAULT_*_PERMS 既有条目(只加 distribute)/ casbin 角色枚举 / devices/bookings 域 / DataScope / Role.data_scope / Principal 模块(ADR-0001 边界)/ 门店间隔离逻辑(铁律)。

---

## 实施切片(EP2 to-tickets 产出)

> 4 个 tracer-bullet 垂直切片,严格串行(`01 → 02 → 03 → 04`)。每片切穿 schema→repository→service→api→test,单片可独立验证(./init.sh 全绿)。frontier = 切片 01。

### 切片依赖图

```
01(Category CRUD + scope 分级)
  │
  └─→ 02(list + 检索三路径改造 + G1 bypass 接通)
        │
        └─→ 03(下发/撤回 API + distribute 权限码)
              │
              └─→ 04(集成验证 + feature 收尾,末切片)
```

---

### 切片 01 — Category CRUD + scope 分级权限(frontier)✅

- **What it delivers**:Category 的完整 CRUD 落地。各级管理员可创建本级 Category(super_admin→platform / group_admin→group / 门店 owner/admin→store),所有人可 list 可见的上级 Category(platform 全部 + 本集团 group + 本店 store),member 只读。foundation 已建的 `knowledge_categories` 表 + 5 条 platform seed 此切片真正可用。此切片完成后,前端 C/D 的分类目录树有了数据源(虽然 UI 在后续 feature)。
- **Blocked by**: 无(frontier)
- **文件清单**:
  - `app/schemas/document.py`(改:+ KnowledgeCategoryCreate/Read/Update schemas)
  - `app/repositories/knowledge_category.py`(新:Category repo,list_visible 三路径 + scope 归属 CRUD)
  - `app/services/category_service.py`(新:CRUD + scope↔角色校验 G6)
  - `app/api/v1/knowledge.py`(改:+ GET/POST/PUT/DELETE /knowledge/categories 端点)
  - `alembic/versions/2026_08_0X_..._add_knowledge_category_indexes.py`(可选:若 list_visible 需补索引;否则无迁移)
  - `tests/test_knowledge_backend.py`(新,本切片覆盖 Category 部分)
- **Acceptance criteria**:
  - [x] `KnowledgeCategoryCreate/Read/Update` schemas 就位(scope 必填 platform/group/store;group_id scope=group 时必填,其他 null;tenant_id scope=store 时必填,其他 null;sort_order 可选)
  - [x] `KnowledgeCategoryRepository` 新建:list_visible(tenant_id, group_id, platform_role, is_group_admin)三路径(platform 全部 + 本集团 group + 本店 store)+ CRUD(create/update/delete 带 scope 归属)
  - [x] `KnowledgeCategoryService` 新建:CRUD 方法 + scope↔角色校验(scope=platform 需 super_admin / scope=group 需 is_group_admin / scope=store 需本店 owner/admin;member 全域只读不能 create/update/delete)
  - [x] 4 个端点就位:GET /knowledge/categories(list 可见三路径)+ POST /knowledge/categories(create 按 scope 校验)+ PUT /knowledge/categories/{id}(update 同 scope 校验)+ DELETE /knowledge/categories/{id}(软删 is_deleted=true)
  - [x] Category list 可见性测试:门店看 platform+本集团group+本店store / group_admin 看 platform+本集团group+本集团所有门店store(聚合) / super_admin 看全部 / 跨集团不可见
  - [x] Category scope 权限测试:门店 owner 建 store 成功 / 门店 owner 建 platform 拒绝 / group_admin 建 group 成功 / group_admin 建 platform 拒绝 / super_admin 建 platform 成功 / member create 全域拒绝
  - [x] Category 同 scope 同名唯一约束测试(部分唯一索引,scope+name+group_id+tenant_id 活跃唯一)
  - [x] `./init.sh` 全绿(ruff + pytest -m smoke,含新 Category 章节);既有 knowledge 端点零回归(create/list/delete/retrieve 不变)
  - [x] foundation 的 5 条 platform seed 在 list_visible 门店视角可见(验证 seed 与 list 联通)

> **✅ 切片 01 完成**(feat/knowledge-tiered-backend-slice-01)。9 AC 全勾。验证:`./init.sh full` **925 passed**(894 baseline + 31 新)零回归,ruff clean。实现:`KnowledgeCategoryService` + `KnowledgeCategoryRepository`(list_visible 三路径,`is_cross_tenant_viewer` 由 service 计算传 bool 避铁律#1 反向依赖)+ schemas(跨字段 binding 走 service BizError 避 model_validator 422 序列化坑,对齐 BookingCreate 范式)+ 4 端点(update 复用 knowledge:create code,G6 不加新码)。/code-review 双轴(general-purpose ×2 并行):Standards 1 硬违规(repo→service 反向 import → 采纳修复:bool 下传)+ 3 判断项(Refused Bequest Update 不继承 base → 采纳 / CategoryService→KnowledgeCategoryService 改名 → 采纳 / 内联 import 提顶 → 采纳);Spec AC6 补 group_admin→platform 拒绝测试 → 采纳。**非末切片**(02-04 待做),不动 feature_list.json status/evidence。

---

### 切片 02 — list + 检索三路径改造 + G1 bypass 接通(核心)✅

- **What it delivers**:跨 scope 可见性的核心兑现。门店 list/retrieve 看到「本店 store + 上级下发给我」;group_admin 看聚合;super_admin 看全局。同时 G1 接通 group_admin bypass(KnowledgeService 6 处 require 加 db=self.db),让 foundation 留的派生身份真正生效。retrieve_knowledge 工具适配新检索范围(agent 用 True,debug 页用 False,只增不减零负向回归)。此切片完成后,「集团下发的话术门店 agent 能用」真正跑通。
- **Blocked by**: 切片 01(Category repo 范式可复用;且 list 文档的 category_id 字段已就位)
- **文件清单**:
  - `app/repositories/document.py`(改:DocumentRepository +list_visible_for 三路径 + DocumentChunkRepository search_by_embedding 加 include_distributed/角色参数)
  - `app/repositories/knowledge_distribution.py`(新或扩展:distribution repo,提供 list_active_for_target / sibling_tenants helper)
  - `app/services/knowledge_service.py`(改:6 处 require 加 db=self.db [G1]+ list_documents 调 list_visible_for + retrieve 加 include_distributed 参数 + retrieve_for_debug 传 False)
  - `app/schemas/document.py`(改:DocumentRead 加 scope/group_id/category_id 字段)
  - `app/agents/graph.py`(改:retrieve_knowledge 工具调用适配,docstring 更新说明跨 scope)
  - `tests/test_knowledge_backend.py`(扩:list 三路径矩阵 + 检索三路径 + bypass 接通 + D9 越界守卫)
- **Acceptance criteria**:
  - [x] `DocumentRepository.list_visible_for` 三路径就位(G2):super_admin/hq_staff 全局 / group_admin+group_id 聚合(本集团group级 + 本集团所有门店store级)/ 门店(本店store + 上级下发给我,LEFT JOIN distribution is_active=true);永远带 doc.is_deleted=false
  - [x] `DocumentChunkRepository.search_by_embedding` 加 include_distributed/group_id/platform_role/is_group_admin 参数(G3):门店 include_distributed=True 扩下发 / =False 纯本店 / group_admin 聚合 / super_admin 全局;向后兼容(默认 False = 原行为)
  - [x] `KnowledgeService` 6 处 require() 加 db=self.db(G1):list_documents/create_document/delete_document/retrieve_for_debug 的 require 调用 + retrieve_knowledge 工具内的 check;group_admin bypass 真正生效
  - [x] `DocumentRead` schema 加 scope/group_id/category_id 字段(向前兼容,既有响应多三字段)
  - [x] `retrieve_knowledge` 工具适配:检索范围 = 本店 store + 下发(include_distributed=True),docstring 更新说明「检索跨 scope,含上级下发」
  - [x] `retrieve_for_debug` 保持纯本店(include_distributed=False),debug 页行为零回归
  - [x] list 三路径测试矩阵:门店看本店store+下发 / 门店看不到其他门店store / 门店看不到未下发platform / group_admin 看聚合 / super_admin 看全局 / 跨集团不可见
  - [x] 检索三路径测试:门店 include_distributed=True 含下发命中 / =False 纯本店 / 只增不减(本店原命中保留) / group_admin 聚合 / super_admin 全局
  - [x] bypass 接通测试:group_admin 调 knowledge API 放行 / 非 group_admin 传 db 走 casbin 零回归 / group_admin + devices 不放行(D9 守卫)
  - [x] 现有 retrieve 调用点零回归测试:debug 页 / agent 工具 / seed_demo 的 create_document 路径全绿(既有 test_knowledge_* / test_seed 不破)
  - [x] `./init.sh full` 全绿(零回归);smoke 子集含新章节

> **✅ 切片 02 完成**(feat/knowledge-tiered-backend-slice-02,commit `d21f8a9`)。11 AC 全勾。验证:`./init.sh full` **940 passed**(925 baseline + 切片02 新 16)零回归,ruff clean(+1 flaky `test_composite_query_timeout_keeps_completed_fragments` 计时器竞态,单独重跑 3x 全绿,与本切片无关 —— 未碰 fan-out/composite/计时器代码)。实现:
> - **DocumentRepository.list_visible_for 三路径(G2)** —— `document.py:79-131`,三分支(cross-tenant `include_all_tenants` / group_admin `is_group_admin+group_id` 聚合本集团 group 级 + GroupTenant 子查询所有门店 store 级 / 门店 own `scope='store'` + `knowledge_distribution` 子查询 `is_active=true` 下发)+ 全分支守 `is_deleted=False`。镜像切片 01 Category repo 范式:角色 bool 由 service 算后下传,**repo 不 import service 层**(守铁律 #1)。
> - **DocumentChunkRepository.search_by_embedding 三路径(G3)** —— `document.py:160-235`,加 `include_distributed/group_id/include_all_tenants/is_group_admin` 4 参数,**默认 False 向后兼容**(既有 caller 行为零变化);JOIN Document 守 `is_deleted=False`(软删源即使经下发也不浮现);门店 `include_distributed=True` 用 OR 语义**只增不减**(本店命中保留)。
> - **G1 bypass 接通** —— KnowledgeService 4 处 require(`92 read / 116 create / 151 delete / 258 retrieve_for_debug`)+ graph.py retrieve_knowledge 工具内 check(`graph.py:97-99`)全加 `db=self.db` / `db=db`,共 **5 处**(plan 文字「6 处」是规划估算,实际语义完整覆盖:bypass 在所有 knowledge 读写路径生效)。group_admin bypass(`obj=='knowledge' and db is not None` 分支)此前是「死的」(5 处都没传 db),现已真正生效。
> - **DocumentRead 加 scope/group_id/category_id**(AC4)—— `schemas/document.py:51-53`,`scope` 有 server_default='store' 永远有值;group_id/category_id 可选 None。向前兼容,既有响应多三字段。
> - **retrieve_knowledge 工具适配** —— `graph.py:108-110` `retrieve(..., include_distributed=True)`,门店 agent 检索 = 本店 store + 上级下发;docstring 更新说明「检索跨 scope,含上级下发」。**retrieve_for_debug 保持默认 False**(纯本店,debug 页零回归)。
>
> 16 tests(`tests/test_knowledge_backend.py`):list_visible_for 三路径 6(门店本店+下发 / 看不到其他门店 / group_admin 聚合 / super_admin 全局 / 跨集团隔离 / 软删源排除)+ 检索三路径 4(默认向后兼容 / include_distributed 转发 / group_admin 上下文转发 / 只增不减 OR 语义结构守卫)+ G1 bypass 3(group_admin 放行 / 非 group_admin 传 db 走 casbin 零回归 / D9 devices 不放行)+ retrieve_knowledge 工具接线 2(include_distributed=True + db=db 源码守卫 / retrieve_for_debug 保持 False)+ DocumentRead tier 字段 1。
>
> **非末切片**(03 下发/撤回 / 04 集成验证 待做),不动 feature_list.json status/evidence(末切片的事)。下一步:切片 03 下发/撤回 API + distribute 权限码。

---

### 切片 03 — 下发/撤回 API + distribute 权限码 ✅

- **What it delivers**:集团统一管控门店的落地链路打通。super_admin/group_admin 可下发知识到指定门店或整个集团,可撤回(软删 is_active=false 保留审计)。源文档软删后下发关系自动失效。新权限码 knowledge:distribute(seed owner/admin)。此切片完成后,D3「显式下发」语义端到端跑通,前端 D 的下发 Dialog 有了 API 基石。
- **Blocked by**: 切片 02(list_visible_for 已就位,下发的文档能被门店看到验证下发链路闭环)
- **文件清单**:
  - `app/schemas/document.py`(改:+ DistributeRequest [G4 二选一] + KnowledgeDistributionRead)
  - `app/repositories/knowledge_distribution.py`(**新建**:create(下发,pre-check upsert)/ find_for_pair / deactivate(撤回)/ list_for_source / list_for_target / get)
  - `app/services/knowledge_service.py`(改:+ distribute_document [含 target_group_id 展开成 tenant_ids] / revoke_distribution [软删 is_active=false] + 源/撤回所有权校验辅助)
  - `app/api/v1/knowledge.py`(改:+ POST /knowledge/documents/{doc_id}/distribute + DELETE /knowledge/distributions/{dist_id} 端点,require knowledge:distribute)
  - `app/services/permission_service.py`(改:DEFAULT_OWNER/ADMIN_PERMS 加 knowledge:distribute + ACT_CN 加「下发」+ BACKFILLABLE_OBJS 加 knowledge)
  - `scripts/backfill_obj_perms.py`(改:docstring 示例补 knowledge;argparse choices 从 BACKFILLABLE_OBJS 派生自动包含)
  - `tests/test_knowledge_backend.py`(扩:切片 03 章节 35 tests + conftest `_bind_role`/`_make_casbin` 同步 distribute policy)
  - `tests/test_permission_service.py`(改:catalogue guard expected 集合加 knowledge:distribute)
  - ~~`alembic/versions/..._add_knowledge_distribute_perm.py`~~ —— **未建 migration**。权限码走 runtime seed 路径(与 devices/bookings 先例字节对齐):新租户由 `seed_tenant_defaults`(迭代 DEFAULT_*_PERMS)自动 seed,老租户由 `backfill_perm_set_for_existing_tenants`(幂等,seed permissions 目录 + role_permissions SCD2 + casbin 三表同步)。raw SQL migration 只能碰 1/3 表(permissions 目录),留 casbin+SCD2 不一致,违「SCD2+casbin 同步」铁律 —— devices/bookings 因此无 migration。详见下方 AC8 备注。
- **Acceptance criteria**:
  - [x] `DistributeRequest` schema 就位(G4):target_tenant_ids + target_group_id 二选一校验(XOR 在 service 层 BizError → 400,非 pydantic model_validator —— 避 422 序列化坑,与 BookingCreate/Category 同款铁律);KnowledgeDistributionRead 含 source_doc_id/target_tenant_id/distributed_by/distributed_at/is_active
  - [x] `KnowledgeDistributionRepository` 扩展:create(下发,pre-check upsert —— find_for_pair 先查,存在则 re-enable,不存在则 insert;UniqueConstraint 仍是竞态硬守卫)/ deactivate(撤回 is_active=false 软标)/ list_for_source(group_admin/super_admin 看某文档的所有下发,active_only 可选)/ list_for_target(门店看下发给我的,仅 active)
  - [x] `KnowledgeService.distribute_document` 就位:target_tenant_ids 显式列表下发 / target_group_id 展开成该集团所有 tenant_id 批量插(group_admin 只能下发本集团 is_group_admin 校验,跨集团拒绝 BizError;super_admin 全域)/ 重复下发 upsert re-enable(非 BizError,幂等)
  - [x] `KnowledgeService.revoke_distribution` 就位:撤回=软删 is_active=false(保留审计痕迹,非硬删);撤回后门店 list/retrieve 排除该文档(联合谓词自动生效)
  - [x] 源文档软删联动:Document.is_deleted=true 时,list_visible_for 和 search_by_embedding 都自动排除(联合谓词 doc.is_deleted=false AND dist.is_active=true,无需手动 flip 下发关系 —— slice 02 已就位,本切片加测试证明)
  - [x] 2 个端点就位:POST /knowledge/documents/{doc_id}/distribute(require knowledge:distribute)+ DELETE /knowledge/distributions/{dist_id}(require knowledge:distribute)
  - [x] DEFAULT_OWNER/ADMIN_PERMS 加 knowledge:distribute code;member 不加;ACT_CN 加「下发」(OBJ_CN knowledge「知识库」已存在)
  - [x] ~~migration seed~~ → **runtime seed 路径已覆盖**:DEFAULT_*_PERMS 加 distribute + BACKFILLABLE_OBJS 加 knowledge → 新租户 seed_tenant_defaults 自动 seed,老租户 backfill_perm_set_for_existing_tenants 幂等三表同步(permissions + role_permissions SCD2 + casbin)。与 devices/bookings 先例一致(均无 migration);偏离 plan 原文的「raw SQL INSERT...WHERE NOT EXISTS」决策,理由:raw SQL 只能碰 1/3 表,违 SCD2+casbin 同步铁律
  - [x] 下发测试:target_tenant_ids 显式列表 / target_group_id 展开集团 / 二选一校验(都传/都不传=400) / 重复下发 upsert re-enable / group_admin 跨集团下发拒绝 / super_admin 全域下发
  - [x] 撤回测试:撤回=软删 is_active=false / 撤回后门店 list/retrieve 排除 / 撤回保留审计行(不硬删)
  - [x] 源文档软删联动测试:源文档软删后门店 list 看不到 / search_by_embedding 联合谓词排除(结构断言)/ 下发关系行仍存在但被联合谓词排除(is_active 仍 true,审计完整)
  - [x] distribute 权限测试:owner/admin 可下发 / member 拒绝 / group_admin 经 bypass 放行(本集团) / super_admin 全域
  - [x] 一致性测试 G7:下发后上级改文档重新 ingest → 门店检索/list 即时看最新(引用模型 —— list_visible_for/search_by_embedding 均通过 source_doc_id 引用源文档,非拷贝;结构断言 + 数据级证明)
  - [x] `./init.sh full` 全绿(979 passed,零回归)

> **✅ 切片 03 完成**(feat/knowledge-tiered-backend-slice-02 分支叠加)。13 AC 全勾。验证:`./init.sh full` **979 passed**(941 slice-02 baseline + 38 新,含 test_knowledge_backend 切片03 35 tests + permission catalogue guard + conftest distribute policy 同步)零回归,ruff clean。实现:`DistributeRequest`(G4 XOR 在 service BizError 非 schema model_validator,避 422 序列化坑)+ `KnowledgeDistributionRepository`(新建,pre-check upsert `find_for_pair` 先查再 insert/re-enable,非 IntegrityError catch —— SQLite/PG flush timing 分叉 + rollback 丢 pending writes;UniqueConstraint 仍是竞态硬守卫)+ `KnowledgeService.distribute_document`(target_group_id 展开 `GroupTenantRepository.list_for_group`,group_admin 跨集团 is_group_admin 校验拒绝)+ `revoke_distribution`(软删 is_active=false 保留审计)+ 源/撤回所有权 `_get_distributable_source`/`_assert_can_revoke`(super_admin 全域 / group_admin 本集团聚合视图 / store 自店)。权限码走 **runtime seed 路径**(非 migration):DEFAULT_OWNER/ADMIN_PERMS 加 distribute + ACT_CN「下发」+ BACKFILLABLE_OBJS 加 knowledge —— 与 devices/bookings 先例字节对齐,偏离 plan 原文 raw SQL migration 决策(理由:raw SQL 只碰 1/3 表违 SCD2+casbin 同步铁律)。**非末切片**(04 集成验证 + feature 收尾待做),不动 feature_list.json status/evidence。下一步:切片 04 集成验证 + feature 收尾仪式。

---

### 切片 04 — 集成验证 + feature 收尾(末切片)

- **What it delivers**:端到端集成验证 + feature 收尾仪式。确认切片 01-03 的 Category / list+检索三路径 / 下发撤回 协同工作,跑全量回归,刷新 feature_list 状态。解锁下游 C/D 的依赖。
- **Blocked by**: 切片 03
- **文件清单**:
  - `tests/test_knowledge_backend.py`(扩:集成场景 + 收尾覆盖补全)
  - (无源码改动,除非集成测试暴露 bug)
- **Acceptance criteria**:
  - [ ] 集成测试:完整下发链路 —— super_admin 建 platform 文档 → 下发到门店 → 门店 list 看到下发 → 门店 retrieve 搜到下发文档 → 撤回后门店 list/retrieve 都看不到
  - [ ] 集成测试:group_admin 链路 —— 总部 owner(group_admin)建 group 文档 → 下发到本集团分店 → 分店 owner list 看到 → 分店 retrieve 搜到 → 跨集团分店看不到
  - [ ] 集成测试:Category 跨级可见 —— super_admin 建 platform Category / group_admin 建 group Category / 门店建 store Category → 门店 list 看到三级 → 选用上级 Category 创建文档
  - [ ] 集成测试:源文档软删联动 —— 下发后源文档软删 → 门店 list/retrieve 同时排除(联合谓词生效)→ 下发关系行保留(审计完整)
  - [ ] 集成测试:跨租户隔离铁律 —— 门店 A 的 store 文档门店 B 看不到 / 门店 A 的下发文档门店 B 看不到(只下发给 A) / group_admin A 看不到 group B
  - [ ] 集成测试:D9 越界守卫 —— group_admin 对 knowledge 放行 / 对 devices/bookings 不放行(派生身份仅知识库域)
  - [ ] `./init.sh full` 全量绿(ruff + 全量 pytest,零回归,含新 test_knowledge_backend 全章节)
  - [ ] `alembic upgrade head && alembic check` 双库无 drift(本 feature 仅 1 permission seed 迁移,无表结构变更)
  - [ ] feature 收尾仪式(three-tier §4 第1-7步):status→passing + evidence + sync-active + progress.md + 文档影响评估 + 依赖解锁扫描(C/D 的 depends_on=backend 满足 → 可置 in_progress,但 WIP=1 下只一个是 frontier)
  - [ ] 回归确认:既有 retrieve 调用点(debug 页 / agent 工具 / seed_demo)行为零回归;DataScope/Role.data_scope/DEFAULT_*_PERMS(除新增 distribute)/casbin policy 零回归

---

## grill 深化访谈记录(EP2,2026-08-06)

- **入口**:backend feature 走 EP2 单回环(grill → to-spec → to-tickets),foundation 已 passing 是前置
- **不重烤**:EP1 总纲 D1-D12 已锁定(Session 188),foundation E1-E8 已交付(Session 189-192),本回环只深化「实施层」8 个点(G1-G8)
- **codebase-aware 洞察**:读 KnowledgeService/DocumentRepository/knowledge.py/permission_service 后发现 group_admin bypass「未接通」(foundation 加了可选 db 参数但 KnowledgeService 6 处 require 没传),这是 G1 的核心洞察
- **共识**:8 个深化点全部选推荐项(G1 传 db / G2 list_visible_for / G3 include_distributed / G4 二选一扁平 / G5 新 distribute code / G6 service 层 scope 校验 / G7 引用即时一致 / G8 4 切片)
- **下一步**:EP2 收尾 plan 自检(three-tier §3 4 项)→ 回填 feature_list.json plan 字段 → 进 EP3 `/implement` 切片 01(Category CRUD,frontier 无 blocker)
