# 计划:定价写路径提取 PricingService(pricing-service extraction)

> **id**: pricing-service-extraction
> **状态**: in_progress(EP2 完成 v2[经轻量对抗式自审,见 §0],待 EP3 切片 01 实施)
> **优先级**: 98(feature_list.json)
> **创建日期**: 2026-08-25
> **最后修订**: 2026-08-25(v2)

---

## 0. v1 → vN 变更摘要(若有修订,必填)

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| 404 分支(PUT/DELETE 不存在 id)既有测试零覆盖,而它恰是提取中唯一手工重写的判定路径(service 返 None + API 抛 404),迁移手误测试全绿也发现不了 | 🟡 | 采纳:新增 1 条 404 锁定用例(green-on-both 回归锁,同 feature 97 guard 用例先例);D3「零新增」微调为「零改动为主 + 唯一例外 1 条锁定用例」,§5/§10/§12 已含 |
| BillingService 类 docstring "…recharge, pricing" 易被误读为定价写逻辑也在其中 | 🟢 | 采纳:EP3 顺带一行微调指向 PricingService(良性超集留痕,§11 已列入) |
| upsert 唯一性竞态(并发双 POST 同 scope+model 可产生两条活跃行,service 层唯一性无 DB 约束) | 🟢 | 留痕不修:pre-existing 行为,提取不引入不修复;DB 约束化属独立后续任务(§8 已列) |

> 说明:自审(§7)在 v1 起草过程中进行,三项发现已同步吸收进 v1 正文;v2 仅做记档与状态行升级,**正文与 v1 等同**。

---

## 0.1 决策拍板状态说明

本 feature 的提取边界 / 端点契约 / 测试深度 / 切片数(D1-D4)按任务要求于 2026-08-25 Session 229 发起 AskUserQuestion 问询,**未获回复**。处置:按 Session 219/222 先例(「未获回复按推荐采纳并如实标注」),D1-D4 全部按推荐方案落地,逐项如实标注。**复核窗口 = EP3 开工前**(EP3 首个动作向用户过一遍 D1-D4 清单,仍未获回复则窗口关闭、维持推荐,留痕于此;推翻成本局部 —— 提取是纯迁移,任何决策回退只影响落点不影响行为)。

---

## 1. Problem Statement

`app/api/v1/billing.py` 的定价段(4 端点 + 3 个模块级 helper,约 200 行)把**业务逻辑、审计埋点、事务提交**全部压在 API 层:

- **分层铁律违反**:upsert 的唯一性查找是一条裸 `select(ModelPricing)`(违反铁律 2「数据查询归 Repository 层」);审计 record 调用写在路由函数体内(违反「审计属 Service 职责」,feature 92 code-review 已判 1 硬违规并明文留痕「提取 pricing 写路径入 service 层属独立重构,留痕为后续候选」—— 本 feature 即该候选的兑现);
- **讽刺的自相矛盾**:`ModelPricing` 模型 docstring 声称「Uniqueness is enforced at the service layer」—— 但这段逻辑实际住在 API 层,声明名不副实;
- **范式孤岛**:同文件的充值早已在 `BillingService.recharge`(record→commit 原子范式的仓库样板),定价写路径是 billing 域内唯一游离在外的写路径。

这是第 11 次巡检(2026-08-25)候选 Ⓑ(Worth exploring,暂定 pri 98)的原始发现,feature 97(Ⓐ)D3 决策「定价不碰,Ⓑ 独立立项」后本条独立成军。

**为什么现在做**:feature 92 树立的审计范式(record→commit 原子 + HTTP 接缝持久性断言)与 feature 97 的 conftest 事务语义适配已把测试地基打牢,「审计随迁零改动通过」第一次成为可验收的提取目标;risk-hardening 系列 6 条 + Ⓐ 收官后,这是巡检清单上唯一挂账的结构债。

## 2. Solution

把定价**写路径**(POST upsert / PUT update / DELETE deactivate 三端点)的业务 + 审计 + 事务整体迁入新文件 `app/services/pricing_service.py` 的 `PricingService`;裸 select 归位为 `ModelPricingRepository.get_active_for_scope`(精确 scope 查找);API 层三端点收缩为「取身份 → 调 service → None 转 404」的薄壳,**路由/签名/response_model/状态码/权限门零变化**;审计 4 处 record 逐字随迁且全部保持在业务 commit 之前(feature 92 范式)。

