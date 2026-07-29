# 计划:Two-Scope Config 范式 leverage — 抽 `TwoScopeRepository` 基类

> **id**: twoscope-config
> **状态**: passing(draft v2 经子智能体对抗式审查 + 主持人复核修正;EP2 回环落 plan + 登记 in_progress,3 切片全 ✅ 收官 2026-07-29 Session 162)
> **优先级**: 74(新登记,「工程化」area,第 5 次巡检候选 1 Top recommendation)
> **创建日期**: 2026-07-29
> **最后修订**: 2026-07-29(v2:子智能体审查发现 3 P0 + 2 P1,全部坐实并回炉决策)
> **来源**: 第 5 次巡检(2026-07-29)Top recommendation —— 「平台默认 + 租户覆盖」两级配置范式在代码里重复,4 repo + 3 service 互相 docstring 指认「Mirrors XxxConfig」但从未提取。详见 [`codebase-health-log.md`](./codebase-health-log.md)。

---

## 0. v1 → v2 变更摘要(对抗式审查回炉)

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| 决策 3「给 booking_config 加 is_active 列」→ 三处 service `_upsert` 均不写 `is_active=False`(核实:全代码库仅 security/api_token/model_pricing 设 False),**is_active 在三个配置里都是预留死列**;给 booking 加列 = 为对称引入死列 + schema 改动 + 迁移风险,违反 AGENTS.md 铁律 6「不过度设计」 | 🔴 | **推翻决策 3,改用基类钩子 `_active_filter`**:llm/embedding 设 `is_active.is_(True)`,booking 设 None 不过滤。零 schema、零死列、零迁移。诚实承认 is_active 在三者都是预留死列(软停用是独立 feature) |
| slice 3「补 ModelPricingService」→ `ModelPricingRepository` 已存在(wallet.py:87)+ 已被 `BillingService` 注入(billing_service.py:62)+ calc_cost 已封装二维解析。补 service 是为对称造空架子 | 🔴 | **删除 slice 3**。ModelPricing 写路径在 router 是项目既有范式(不违反 Four-Layer,repo 直接被 service 读 + router 写) |
| 缺 ADR 钉边界 → CONTEXT.md 已写 `Two-Scope Config` 词汇却无 ADR,下次巡检会 re-suggest「为什么 ModelPricing/tenant_config 不纳入」 | 🔴 | **必须产出 ADR-0002**(复刻 ADR-0001 范式),钉死纳入/排除清单 + Superseding 流程 |
| frontier 选 booking(需改 schema)+ repo 层零直接测试覆盖 | 🟡 | **frontier 改 llm_config**(已带 is_active、零 schema、形态最标准、试点变量最少);**切片 1 先补 repo 契约测试四态**再动基类 |
| v1 措辞「4 repo 重复」→ tenant_config 是单租户异类(无 platform 默认),真重复只有 3 个 | 🟢 | 措辞修正为「3 repo」(booking/llm/embedding) |

---

## 1. Problem Statement

「平台默认 + 租户覆盖」两级配置范式(平台行 `tenant_id IS NULL` + 租户覆盖行)在代码里重复了 **3 个 repo + 3 个 service**(booking_config / llm_config / embedding_config),且互相用 docstring 指认对方是模板(`booking_config.py:7`「Mirrors LlmConfigRepository」、`embedding_config_service.py:9`「Mirrors LlmConfigService」),但**从没真正提取**。三个 repo 的 `get_platform`/`get_for_tenant` 查询**逐字相同**(仅 `is_active` 过滤差异),三个 service 的读路径 `get_platform`/`get_tenant` 也逐字相同。

**为什么现在做**:第 5 次巡检 Top recommendation。leverage 大(一次抽,3 repo + 3 service 归一,未来新 config table 零成本),且恶化趋势(上次估 2 实例,实测 3 repo + 3 service)。改范式现在动 1 处,不抽只会继续长。

**性质**:**纯架构卫生**(零运行时行为变化)。诚实标注,不包装成业务能力。项目历史里纯重构 feature 已有先例(principal-module / bookings-page-split / bookings-shared-split 全 passing)。

---

## 2. Solution

抽一个 `TwoScopeRepository(BaseRepository[M])` 基类,吃掉三个 repo 的 `get_platform`/`get_for_tenant` 读路径重复(逐字相同的查询逻辑)。`is_active` 过滤差异用基类钩子 `_active_filter` 属性吸收(llm/embedding 设 `model.is_active.is_(True)`,booking 设 None 不过滤),**不靠给 booking 加死列**。

