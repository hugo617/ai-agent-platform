# ADR-0002: Two-Scope config repository boundary(两级配置范式基类边界)

- **Status**: Accepted
- **Date**: 2026-07-29(ADR 立档日期;决策源自 2026-07-29 第 5 次巡检 + `twoscope-config` grill 共识,经 opus 子智能体对抗式审查回炉)
- **Deciders**: 2026-07-29 第 5 次代码健康度巡检 + `plan-twoscope-config` grill 共识(opus 子智能体审查 ×2:真相核查 + 业务设计)
- **Supersedes**: —(本 ADR 不推翻任何前序 ADR;与 [ADR-0001](0001-principal-scope-boundary.md) 互补 —— ADR-0001 钉 Principal 半收口边界,本 ADR 钉 Two-Scope 配置基类边界,同属「Repository 层范式基类的采纳范围裁决」)
- **Superseded by**: —(尚无后续 ADR 推翻)

---

## Context

`twoscope-config` feature(priority 74,2026-07-29 收官)抽出了 `TwoScopeRepository` 基类(`app/repositories/two_scope.py`),吸收「平台默认 + 租户覆盖」两级配置范式中 **3 个 repo 的读路径重复**(`get_platform` / `get_for_tenant` 逐字相同的查询逻辑):

| 纳入的 repo | `_active_filter` 钩子 | 理由 |
|---|---|---|
| `LlmConfigRepository` | `LlmConfig.is_active.is_(True)` | 标准形态(已带 `is_active` 列),frontier 试点 |
| `EmbeddingConfigRepository` | `EmbeddingConfig.is_active.is_(True)` | 与 llm 同构(同样 `is_active` 过滤) |
| `BookingConfigRepository` | `None`(不过滤) | 表无 `is_active` 列,钩子保持默认 |

但 `twoscope-config` 的 plan 经过 EP2 回环的 opus 子智能体审查后,**明确列出 2 个不纳入 repo + 2 类不进基类的方法**(均有 leverage 论证):

| 不纳入的 repo | 不纳入原因 |
|---|---|
| `ModelPricingRepository` | **二维 key 异类**:key 是 `(tenant_id, model)` 而非 nullable `tenant_id`,不匹配 `get_platform`/`get_for_tenant` 的「单 key + NULL=平台」语义。repo 已存在(`app/repositories/wallet.py:87`)+ 已被 `BillingService` 注入(`billing_service.py:62`)+ `calc_cost` 已封装二维解析,纳入基类 = 强行套单 key 模型 |
| `tenant_config` | **单租户异类**:无 platform 默认行(纯 tenant-scoped 业务数据),根本没有「两级覆盖」语义,与 `TwoScopeRepository` 的前提(可空 `tenant_id`)不匹配。它本就属于 `TenantScopedRepository` 范式 |

| 不进基类的方法 | 不进原因 |
|---|---|
| `get_effective`(三级 fallback:tenant > platform > 第三级) | 返回类型(`EffectiveLlm`/`EffectiveEmbedding`/`EffectiveBookingConfig`)各异 + 第三级投影(env vs 硬编码 + source tag)是真业务差异。强行泛型化会引入 `TypeVar` 绑定 + 第三级分支特化,收益打折 |
| `_upsert`(写路径) | 三种真业务差异:`LlmConfigService` 有 crypto 加密 API key、`BookingConfigService` 有 audit log、`EmbeddingConfigService` 无 crypto 但有 masked read。这些是各 service 的核心职责,不是样板 |

**为何用 `_active_filter` 钩子而非给 `BookingConfig` 加 `is_active` 列**(审查 P0-1 回炉):

v1 决策曾考虑「给 `BookingConfig` 加 `is_active` 列以对称」。但核查代码后发现:**三个配置的 `is_active` 全是预留死列** —— 全代码库仅 `security/api_token/model_pricing` 设过 `is_active=False`,三个 config repo/service 的 `_upsert` 均不写 `is_active=False`。给 booking 加列 = 为对称引入死列 + schema 改动 + 迁移风险,违反 AGENTS.md 铁律 6「不过度设计」。钩子方案(`_active_filter` 属性,booking 设 `None`)零 schema、零死列、零迁移,且**诚实承认 `is_active` 在三者都是预留死列**(配置软停用是独立业务 feature,不在本次)。

**触发本 ADR 的张力**:

`twoscope-config` 收官前,这个「纳入/排除边界」散落在 plan §4 + 三个 repo/service 的 docstring 互指里,且**口径不一致**:

1. 三个 repo 的 docstring 互指「Mirrors LlmConfigRepository / Mirrors LlmConfigService」(booking/embedding 指认 llm 是模板),暗示「未提取的重复」,而非「已裁决的边界」
2. CONTEXT.md `Two-Scope Config` 词汇条目(grill 阶段已加)提到了 `TwoScopeRepository` 却无 ADR 钉边界
3. plan §1 措辞「3 repo 重复」与「为何排除 ModelPricing/tenant_config」的论证只藏在 plan §2/§4,未固化成不可变档案

**后果**:未来巡检 agent 会 re-suggest「为什么 ModelPricing 不纳入基类」「为什么 `_upsert` 不进基类」(本项目第 5 次巡检已把 ModelPricing 当候选提过),因为读 docstring 看到的是「开放重复」而非「已裁决边界」。每次都要重新走一遍 grill。

---

## Decision

**`TwoScopeRepository` 的采纳范围定格在「booking_config / llm_config / embedding_config 三个 repo 的读路径(`get_platform`/`get_for_tenant`)」**,不扩到上述不纳入清单。具体边界:

1. **纳入的 3 个 repo**(`LlmConfigRepository` / `EmbeddingConfigRepository` / `BookingConfigRepository`)改继承 `TwoScopeRepository`,自写的读路径删除,`is_active` 过滤差异用 `_active_filter` 钩子吸收(前两者设过滤,booking 设 `None`)
2. **不纳入的 2 个 repo**(`ModelPricingRepository` / `tenant_config`)继续各自独立,**理由见上方 Context 表**(二维 key 异类 + 单租户异类,均 leverage 论证)
3. **2 类不进基类的方法**(`get_effective` / `_upsert`)继续由各 service 自留,**理由见上方 Context 表**(返回类型 + 第三级投影 + crypto/audit/字段集是真业务差异)
4. **`_active_filter` 钩子的契约**:子类覆盖 `_active_filter` 类属性;`None` = 不过滤(booking),带值(如 `Model.is_active.is_(True)`) = 查询追加 `.where(self._active_filter)`。**不给无 `is_active` 列的表设过滤** —— 钩子比加死列更诚实(不假装 booking 也有此语义)

**单一真相源**:本 ADR 是「Two-Scope 配置基类采纳清单」的权威记录。其他文档(CONTEXT.md / 三个 repo docstring / 两个 service docstring / embedding model docstring)只做「见 ADR-0002」的指针,**不枚举清单**(避免双重维护漂移)。

---

## Consequences

**正面**:

- **防 re-suggest**:未来巡检 agent 看到 ADR-0002 Accepted + supersede 流程,知道这是已裁决边界,re-suggest「ModelPricing 纳入」「`_upsert` 进基类」时必须先走 supersede 流程(不能直接当新候选提)
- **口径统一**:三个 repo/service/model 的「Mirrors XxxConfig」互指统一收口为「Extends TwoScopeRepository(见 ADR-0002)」,docstring 互指债务消解,grep「Mirrors LlmConfig / Mirrors .*ConfigService / Mirrors .*ConfigRepository」→ 0 处
- **范式互补**:本 ADR 与 ADR-0001 共同建立「Repository 层两大范式基类的采纳边界」—— `TenantScopedRepository`(业务数据隔离,`tenant_id` 必填)+ `TwoScopeRepository`(配置两级覆盖,`tenant_id` 可空),边界均有 ADR 钉死
- **零运行时影响**:基类只吃读路径,查询语义逐字不变;`is_active` 钩子方案零 schema、零死列、零迁移

**负面**:

- **未来扩基类的成本变高**:必须先写 ADR-NNNN 标 `Superseding ADR-0002` + 改本 ADR Status,不能顺手加 repo。这是设计意图(防止误纳入异类),但确实是流程成本
- **清单维护**:纳入/排除清单(3 纳入 + 2 排除 + 2 类方法不进)现在固定在 ADR 里,如果未来新增一个真正的两级配置表,应纳入基类 —— 此时需更新本 ADR 的纳入清单(增量加一行),但排除清单(ModelPricing/tenant_config)除非其 key 模型根本改变,否则不动
- **钩子的 TypeScript 式约束缺失**:Python 无法在类型层强制「子类 `_active_filter` 必须是 `ColumnElement[bool] | None`」,靠 docstring + review 把关。继承者若给无 `is_active` 列的表误设过滤,会运行时炸查询(缓解:基类 docstring 写清契约 + 本 ADR 记录)

**中性**:

- **零代码影响**:本 ADR 是边界固化决策,代码改动在 `twoscope-config` 切片 1/2 已落地,本 ADR 只做档案固化 + 指针对齐

---

## Superseding this ADR

**要扩/改 `TwoScopeRepository` 的采纳范围超出本 ADR**(如把 `ModelPricing` 纳入基类 / 把 `get_effective` 或 `_upsert` 收进基类 / 改 `_active_filter` 钩子机制为加列方案),必须:

1. 新建 `docs/adr/NNNN-*.md`(NNNN = 下一个 ADR 编号),Status 标 `Superseding ADR-0002`
2. 在新 ADR 的 Context 段论证:为什么推翻 ADR-0002 的 leverage 论证(如「ModelPricing 的 key 模型重构为 nullable `tenant_id` 后,纳入基类的成本变低了」/「`get_effective` 的第三级投影经抽象后可统一」)
3. 把本文件(ADR-0002)的 Status 从 `Accepted` 改为 `Superseded by ADR-NNNN`
4. 同步更新 CONTEXT.md / 三个 repo docstring / 两个 service docstring / embedding model docstring 的指针(从「见 ADR-0002」改成「见 ADR-NNNN」)

**禁止**:直接编辑本 ADR 的 Decision 段(增量加 repo / 删 repo / 改钩子机制)。ADR 是不可变档案,改决策 = 推翻 + 新建。

---

## References

- [`harness/docs/plan-twoscope-config.md`](../../harness/docs/plan-twoscope-config.md) §4 决策矩阵 + §4.7 Out of Scope(本 ADR 的 leverage 论证来源)
- [`harness/docs/plan-twoscope-config.md`](../../harness/docs/plan-twoscope-config.md) §0 v1→v2 变更摘要(`_active_filter` 钩子方案回炉历程)
- [`CONTEXT.md`](../../CONTEXT.md) Two-Scope Config 条目(L119-121,本 ADR 钉死其边界措辞)
- [`app/repositories/two_scope.py`](../../app/repositories/two_scope.py) `TwoScopeRepository` 基类本体
- [ADR-0001](0001-principal-scope-boundary.md) Principal scope boundary(本 ADR 的结构范式来源 + 互补边界)
- [`harness/docs/codebase-health-log.md`](../../harness/docs/codebase-health-log.md) 2026-07-29 第 5 次巡检 Top recommendation(本 ADR 的触发源)