**GET /pricing 留在 API 层**(与兄弟读端点 GET /wallet、/transactions、/usage 的 repo 直调范式一致;它无审计、无事务、无提取收益)。**验收锚点:`tests/test_super_admin_audit.py` 的 5 个定价审计用例 + `tests/test_billing.py` 的 3 个定价端点用例零改动全绿** —— 纯结构迁移,用户可见行为逐字不变。

## 3. User Stories

1. 作为 super_admin,我通过定价端点新建/改价/停用定价,期望 API 契约与行为(含审计记录)与提取前逐字一致,以便无感升级。
2. 作为门店 owner,我在计费页读取生效价(平台默认 + 本店覆盖),期望读取结果与顺序零变化。
3. 作为门店 owner(有 logs:read),我希望「被改价」审计记录照常落 SystemLog 且经 /logs 可查,以便定价争议时还原现场。
4. 作为平台运维,我希望定价写路径的事务与审计原子性(record→commit)在迁移后逐处保持,以便审计行永不悬空丢失。
5. 作为后续开发者,我希望定价写逻辑在 Service 层可发现(PricingService 单一入口),以便改定价规则时不必翻 API 路由文件;仓库分层检查(铁律 1/2)对 billing 域全部通过。
6. 作为巡检 agent,我希望 API 层不再有 ModelPricing 裸 select 与审计 record 直调,以便「审计属 Service 职责」的 Standards 轴检查不再报违规。

## 4. Implementation Decisions

### 4.1 影响面清单(项目特化,必填)

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 3 | `app/services/pricing_service.py`(新建,PricingService + 2 私有 helper 迁入)、`app/repositories/wallet.py`(ModelPricingRepository 加 1 方法)、`app/api/v1/billing.py`(定价写段收缩为薄壳 + import 收拾) |
| 数据库迁移 | 0 | 零 schema 变化(纯代码迁移) |
| 前端文件改动 | 0 | API 契约零变化,前端零感知 |
| 测试文件改动 | 1 | `tests/test_billing.py`(新增 404 锁定用例,见 §5);`tests/test_super_admin_audit.py` **零改动** |
| Skill / Hook / 配置 | 0 | — |

### 4.2 多租户影响评估(项目特化)

- 是否新增租户 scoped 表? **NO**(零 schema 变化)
- 是否修改现有租户隔离逻辑? **NO**(定价写路径是平台级 super_admin 操作,tenant override 是数据维度而非隔离边界;GET 读路径的 scope 计算不动)
- 是否引入跨租户访问点? **NO**(权限门 require_super_admin 原样,跨租户写入口数量零变化)
- 验证:既有用例已含多租户维度 —— audit 用例含「租户 override scope(tenant_id=被覆盖租户)+ 平台 scope(tenant_id NULL)」与「门店 owner 经 /logs 读侧可见性」;billing 用例含「owner 读生效价(平台+本店合并)」。全部零改动通过即证。

### 4.3 权限影响评估(项目特化)

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 require_permission caller? **NO**(GET /pricing 的 `billing:read` 与三写端点的 require_super_admin 依赖声明原样保留)
- 是否影响 graph.py 工具内 check? **NO**
- 验证:`test_pricing_owner_cannot_write`(owner POST → 403)零改动通过即证。

### 4.4 数据库表设计 checklist(呼应 AGENTS.md 铁律 6)

不适用 —— 零新表、零列变化、零迁移。既有事实留痕:`model_pricing` 表**无 is_deleted 列**,软停用走 `is_active`(与本仓库「软删除 + is_deleted」惯例的已知特例,docstring 有说明);「一 scope 一 model 一活跃行」的唯一性由 service 层查找保证而非 DB 约束(PG/SQLite 对 `NULLS NOT DISTINCT` 部分唯一索引的方言差异,模型 docstring 有决策留痕)—— 本提取恰好使「service 层保证」这句话从名不副实变为名副其实。

