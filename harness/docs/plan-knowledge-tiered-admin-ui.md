# 计划:知识库分级 Feature D — 前端分类管理 + 下发操作 UI(含后端接缝补齐)

> **id**: `knowledge-tiered-admin-ui`
> **状态**: in_progress(切片 01+02 ✅ 已交付;切片 03-05 待续。与 feature_list.json status=in_progress 一致)
> **优先级**: 87(feature_list.json;depends_on `knowledge-tiered-backend` p89 ✅ passing 已解锁)
> **创建日期**: 2026-08-07
> **来源**: Session 198 `/grill-with-docs` 收敛 13 决策(B1-B4 后端接缝补齐 + F1-F7 前端形态 + T1-T2 测试切片)
> **承接**: [`plan-knowledge-tiered-overview.md`](./plan-knowledge-tiered-overview.md)(系列总纲,D1-D12 决策)+ [`plan-knowledge-tiered-backend.md`](./plan-knowledge-tiered-backend.md)(Feature B ✅ passing,已交付 distribute/revoke + Category CRUD API)+ [`plan-knowledge-tiered-reader-ui.md`](./plan-knowledge-tiered-reader-ui.md)(Feature C ✅ passing,已交付三栏阅读 + 类型层 + msw + scope-badge 范式)

---

## 0. 范围扩展声明(为什么本 feature 含后端改动)

`knowledge-tiered-admin-ui` 在 feature_list.json 登记为「前端 Feature D」,但 EP2 grill 发现 **3 个后端接缝缺口**阻挡前端 admin-ui 落地(用户确认扩本 feature 范围含后端补齐,对齐 reader-ui 也含了类型层补齐的先例):

| 缺口 | 现状 | 阻挡的前端能力 |
|---|---|---|
| **B1** `/me` 不返回 `group_id`/`is_group_admin` | 前端无法判定 group_admin 派生身份 | scope 按角色过滤(F3)+ 下发按钮控制(F7)+ group_admin 专属管理 UI |
| **B2** `create_document` 不接 scope/category/group_id/tenant_id | service 层硬写 `tenant_id=当前门店`,server_default scope='store' | super_admin/group_admin 无法创建 platform/group scope 文档(D12 集团级知识落不了地) |
| **B3** 无 `GET /documents/{doc_id}/distributions` 端点 | backend 只有 POST(下发)/DELETE(撤回),无 list | 下发 Dialog 的「管理下发」视图无法显示已下发列表 + 撤回按钮 |

**决策**:本 feature 同时做后端补齐(切片 01)+ 前端 admin-ui(切片 02-05)。后端改动是「补 backend feature 已交付物的接缝」,非重建 —— 都消费 foundation 已建的表/权限派生逻辑。

---

## 1. Problem Statement

`knowledge-tiered-backend`(Feature B)已交付三级权限 + 分类 + 下发/撤回的完整后端 API,`knowledge-tiered-reader-ui`(Feature C)已交付三栏可视化阅读页,但**知识库分级管理的「管理侧」操作 UI 仍是空白**:

1. **下发/撤回无可视入口**:backend 的 `POST /knowledge/documents/{id}/distribute` 和 `DELETE /knowledge/distributions/{id}` 已就位,但前端没有任何按钮/Dialog 调它们。集团统一管控门店的「落地动作」(选目标门店/集团 → 下发 → 撤回)无 UI 落点。「集团统一话术下发到分店」(D3 显式下发)的最后一公里断了。
2. **上级无法创建上级 scope 文档**:`DocumentCreate` 当前只接 name/content/source_type,service 层硬写 `tenant_id=当前门店`。super_admin/group_admin 在前端无法创建 `scope=platform`/`scope=group` 的文档(D12 集团级知识、D2 scope 双维度分类无法兑现到创建路径)。
3. **Category 管理 CRUD 无 UI**:backend 的 `GET/POST/PUT/DELETE /knowledge/categories` 已就位(D5 预置+扩展),但前端无管理入口 —— 各级管理员(super_admin/group_admin/门店 owner)无法创建本级 Category 补充本地需求,Category 列表也无 scope 分组的管理视图。
4. **group_admin 派生身份前端不可见**:`is_group_admin(db, user_id, group_id)` 是 foundation 交付的派生身份判定,但 `/me` 不返回该信息。前端无法做「按角色过滤可选 scope」「下发按钮仅 group_admin+super_admin 可见」等权限按钮控制(F7)。reader-ui 的「group_admin 聚合视图」其实是靠 backend list 返回不同数据被动渲染,前端从没主动判过 group_admin。
5. **下发关系无可视管理**:撤回是下发的逆操作,但「这文档已下发给哪些门店」无 GET 端点。前端想显示「已下发列表 + 撤回按钮」无数据源,撤回只能撤当次 POST 返回的行(历史下发盲区)。

**用户痛点(承接 overview 背景)**:集团总部门店的 owner(group_admin 派生)需要一个「管控工作台」—— 选一篇集团话术 → 下发到本集团所有分店 → 看到哪些店已收到 → 必要时撤回。门店 owner 需要管理本店 Category(建「理疗话术」集团没有的主题)+ 录入文档时归类。super_admin 需要平台级知识治理。这些「管理动作」目前在 UI 层全部缺失。

**为什么现在做**:backend(987 测试)+ reader-ui(189 测试)均 passing,依赖解锁;WIP=1 下 admin-ui(p87)是当前最高优先级 not_started frontier。本 feature 是分级管理价值「从集团运营落到操作动作」的最后一环。

---

## 2. Solution

在 reader-ui 交付的三栏阅读页基础上,**加一个「管理」tab**(F1 同页 Tabs,门店 owner/admin 可见,member 只读),内部子 Tabs 分「文档与下发」/「分类管理」两块(F2)。配套补齐 3 个后端接缝(B1-B3)让前端有数据可用。

**四块能力**:
1. **文档与下发**(子 tab 1):文档表格(按 scope/group 过滤)+ 行操作「下发」(F4 Radio 切模式:按门店 Checkbox / 按集团 Select,XOR 构造 DistributeRequest)+「管理下发」(F5 显示已下发列表 GET /distributions + 每行撤回二次确认)。顶部「创建文档」按钮开 admin 表单(F3 getAvailableScopes 按角色过滤 scope + group/tenant 联动 + category 下拉)。
2. **分类管理**(子 tab 2):Category 列表按 scope 分组(F6 platform/group/store 卡片)+ 新建/编辑 Dialog(scope 可选范围按角色 + name + sort_order,scope 创建后不可改对齐后端 KnowledgeCategoryUpdate schema)+ 删除(软删)。
3. **后端接缝补齐**(切片 01):B1 MeResponse 加 `group_id`+`is_group_admin`;B2 DocumentCreate 加可选 `scope/group_id/tenant_id/category_id` + service 层 `_resolve_create_target` 校验;B3 新增 `GET /knowledge/documents/{doc_id}/distributions` 端点(service 层 `list_distributions_for_source` 三路径权限)。
4. **reader-ui 联动**(B4):reader-ui 的门店录入 Dialog 加 category 下拉(按本店可见 categories 过滤,scope 固定 store),让门店 owner 录入时可归类。零行为回归。

**权限模型**(F7):管理 tab 对 owner/admin(持 `knowledge:create`)可见,member 隐藏。tab 内按角色条件渲染:
- 「下发」「管理下发」按钮:仅 `isGroupAdmin(me) || isSuperAdmin(me)`(持 `knowledge:distribute`)
- 创建文档表单的 scope 下拉:`getAvailableScopes(me)` —— super_admin→[platform,group,store] / group_admin→[group,store] / 门店 owner/admin→[store] / member→[](不能创建)
- Category 管理的 scope 下拉:同上(各级管理员建本级 Category)
- 门店 owner 在管理 tab:本店文档只读(reader-ui 已能录入,管理 tab 不重复)+ 本店 Category store 管理 + 看本店被下发情况(只读)

**不做**(承接 overview Out of Scope):富文本编辑器 / PDF·Word 预览 / 完整移动端响应式 / 下发定时 / 批量重新下发 / 文档版本树 / Category scope 创建后迁移。

---

## 3. User Stories

> 覆盖 overview D1 三级角色 + 集团/平台管控视角 + 门店管理视角。