service 层不动 `_upsert` 写路径(crypto/audit delta 是真业务差异,各留)、不动 `get_effective` 三级 fallback(返回类型 + 第三级投影是真业务差异,各留)。基类只吃 repo 读路径这一处确定的重复。

**不纳入**的:ModelPricing(`(tenant_id, model)` 二维 key 异类,repo 已存在 + 被 BillingService 调用)、tenant_config(单租户异类,无 platform 默认)。边界由 ADR-0002 钉死。

---

## 3. User Stories

作为后端维护者(AI agent / 人类开发者),相关 user story 围绕「改配置范式时的认知成本」:

- 作为后端维护者,我想「两级配置的读路径逻辑只在一处定义」,以便改 get_platform/get_for_tenant 语义时不必同步改 3 个文件。
- 作为后端维护者,我想「新加一个两级配置表时,读路径零样板」,以便未来扩展(如新的 `xxx_config` 表)只写 model + 一行继承,不抄 repo 查询。
- 作为巡检 agent,我想「Two-Scope Config 的边界有 ADR 钉死」,以便不再 re-suggest「为什么 ModelPricing 不纳入基类」。
- 作为 code reviewer,我想「基类的 docstring 写清子类契约(需 nullable tenant_id)」,以便未来继承时不会运行时炸查询。

> 说明:本任务是纯架构重构,**无终端用户可见行为变化**。user story 面向维护者而非 owner/admin/member。

---

## 4. Implementation Decisions

### 4.0 决策矩阵(v2 最终,经对抗式审查)

| # | 决策点 | v2 定案 | 一句话理由 |
|---|---|---|---|
| 1 | 抽取形状 | **B**:基类只吃读路径(`get_platform`/`get_for_tenant`),service 各留 `_upsert` delta | `_upsert` 三种差异(crypto/audit/字段集)是真业务差异,强行泛型化收益打折 |
| 2 | ModelPricing 异类 | **A**:基类不纳入(二维 key);**不补 service**(repo 已存在 + 被 BillingService 调用,补 service 是空架子) | 审查拦下「为对称造空架子」 |
| 3 | is_active 差异 | **C'(钩子)**:基类带 `_active_filter` 属性,llm/embedding 设过滤,booking 设 None。**零 schema、零死列** | 审查拦下「为对称引入死列」违反铁律 6;诚实承认 is_active 在三者都是预留死列 |
| 4 | get_effective 三级 fallback | **B**:不进基类,各 service 自留 | 返回类型(EffectiveLlm/Embedding/BookingConfig)+ 第三级投影(env vs 硬编码 + source tag)是真业务差异 |
| 5 | 切片顺序 | **3 切片 expand-contract**:1 frontier=基类+llm 试点+repo 契约测试 / 2 migrate embedding+booking / 3 末收尾+ADR-0002 | 删 ModelPricingService slice;llm 做 frontier(已带 is_active、零 schema、变量最少) |

### 4.1 基类形状(决策 1+3 的产物)

`TwoScopeRepository(BaseRepository[M])`:
- 类属性 `_active_filter: ColumnElement[bool] | None = None`(子类覆盖;None = 不过滤,带值 = 查询追加 `.where(self._active_filter)`)
- 方法 `get_platform() -> M | None`:`select(M).where(M.tenant_id.is_(None))` + 若 `_active_filter` 非 None 追加
- 方法 `get_for_tenant(tenant_id: str) -> M | None`:`select(M).where(M.tenant_id == tenant_id)` + 若 `_active_filter` 非 None 追加
- docstring 契约:子类 model **必须**有 nullable `tenant_id`;`_active_filter` 默认 None(如 llm/embedding 设 `M.is_active.is_(True)`,booking 保持 None)

子类(切片 1-2):
- `LlmConfigRepository(TwoScopeRepository[LlmConfig])`,`_active_filter = LlmConfig.is_active.is_(True)`,删自写的两个方法
- `EmbeddingConfigRepository(TwoScopeRepository[EmbeddingConfig])`,`_active_filter = EmbeddingConfig.is_active.is_(True)`,删自写
- `BookingConfigRepository(TwoScopeRepository[BookingConfig])`,`_active_filter = None`(保持默认),删自写