### 4.5 用户拍板决策(D1-D4;AskUserQuestion 未获回复,按 Session 219/222 先例按推荐采纳,复核窗口 = EP3 开工前)

| # | 决策 | 结论 | 状态 |
|---|---|---|---|
| D1 | 提取边界(哪些端点进 service) | **写 3 端点(POST/PUT/DELETE)入 PricingService;GET /pricing 留 API**。论据:兄弟读端点(GET /wallet、/transactions、/usage)全部 repo 直调留 API,GET 入 service 会破坏该范式;GET 无审计无事务,提取收益趋零 | 未获回复按推荐采纳 |
| D2 | 端点契约与 404 语义 | **路由/签名/response_model/状态码零变化;service 返回 None,API 层抛 HTTPException(404, "定价不存在")** —— 镜像本文件 PUT /wallet 的 None+404 惯例,异常通路零变化,最保守的零行为变化。(对照事实:NotFoundError→404 全局 handler 已存在,service 抛错的备选形态 HTTP 输出等价,但异常通路改变,不采) | 未获回复按推荐采纳 |
| D3 | 测试改造深度 | **既有用例零改动为主**(8 用例全走 HTTP 接缝,零改动全绿即提取正确性验收器,纯迁移无新行为可 TDD);唯一例外见 §5(404 锁定用例,v2 自审采纳) | 未获回复按推荐采纳(v2 微调,见 §0) |
| D4 | 切片划分 | **1 切片**(~200 行单文件纯迁移,单片可独立验证、一个 PR 端到端,同 feature 92/97 单切片先例;repo 归位 + service 提取 + import 收拾同片完成) | 未获回复按推荐采纳 |

工程判断项(非用户拍板,EP2 会话内定):`PricingService` 独立新文件(不并入 BillingService —— 后者 298 行专注钱包记账,docstring 已声明含 pricing 的是成本计算 calc_cost,写路径管理混入会破坏单一职责);`_pricing_snapshot` / `_pricing_scope` 原名原 docstring 迁为 `pricing_service.py` 模块级私有函数(全仓 grep 确认无外部消费者)。

### 4.6 提取规格(逐处)

**新建 `app/services/pricing_service.py`**:

- `class PricingService`,`__init__(db)` 持 `ModelPricingRepository`(镜像 BillingService 的 repo 持有形态);
- `async def upsert(payload: ModelPricingUpsert, operator_id: str) -> ModelPricing` —— `_upsert_pricing` 逻辑整体迁移:repo.get_active_for_scope 查既有行 → 命中则改字段 + record(old_values 双快照)/ 未命中则新建 + record,record 全在 `await db.commit()` 之前,commit 后 refresh 返回(镜像 BillingService.recharge 的 commit/refresh 归属);
- `async def update(pricing_id: str, payload: ModelPricingUpsert, operator_id: str) -> ModelPricing | None` —— repo.get(pricing_id) → None 即返回(None=不存在,由 API 转 404);命中则改字段 + record(pricing.update 双快照)+ commit + refresh;
- `async def deactivate(pricing_id: str, operator_id: str) -> ModelPricing | None` —— repo.get → None 返回;命中则 is_active=False + record(pricing.deactivate,warn)+ commit;返回被停用行(API 层丢弃返回值,204 无 body);
- 审计 4 处 record(upsert 命中 / upsert 新建 / update / deactivate)的 **kwargs 逐字保持 feature 92 落地值**(action/module/message/level/resource_type/resource_id/details/old_values/new_values/user_id/tenant_id 一律不动);
- 模块级私有 `_pricing_snapshot` / `_pricing_scope` 连同 docstring 原样迁入(Decimal 量化 6dp 字符串化的注释语义是 feature 92 的实证结论,不得改写)。

**`ModelPricingRepository` 新方法**(铁律 2 归位):

- `async def get_active_for_scope(model: str, tenant_id: str | None) -> ModelPricing | None` —— 按精确 scope(tenant_id IS NULL 或 == tenant_id)+ model + is_active=True 查单行。**docstring 必须显式区分既有 `get_for_model`**:后者是读侧解析链(tenant override → platform 默认 fallback),前者是写侧 upsert 查找的精确 scope 匹配(不做 fallback)—— 两者语义不可互换,EP3 防误用。