**下发/撤回(集团统一管控核心,D3)**
1. 作为 group_admin(派生身份),我想在管理 tab 选一篇集团文档后点「下发」,在弹出的 Dialog 里选「按集团」(默认本集团,锁定)或「按门店」(本集团分店多选),确认后下发,以便集团统一话术触达所有分店
2. 作为 group_admin,我想点「管理下发」看到某文档已下发给哪些门店(含已撤回的灰显),每行有「撤回」按钮 + 二次确认,以便必要时收回下发的知识
3. 作为 super_admin,我想下发 platform 文档到任意集团或指定门店(全平台范围选),以便平台统一知识治理
4. 作为 super_admin,我想撤回任意下发关系(跨集团全域),以便平台级收回
5. 作为 group_admin,我想下发时只能选本集团目标(跨集团目标不出现/禁用),以防误下发到别的集团(后端 is_group_admin 校验兜底)
6. 作为开发,下发到整个集团时,前端传 target_group_id,后端 service 层展开成该集团所有 tenant_id 批量插(G4,backend 已交付)
7. 作为平台运维,撤回 = 软标 is_active=false(保留审计痕迹),非硬删(D4)

**上级文档创建(D12 集团级 + D2 scope 双维度)**
8. 作为 super_admin,我想在创建文档表单选 scope=platform(目标层 = 平台,无 group/tenant),录入后文档 scope=platform 全局可见,以便建立平台级知识
9. 作为 group_admin,我想选 scope=group(group_id 默认本集团,锁定),录入后文档 scope=group 存集团层级,以便建立集团统一话术
10. 作为 group_admin,我想选 scope=group 时不能改 group_id(锁定本集团),以防误建到别的集团(后端 is_group_admin 校验兜底)
11. 作为门店 owner,我想创建文档表单的 scope 下拉只有 store(无 platform/group 选项),group/tenant 字段隐藏默认本店,以便我永远只建本店文档(防越权)
12. 作为任意创建者,我想在创建表单选 category(按所选 scope 可见的 categories 过滤),以便文档归类到主题(产品手册/FAQ/话术)

**Category 管理 CRUD(D5 预置+扩展)**
13. 作为 super_admin,我想在分类管理 tab 建 scope=platform 的 Category,以便建立全局统一业务语言
14. 作为 group_admin,我想建 scope=group 的 Category(补充本集团特有主题,如「理疗话术」),group_id 默认本集团锁定
15. 作为门店 owner,我想建 scope=store 的 Category(本店本地需求),tenant_id 默认本店锁定
16. 作为任意管理员,我想 Category 列表按 scope 分组显示(platform/group/store 分区),以便一眼看出「平台预置/集团扩展/本店自建」
17. 作为任意管理员,我想编辑 Category 的 name/sort_order(scope 创建后不可改,对齐后端 schema),以便修正名称或排序
18. 作为任意管理员,我想删除 Category(软删,name 释放可复用),以便清理废弃分类
19. 作为门店 member,我只能 read Category(不能创建/编辑/删除),管理 tab 对我隐藏(F7)

**权限按钮控制(F7 + D9)**
20. 作为门店 owner,我进管理 tab 能看到本店文档(只读,录入仍走 reader-ui)+ 本店 Category 管理 + 看本店被下发情况(只读),但看不到「下发」「管理下发」按钮(非 group_admin/super_admin)
21. 作为 group_admin,我对 knowledge 域有管理权(下发/管理下发/集团创建/集团 Category),但对 devices/bookings 等其他 object 无特殊权(D9 越界守卫,后端 foundation 已锁 obj=='knowledge' bypass)
22. 作为 member,我完全看不到管理 tab(无 knowledge:create),只读走 reader-ui 阅读页

**reader-ui 联动(B4)**
23. 作为门店 owner,我在 reader-ui 录入文档时能选 category(按本店可见 categories 过滤),以便录入时归类(零行为回归,仅加一个可选下拉)
24. 作为门店 owner,我不选 category 也能录入(默认 uncategorized,category_id=null),行为与现状一致

**管理 tab 入口与可见性(F1)**
25. 作为门店 owner/admin,我打开知识库页看到顶部「阅读」/「管理」两个 tab,默认「阅读」(reader-ui 三栏),切「管理」进管控面板
26. 作为 member,我只看到「阅读」tab(管理 tab 隐藏),无管理动作
27. 作为 group_admin/super_admin,我在管理 tab 看到完整的「文档与下发」+「分类管理」子 tab,所有按钮可用

---

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动(schema) | 1 | `app/schemas/document.py`(DocumentCreate 加 scope/group_id/tenant_id/category_id 可选)+ `app/schemas/auth.py`(MeResponse 加 group_id/is_group_admin) |
| 后端文件改动(service) | 2 | `app/services/knowledge_service.py`(create_document 加 `_resolve_create_target` 校验 + 新增 `list_distributions_for_source` 三路径)+ `app/services/auth_service.py` 或 `app/api/v1/auth.py` `_build_me_response`(反查 user 作为 HQ 门店 owner/admin 的 group + is_group_admin 计算) |
| 后端文件改动(api) | 1 | `app/api/v1/knowledge.py`(+ `GET /knowledge/documents/{doc_id}/distributions` 端点,require `knowledge:distribute`) |
| 后端文件改动(repository) | 1 | `app/repositories/knowledge_distribution.py`(+ `list_for_source(doc_id, active_only=False)` 方法,backend feature 切片03 已建 repo,本 feature 补 list_for_source) |
| 数据库迁移 | **0** | 无 schema 变化(只读现有 documents/knowledge_distribution/knowledge_categories 表 + group 反查);MeResponse 字段是计算字段非存储 |
| 前端文件改动 | ~12 | `pages/knowledge/index.tsx`(改:加 Tabs 阅读/管理编排);`pages/knowledge/admin-panel.tsx`(新:管理 tab 主体 + 子 Tabs);`pages/knowledge/document-form.tsx`(新:admin 创建文档表单 Dialog);`pages/knowledge/distribute-dialog.tsx`(新:F4 下发 Dialog);`pages/knowledge/distribution-list-dialog.tsx`(新:F5 管理下发 + 撤回二次确认);`pages/knowledge/category-manager.tsx`(新:F6 Category CRUD);`pages/knowledge/document-list.tsx`(改:B4 加 category 下拉);`lib/permission.ts`(加 `isGroupAdmin`/`getAvailableScopes` helper);`api/types.ts`(扩 DocumentCreate + MeResponse + 新 KnowledgeDistributionRead);`api/endpoints/knowledge.ts`(+ distributeDocument/revokeDistribution/listDistributions/create/update/deleteCategory);`hooks/queries/knowledge.ts`(+ useDistributeDocument/useRevokeDistribution/useDistributions/useCategoryMutations) |
| 新增测试类 | ~7 | 后端:扩 `tests/test_knowledge_backend.py`(MeResponse + create_document scope 校验 + list_distributions 三路径);前端:`__tests__/admin-panel.test.tsx` / `document-form.test.tsx` / `distribute-dialog.test.tsx` / `distribution-list-dialog.test.tsx` / `category-manager.test.tsx` / 扩 `knowledge-api.test.ts`(msw 锁新端点契约)+ 扩 `document-list.test.tsx`(B4 category 联动) |
| 新增依赖 | 0 | msw 已在 reader-ui 引入,复用;无新前端依赖 |
| Skill / Hook / 配置 | 0 | 无 |

### 4.2 多租户影响评估