### 4.2 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 新增后端文件 | 1 | `app/repositories/two_scope.py`(基类) |
| 改后端文件 | 3 | `app/repositories/booking_config.py`、`llm_config.py`、`embedding_config.py`(改继承 + 删重复方法) |
| 数据库迁移 | 0 | **零 schema 改动**(决策 3 钩子方案的直接收益) |
| 前端文件改动 | 0 | 纯后端 |
| 新增测试 | 1 | `tests/test_two_scope_repo.py`(repo 层契约测试四态) |
| 改测试 | 0 | 现有 `test_booking_config_api.py` 等 service/API 测试零改动(零行为变更) |
| 新增 ADR | 1 | `docs/adr/0002-twoscope-config-repository.md` |
| 改 CONTEXT.md | 1 | `Two-Scope Config` 条目补 ADR-0002 指针(grill 阶段已加词汇,末切片补指针) |
| 清理 docstring | 3 | 三个 repo 的「Mirrors XxxConfig」→「Extends TwoScopeRepository(见 ADR-0002)」 |

### 4.3 多租户影响评估

- 是否新增租户 scoped 表?**NO**(零 schema)
- 是否修改现有租户隔离逻辑?**NO**。基类在 Repository 层(符合铁律「多租户隔离在 Repository 层」),`get_platform`/`get_for_tenant` 的查询语义**逐字不变**(含 is_active 过滤也逐字保留)。booking_config 的跨租户防伪仍在 API 层(`booking_config.py` 的 `_ensure_tenant_access`),基类不碰。
- 是否引入跨租户访问点?**NO**
- 验证:现有 `test_booking_config_api.py`(19 用例,含 X 跨租户守卫)+ `test_llm_config`/`test_embedding_config` 全绿验证零行为变更

### 4.4 权限影响评估

- 是否新增 permission code?**NO**
- 是否影响 `require_permission` caller?**NO**(纯 repo 层重构,API/service 签名不变)
- 是否影响 graph.py 工具内 check?**NO**

### 4.5 数据库表设计 checklist

**N/A —— 零 schema 改动**(决策 3 钩子方案,不给 booking 加列)。这是对抗式审查后回炉的直接收益,规避了 schema 改动 + 迁移风险 + 死列。

### 4.6 范式对齐

- 呼应 `TenantScopedRepository`(`base.py`):后者 `tenant_id` 必填(业务数据隔离),前者 `tenant_id` 可空(配置两级覆盖)。两者互补,是 Repository 层的两大范式基类。
- 呼应 ADR-0001(principal-scope-boundary)的 Superseding 流程:ADR-0002 复刻其结构(Context / Decision / Consequences / Superseding)。

### 4.7 Out of Scope(明确不做)

- ❌ **配置软停用语义**(is_active 设 False 保留历史行):三个配置的 is_active 目前都是预留死列,软停用是独立业务 feature(若未来需要),不在本次
- ❌ **ModelPricing 纳入基类 / 补 ModelPricingService**:二维 key 异类 + repo 已存在,补 service 是空架子(审查 P0-2)
- ❌ **get_effective / _upsert 进基类**:真业务差异,各留(决策 4 + 决策 1)
- ❌ **tenant_config 纳入**:单租户异类(无 platform 默认)

---

## 5. Testing Decisions

- **测试金字塔**:unit(repo 契约四态)+ integration(现有 service/API 测试回归,零改动验证零行为变更)
- **测试库**:SQLite 内存库(与现有 `test_booking_config_api.py` 同范式;零 VECTOR / 部分索引 / server_default 依赖,SQLite 足够)
- **测试缝位**:**repo 层契约测试**(审查 P1-2:当前 repo 的 get_platform/get_for_tenant 零直接覆盖,基类抽取前必须补,防「抽取后行为悄悄变却测不出」)。这是**新缝位**(现有测试都在 service/API 层),但它是这个重构唯一的可信验证点 —— 基类吃的就是 repo 读路径,必须直测 repo。
- **四态用例**(每个 config repo × 4 态):
  1. 平台行存在(`tenant_id IS NULL`)→ `get_platform` 返回它
  2. 租户行存在(`tenant_id=X`)→ `get_for_tenant(X)` 返回它,`get_for_tenant(Y)` 返回 None
  3. 两都不存在 → 两个方法都返回 None
  4. **is_active 过滤**(llm/embedding):插入 `is_active=False` 行 → `get_platform`/`get_for_tenant` 不返回它;**booking 无此态**(钩子 None 不过滤,但 booking 表无 is_active 列,测试验证「不过滤」语义即所有行都返回)