**`app/api/v1/billing.py` 收缩**:

- 删除模块级 `_pricing_snapshot` / `_pricing_scope` / `_upsert_pricing` 三定义;
- POST `create_pricing`:体 → `return await PricingService(db).upsert(payload, operator_id=user.user_id)`;
- PUT `update_pricing`:体 → `row = await PricingService(db).update(pricing_id, payload, operator_id=user.user_id)` + `if row is None: raise HTTPException(404, "定价不存在")` + return;
- DELETE `delete_pricing`:体 → 同上 None 转 404,成功 `return None`(204);
- GET `list_pricing` **零改动**(scope 三元 + repo.list_active 留 API);
- import 收拾:`select` / `LoggingService` / `Decimal` 移出(定价段是这三者在 billing.py 的仅存消费者);`ModelPricing`(类型注解)与 `ModelPricingRepository`(GET 直调)保留;
- 模块 docstring 的 pricing write 措辞指向 PricingService(读段措辞不动)。

### 4.7 取证留痕(源码级,本 EP2 会话 grep/直读确认)

1. **三 helper 无外部消费者**:`_pricing_snapshot|_pricing_scope|_upsert_pricing` 在 app/ + tests/ 全仓 grep,除 billing.py 自身外 0 处 —— 迁移无隐藏耦合面。
2. **裸 select 仅 1 处**:billing.py 内 ModelPricing 的裸查询只有 `_upsert_pricing` 的 scope 查找(L249-255 一带);GET 走 repo.list_active、PUT/DELETE 走 repo.get —— 归位面收敛为单方法。
3. **定价测试全景 8 用例,全 HTTP 接缝**:test_super_admin_audit.py 5 例(upsert 新建平台行含 /logs?action= 精确匹配断言 / upsert 命中带 old_values / 租户 override scope / update 双快照 / deactivate warn)+ test_billing.py 3 例(CRUD 全链含 GET scope 与 204 / owner 403 / owner 读生效价)。断言的是路由行为与 SystemLog DB 行,不 import 任何被迁移符号 —— **提取后天然零改动**。
4. **404 分支既有零覆盖**:PUT/DELETE 对不存在 pricing_id → 404「定价不存在」的判定路径,8 用例均未触及 —— 该路径恰是提取中唯一手工重写的逻辑(service 返回 None + API 判断),v2 采纳补 1 条锁定用例(见 §0/§5)。
5. **BillingService 现状**:298 行,已持 `self.pricing = ModelPricingRepository(db)` 但仅用于只读 `calc_cost`(解析链 + 成本量化);recharge 是 record→commit 原子范式与「service 持有 commit/refresh」的仓库样板 —— PricingService 的方法形态直接镜像它。
6. **异常映射基建**:main.py 全局 handler BizError→400 / NotFoundError→404 / ScopeError→422 已存在 —— D2 备选形态(NotFound 抛出)技术上可行但异常通路改变,不采。
7. **权限门现状**:三写端点 `dependencies=[Depends(require_super_admin())]` + `user: CurrentUser` dep(feature 92 补)—— 迁移后两者原样保留在 API 层,service 只收 operator_id 参数。

## 5. Testing Decisions

- **测试哲学**:纯结构迁移,唯一值得测的是「外部行为逐字不变」—— 既有 HTTP 接缝用例就是验收器,**不为迁移新造 service 直连单测**(与 test_billing.py 里 calc_cost/charge 的直连单测不冲突:那些测的是计算逻辑,定价写路径的全部逻辑已被 HTTP 用例覆盖)。
- **既有 8 用例零改动通过**(§4.7-3 清单)= 主验收;执行顺序:提取前先跑一遍确认基线绿,提取后再跑确认仍绿。
- **新增 1 条 404 锁定用例**(v2 自审采纳):test_billing.py 增 `PUT/DELETE 不存在 pricing_id → 404 + detail="定价不存在"`(一条用例覆盖两动词,green-on-both 回归锁 —— 提取前后都绿,价值在锁住 None+404 判定语义不被迁移改写;同 feature 97 guard 对称用例先例)。
- **审计原子性**:不新增「审计失败不阻断」用例 —— record→commit 顺序由代码位置保证 + 既有 upsert/update/deactivate 用例的 request-close 后 DB 行存在断言覆盖(feature 92 树立、feature 97 conftest 事务语义适配后红绿可信)。
- **全量门**:`./init.sh full` 零回归 + ruff 绿(新文件 import 排序)+ 前端 build 绿(零前端改动确认)。
- 多租户/权限:不新增(§4.2/§4.3 既有用例零改动通过即证)。