- **是否新增租户 scoped 表?** NO —— 本 feature 不建表(foundation 已建好),只读现有表 + group 反查
- **是否修改现有租户隔离逻辑?** YES(受控) —— ① B2 `create_document` 加 scope 参数后,super_admin/group_admin 可创建非本店文档(scope=platform/group)。**关键守卫**:service 层 `_resolve_create_target` 严格校验 scope↔角色映射(scope=platform 需 super_admin / scope=group 需 is_group_admin(user, group_id) / scope=store 需本店 owner/admin),跨字段 binding(scope=group 必带 group_id / scope=store 必带 tenant_id / scope=platform 两者皆 null)。门店 owner 永远只能 scope=store(group_id null + tenant_id=本店),无越权路径。② B3 `list_distributions_for_source` 三路径权限:super_admin 看任意文档的下发 / group_admin 看「doc 属于本集团(scope=group 且 group_id=本集团 OR doc.tenant_id IN 本集团门店)」的下发 / 门店 owner 只看「doc 属于本店」的下发。跨集团/跨门店不可见。
- **是否引入跨租户访问点?** YES(受控) —— ① 下发操作本身是跨租户写(super_admin/group_admin 写入 knowledge_distribution 到其他 tenant_id),但这是 backend feature 切片03 已交付的能力(G4 + is_group_admin 校验),本 feature 只补 list 读路径;② list_distributions 的跨租户读受三路径 WHERE 约束(同 list_visible_for 范式)。所有跨租户访问都在 Repository 层 WHERE 显式约束,不靠 service「记得加过滤」(守铁律 #2)。
- **验证**:多租户测试用例 —— 门店 A 的 owner 不能下发(非 group_admin) / group_admin A 不能下发到 group B / group_admin A 不能 list group B 文档的下发关系 / 门店 owner 不能 list 其他门店文档的下发 / super_admin 全域 / 门店 owner 创建 scope=platform/group 被拒。

### 4.3 权限影响评估

- **是否新增 permission code?** **NO** —— 本 feature 复用现有 `knowledge:create`/`knowledge:read`/`knowledge:delete`/`knowledge:distribute`(distribute 在 backend feature 切片03 已加)。B3 list distributions 复用 `knowledge:distribute`(下发权限 = 看下发关系的权限,语义一致)。Category CRUD 复用 backend feature 切片01 的 scope 权限(service 层校验,不加 code)。
- **是否修改 DEFAULT_*_PERMS?** NO —— 现有 owner/admin 已持 `knowledge:create`/`knowledge:distribute`,member 不持;本 feature 不动 DEFAULT_*_PERMS。
- **是否影响 60+ 处 require_permission caller?** NO —— 现有 knowledge 端点 read/create/delete 的 require 不变;新增的 list_distributions 端点是新 require 调用点(`knowledge:distribute`),不改老 caller。
- **是否影响 graph.py 工具内 check?** NO —— retrieve_knowledge 工具不改(检索范围在 backend feature 切片02 已交付)。
- **scope 闸门**:本 feature 不涉及 API token scope。
- **group_admin 派生身份前端可见化(B1)**:MeResponse 加 `group_id`+`is_group_admin` 是「让前端看到后端已有的派生身份」,非新增权限。后端 `is_group_admin(db, user_id, group_id)` 逻辑不变,只是 `_build_me_response` 反查用户作为哪个 group 的 HQ 门店 owner/admin,把结果填进 MeResponse。**关键**:一人只管一个 group 的假设 —— 当前后端 `is_group_admin` 是单 group_id 参数化,本 feature 假定用户至多是一个 group 的 group_admin(MeResponse.group_id 单值)。若未来需多集团管理,扩 `admin_groups: []` 数组(留后续)。

### 4.4 数据库表设计 checklist

N/A —— 本 feature 不新建表、不加列、无 migration。只读现有表:
- `documents`(scope/group_id/tenant_id/category_id 已在 foundation 加)
- `knowledge_distribution`(foundation 已建)
- `knowledge_categories`(foundation 已建)
- `groups` + `group_tenants`(foundation 已建,反查 user 的 HQ 门店归属)

**索引考量**:`list_distributions_for_source` 按 `source_doc_id` 查,UniqueConstraint(source_doc_id, target_tenant_id)(backend feature 切片03 已建)兼作覆盖索引,无需新索引。

### 4.5 核心实施决策(B1-B4 + F1-F7 落地)

#### B1:MeResponse 加 group_id + is_group_admin 两字段

`_build_me_response`(`app/api/v1/auth.py`)扩展:
- 反查 `group_tenants` 找用户 `tenant_id` 所属的 group(`group_tenants.tenant_id = user.tenant_id`)
- 检查该 group 的 `headquarters_tenant_id` 是否 = 用户 `tenant_id`(用户是否是总部门店)
- 若是,检查用户在该总部门店的 role 是否 owner/admin(`user_tenants` SCD2 valid_to IS NULL)
- 若是,填 `group_id = 该 group.id` + `is_group_admin = True`
- 否则 `group_id = None` + `is_group_admin = False`

**为何单值 group_id**:对齐后端 `is_group_admin` 单 group_id 参数化范式;「一人管多集团」当前业务不存在(连锁总部一人管多品牌集团是极端 case,留后续)。前端 `isGroupAdmin(me) = me.is_group_admin` + `getMyGroupId(me) = me.group_id`。

#### B2:DocumentCreate 加可选 scope/group_id/tenant_id/category_id

`app/schemas/document.py` DocumentCreate 扩展(跨字段 binding 校验在 service 层 BizError,非 pydantic model_validator —— 避 422 序列化坑,对齐 CategoryCreate/BookingCreate 范式):

```python
class DocumentCreate(BaseModel):
    name: str
    content: str
    source_type: str = "text"
    # admin-ui 接缝补齐(B2):可选,默认 store 保持 reader-ui 零回归
    scope: str | None = None          # None→service 按 user 角色推导(门店=store)
    group_id: str | None = None       # scope=group 时必填
    tenant_id: str | None = None      # scope=store 时默认本店,scope=group/platform 留 null
    category_id: str | None = None    # 可选归类(B4 reader-ui 也启用)
```

`KnowledgeService.create_document` 加 `_resolve_create_target(user, payload)`:
- `scope=None`(reader-ui 旧路径)→ 推导 scope=store + tenant_id=user.tenant_id + group_id=None(零回归)
- `scope=store` → 校验 tenant_id=user.tenant_id 或 None(默认本店),group_id 必须 None
- `scope=group` → 校验 `is_group_admin(db, user_id, group_id)`(跨集团拒绝 BizError),tenant_id 必须 None
- `scope=platform` → 校验 `is_cross_tenant_viewer(platform_role)`(super_admin),group_id/tenant_id 必须 None
- 跨字段 binding 冲突 → BizError → 400(非 422)

category_id:校验存在 + scope 可见性(可选,后续优化;首版只校验非空存在)。

#### B3:新增 GET /knowledge/documents/{doc_id}/distributions

`app/api/v1/knowledge.py` + `app/repositories/knowledge_distribution.py`:
- 端点:`GET /knowledge/documents/{doc_id}/distributions`,require `knowledge:distribute`,响应 `list[KnowledgeDistributionRead]`(含已撤回 is_active=false,让前端区分)
- service 层 `list_distributions_for_source(doc_id, user, platform_role)` 三路径权限:
  - super_admin → 全部下发关系
  - group_admin → 仅当 doc 属于本集团(scope=group AND group_id=本集团)OR doc.tenant_id IN 本集团门店的下发关系
  - 门店 owner → 仅当 doc.tenant_id = 本店(自己创建的文档)的下发关系
  - 跨集团/跨门店 → NotFoundError(404,不泄露)
- repo `list_for_source(doc_id, active_only=False)`:返回所有下发关系含 is_active=false

#### B4:reader-ui 录入 Dialog 加 category 下拉

`frontend/src/pages/knowledge/document-list.tsx` 的录入 Dialog 加一个 category `<Select>`(数据源 `useKnowledgeCategories()` 按本店可见过滤:platform + 本集团 group + 本店 store),可选不选(默认 uncategorized)。scope 固定 store(门店用户不能选),零行为回归。DocumentCreate 类型加 category_id 可选字段(B2 已加),reader-ui 提交时透传选中的 category_id 或 undefined。

#### F1:同页 Tabs(阅读/管理)

`frontend/src/pages/knowledge/index.tsx` 改:顶部加 shadcn `<Tabs>`,「阅读」tab 渲染现有三栏(CategoryTree + DocumentList + MarkdownReader + RetrievalDebugCard),「管理」tab 渲染新 `<AdminPanel/>`。
- 默认 tab = 「阅读」
- 「管理」tab 可见性:`hasPermission(me, "knowledge", "create")`(owner/admin 可见,member 隐藏)—— F7
- index.tsx 选中态(selectedScope/selectedCategoryId/selectedDoc)只在「阅读」tab 用,「管理」tab 内部自管状态

#### F2:管理 tab 内子 Tabs(文档与下发 / 分类管理)

`frontend/src/pages/knowledge/admin-panel.tsx` 新建:shadcn `<Tabs>` 两个子 tab:
- 「文档与下发」:文档表格(useDocuments 按 scope/group 过滤)+ 行操作 DropdownMenu(下发/管理下发,仅 isGroupAdmin||isSuperAdmin)+ 顶部「创建文档」按钮(开 document-form Dialog)
- 「分类管理」:`<CategoryManager/>` 组件(F6)

#### F3:前端 getAvailableScopes(me) helper + scope 联动

`frontend/src/lib/permission.ts` 加:
```ts
export function isGroupAdmin(me): boolean { return !!me?.is_group_admin; }
export function getAvailableScopes(me): KnowledgeScope[] {
  if (isSuperAdmin(me)) return ["platform", "group", "store"];
  if (isGroupAdmin(me)) return ["group", "store"];
  if (hasPermission(me, "knowledge", "create")) return ["store"]; // 门店 owner/admin
  return []; // member
}
```

`document-form.tsx`:scope Select 选项从 `getAvailableScopes(me)` 派生。scope 变化联动:
- scope=platform → 隐藏 group/tenant 字段(两者 null)
- scope=group → 显示 group 下拉(选项 = me.group_id,锁定不可改,group_admin);super_admin 可选任意 group(useGroups)
- scope=store → 隐藏 group,显示 tenant(默认 me.tenant_id,锁定;super_admin 可选任意 tenant)
category 下拉:按所选 scope 过滤 useKnowledgeCategories(scope 匹配 + 可见性)

#### F4:下发 Dialog Radio 切模式

`frontend/src/pages/knowledge/distribute-dialog.tsx` 新建:
- RadioGroup「按门店」/「按集团」二选一(XOR 语义)
- 「按门店」:Checkbox 多选列表(super_admin → useAllTenants 全平台;group_admin → useGroups 的 me.group_id.tenants[] 展开,锁定本集团)
- 「按集团」:Select 单选(useGroups,group_admin 锁定 me.group_id 不可改)
- 提交:按模式构造 `{target_tenant_ids}` 或 `{target_group_id}`(XOR,后端 service 层二次校验)
- 重复下发 upsert re-enable(backend 切片03 已交付),前端 toast「已下发(含重新激活 N 条)」

#### F5:撤回两入口 + 管理下发 Dialog

文档表格行 DropdownMenu 两项:
- 「下发」→ 开 distribute-dialog(F4)
- 「管理下发」→ 开 distribution-list-dialog(`GET /documents/{doc_id}/distributions` 渲染已下发列表 + 每行「撤回」按钮 + 二次确认 Dialog)
- 仅 `isGroupAdmin(me) || isSuperAdmin(me)` 可见(F7)
- 撤回:调 `DELETE /knowledge/distributions/{dist_id}`(backend 切片03 已交付),二次确认 Dialog(feature_list.json verification 硬约束)

#### F6:Category 管理 scope 分组列表 + CRUD Dialog

`frontend/src/pages/knowledge/category-manager.tsx` 新建:
- 列表按 scope 分组(platform/group/store 三个 Card 区块,对齐 reader-ui category-tree 的 scope 分区范式)
- 顶部「新建分类」按钮 → Dialog:scope Select(getAvailableScopes 过滤)+ name Input + sort_order Input;scope=group 时 group_id 默认 me.group_id(隐藏)/scope=store 时 tenant_id 默认 me.tenant_id(隐藏)/scope=platform 两者 null
- 每行 Category:DropdownMenu「编辑」/「删除」
- 编辑 Dialog:只改 name/sort_order(scope 不可改,对齐后端 KnowledgeCategoryUpdate schema)+ 后端 PUT
- 删除:二次确认 + 后端 DELETE(软删)

#### F7:管理 tab 可见性 + 按角色条件渲染

- 管理 tab 可见:`hasPermission(me, "knowledge", "create")`(owner/admin 可见,member 隐藏)
- 下发/管理下发按钮:`isGroupAdmin(me) || isSuperAdmin(me)`(持 distribute)
- 创建文档表单 scope 下拉:`getAvailableScopes(me)` 过滤
- Category 管理 scope 下拉:同上
- 门店 owner 在管理 tab:本店文档只读(不显示「创建文档」按钮,reader-ui 已能录入)+ 本店 Category store 管理 + 看本店被下发情况(只读,不显示「下发/管理下发」)

> **职责切割(避免重复)**:门店 owner 的「本店文档创建」留在 reader-ui(B4 加 category),管理 tab 的「创建文档」按钮仅 `isGroupAdmin(me) || isSuperAdmin(me)` 可见(上级创建)。门店 owner 进管理 tab 只为 Category store 管理 + 看本店文档被下发情况。这样 reader-ui 与 admin-ui 无功能重复。

### 4.6 测试 seam 决策(T2)

**后端单 seam**(扩 `tests/test_knowledge_backend.py`,沿用 backend feature 范式):
- B1:`_build_me_response` 对 group_admin 用户返回 group_id+is_group_admin=True / 普通门店用户返回 null+False / super_admin 返回 null+False(非 group_admin)
- B2:create_document scope 校验矩阵(scope=None 零回归 / store 本店 / group is_group_admin 校验 / platform super_admin / 跨字段 binding 冲突 400 / category_id 可选)
- B3:list_distributions 三路径(super_admin 全部 / group_admin 本集团 / 门店 owner 本店 / 跨集团 404)

**前端双 seam**(沿用 reader-ui 范式):
1. **mock-hook 组件测试**(主 seam):每个新组件一个 test 文件(admin-panel/document-form/distribute-dialog/distribution-list-dialog/category-manager),`renderWithProviders` + `vi.mock("@/hooks/queries")` stub hooks + `vi.mock("@/components/auth/auth-context")` 注入角色(覆盖角色矩阵:member/owner/group_admin/super_admin)
2. **msw API 集成测试**(扩 `knowledge-api.test.ts`):锁新端点契约 —— distributeDocument 请求构造(XOR)/ revokeDistribution DELETE / listDistributions GET / create/update/delete Category,沿用 reader-ui 切片01 引入的 msw 基建(`@/test/msw-server`)
3. **B4 reader-ui 联动**:扩 `document-list.test.tsx`(录入 Dialog category 下拉渲染 + 选中提交透传 category_id + 不选默认 undefined 零回归)

### 4.7 镜像范式对照

| 范式点 | reader-ui(参照) | admin-ui(本 feature) |
|---|---|---|
| 页面结构 | 三栏阅读(CategoryTree + DocumentList + MarkdownReader) | 同页 Tabs(阅读 + 管理),管理内子 Tabs(文档与下发 + 分类管理) |
| 子组件 data 流 | 子组件自调 hook(G1) | 同(admin-panel/document-form/distribute-dialog 等自调 hook) |
| scope 来源标识 | ScopeBadge 三色实心(reader-ui G3) | 复用 ScopeBadge(展示)+ 新 getAvailableScopes(选择) |
| 类型层 | DocumentRead + KnowledgeCategoryRead(reader-ui G6) | 扩 DocumentCreate + MeResponse + 新 KnowledgeDistributionRead |
| msw 基建 | reader-ui 切片01 引入 | 复用 `@/test/msw-server` |
| 权限按钮 | hasPermission(me, knowledge, create/delete) | 复用 + 新 isGroupAdmin/getAvailableScopes |
| 角色注入测试 | renderWithProviders + vi.mock auth-context | 同范式 |

**差异**:reader-ui 是「阅读 + 门店 CRUD」,admin-ui 是「管控 + 上级创建 + 下发管理」,职责正交(F1/F2 Tabs 切分)。门店 owner 的本店 CRUD 留 reader-ui(B4),admin 专注上级 + Category 管理。

---

## 5. Testing Decisions

- **测试金字塔**:后端 unit/集成 ~10 用例(扩 test_knowledge_backend)+ 前端组件 ~20 用例(mock-hook)+ msw API 集成 ~8 用例 = ~38 用例
- **后端测试库**:SQLite 内存库(对齐 backend feature 范式);检索相关不涉及(本 feature 不改 search_by_embedding)
- **前端测试库**:vitest + jsdom + msw(沿用 reader-ui)
- **覆盖率目标**:新代码(create_document scope 校验 / list_distributions / MeResponse group 反查 / 5 个新前端组件)全覆盖;角色矩阵(member/owner/group_admin/super_admin)每角色至少 1 断言
- **prior art**:`tests/test_knowledge_backend.py`(backend feature 三路径测试范式)+ `frontend/src/pages/knowledge/__tests__/`(reader-ui 组件测试范式)+ `frontend/src/pages/devices/__tests__/`(角色注入 + target picker 范式)
- **边界 case 清单**:
  - **B1 MeResponse**:group_admin 用户 group_id 正确 / 普通门店 null / super_admin null / hq_staff null / 用户在非 HQ 门店是 owner(非 group_admin)
  - **B2 create_document**:scope=None 零回归(reader-ui 旧路径)/ store 本店 / group is_group_admin 通过 + 跨集团拒绝 / platform super_admin 通过 + 非 super_admin 拒绝 / 跨字段 binding 冲突(scope=group 但无 group_id → 400)/ category_id 可选
  - **B3 list_distributions**:super_admin 全部 / group_admin 本集团(scope=group 的 doc + 本集团门店的 store doc)/ 门店 owner 本店 doc / 跨集团 404 / 跨门店 404 / 含 is_active=false(撤回的)
  - **F3 getAvailableScopes**:4 角色映射(member空/storeowner[group_admin[group+store/super[全)
  - **F4 下发 Dialog**:Radio 切模式 / 按门店多选构造 target_tenant_ids / 按集团单选构造 target_group_id / XOR 防互斥 / group_admin 锁定本集团 / super_admin 全平台 / 重复下发 toast
  - **F5 撤回**:管理下发列表渲染 / 撤回二次确认 / 撤回后列表更新(is_active=false 灰显)/ 跨集团不可见
  - **F6 Category CRUD**:scope 分组渲染 / 新建 Dialog scope 过滤 / 编辑只改 name/sort_order / 删除二次确认 / scope=group 锁 group_id
  - **F7 权限按钮**:member 无管理 tab / 门店 owner 有管理 tab 无下发按钮 / group_admin 全套 / super_admin 全套
  - **B4 reader 联动**:录入 Dialog category 下拉 + 选中提交 + 不选默认 undefined 零回归
  - **回归**:reader-ui 三栏阅读 + CRUD + RetrievalDebugCard 零行为回归(B4 只加可选 category 下拉)

---

## 6. 切片规划(对齐 to-tickets tracer-bullet)

> **切片策略**:5 切片线性依赖(T1),首片后端接缝补齐(可独立 ./init.sh full 验证),后续 4 片前端按 F1/F2 子 tab 边界切。每片切穿「类型层 → hook → 组件 → test」全栈(前端)或「schema → service → api → test」全栈(后端),单片可独立 demo/verify。
>
> **切片依赖图**:
> ```
> 01(后端接缝补齐:B1+B2+B3) ──→ 02(管理 tab 骨架 + 创建文档表单 F1+F2+F3) ──→ 03(下发 Dialog + 管理下发撤回 F4+F5) ──→ 04(Category 管理 CRUD F6) ──→ 05(reader-ui category 联动 B4 + 集成验证收尾)
> ```

详见下方「实施切片」段(to-tickets 产出)。5 切片线性依赖(01→02→03→04→05),首片无 blocker 可立即开工。

---

## 7. v1 → v2 对抗式审查段

**触发条件评估**:
- 改动文件 ~12 后端 + 前端(>10 边界)→ 触发
- 涉及鉴权/权限? **YES**(B1 group_admin 派生身份前端可见化 + B2 create_document scope 越权校验 + B3 list_distributions 跨租户读)→ 触发
- 涉及数据迁移/跨服务? NO(无 migration)/ 跨 service(knowledge_service + auth_service + permission_service 反查)→ 接近触发
- 涉及安全敏感操作? NO(token/key 不碰)
- 涉及不可逆操作? NO(纯加法 + 接缝补齐,无删列改类型)

**结论**:**本 feature 属复杂任务**(改动文件超阈值 + 鉴权/权限/跨租户读)。v1 阶段**触发对抗式审查**。审查方式:EP2 收尾 plan 自检后,跑 `/code-review` 双轴(Standards + Spec)审 plan,或 EP3 实施首切片(切片01 后端)前审查。审查产出回写本 plan §0。

**审查重点**(预期 🔴/🟡/🟢):
- 🔴 B2 `_resolve_create_target` scope↔角色校验是否覆盖所有越权路径(防门店 owner 传 scope=group 绕过 / 防 group_admin 传别集团的 group_id)
- 🔴 B3 `list_distributions_for_source` 三路径 WHERE 是否真的覆盖所有角色分支(防门店 owner 看其他门店文档的下发 / 防跨集团泄露)
- 🔴 B1 `_build_me_response` 反查 group_admin 的逻辑是否与 `is_group_admin` helper 一致(避免前端看到的 is_group_admin 与后端 require 判定不一致 → 按钮显示但 API 拒绝的撕裂)
- 🟡 F3 getAvailableScopes 与后端 _resolve_create_target 角色映射是否对齐(前端显示的 scope 选项 = 后端允许的 scope,防前端显示但后端拒绝)
- 🟡 F4 group_admin 下发锁定本集团是否前端 + 后端双守卫(前端锁 UI + 后端 is_group_admin 校验兜底)
- 🟢 F7 门店 owner 在管理 tab 的「本店文档只读」是否真的不显示创建按钮(职责切割,防与 reader-ui 重复)
- 🟢 B4 reader-ui category 联动是否零回归(只加可选下拉,不动现有提交逻辑)

> 实施期每个切片仍走 `/code-review` 双轴(EP3 硬规则),与本节 v1→v2 审查独立。

---

## 8. Out of Scope

承接 overview Out of Scope + 本 feature 边界:

- ❌ 富文本/Markdown 文档**编辑器**(创建仍只 textarea 纯文本,编辑留后续)
- ❌ PDF/Word 预览(系列级 Out of Scope)
- ❌ **下发定时 / 批量重新下发**(单个操作即时下发,feature_list.json notes 明示)
- ❌ **文档版本树 / 历史版本**(下发是引用,上级改门店即时看到,不做版本)
- ❌ **Category scope 创建后迁移**(scope 创建后不可改,对齐后端 KnowledgeCategoryUpdate schema;改层级 = 删除 + 重建)
- ❌ **一人管多集团**(MeResponse.group_id 单值;若未来需多集团管理,扩 admin_groups 数组,留后续)
- ❌ **完整移动端响应式**(沿用 reader-ui lg 断点,完整移动端归移动端系列)
- ❌ **改 group_admin 派生身份判定逻辑**(foundation 已锁 is_group_admin + obj=='knowledge' bypass;本 feature 只让前端看到,不改判定)
- ❌ **改 backend feature 已交付的 distribute/revoke/Category CRUD API**(本 feature 只补 list distributions 读端点 + 扩 create_document 接缝,不动已交付端点)
- ❌ **reader-ui 三栏阅读行为回归**(B4 只加可选 category 下拉,不动三栏结构)
- ❌ **devices/bookings 域**(D9,group_admin 派生身份仅知识库域)

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| B2 `_resolve_create_target` scope 越权校验漏角色分支(门店 owner 传 scope=group 绕过) | 高 | service 层严格校验 scope↔角色映射 + 跨字段 binding;测试矩阵覆盖 4 角色 × 3 scope × 跨字段冲突;前端 getAvailableScopes 与后端映射对齐(F3)|
| B3 `list_distributions_for_source` 三路径 WHERE 漏分支(门店看其他门店下发) | 高 | 三路径显式 WHERE 在 Repository 层(守铁律 #2);测试矩阵覆盖 4 角色边界 + 跨集团/跨门店 404 |
| B1 `_build_me_response` 反查 group_admin 与 is_group_admin helper 不一致(前端显示但 API 拒绝) | 高 | 反查逻辑复用 is_group_admin 的判定条件(HQ 门店 + owner/admin role);测试覆盖一致性 |
| F3 getAvailableScopes 与后端 _resolve_create_target 角色映射不对齐 | 中 | 前后端映射同源(基于 me.is_group_admin + platform_role);前端显示 = 后端允许 |
| reader-ui B4 加 category 下拉引入行为回归 | 中 | 只加可选下拉,默认 undefined 等价不传;扩 document-list.test 验零回归 |
| 同页 Tabs(F1)破坏 reader-ui 三栏布局 | 低 | index.tsx 改 barrel+Tabs,阅读 tab 内部渲染原三栏(零变化);Tabs 切换不持久化选中态 |
| 门店 owner 在管理 tab 看到与 reader-ui 重复的创建入口 | 低 | 职责切割:管理 tab「创建文档」按钮仅 group_admin+super 可见;门店 owner 创建走 reader-ui(B4)|
| msw 测试与 mock-hook 测试边界模糊(新组件该用哪个) | 低 | API 契约层用 msw(请求构造 + 响应解析),组件交互行为用 mock-hook(沿用 reader-ui 双 seam 范式)|

---

## 10. 验收标准(同步 feature_list.json verification)

1. **后端接缝补齐**(切片 01):`app/schemas/auth.py` MeResponse 加 `group_id: str \| None` + `is_group_admin: bool`;`_build_me_response` 反查填充;`app/schemas/document.py` DocumentCreate 加可选 `scope/group_id/tenant_id/category_id`;`KnowledgeService.create_document` 加 `_resolve_create_target` scope↔角色校验(scope=None 零回归 / store 本店 / group is_group_admin / platform super_admin);`app/api/v1/knowledge.py` 新增 `GET /knowledge/documents/{doc_id}/distributions`(require knowledge:distribute)+ `list_distributions_for_source` 三路径
2. **前端管理 tab 框架**(切片 02):`pages/knowledge/index.tsx` 加 Tabs(阅读/管理,管理对 owner/admin 可见);`pages/knowledge/admin-panel.tsx` 子 Tabs(文档与下发 / 分类管理);`pages/knowledge/document-form.tsx` admin 创建表单(scope 下拉 getAvailableScopes 过滤 + group/tenant 联动 + category 下拉);`lib/permission.ts` 加 `isGroupAdmin` + `getAvailableScopes`
3. **下发/撤回 UI**(切片 03):`distribute-dialog.tsx`(Radio 切按门店/按集团 + Checkbox/Select + XOR 构造 DistributeRequest + group_admin 锁本集团)+ `distribution-list-dialog.tsx`(GET list 渲染已下发 + 每行撤回二次确认);`hooks/queries/knowledge.ts` 加 useDistributeDocument/useRevokeDistribution/useDistributions;行菜单「下发」「管理下发」两入口(仅 group_admin+super 可见)
4. **Category 管理 CRUD**(切片 04):`category-manager.tsx` scope 分组列表 + 新建 Dialog(scope 过滤 + name + sort_order)+ 编辑 Dialog(只改 name/sort_order)+ 删除二次确认;`api/endpoints/knowledge.ts` 加 create/update/deleteCategory;hooks 加 useCreateCategory/useUpdateCategory/useDeleteCategory
5. **reader-ui category 联动 + 收尾**(切片 05):`document-list.tsx` 录入 Dialog 加 category 下拉(按本店可见过滤,可选,默认 undefined 零回归)
6. **类型层**:`api/types.ts` DocumentCreate 加 scope/group_id/tenant_id/category_id 可选 + MeResponse 加 group_id/is_group_admin + 新 KnowledgeDistributionRead;`api/endpoints/knowledge.ts` 扩;`hooks/queries/knowledge.ts` 扩
7. **测试** ~38 用例(后端 ~10 扩 test_knowledge_backend + 前端组件 ~20 + msw ~8)+ `npm test` 全绿 + `npm run build` 0 错 + `tsc -b` 0 错 + `oxlint` 0/0 + `./init.sh full` 后端零回归(后端改动是补接缝,backend feature 987 测试不破)
8. **零行为回归**:reader-ui 三栏阅读 + CRUD + RetrievalDebugCard 行为不变(B4 只加可选 category);现有 knowledge 端点 read/create/delete/retrieve 行为零变化(B2 scope=None 零回归路径)

---

## 11. 不越界声明

本次改动**只**涉及:
- **后端接缝补齐**(切片 01):`app/schemas/auth.py`(MeResponse 加字段)+ `app/schemas/document.py`(DocumentCreate 加可选字段)+ `app/services/knowledge_service.py`(create_document 加 _resolve_create_target + 新增 list_distributions_for_source)+ `app/api/v1/auth.py`(`_build_me_response` 反查 group_admin)+ `app/api/v1/knowledge.py`(+ GET distributions 端点)+ `app/repositories/knowledge_distribution.py`(+ list_for_source 方法)
- **前端 admin-ui**(切片 02-04):`frontend/src/pages/knowledge/` 新文件(admin-panel/document-form/distribute-dialog/distribution-list-dialog/category-manager)+ `index.tsx` 改 Tabs + `lib/permission.ts` 加 helper + `api/types.ts` 扩 + `api/endpoints/knowledge.ts` 扩 + `hooks/queries/knowledge.ts` 扩 + `__tests__/` 测试文件
- **reader-ui 联动**(切片 05):`document-list.tsx` 录入 Dialog 加 category 下拉 + 扩 `document-list.test.tsx`

**不**触碰:
- 后端已交付的 distribute/revoke/Category CRUD API 逻辑(backend feature 切片01-04 不动)
- foundation 的数据模型 + 权限派生逻辑(Group/GroupTenant/knowledge_categories/knowledge_distribution 表 + is_group_admin helper 不改)
- 数据库 migration(无 schema 变化)
- permission code / DEFAULT_*_PERMS / casbin 策略(复用现有)
- graph.py retrieve_knowledge 工具(检索范围 backend feature 切片02 已交付)
- reader-ui 的三栏结构 / Markdown 阅读器 / 检索调试卡(B4 只加可选 category 下拉)
- devices/bookings/customers/chat 等其他前端 page
- hq_staff 语义 / 门店间隔离逻辑(铁律)

---

## 实施切片(EP2 to-tickets 产出)

> **5 个 tracer-bullet 垂直切片,严格串行**(`01 → 02 → 03 → 04 → 05`)。切片 01 切穿 schema→service→api→test(后端全栈),切片 02-05 切穿 类型层→hook→组件→test(前端全栈)。每片可独立验证(后端 `./init.sh full` / 前端 `npm test` + `npm run build`)。frontier = 切片 01(无 blocker)。

### 切片依赖图

```
01(后端接缝补齐:B1 MeResponse + B2 DocumentCreate scope + B3 list distributions)
  │
  └─→ 02(管理 tab 框架 + 创建文档表单:F1 同页 Tabs + F2 子 Tabs + F3 getAvailableScopes)
        │
        └─→ 03(下发 Dialog + 管理下发撤回:F4 Radio 切模式 + F5 两入口 + 二次确认)
              │
              └─→ 04(Category 管理 CRUD:F6 scope 分组 + 新建/编辑/删除 Dialog)
                    │
                    └─→ 05(reader-ui category 联动 B4 + 集成验证收尾,末切片)
```

### AC 覆盖映射

(对照 §10 验收标准 8 条):切片 01 覆盖 AC1(后端接缝)+ AC6 部分(类型层后端);切片 02 覆盖 AC2(管理 tab 框架 + 创建表单)+ AC5(helper);切片 03 覆盖 AC3(下发/撤回 UI)+ AC6 部分(下发类型层);切片 04 覆盖 AC4(Category 管理)+ AC6 部分(Category 类型层);切片 05 覆盖 AC5(reader category 联动)+ AC7(全量验证)+ AC8(零回归)+ feature 收尾仪式。

---

### 切片 01 — 后端接缝补齐(B1 MeResponse + B2 DocumentCreate scope + B3 list distributions)✅

- **What it delivers**:补齐阻挡 admin-ui 的 3 个后端接缝,让前端有数据可用。① `/me` 返回 `group_id` + `is_group_admin`(用户作为哪个集团的 HQ 门店 owner/admin,前端可判 group_admin 派生身份);② `create_document` 接受可选 `scope/group_id/tenant_id/category_id`,service 层 `_resolve_create_target` 按 scope↔角色校验(super_admin 建 platform / group_admin 建 group / 门店 owner 建 store,跨集团/跨字段冲突 BizError → 400),scope=None 零回归路径保 reader-ui 旧行为;③ 新增 `GET /knowledge/documents/{doc_id}/distributions` 端点(list 某文档已下发给哪些门店,含已撤回 is_active=false),service 层三路径权限(super_admin 全部 / group_admin 本集团 / 门店 owner 本店)。此切片完成后,前端 admin-ui 的所有数据依赖就位,切片 02-05 可纯前端推进。

- **Blocked by**: 无(frontier,可立即开工)

- **Acceptance criteria**:
  - [x] `app/schemas/auth.py` MeResponse 加 `group_id: str | None = None` + `is_group_admin: bool = False`(向前兼容,既有响应多两字段)
  - [x] `app/api/v1/auth.py` `_build_me_response` 扩展:反查用户 `tenant_id` 所属 group → 该 group 的 `headquarters_tenant_id` 是否 = 用户 tenant_id → 用户在该 HQ 门店 role 是否 owner/admin(SCD2 valid_to IS NULL)→ 填 `group_id` + `is_group_admin=True`;否则 null+False。反查逻辑与 `is_group_admin(db, user_id, group_id)` helper 判定条件一致(避免前端显示与后端 require 撕裂)
  - [x] `app/schemas/document.py` DocumentCreate 加可选 `scope: str | None = None` + `group_id: str | None = None` + `tenant_id: str | None = None` + `category_id: str | None = None`(默认 None 保持 reader-ui 零回归)
  - [x] `app/services/knowledge_service.py` `create_document` 加 `_resolve_create_target(user, payload)`:scope=None → 推导 store+本店 tenant(零回归)/ scope=store → 校验 tenant_id=本店或 None + group_id None / scope=group → 校验 `is_group_admin(db, user_id, group_id)` + tenant_id None / scope=platform → 校验 `is_cross_tenant_viewer(platform_role)` + group_id/tenant_id None;跨字段 binding 冲突 BizError → 400(非 pydantic model_validator,避 422 序列化坑,对齐 CategoryCreate/BookingCreate 范式);category_id 可选(非空时校验存在)
  - [x] `app/repositories/knowledge_distribution.py` 加 `list_for_source(doc_id, active_only=False)` 方法:返回某文档所有下发关系(含 is_active=false),backend feature 切片03 已建 repo,本切片补该方法
  - [x] `app/services/knowledge_service.py` 加 `list_distributions_for_source(doc_id, user, platform_role)` 三路径权限:super_admin 看任意 / group_admin 看「doc 属于本集团(scope=group AND group_id=本集团)OR doc.tenant_id IN 本集团门店」/ 门店 owner 看「doc.tenant_id=本店」;跨集团/跨门店 NotFoundError(404 不泄露)
  - [x] `app/api/v1/knowledge.py` 新增 `GET /knowledge/documents/{doc_id}/distributions` 端点,require `knowledge:distribute`,响应 `list[KnowledgeDistributionRead]`(含 is_active=false)
  - [x] 测试扩 `tests/test_knowledge_backend.py`:B1 MeResponse(group_admin 用户 group_id 正确 / 普通门店 null / super_admin null / 用户在非 HQ 门店是 owner 非 group_admin)+ B2 create_document scope 矩阵(scope=None 零回归 / store 本店 / group is_group_admin 通过 + 跨集团拒绝 / platform super_admin 通过 + 非 super 拒绝 / 跨字段 binding 冲突 400 / category_id 可选)+ B3 list_distributions 三路径(super_admin 全部 / group_admin 本集团 / 门店 owner 本店 / 跨集团 404 / 跨门店 404 / 含 is_active=false)
  - [x] `./init.sh full` 全绿(backend feature 987 baseline 零回归,含新章节);ruff clean
  - [x] 现有 reader-ui 调用 createDocument 路径零回归(scope=None 推导本店,行为不变)

> **非末切片**(02-05 待做),不动 feature_list.json status/evidence(末切片的事)。

---

### 切片 02 — 管理 tab 框架 + 创建文档表单(F1 同页 Tabs + F2 子 Tabs + F3 getAvailableScopes)✅

- **What it delivers**:admin-ui 的「骨架 + 第一块功能」落地。知识库页顶部出现「阅读」/「管理」两个 tab(管理对 owner/admin 可见,member 隐藏)。切「管理」进子 Tabs(文档与下发 / 分类管理)。文档与下发子 tab 先交付「创建文档」表单 —— super_admin 看到 scope 下拉(platform/group/store 全选)+ group/tenant/category 联动;group_admin 看到 scope(group/store)+ group 锁定本集团;门店 owner 看到 scope(仅 store)+ 创建按钮在管理 tab 隐藏(职责切割,门店创建走 reader-ui)。配套 `lib/permission.ts` 加 `isGroupAdmin` + `getAvailableScopes` helper。此切片完成后,管理 tab 骨架就位,下发/Category 可在后续切片填入。

- **Blocked by**: 切片 01(B1 me.is_group_admin + B2 DocumentCreate scope 字段 + B3 类型层)

- **Acceptance criteria**:
  - [x] `frontend/src/api/types.ts` 扩:DocumentCreate 加 `scope?/group_id?/tenant_id?/category_id?` 可选;MeResponse 加 `group_id: string | null` + `is_group_admin: boolean`;新 `KnowledgeDistributionRead`(id/source_doc_id/target_tenant_id/distributed_by/distributed_at/is_active)
  - [x] `frontend/src/api/endpoints/knowledge.ts` 扩:`createDocument` 透传 scope/group_id/tenant_id/category_id(可选);新增 `distributeDocument(docId, payload)` + `revokeDistribution(distId)` + `listDistributions(docId)` + `createCategory/updateCategory/deleteCategory`(后两者切片04 用,本切片先落 endpoint)
  - [x] `frontend/src/hooks/queries/knowledge.ts` 扩:`useCreateDocument` 透传新字段;qk 加 `documentDistributions(docId)`;新增 `useDistributeDocument`/`useRevokeDistribution`/`useDistributions(docId)`/`useCreateCategory`/`useUpdateCategory`/`useDeleteCategory`
  - [x] `frontend/src/lib/permission.ts` 加:`isGroupAdmin(me) = !!me?.is_group_admin` + `getAvailableScopes(me)`(super→[platform,group,store] / group_admin→[group,store] / owner/admin→[store] / member→[])
  - [x] `frontend/src/pages/knowledge/index.tsx` 改:顶部 shadcn `<Tabs>`(「阅读」= 现有三栏 / 「管理」= `<AdminPanel/>`);默认阅读 tab;管理 tab 可见性 `hasPermission(me, "knowledge", "create")`;选中态只在阅读 tab 用
  - [x] `frontend/src/pages/knowledge/admin-panel.tsx` 新建:子 `<Tabs>`(文档与下发 / 分类管理);文档与下发子 tab 渲染文档表格(useDocuments)+ 顶部「创建文档」按钮(仅 `isGroupAdmin(me) || isSuperAdmin(me)` 可见,F7 职责切割)+ 占位「分类管理」子 tab(切片04 填)
  - [x] `frontend/src/pages/knowledge/document-form.tsx` 新建:admin 创建文档表单 Dialog;scope Select(getAvailableScopes 过滤)+ scope 联动(scope=platform 隐藏 group/tenant / scope=group 显示 group 锁定 me.group_id,super_admin 可选 useGroups / scope=store 显示 tenant 默认 me.tenant_id)+ category 下拉(按所选 scope 过滤 useKnowledgeCategories)+ name/content/source_type(沿用 reader-ui 范式);提交调 useCreateDocument 透传 scope/group_id/tenant_id/category_id
  - [x] `__tests__/admin-panel.test.tsx`: Tabs 渲染(阅读/管理)+ member 无管理 tab + owner/admin 有管理 tab + 子 Tabs 切换
  - [x] `__tests__/document-form.test.tsx`:scope 下拉按角色过滤(member 空 / owner 仅 store / group_admin group+store / super 全)+ scope 联动 group/tenant 显隐 + group_admin group 锁定 + category 下拉过滤 + 提交透传字段
  - [x] 扩 `__tests__/knowledge-api.test.ts`(msw):createDocument 带 scope/group_id 请求构造 + distributeDocument XOR 请求构造 + listDistributions GET 契约(锁新端点契约)
  - [x] 验证:`npm test` 全绿 + `npm run build` 0 错 + `tsc -b` 0 错 + `oxlint` 0/0;reader-ui 三栏阅读零回归(阅读 tab 渲染原结构)

> **实现偏离(AC5/AC6,用户确认)**:plan 字面写「shadcn `<Tabs>`」,实际用「plain button list + useState activeId」范式(镜像 settings-page.tsx,项目惯例)。原因:`@radix-ui/react-tabs` 在 package.json 声明但 node_modules 未装、src 零引用,settings-page 注释明示「no new Radix Tabs wrapper component」。功能等价(Tabs 切换 + 可见性守卫),零新依赖。code-review 双轴(Standards 0 硬违规 + Spec 0 偏差)确认可接受。

> **非末切片**(03-05 待做),不动 feature_list.json status/evidence。

---

### 切片 03 — 下发 Dialog + 管理下发撤回(F4 Radio 切模式 + F5 两入口 + 二次确认)✅

- **What it delivers**:下发/撤回操作 UI 落地,集团统一管控门店的「动作链」打通。文档表格每行 DropdownMenu 出现「下发」「管理下发」两入口(仅 group_admin+super 可见)。点「下发」开 Dialog:Radio 切「按门店」(Checkbox 多选,group_admin 锁本集团分店 / super 全平台)或「按集团」(Select 单选,group_admin 锁 me.group_id),确认后调 POST distribute,toast 提示(含重新激活数)。点「管理下发」开 Dialog:`GET /documents/{doc_id}/distributions` 渲染已下发列表(含已撤回灰显),每行「撤回」按钮 + 二次确认,调 DELETE revoke。此切片完成后,D3 显式下发语义端到端 UI 跑通。

- **Blocked by**: 切片 02(管理 tab 骨架 + AdminPanel + hooks/endpoints)

- **Acceptance criteria**:
  - [x] `frontend/src/pages/knowledge/distribute-dialog.tsx` 新建:props `{ docId, open, onOpenChange }`;RadioGroup「按门店」/「按集团」二选一(XOR 语义);按门店 = Checkbox 多选(group_admin → useGroups 的 me.group_id.tenants[] 展开,锁定本集团;super → useAllTenants 全平台);按集团 = Select 单选(useGroups,group_admin 锁 me.group_id 不可改);提交按模式构造 `{target_tenant_ids}` 或 `{target_group_id}`(XOR);调 useDistributeDocument;toast「已下发(N 条,含重新激活 M 条)」;空选校验
  - [x] `frontend/src/pages/knowledge/distribution-list-dialog.tsx` 新建:props `{ docId, open, onOpenChange }`;自调 `useDistributions(docId)`(GET /documents/{doc_id}/distributions);渲染已下发列表(门店名 + distributed_at + is_active 状态:生效绿/已撤回灰);每行「撤回」按钮(is_active=true 才可点)+ 二次确认 Dialog;调 useRevokeDistribution;撤回后列表刷新(is_active=false 灰显)
  - [x] `frontend/src/pages/knowledge/admin-panel.tsx` 文档表格行 DropdownMenu 加「下发」「管理下发」两入口:仅 `isGroupAdmin(me) || isSuperAdmin(me)` 可见(F7);门店 owner 隐藏这两项(本店文档被下发情况只读由 distribution-list-dialog 在 owner 视角降级,或 owner 不进此入口 —— 实施时定)
  - [x] `__tests__/distribute-dialog.test.tsx`:Radio 切模式 + 按门店多选构造 target_tenant_ids + 按集团单选构造 target_group_id + XOR 防互斥(选门店时集团 disabled)+ group_admin 锁本集团(目标选项只含本集团)+ super 全平台 + 空选校验 + 提交触发 mutateAsync + 成功 toast
  - [x] `__tests__/distribution-list-dialog.test.tsx`:列表渲染(useDistributions 返回)+ is_active 状态显示(生效/已撤回)+ 撤回按钮触发二次确认 + 确认后调 useRevokeDistribution + 撤回后刷新 + 空态(无下发关系)
  - [x] 验证:`npm test` 全绿 + `npm run build` 0 错 + `tsc -b` 0 错 + `oxlint` 0/0

> **实现偏离(AC1/AC2,code-review 确认可接受)**:① plan §F4 写「RadioGroup」,实际用 button-list 切模式(项目无 radio-group.tsx 组件,`@radix-ui/react-radio-group` 声明未装,同切片02 Tabs 先例);XOR 语义通过 switchMode 清空对方选择 + 单区渲染实现(选门店时不渲染集团区,反之亦然),功能等价。② plan §F5 写「二次确认 Dialog」,用普通 Dialog(无 alert-dialog.tsx,镜像 document-list 删除确认范式)。零新依赖。

> **遗留 follow-up(toast 重新激活计数)**:AC1 toast 写「已下发(N 条,含重新激活 M 条)」,当前仅交付「已下发 N 条」。M(重新激活数)需后端 `KnowledgeDistributionRead` 增 `was_reactivated` 字段才能计算 —— 现 distribute upsert 返回的 row 重激活与新建无法区分(均 is_active=True,无标记)。本切片纯前端,不动后端;M 计数作为独立小切片(可并入切片05 收尾或单开)。当前「已下发 N 条」是诚实可算的最大信息量,D3 显式下发语义不依赖 M。

> **非末切片**(04-05 待做),不动 feature_list.json status/evidence。

---

### 切片 04 — Category 管理 CRUD(F6 scope 分组 + 新建/编辑/删除 Dialog)

- **What it delivers**:Category 管理的完整 CRUD UI 落地。管理 tab 的「分类管理」子 tab 渲染 Category 列表按 scope 分组(platform/group/store 三个 Card 区块,对齐 reader-ui category-tree 范式)。顶部「新建分类」按钮开 Dialog:scope 下拉(getAvailableScopes 过滤)+ name + sort_order;scope=group 时 group_id 默认 me.group_id(隐藏)/scope=store 时 tenant_id 默认 me.tenant_id(隐藏)/scope=platform 两者 null。每行 Category「编辑」(只改 name/sort_order,scope 不可改对齐后端 KnowledgeCategoryUpdate schema)「删除」(二次确认,软删)。此切片完成后,D5 预置+扩展的 Category 管理前端闭环。

- **Blocked by**: 切片 02(AdminPanel 子 Tabs + hooks/endpoints)

- **Acceptance criteria**:
  - [ ] `frontend/src/pages/knowledge/category-manager.tsx` 新建:自调 `useKnowledgeCategories()`;按 scope 分组渲染(platform/group/store 三个 Card 区块,用 ScopeBadge 标识);每行 Category 显示 name + sort_order + DropdownMenu(编辑/删除)
  - [ ] 新建 Dialog:scope Select(getAvailableScopes 过滤)+ name Input + sort_order Input;scope 联动(scope=group → group_id 默认 me.group_id 隐藏 / scope=store → tenant_id 默认 me.tenant_id 隐藏 / scope=platform → 两者 null);提交调 useCreateCategory
  - [ ] 编辑 Dialog:只改 name + sort_order(scope 不可改 + group_id/tenant_id 不可改,对齐后端 KnowledgeCategoryUpdate schema);提交调 useUpdateCategory
  - [ ] 删除:二次确认 Dialog + 调 useDeleteCategory(软删)
  - [ ] `__tests__/category-manager.test.tsx`:scope 分组渲染(platform/group/store 三区块)+ 新建 Dialog scope 过滤(角色映射)+ scope 联动 group/tenant 隐藏 + 编辑只改 name/sort_order(scope 不可改)+ 删除二次确认 + member 无新建/编辑/删除按钮(member 在管理 tab 隐藏,但 helper 守卫仍测)
  - [ ] 验证:`npm test` 全绿 + `npm run build` 0 错 + `tsc -b` 0 错 + `oxlint` 0/0

> **非末切片**(05 待做),不动 feature_list.json status/evidence。

---

### 切片 05 — reader-ui category 联动 B4 + 集成验证 + feature 收尾(末切片)

- **What it delivers**:reader-ui 的门店录入 Dialog 加 category 下拉(B4),门店 owner 录入时可归类(零行为回归)。全量集成验证 + feature 收尾仪式。此切片是末切片,完成后 admin-ui feature 全部 5 切片交付,分级管理的「管理侧」UI 完整闭环。

- **Blocked by**: 切片 01 + 02 + 03 + 04(类型层 + DocumentCreate category_id + 管理主体全部完成,本片做 reader 联动 + 收尾)

- **Acceptance criteria**:
  - [ ] `frontend/src/pages/knowledge/document-list.tsx` 录入 Dialog 加 category 下拉:数据源 useKnowledgeCategories(按本店可见过滤:platform + 本集团 group + 本店 store);可选不选(默认 undefined 等价不传,零回归);scope 固定 store(门店用户不能选);提交时透传 category_id 或 undefined
  - [ ] 扩 `__tests__/document-list.test.tsx`:录入 Dialog category 下拉渲染 + 选中提交透传 category_id + 不选默认 undefined 零回归 + 现有 CRUD 测试不破
  - [ ] 集成验证:跨角色权限矩阵测试(member 无管理 tab / owner 有管理 tab 无下发按钮 + reader 录入加 category / group_admin 全套管理 + 创建 group scope / super_admin 全套 + 创建 platform scope)
  - [ ] grep 残留:`pages/knowledge-page` 旧路径外部 import 仅 App.tsx barrel;旧 knowledge-page.tsx barrel 不变
  - [ ] 验证(plan §10 AC 全绿):`npm test` 全绿(目标 ~38 用例,含后端 ~10 + 前端组件 ~20 + msw ~8)+ `npm run build` 0 错 + `tsc -b` 0 错 + `oxlint` 0/0 + `./init.sh full` 后端零回归(后端改动是补接缝,backend feature 987 测试不破)
  - [ ] feature 收尾仪式(three-tier §4 第1-7步):`./init.sh full` 全绿 + feature_list.json status `in_progress → passing` + evidence + sync-active 刷新 + progress.md 更新 + 文档影响评估 + 依赖解锁扫描(本 feature 是知识库分级系列最后一片,系列收官时 overview 加「系列状态:✅ 全部完成」段)

---

## grill 访谈记录(EP2,Session 198,2026-08-07)

- **入口**:admin-ui feature 走 EP2 单回环(grill → to-spec → to-tickets),backend ✅ + reader-ui ✅ 是前置
- **不重烤**:EP1 总纲 D1-D12 已锁定(Session 188),backend G1-G8 + reader-ui G1-G7 已交付,本回环只深化「实施层」13 个点(B1-B4 后端接缝 + F1-F7 前端形态 + T1-T2 测试切片)
- **codebase-aware 洞察**(双 Explore agent 并行 recon):读 backend API + 前端 reader-ui 范式后发现 **3 个后端接缝缺口**阻挡 admin-ui(MeResponse 无 group_admin / DocumentCreate 无 scope / 无 list distributions),这是 B1-B3 的核心洞察;前端 recon 发现 getAvailableScopes/scope 选择器/group_admin 判定全部从零建(reader-ui 只读消费,从未主动判角色→scope)
- **关键决策**:范畴扩展(用户确认本 feature 含后端补齐,对齐 reader-ui 含类型层补齐先例);5 切片线性(T1);后端单 seam + 前端双 seam(T2)
- **共识**:13 决策全部选推荐项(B1 group_id+is_group_admin / B2 扩 DocumentCreate / B3 新增 list / B4 reader 加 category / F1 同页 Tabs / F2 子 Tabs / F3 getAvailableScopes / F4 Radio 切模式 / F5 两入口 / F6 scope 分组 / F7 owner+admin 可见管理 tab / T1 5 切片 / T2 后端单 seam + 前端双 seam)
- **下一步**:EP2 收尾 plan 自检(three-tier §3 4 项)→ 回填 feature_list.json plan 字段 → 进 EP3 `/implement` 切片 01(后端接缝补齐,frontier 无 blocker)