- **回归**:切片 2/3 跑全量 `./init.sh full`(基线 828 passed 零回归)+ 现有 `test_booking_config_api.py` 19 用例 + `test_llm_config` + `test_embedding_config` 全绿
- **覆盖率**:不低于项目基线 93%(本任务新增 repo 测试反而提升 repo 层覆盖)

---

## 6. 切片规划

本任务是 **wide refactor**(纯 locality 搬运,零行为变更),按 [three-tier-workflow.md](./three-tier-workflow.md) §7,wide refactor 走 **EP3 单入口 + expand-contract 序列**。3 切片:

### 切片 1:抽基类 + llm 试点 + repo 契约测试(expand)✅

- **What to build**:新建 `TwoScopeRepository` 基类(带 `_active_filter` 钩子);`LlmConfigRepository` 改继承基类 + 删自写的 `get_platform`/`get_for_tenant`;新建 `tests/test_two_scope_repo.py` 覆盖 llm repo 的四态契约(含 is_active 过滤态)。
- **Blocked by**: 无(frontier)
- **文件清单**:新建 2(基类 + 测试)+ 改 1(llm_config repo)= 3 文件
- **验证命令**:`./init.sh`(ruff + pytest smoke)+ 新 repo 测试四态全绿
- **AC**:
  - [x] `TwoScopeRepository` 基类存在,`_active_filter` 默认 None,get_platform/get_for_tenant 逻辑逐字对齐 llm 现状
  - [x] `LlmConfigRepository` 改继承基类,`_active_filter = LlmConfig.is_active.is_(True)`,自写两方法删除
  - [x] `tests/test_two_scope_repo.py` 覆盖 llm 四态:平台行/租户行/无行/is_active 过滤
  - [x] 现有 `test_llm_config` 全绿(零行为变更)
  - [x] `./init.sh` smoke 全绿 + ruff clean

### 切片 2:迁移 embedding + booking 改继承(migrate batch)✅

- **What to build**:`EmbeddingConfigRepository` + `BookingConfigRepository` 改继承基类(booking 设 `_active_filter=None` 保持不过滤);删两者自写的重复方法;测试补 embedding 四态 + booking 三态(无 is_active 态)。
- **Blocked by**: 切片 1(基类就绪)
- **文件清单**:改 2 repo + 改 1 测试(补 embedding/booking 用例)= 3 文件
- **验证命令**:`./init.sh full`(全量回归,基线 828 passed 零回归)
- **AC**:
  - [x] `EmbeddingConfigRepository` 改继承,`_active_filter = EmbeddingConfig.is_active.is_(True)`,自写删除
  - [x] `BookingConfigRepository` 改继承,`_active_filter = None`(不过滤),自写删除
  - [x] repo 测试补 embedding 四态 + booking 三态(平台/租户/无行;无 is_active 态因表无此列)+ 额外 no-filter 语义验证
  - [x] `test_booking_config_api.py` 19 用例 + `test_embedding_config` 全绿(36 passed,零行为变更)
  - [x] `./init.sh full` 全绿(840 passed,基线 828 + 新增 12 repo 契约用例零回归)+ ruff clean

### 切片 3:收尾验证 + ADR-0002 + docstring 清理 + feature passing(contract)✅

- **What to build**:无新源码逻辑。清理三个 repo 的 docstring 互指(「Mirrors XxxConfig」→「Extends TwoScopeRepository(见 ADR-0002)」);产出 ADR-0002 钉边界;CONTEXT.md `Two-Scope Config` 条目补 ADR-0002 指针;feature 收尾。
- **Blocked_by**: 切片 2
- **文件清单**:0 源码逻辑 + 6 docstring 改(3 repo 补指针 + 2 service + 1 model 互指清解)+ 1 ADR 新建 + CONTEXT.md 指针确认 + feature 收尾文档
- **验证命令**:`./init.sh full` 全量 + grep 验证 docstring 互指清零
- **AC**:
  - [x] 三个 repo docstring 的「Mirrors XxxConfig」全部改为「Extends TwoScopeRepository(见 ADR-0002)」(切片 1/2 已改继承,切片 3 补「(见 ADR-0002)」指针 + 连带清理 2 service + 1 model 的同源「Mirrors LlmConfig(Service)」互指)
  - [x] `docs/adr/0002-twoscope-config-repository.md` 存在,复刻 ADR-0001 五段式(Context/Decision/Consequences/Superseding/References),含纳入 3 repo + 排除 ModelPricing/tenant_config 理由 + `_active_filter` 钩子理由 + get_effective/_upsert 不进基类理由
  - [x] CONTEXT.md `Two-Scope Config` 条目加 `[ADR-0002](docs/adr/0002-...)` 指针(grill 阶段已就位,本次确认)
  - [x] feature_list.json status → passing,evidence 写齐(3 切片 + 收尾条)
  - [x] progress.md 顶部「最高优先级未完成」清空
  - [x] 跑 `./scripts/sync-active-features.sh` 刷新 active 视图(0 活跃 + 5 最近 passing)
  - [x] grep「Mirrors LlmConfig / Mirrors .*Repository」→ 0 处(docstring 互指债务消解,配置范式语义:grep「Mirrors.*(LlmConfig|ConfigService|ConfigRepository)」→ 0)
  - [x] 末切片依赖解锁扫描:无 feature depends_on 指向 twoscope-config(纯重构,无下游)→ 无需推进