## 6. 切片规划

### Ticket 1(唯一切片):PricingService 提取 + 裸 select 归位 + 404 锁定用例
- **What to build**: 定价写三端点的业务/审计/事务迁入 PricingService,裸 select 归位 repo 新方法,API 收缩为薄壳;全部既有定价用例零改动通过 + 1 条 404 锁定用例新增;全量零回归。
- **Blocked by**: 无
- **文件清单**: 3 改后端(1 新建)+ 1 改测试
- **验证命令**: `pytest tests/test_super_admin_audit.py tests/test_billing.py -q`(先基线后回归)+ `grep -n "select(" app/api/v1/billing.py`(应 0 处)+ `./init.sh full`

## 7. 对抗式审查(轻量自审;未触发复杂任务条件 —— 文件 ≤5、无鉴权/迁移/跨服务变化)

单模型双轴自查(Standards:铁律/分层/范式;Spec:本 plan 承诺 vs 代码现状):

- 🟡 **404 分支零覆盖**(Standards 轴):提取唯一手工重写路径(service None + API 404)无任何用例锁定,迁移手误(漏判 None / 404 文案改写)测试全绿也发现不了。→ **采纳**:新增 1 条 404 锁定用例(D3 微调,green-on-both 回归锁)。
- 🟢 **BillingService docstring 措辞**(Spec 轴):其类 docstring "…recharge, pricing" 中的 pricing 指 calc_cost 成本计算,提取后仍准确,但为防「定价写逻辑在 BillingService」的误读,微调为指向 PricingService 的一句说明。→ **采纳**(EP3 顺带一行,良性超集留痕)。
- 🟢 **upsert 唯一性竞态留痕不修**(Standards 轴):并发双 POST 同 scope+model 可产生两条活跃行(service 层唯一性、无 DB 约束)—— pre-existing 行为,提取不引入也不修复;若未来上 PG NULLS NOT DISTINCT 部分索引属独立任务(镜像 booking-toctou-guard 的 EXCLUDE 路径)。→ **留痕不修**,入 §8 Out of Scope。

## 8. Out of Scope

- ❌ GET /pricing 行为/落点任何变化(D1:留 API)
- ❌ API 路由路径/方法/response_model/状态码/权限门/请求响应 schema 任何变化(D2)
- ❌ ModelPricing 表结构、任何 alembic 迁移、「一 scope 一 model」唯一性的 DB 约束化(upsert 竞态留痕,§7)
- ❌ BillingService 钱包方法(recharge/charge/update_wallet_settings/calc_cost)任何改动 —— calc_cost 的读侧解析链原样
- ❌ LoggingService / SystemLog / 前端审计页 / 前端任何文件
- ❌ billing.py 其余端点(wallet/transactions/usage/recharge)的任何改动(它们的 repo 直调读范式是 D1 的论据,不动)
- ❌ 顺手重构无关代码(命名/注释风格/格式化蔓延)

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 迁移手误改语义(审计 kwargs 抄错/record-commit 顺序颠倒/快照逻辑走样) | 高 | 既有 8 用例零改动全绿(先跑基线)+ EP3 diff 对照 4 处 record kwargs 与 feature 92 落地值逐字一致(§4.6 硬要求) |
| 404 判定路径重写无锁 | 中 | v2 新增 404 锁定用例(green-on-both,§5) |
| repo 新方法被误用为 fallback 语义(get_for_model 混淆) | 低 | get_active_for_scope docstring 显式区分两种语义(§4.6)+ upsert 命中用例覆盖既有行场景 |
| import 残留(F401)/ 循环引用 | 低 | ruff 门 + pricing_service 只 import repo/schema/model/logging_service(无反向依赖,铁律 1 方向天然成立) |
| conftest 事务语义与审计原子性交互 | 低 | feature 97 已把 test engine 对齐 PG 回滚语义(isolation_level=None + 显式 BEGIN),HTTP 接缝用例的持久性断言直接可信,无需本 feature 适配 |

