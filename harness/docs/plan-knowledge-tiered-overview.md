# 计划:知识库分级管理 + 可视化阅读(三级权限 + 分类 + 下发)

> 这是 **知识库分级管理系列的总纲文档**(EP1,登记性质,grill 访谈成果固化)。
> 2026-08-05 Session 188 `/grill-with-docs` 收敛,**12 个决策点全定**(D1-D12)。
> 本文档是后续各 feature 的 `/to-spec`(落 plan-<id>.md)+ `/to-tickets`(拆切片)的输入。
> 对应 feature_list.json 待登记的 `id`(见 §6 系列 feature 拆分)。
> **承接** [`plan-knowledge-base-rag.md`](plan-knowledge-base-rag.md)(p57 ✅ passing,已激活 pgvector + Document/Chunk + embedding 管线 + retrieve_knowledge 工具)。本系列在其之上叠加**三级权限 + 分类 + 下发 + 可视化阅读**。
>
> **🎯 系列状态:✅ 全部完成(2026-08-08)**。4 feature 全 passing:
> - **Feature A** `knowledge-tiered-foundation` p90 ✅(数据模型 + 权限地基,全 3 切片)
> - **Feature B** `knowledge-tiered-backend` p89 ✅(后端 CRUD + 下发 API + 检索改造,全 4 切片,PR #154)
> - **Feature C** `knowledge-tiered-reader-ui` p88 ✅(前端三栏可视化阅读,全 3 切片,PR #155/#156/#157)
> - **Feature D** `knowledge-tiered-admin-ui` p87 ✅(前端分类管理 + 下发操作 UI + 后端接缝补齐,全 5 切片,PR #158/#159/#160/#161)
>
> 三级权限(super_admin / group_admin 派生身份 / 门店 owner-admin-member)+ 双维度分类(scope + category)+ 显式下发(引用模型,撤回软删)+ 三栏阅读 + 管理操作 UI 全部端到端交付。「门店=最小 OPC 产业单元」。**遗留 follow-up**:toast「重新激活 M 条」需后端 `KnowledgeDistributionRead` 加 `was_reactivated` 字段(独立小切片,已记入 admin-ui plan)。

---

## 背景:为什么做知识库分级管理

### 业务起点:OPC 产业的核心诉求

项目核心是「**一家门店为一个 OPC 产业**」—— 门店是最小产业单元,但具备完整经营闭环。知识库必须服务这个结构:

- **门店**(Tenant):最小产业单元,有自己专属知识库(产品手册/话术/服务规范),门店间**严格隔离**(铁律,不可破)
- **集团**(Group):门店的归属实体。**单门店 = 自成一集团**(自己既是门店也是集团);连锁场景 = 一个集团总部 + 多家分店
- **平台**(super_admin):跨所有集团所有门店,负责全局知识

### 现状(p57 已交付,但权限粒度粗)

p57 `knowledge-base-rag` 已交付:
- `Document`(tenant 级,软删)+ `DocumentChunk`(pgvector 向量)
- `KnowledgeService`:list/create/delete + ingest(分块+embedding)+ retrieve(余弦检索)
- `retrieve_knowledge` agent 工具(搜当前租户)
- 前端:知识库管理页 + retrieve 调试页

**缺失(本系列要补)**:
1. **无分类**:所有 Document 平铺,无主题归类(产品手册/FAQ/话术混在一起)
2. **无分级**:`scope` 概念不存在,知识库是纯 tenant 级(无平台级/集团级),上级无法统一管控
3. **无下发**:上级(平台/集团)无法把知识下发给下级(门店),集团统一话术无法触达分店
4. **门店视角弱**:门店只能看自己的,无「上级下发给我的」聚合,「集团统一管控门店」无法落地
5. **阅读体验差**:纯列表,无分类目录树、无在线阅读器,「门店处理得非常好」做不到

### 目标

在 p57 RAG 管线之上,叠加三级权限 + 分类 + 下发 + 可视化阅读:

1. **三级权限**(super_admin / group_admin / 门店 owner/admin/member),按 scope(platform/group/store)控制知识可见性
2. **双维度分类**:scope(权限层)+ category(主题层),既有权限边界又有业务归类
3. **显式下发**:上级创建知识后,可选择下发到指定门店/集团(引用模型,共享 chunks,不拷贝)
4. **RAG 兜底**:门店 agent 的 `retrieve_knowledge` 检索范围 = 本店 + 上级下发给我的
5. **可视化阅读**:三栏布局(分类目录树 + 文档列表 + Markdown 在线阅读器),门店视角直观

---

## 总体方案(grill 12 决策点)

### 决策汇总表(速查)

| # | 决策点 | 选择 | 确认方式 |
|---|---|---|---|
| D1 | 三级角色 | super_admin / **group_admin 派生**(总部门店 owner/admin)/ 门店 owner/admin/member | 用户确认 |
| D2 | 分类双维度 | scope(platform/group/store)+ category(主题)正交 | 用户确认 |
| D3 | 下发机制 | 显式下发(可选推送到指定门店/集团) | 用户确认 |
| D4 | 下发数据模型 | **引用**(共享 chunks 不拷贝,撤回软删 is_active) | agent 推荐,用户未推翻 |
| D5 | Category 管理 | 预置 + 允许扩展(平台预置+各级自建) | agent 推荐,用户未推翻 |
| D6 | RAG 检索范围 | 本店 + 上级显式下发(三路径:门店/group_admin/super_admin) | agent 推荐,用户未推翻 |
| D7 | 可视化阅读 | 三栏(目录树+列表+Markdown 阅读器) | agent 推荐,基于「门店处理得非常好」 |
| D8 | 门店集团归属 | **一对一**(一门店只属一集团,单门店=自成一集团,创建后不可迁移) | 用户确认 |
| D9 | 范畴边界 | 只做知识库域,group_admin 不扩其他 object | agent 推荐,用户未推翻 |
| D10 | Group 模型 | 集团独立 + 总部门店指针(`headquarters_tenant_id`) | 用户确认 |
| D11 | group_admin 身份 | **派生**(总部门店 owner/admin,不加角色枚举) | 用户确认 |
| D12 | 集团级知识 | scope=group 独立层级(存 Group,非总部门店 store) | 用户确认 |

> 下方各 D 节为决策详细论证(否决方案 + 推理依据)。审查补强点已就地标注(身份叠加规则、撤回语义统一、检索回归风险、迁移边界)。

### D1:三级角色模型 ✅(用户确认)

| 角色 | 定位 | 谁来当 | 知识库可见/管理范围 |
|---|---|---|---|
| `super_admin` | 平台级(现有) | 平台运营 | 平台 + 所有集团 + 所有门店 |
| `group_admin` | **派生身份**(D11) | 集团总部门店的 owner/admin **自动获得** | 本集团级(scope=group)+ 本集团**所有门店**知识(聚合管理) |
| 门店 `owner`/`admin` | 门店级(现有) | 各门店 | 本门店知识(scope=store)+ 上级下发给我的 |
| 门店 `member` | 门店成员(现有) | 各门店 | 同 owner/admin 但只读 |

**关键**:`group_admin` **不是显式角色枚举**,而是**派生身份** —— 谁是集团总部门店的 owner/admin,谁自动获得本集团的 group_admin 权限。单门店场景下,门店 owner = 自己这个集团的 group_admin(自己管自己,符合「门店集团同义」)。

**身份叠加与边界规则**(审查补强):
1. **总部门店的 member**(非 owner/admin)—— **不是 group_admin**,等同普通门店 member(只读,不能下发/管理)。group_admin 派生判定严格限定在 owner/admin 两个角色。
2. **跨门店身份叠加**(同一 user 在不同 tenant 有不同 role):`is_group_admin(user, group)` **只看 user 是否为 `group.headquarters_tenant_id` 的 owner/admin**,与他在其他 tenant 的 role 解耦。即 group_admin 权限「以总部身份操作时生效」,不会因 user 同时是某分店 owner 而获得该分店所属集团的 group_admin 身份(除非该分店恰好是另一个集团的总部)。
3. **group_admin 的聚合视图数据来源**:group_admin list 知识时,WHERE 子句 = `doc.scope='group' AND doc.group_id=:group`(本集团级)OR `doc.tenant_id IN (该 group 下所有 tenant) AND doc.scope='store'`(本集团所有门店的 store 级)。这是独立于 D6 门店视角的第三条检索路径,在 Feature B 后端实现。

**否决方案**:
- ❌ 新增独立 `group_admin` 角色枚举 + `user_groups` 关联表(过度复杂,派生身份够用)
- ❌ 复用现有 `hq_staff`(全局跨租户只读,不绑 Group,无法区分 A/B 集团)
- ❌ 用租户层级表达集团(现有 Group/Tenant 是平级关联非父子,改造大)

### D2:「分类」双维度 ✅(用户确认)

两个维度都要:
- **scope**(权限层):`platform` / `group` / `store` —— 决定谁能看
- **category**(主题层):产品手册/FAQ/话术脚本/服务规范/促销文案等 —— 决定业务归类

一个 Document 同时有 `scope` + `category_id` 两个字段,互为正交。

### D3:知识下发机制 ✅(用户确认)

**显式下发**(可选推送到指定下级)。上级创建(scope=platform/group)后,可选择下发到指定门店或整个集团。
- 新表 `knowledge_distribution` 记录下发关系(source_doc_id + target_tenant_id + distributed_by/at)
- 门店看到 = 本店自建(scope=store)+ 上级**显式下发给我**的

**否决**:
- ❌ 自动可见(scope 隐式,无下发动作):不符合「集团统一管控」语义,无法控制「下发到哪些店」
- ❌ 自动可见 + 置顶推荐:模糊「下发」语义

### D4:下发数据模型 ✅(agent 推荐,用户未推翻)

**引用**(共享同一份 chunks,不拷贝)。
- `knowledge_distribution` 只存关系(source_doc_id + target_tenant_id + distributed_by/at + is_active)
- 门店检索时 join 这张表 + 原 Document/chunks(共享 chunks,不拷贝 embedding)
- 上级改文档 → 重新 ingest → 门店**即时**看到最新(强一致性)
- 上级「撤回下发」= **软删**(`UPDATE is_active=false`,保留审计痕迹,与现有 Document 软删惯例一致),门店侧 list/retrieve 排除 `is_active=false` 的关系
- **源文档软删**(Document.is_deleted=true)→ 所有引用该文档的下发关系**自动失效**(list/retrieve 同时排除 `doc.is_deleted=false` AND `dist.is_active=true`),门店侧文档消失

**否决**:
- ❌ 拷贝(门店独立副本):存储膨胀 + embedding 重复计算 + 同步需手动
- ❌ 引用 + 可锁定/可 fork:过度复杂
- ❌ 撤回用硬删(DELETE 关系行):丢失审计痕迹,与项目软删惯例不一致(审查修正:统一为软删 is_active)

### D5:Category 管理 ✅(agent 推荐,用户未推翻)

**预置 + 允许扩展**。
- 平台预置全局 Category(产品手册/FAQ/话术脚本/服务规范/促销文案等,migration seed),建立统一业务语言
- Category 也有 scope(platform/group/store):各级管理员可创建本级 Category 补充本地需求
- 下级能看到 + 选用上级 Category

**推理**:纯预置无本地出口(某门店做理疗,需「理疗话术」集团没有的主题);纯分级自建碎片化(各搞各的,失去统一语言)。预置+扩展平衡一致性+灵活性(对齐 `DEFAULT_OWNER/ADMIN/MEMBER_PERMS` 预置+可扩展惯例)。

### D6:RAG 检索范围 ✅(agent 推荐,用户未推翻)

**本店 + 上级显式下发**。
- 门店 agent `retrieve_knowledge` 检索范围 = scope=store 本店 + `knowledge_distribution` 里显式下发给本店的 platform/group 文档
- 改 `DocumentChunkRepository.search_by_embedding`:join documents + LEFT JOIN knowledge_distribution,WHERE `(doc.tenant_id=本店 AND doc.scope='store') OR (distribution.target_tenant_id=本店 AND distribution.is_active=true AND doc.is_deleted=false)`

**三条检索路径**(按角色):
- 门店视角(owner/admin/member 的 agent + list):`scope=store 本店 OR 下发给我` —— 见上
- group_admin 聚合视角:`scope=group 本集团 OR 本集团所有 tenant 的 scope=store`(见 D1 边界规则 3)
- super_admin 全局视角:全部(无过滤)

**回归风险评估**(审查补强):`search_by_embedding` 改造影响**所有调用点**,不止 `retrieve_knowledge` 工具(`app/agents/graph.py`),还包括 retrieve 调试页(`frontend/src/pages/knowledge-page.tsx` 的 RetrievalDebugPanel,经 `KnowledgeService.retrieve_for_debug`)。调试页若需保持「纯本店」视图调试,Feature B 实现时需通过**参数控制 scope 范围**(如 `retrieve_for_debug(..., include_distributed: bool)`),而非全局改死 —— 调试页传 `include_distributed=False`,agent 工具传 `True`。现有 retrieve 行为对门店是「只增不减」(本店原结果保留 + 新增下发命中),零负向回归。

**推理**:这是「分级管理」价值兑现到 AI agent 的关键 —— 集团下发的话术门店 agent 能用。纯本店削弱下发价值;含未下发(scope=group/platform 但未显式下发)模糊「显式下发」语义(D3)。

### D7:可视化阅读形态 ✅(agent 推荐,基于「门店处理得非常好」)

**三栏布局**:
- **左:分类目录树**(sidebar)—— scope 分区(平台下发/集团下发/本店)+ category 分组(主题),树形导航
- **中:文档列表** + 元信息卡片(状态徽章 / scope 来源标识 / 更新时间 / chunk 数)
- **右:在线阅读器** —— Markdown 渲染 + 目录大纲 + 全文搜索 + 高亮

**不做**:PDF/Word 在线预览(超范围,现有 source_type=text/upload 仅 .txt);文档编辑器(本系列只做阅读 + 管理 CRUD,不做富文本编辑)。

**推理**:「可视化阅读」自然指向目录树 + 阅读器组合;「门店处理得非常好」=简洁直观的三栏布局,门店 owner 一眼看出「这是平台下发的/这是集团的/这是我自己加的」。

### D8:门店集团归属 ✅(用户确认)

**一家门店只属于一个集团**(一对一,不是多对多)。
- 现有 `GroupTenant` 是多对多 → 加唯一约束收敛为「一个 tenant 只能属一个 group」(group_tenants.tenant_id 加唯一索引)
- **单门店 = 自成一集团**:创建门店时若未指定集团,自动创建一个 Group(name=门店名,headquarters_tenant_id=该门店),并把该门店挂到这个 Group 下
- 所以**每个门店必然属于恰好一个集团**(自己这个,或某个连锁集团)

**门店迁移集团的处理规则**(审查补强,见 Out of Scope):本系列**不做「门店创建后迁移到另一个集团」的操作**。创建时定集团后,归属不可改。理由:D8 加了 tenant_id 唯一索引,迁移需先脱离原集团(若原集团是「自成一集团」的空壳,还需处理该空壳 Group 的清理),逻辑复杂且非核心诉求。留作后续独立系列。因此「自动建的自成一集团 Group A,后续手动关联到集团 B」这种冲突场景**在本系列不会发生**(无迁移操作)。

**用户原话对齐**:「集团拥有所有门店的知识库,每一家门店只能看到自己的知识库」—— 集团是聚合视角(看所有门店),门店是隔离视角(只看自己)。门店间**始终隔离**(铁律,D8 只问门店与集团的归属数量,不破门店间隔离)。

### D9:范畴边界 ✅(agent 推荐,用户未推翻)

**本系列只做知识库域**,不顺带改 Group 角色体系全局。
- `group_admin` 派生身份**仅作用于知识库域**(object="knowledge"),不扩展到其他 object(devices/bookings 等不动)
- 不改 `hq_staff` 现有语义(保持全局跨租户只读,与 group_admin 并存)
- 不引入 group_admin 对门店成员/设备/预约的管理权(超范围,未来可独立系列扩展)

**推理**:WIP=1 + 不越界铁律;group_admin 是「知识库域的集团管理员」非「全局集团管理员」。

### D10:Group 模型调整 ✅(用户确认)

**集团独立 + 总部门店指针**。
- Group 表加字段:`headquarters_tenant_id: str`(FK tenants.id,指向总部门店)
- `GroupTenant` 从多对多收敛为「门店对集团一对一」(tenant_id 加唯一索引)
- 单门店场景:门店创建时自动建一个只有自己的 Group 并把自己设为总部
- 连锁场景:集团有独立总部门店 + 多个分店门店

**否决**:
- ❌ 集团 = 特殊门店(Group 与 Tenant 合并):破坏现有 Group/Tenant 两层实体,改动大
- ❌ 不做连锁,门店=集团=一条记录:限制了业务扩展性

### D11:group_admin 身份确定 ✅(用户确认)

**派生身份**(总部门店 owner/admin = group_admin,推荐项)。
- 谁是集团总部门店(`group.headquarters_tenant_id` 指向的 tenant)的 owner/admin,谁自动获得本集团的 group_admin 权限
- 单门店:门店 owner 自动是本集团 group_admin
- 连锁:总部门店 owner 管所有分店的知识库
- **不加角色枚举 / 不加 user_groups 表**,最大化复用现有 owner/admin 角色

**否决**:
- ❌ 显式角色(手动赋予特定成员):需加角色枚举 + casbin 策略 + 赋予机制,过度复杂

### D12:集团级知识存在哪 ✅(用户确认)

**集团级(scope=group,存 Group)** —— 独立层级,非用总部门店的 scope=store 表达。
- scope=group 的知识,`group_id` 指向 Group,不属于任何门店,存在集团层级
- 集团管理员(group_admin)创建后下发到分店
- 下属门店默认看不到未下发的集团知识(严格显式下发)

**否决**:
- ❌ 集团级 = 总部门店的 scope=store 知识:不引入 scope=group 看似简单,但「总部门店自己的知识」与「集团级知识」语义混淆(总部门店也可能有自己的门店内部知识)

---

## 数据模型变更总览

### 改表

#### `groups`(D10)
新增字段:
- `headquarters_tenant_id: str`(FK tenants.id,nullable,总部门店指针)

#### `group_tenants`(D8)
- `tenant_id` 加唯一索引(收敛为一门店只属一集团)

#### `documents`(D2 + D12)
新增字段:
- `scope: str`(platform/group/store,默认 store,NOT NULL;现有数据回填 store)
- `group_id: str | None`(FK groups.id,scope=group 时必填,其他 null)
- `category_id: str | None`(FK knowledge_categories)

### 新表

#### `knowledge_categories`(D5)
主题分类,带 scope + 归属:
- `id, name, scope(platform/group/store), group_id(可空), tenant_id(可空), sort_order, is_deleted, created_at, updated_at`
- 平台预置(scope=platform,group_id/tenant_id null)+ 各级自建

#### `knowledge_distribution`(D3 + D4)
下发关系(引用模型):
- `id, source_doc_id(FK documents), target_tenant_id(FK tenants), distributed_by(FK users), distributed_at, is_active(撤回用软标)`
- UniqueConstraint(source_doc_id, target_tenant_id)—— 同一文档对同一门店只下发一次

---

## 系列拆分(EP1 → 多 feature,后续各自 EP2 拆切片)

本系列预估拆成 **4 个 feature**,各自走 EP2 grill → spec → tickets。依赖关系:`A → B → (C, D 并行)`,A 是地基。

| Feature id(候选) | 内容 | 复杂度 | depends_on |
|---|---|---|---|
| `knowledge-tiered-foundation` | **Feature A:数据模型 + 权限地基**。groups 加 headquarters_tenant_id + group_tenants 唯一约束 + documents 加 scope/group_id/category_id + 新建 knowledge_categories/knowledge_distribution 表 + migration + seed 预置 Category + group_admin 派生身份逻辑(总部门店 owner 判定)+ casbin 策略调整 + 单门店自成一集团自动化 | 高(架构地基) | — |
| `knowledge-tiered-backend` | **Feature B:后端 CRUD + 下发 API + 检索改造**。KnowledgeService 扩展 scope/category/分发逻辑 + 下发/撤回 API + 按角色/scope 过滤的 list API + `search_by_embedding` 改造(join distribution)+ Category CRUD API | 高 | `knowledge-tiered-foundation` |
| `knowledge-tiered-reader-ui` | **Feature C:前端三栏可视化阅读页**。分类目录树(scope 分区 + category 分组)+ 文档列表卡片 + Markdown 在线阅读器 + scope 来源标识 + 全文搜索。门店视角「平台下发/集团下发/本店」分区直观 | 中-高(前端) | `knowledge-tiered-backend` |
| `knowledge-tiered-admin-ui` | **Feature D:前端分类管理 + 下发操作 UI**。Category 管理(各级创建)+ 下发/撤回操作流程(集团/平台视角选门店/集团批量下发)+ 权限按钮控制(group_admin 才能下发)+ scope 切换的文档创建表单 | 中 | `knowledge-tiered-backend` |

**实施顺序**:A(地基)→ B(后端)→ C + D(前端,可并行或串行)。

---

## 范畴边界(Out of Scope)

本系列**不做**(避免越界):
- ❌ 富文本/Markdown 文档**编辑器**(只做阅读 + 管理 CRUD,编辑留后续)
- ❌ PDF/Word 在线预览(现有 source_type=text/upload 仅 .txt)
- ❌ group_admin 扩展到知识库**之外**的 object(devices/bookings 等不动)
- ❌ 改 `hq_staff` 现有语义(保持全局跨租户只读)
- ❌ 门店间知识共享(门店间始终隔离,铁律)
- ❌ 版本控制 / 文档历史(下发是引用,上级改门店即时看到,不做版本树)
- ❌ **门店创建后迁移到另一个集团**(创建时定集团后归属不可改,见 D8 处理规则;迁移需处理空壳 Group 清理,留作后续系列)
- ❌ **完整移动端响应式适配**(Feature C 仅做 `lg` 断点下的左栏折叠[基础可用],完整移动端响应式归「移动端系列」,对齐 design-system 总纲边界)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| p57 承接的 RAG plan | [`plan-knowledge-base-rag.md`](plan-knowledge-base-rag.md) |
| Group 模型(待改) | `app/models/group.py` `Group` / `GroupTenant` |
| Document 模型(待改) | `app/models/document.py` `Document` / `DocumentChunk` |
| KnowledgeService(待扩展) | `app/services/knowledge_service.py` |
| DocumentChunkRepository(待改检索) | `app/repositories/document.py` `search_by_embedding` |
| retrieve_knowledge 工具(待适配) | `app/agents/graph.py` `_build_tenant_tools` |
| 现有门店角色(user_tenants.role) | `app/models/tenant.py` `UserTenant.role`(owner/admin/member) |
| permission_service(待加 group_admin 判定) | `app/services/permission_service.py` |
| 现有知识库前端页 | `frontend/src/pages/knowledge-page.tsx`(待重构成三栏) |

---

## grill 访谈记录(Session 188,2026-08-05)

- **入口**:用户新加任务「按权限的知识库分类管理和知识库可视化阅读,超级管理员/租户管理员/门店管理员分级,门店为核心 OPC 产业」
- **澄清**:用户纠正「租户管理员」→ 实为「集团管理员」(集团=Group),三级为 super_admin / 集团管理员 / 门店管理员
- **关键洞察**:用户确认「一家门店就是一个集团」(OPC 产业核心),由此简化 group_admin 为派生身份(D11),避免新增独立角色枚举
- **决策密度**:12 个决策点(D1-D12),其中 D1-D3 + D8 + D10-D12 用户直接确认,D4-D7 + D9 用户跳过后 agent 按最佳判断推荐(均给出推理依据,用户未推翻)
- **下一步**:本总纲落定后,各 feature 走 EP2 grill → spec → tickets(A 先,frontier)