---

## 7. v1 → v2 对抗式审查段

**已触发并完成**(本任务满足「涉及数据迁移」的初判,虽 v2 后零 schema,但审查已在 v1「可能加列」阶段执行)。

**审查方式**:子智能体 ×2 并行(opus general-purpose):① 真相核查员(逐项核查 5 决策事实基础)② 业务设计审查员(业务价值 + 高质量标准 + 切片顺序 + 遗漏点)。

**审查产出**(详见 §0 变更摘要):
- 🔴 P0 ×3:决策 3 推翻(死列)→ 钩子 / 删 slice 3(空架子)/ 补 ADR-0002
- 🟡 P1 ×2:frontier 改 llm / 切片 1 先补 repo 契约测试
- 🟢 P2 ×3:措辞 4→3 repo / 基类名严格 TwoScopeRepository / 清理 docstring 互指

**审查的价值**:3 个 P0 阻止了「为对称引入死列(违反铁律 6)+ 迁移风险」「为对称造空架子」「边界不落 ADR 致下次巡检 re-suggest」三类问题进 PRD。回炉后变为零 schema、零死列、零业务回归的纯架构卫生 feature。

---

## 8. Out of Scope

- ❌ 配置软停用语义(is_active 设 False):独立业务 feature,不在本次(三个配置 is_active 目前都是预留死列)
- ❌ ModelPricing 纳入基类 / 补 ModelPricingService:二维 key 异类 + repo 已存在
- ❌ get_effective / _upsert 进基类:真业务差异
- ❌ tenant_config 纳入:单租户异类

---

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 基类抽取后某 config 的 get_platform/get_for_tenant 行为悄悄变(如漏 is_active 条件)却测不出 | 中 | 切片 1 先补 repo 契约测试四态(审查 P1-2),基类落地前测试就位 |
| 钩子 `_active_filter` 未来继承者误用(拿无 is_active 的模型设了过滤) | 低 | 基类 docstring 写清契约 + ADR-0002 记录;TypeScript 式约束在 Python 不可得,靠 docstring + review |
| llm/embedding 的 is_active 永远是 True(死列),基类带过滤是否误导 | 低 | ADR-0002 + CONTEXT.md 诚实记录「is_active 在三者都是预留死列,软停用是独立 feature」;钩子方案比加死列更诚实(不假装 booking 也有此语义) |

---

## 10. 验收标准(同步 feature_list.json verification)

1. `app/repositories/two_scope.py` 存在,`TwoScopeRepository` 基类含 `_active_filter` 钩子 + get_platform/get_for_tenant
2. 三个 repo(booking/llm/embedding)改继承基类,自写的 get_platform/get_for_tenant 全部删除
3. `tests/test_two_scope_repo.py` 覆盖三 repo 契约(llm/embedding 四态含 is_active / booking 三态无 is_active)
4. `./init.sh full` 全绿(828 passed 基线零回归)+ ruff clean
5. `docs/adr/0002-twoscope-config-repository.md` 存在,复刻 ADR-0001 结构
6. grep「Mirrors LlmConfig / Mirrors .*Repository」→ 0 处(docstring 互指消解)
7. CONTEXT.md `Two-Scope Config` 条目带 ADR-0002 指针

---

## 11. 不越界声明

本次改动**只**涉及 `app/repositories/` 层的 3 个 config repo + 新建 1 基类 + 1 repo 测试 + 1 ADR + 3 docstring;**不**触碰 service 层(`_upsert`/`get_effective` 不动)、**不**触碰 schema(零迁移)、**不**触碰 API 层、**不**触碰前端、**不**碰 ModelPricing/tenant_config、**不**实现配置软停用语义。