## 10. 验收标准(同步 feature_list.json verification)

1. 既有 8 定价用例零改动通过:test_super_admin_audit.py 5 例(HTTP 接缝 + request-close 后 SystemLog 行仍在)+ test_billing.py 3 例(CRUD/403/读生效价);执行序列 = 提取前基线绿 → 提取后仍绿。
2. 新增 404 锁定用例通过:PUT + DELETE 不存在 pricing_id → 404 detail=「定价不存在」。
3. 审计原子性逐处保持:PricingService 内 4 处 record(upsert 命中/新建、update、deactivate)全部位于对应 `db.commit()` 之前,kwargs 与 feature 92 落地值逐字一致(EP3 diff 对照留痕)。
4. 裸 select 归位:`grep -n "select(" app/api/v1/billing.py` → 0 处;`ModelPricingRepository.get_active_for_scope` 就位且 docstring 与 get_for_model 语义区分明确。
5. 分层合规:app/api/v1/billing.py 定价写段无业务逻辑(仅取身份/调 service/None→404);依赖向 API → PricingService → ModelPricingRepository → Model 单向。
6. `./init.sh full` 全量零回归 + ruff 绿 + 前端 build 绿(git diff frontend/src 为空)。

## 11. 不越界声明

本次改动**只**涉及:新建 app/services/pricing_service.py(PricingService 三方法 + 两私有 helper 迁入)、ModelPricingRepository 加 get_active_for_scope 一方法、app/api/v1/billing.py 定价写段收缩为薄壳 + import 收拾 + 模块 docstring 一句措辞、BillingService 类 docstring 一行微调(§7 🟢)、tests/test_billing.py 新增 1 条 404 用例。**不**触碰:GET /pricing 及兄弟读端点、API 契约与权限门、ModelPricing schema 与任何迁移、BillingService 方法体、LoggingService/SystemLog/前端、审计 kwargs 语义、唯一性竞态(留痕不修)。

## 12. 实施切片(to-tickets 产出)

### 切片依赖图

```
01 ⬜(唯一 = 末切片)
```

### 切片 01 — PricingService 提取 + 裸 select 归位 + 404 锁定用例
- **Blocked by**: 无(可立即开工)
- **What it delivers**: 定价写三端点(POST/PUT/DELETE /billing/pricing)的业务、审计、事务全部由 PricingService 承接,API 层只剩薄壳;裸 select 归位 Repository(铁律 2);「审计属 Service 职责」的分层违规清零(feature 92 code-review 留痕的独立候选兑现);外部行为逐字不变 —— 既有 8 定价用例零改动通过 + 新增 404 锁定用例。
- **Acceptance criteria**:
  - [ ] `app/services/pricing_service.py` 新建:PricingService(upsert/update/deactivate)+ `_pricing_snapshot`/`_pricing_scope` 迁入;4 处 record 全在 commit 前,kwargs 与 feature 92 落地值逐字一致(diff 对照)
  - [ ] `ModelPricingRepository.get_active_for_scope` 新方法:精确 scope 查找语义,docstring 显式区分 get_for_model 的 fallback 解析链
  - [ ] `app/api/v1/billing.py`:三写端点收缩为「取身份 → 调 service → None 抛 404『定价不存在』」;删三模块级 helper;import 收拾(select/LoggingService/Decimal 出);GET /pricing 与其余端点零改动
  - [ ] `tests/test_billing.py` 新增 404 锁定用例(PUT+DELETE 不存在 id → 404,green-on-both)
  - [ ] 既有 8 定价用例零改动通过(提取前基线绿留痕 → 提取后仍绿)
  - [ ] `grep -n "select(" app/api/v1/billing.py` = 0;`./init.sh full` 零回归 + ruff + 前端 build 绿(零前端改动)
  - [ ] BillingService 类 docstring 一行微调(§7 🟢 良性超集留痕)
  - [ ] feature 收尾八步(three-tier §4:status/evidence/sync-active/progress.md/checklist/文档影响评估/依赖解锁扫描/分支清理)
