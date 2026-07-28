# 计划:Principal 范围边界文档对齐(CONTEXT + docstring + ADR-0001)

> **id**: principal-scope-doc-alignment
> **状态**: passing(EP3 切片 01 已完成,2026-07-28)
> **优先级**: 71(「工程化」area,文档对齐债)
> **创建日期**: 2026-07-28
> **来源**: [codebase-health-log.md](./codebase-health-log.md) 2026-07-27 第 4 次巡检 · 候选 3(Strong,Principal 半收口 — CONTEXT 措辞 vs 代码张力)

---

## 1. Problem Statement

principal-module feature(priority 70,2026-07-27 收官)抽出了 `Principal` 深模块,吸收 booking/device/customer 三 service 的鉴权决策。**但 plan §4.2 明确有 4 个不迁方法 + plan §6 明确有 4 个非采用 service**(均有 leverage 论证,经 principal-module EP2 回环的 opus 子智能体审查过)。

然而这个「半收口」决策只散落在三处,且**口径不一致**:

1. **CONTEXT.md:30** 措辞过宽:「booking / device / customer 三 service 的鉴权决策**统一走 Principal**」—— 暗示全覆盖,漏掉了 plan §4.2 的 4 方法 + 4 service 不采用
2. **principal.py docstring(L18-22)** 留模糊口子:「retained for out-of-scope callers; adoption of Principal across other services can be evaluated in future architecture reviews」—— 把已审查的「不迁」说成「未来可扩」
3. **4 个 helper docstring(permission_service L677/L702 + _tenant_target L40-42 + data_scope L70-71)** 同款「future architecture reviews」口子,共 5 处散落

**核心张力**:CONTEXT.md 宣称「统一走」、docstring 留「未来可扩」口子,与 plan §4.2 的「明确不迁 + leverage 论证」形成口径冲突。**未来巡检会 re-suggest 候选 3**(本次第 4 次巡检就已 re-suggest),因为读 docstring 看到的是「开放决策」而非「已裁决边界」。

> **溯源**:principal-module EP2 回环的 grill 把「不迁范围」钉死在 plan §4.2(opus 审查 §1.4 RED:纠正了把 `get_device_schedule` 误归 panorama 的判断),切片 02a AC2a.3 为 booking 4 方法加了 `# Note(principal-scope):` 注释,切片 03 AC3.5 为 4 helper docstring 加交叉引用。**但当时没建 ADR,docstring 措辞仍留「可扩」口子**。本任务就是这个债的收尾。

## 2. Solution

**纯文档对齐**(零代码改、零行为变更)。把「Principal 半收口边界」从散落的 5 处口径统一收口为 **ADR-0001 单一真相源**,其他 6 处只做「见 ADR-0001」的指针。

**核心原则**:清单只在 ADR-0001 出现完整版,其他 6 处只写「见 ADR-0001」+ 不枚举(避免双重维护漂移)。

## 3. User Stories

- 作为**未来巡检 agent**,我想看到 ADR-0001 的「Accepted + supersede 流程」就知道候选 3 是已裁决边界,以便不再 re-suggest
- 作为**后端开发者**,我想 CONTEXT.md + principal.py docstring 准确告诉我 Principal 的覆盖范围,以便写新 service 时知道该不该用 Principal
- 作为**项目维护者**,我想项目的第一个 ADR 走顺范式,以便未来其他架构决策(候选 2/4 等)能复用模板

---

## 4. Implementation Decisions

### 4.0 grill 共识(本 plan 决策真相源)

| # | 决策点 | 锁定值 | 论证 |
|---|---|---|---|
| A | 方向 | **文档对齐**(非扩 Principal,非维持现状) | plan §4.2 不迁论证是 opus 审查过的,扩 Principal 会破坏 Principal 语义纯净度(customer principal 无 tenant 概念);维持现状会持续发酵 |
| A1 | CONTEXT 改粒度 | **最小补丁 + 跳转 plan** | CONTEXT 是 glossary 不是 spec,完整清单留给 plan/ADR;措辞用「读写鉴权路径」+「少量方法因不属于角色-租户三元组」不点名方法 |
| B1 | principal docstring | **指向 ADR + 硬约束** | docstring 列具体 service 名(用户可见 API,改名频率低,对读者直接有用);用「superseding that ADR」替代「re-opening plan decision」(ADR 是裁决,推翻 ADR 是标准流程) |
| C1 | ADR | **新建 ADR-0001**(项目第一个) | plan §4.2 是已审查的不迁决策,值得 ADR 钉死防 re-suggest;CONTEXT.md L5 已声明「lazy 创建」,本任务正好触发 |
| D1 | 切片策略 | **单切片 EP3,7 改动绑一个 commit** | 7 改动是同一决策的落点,分开破坏 locality + 留中间状态不一致窗口(ADR 说不扩、docstring 还说可扩) |
| E1 | scope 确认 | **维持单切片(含漏 3 必须 + 漏 1 推荐 + 漏 2 可选)** | 漏 3 必须修(否则 5 处「可扩」措辞架空 ADR);漏 1/2 是 ADR 锚点扩散,加强防线 |

### 4.1 子智能体审查发现(opus × 2,共 3 RED + 4 YELLOW + 漏掉事实)

**真相核查 agent(8 条判断核查)**:

| 判断 | 评级 | 说明 |
|---|---|---|
| 1. Explore agent 误判(L414/L727 是 get_tenant_schedule/start,不是 list_schedule_grid/update_booking) | ✅ GREEN | 行号语义对,Explore 编造方法名 |
| 2. plan §4.2 不迁清单 4 方法 + leverage 论证 | ✅ GREEN | 表内行号漂移(:653→实际:680 等),不影响判断 |
| 3. 「切片 03 AC3.5 要求 # Note 注释」 | 🔴 RED | **对象错位**:`# Note(principal-scope)` 由切片 **02a AC2a.3** 要求(booking 4 方法);切片 **03 AC3.5** 要求改 **4 helper docstring**(即漏 3 那批)。两个 AC 是不同切片、不同对象 |
| 4. principal.py docstring 留模糊口子 | ✅ GREEN | 措辞逐字准确 |
| 5. 其他 4 service 完全没用 Principal | ✅ GREEN | 但漏看了 6 个 api 层调用点(exports/logs/search/customers/booking_config/deps) |
| 6. CONTEXT.md「统一走 Principal」 | ✅ GREEN | 逐字准确 |
| 7. device 7/7、customer 2/2 | ✅ GREEN | 但 customer_service 还有 2 个 super_admin 全局读方法(list_customers_hq/get_customer_aggregate)无 helper 无 require,plan §6 隐含覆盖但 §4.2 未显式列 |
| 8. docs/adr/ 不存在 | ✅ GREEN | 且是项目 lazy 创建设计(CONTEXT.md L5 声明) |

**设计审查 agent(4 改动 + 漏项评估)**:

| 改动 | 评级 | 关键问题 |
|---|---|---|
| 改动 1 CONTEXT.md | 🟡 YELLOW | 漏 customer scope 分支;误并 `get_device_schedule` 为 panorama 类(它是纯 store require,plan §4.2 L166 明说「不用 helper」) |
| 改动 2 principal.py docstring | 🔴 RED | 「re-opening plan decision」定位不到权威;措辞与 ADR 冲突;覆盖 4 方法不全(漏 `get_device_schedule` + 错归 `list_my_bookings`) |
| 改动 3 ADR-0001 | 🟡 YELLOW | 结构对;建议列完整清单(不纯引用);补 supersede 流程说明 + Deciders 字段 |
| 改动 4 plan §4.2 交叉引用 | 🟡 YELLOW | 相对路径多一层(`../../../` → 根相对 `docs/adr/`)+ `⓵` 换纯 markdown + 位置放表格后 |
| **漏 1**(推荐补) | 🟡 推荐 | booking_service 4 处 `# Note(principal-scope)` 加 ADR 引用(纯注释,零风险) |
| **漏 2**(可选) | 🟢 低优先 | 4 非采用 service docstring 加「intentionally bypasses」(device_model/group 是 platform-level,措辞要区分) |
| **漏 3**(必须补) | 🔴 必须 | 4 helper docstring 同款「future architecture reviews」口子,与 ADR「不扩」直接冲突 |

**关键洞察**(设计审查核心建议):**「不迁清单」真相源单一化到 ADR-0001**(完整清单 + supersede 流程);其他 6 处只做「见 ADR-0001」的指针,不枚举。

### 4.2 不可违反契约

1. **零代码改、零行为变更** —— 仅文档/注释改动,任何 `.py` 文件不能改代码逻辑(docstring/注释除外)
2. **单一真相源** —— 清单只在 ADR-0001 出现完整版,其他 6 处只写「见 ADR-0001」
3. **引用链闭合** —— CONTEXT → plan §4.2 → ADR-0001 → plan §4.2 闭环;principal docstring / 4 helper docstring / booking Note / 4 service docstring 都指向 ADR
4. **supersede 流程明确** —— ADR 必须说明「推翻 ADR 需新建 ADR-NNNN 标 Superseding + 改本 ADR Status」
5. **零测试影响** —— `./init.sh` 必须仍 783 passed(零代码改 → 零回归)

---

## 5. Implementation Slice(EP3 单切片)

### 切片 01 — 文档对齐 7 改动(单切片 = 末切片) ✅(2026-07-28)

**What to build**(用户视角):作为未来巡检 agent / 后端开发者 / 项目维护者,我能在 ADR-0001 看到 Principal 半收口的完整裁决,在 CONTEXT / principal docstring / 4 helper docstring / booking Note / 4 service docstring 看到「见 ADR-0001」的统一指针,口径不再冲突。

**Blocked by**: 无(frontier,可立即开工)

**Status**: ✅ done(2026-07-28)

**改动清单**(7 改动 = 1 新建 + 6 编辑):

- [x] AC1.1 **改动 1**(CONTEXT.md Principal 条目 L29-31):把「booking / device / customer 三 service 的鉴权决策统一走 Principal」改为「booking/device/customer 三 service 的**读写鉴权路径**(写路径 + 读路径的 panorama 与 store scope 两分支)走 Principal;**少量方法因不属于角色-租户三元组**(三叉 customer / 全局读 / panorama 无 require / 纯 store require)**仍直接用 helper** —— 边界清单见 `harness/docs/plan-principal-module.md` §4.2(由 [ADR-0001](docs/adr/0001-principal-scope-boundary.md) 钉死,扩展需先 supersede ADR)。**不点名具体方法,不枚举 service**(/code-review Standards HARD 修正:删去 4 类方法名展开,改 glossary 性质的关键词)
- [x] AC1.2 **改动 2**(principal.py docstring L18-22):把「plus for out-of-scope callers; adoption can be evaluated in future architecture reviews」改为「plus for the **explicitly out-of-scope callers** pinned by **ADR-0001** —— these intentionally bypass Principal; **do NOT extend Principal to them without superseding that ADR**. The full scope decision (non-migrating methods + non-adopting services) lives in `harness/docs/plan-principal-module.md` §4.2.」**不枚举清单,不列具体 service 名**(/code-review Spec YELLOW 修正:删去 `like conversation / dashboard / device_model / group`,改为「non-adopting services」)
- [x] AC1.3 **改动 3**(新建 `docs/adr/0001-principal-scope-boundary.md`):Nygard 五段式 ADR + Superseding 流程段 + Deciders 字段。Decision 段完整列出不迁清单:4 方法 + 2 super_admin 方法 + 4 service + 6 api 文件。Status: Accepted,Date: 2026-07-28(注释说明与 Deciders 的 27 号关系)
- [x] AC1.4 **改动 4**(plan §4.2 表格后):加一行 markdown 引用(纯文字 `> 🔒`,不用 `⓵`):「本节不迁范围由 [ADR-0001](../../docs/adr/0001-principal-scope-boundary.md) 裁决,扩展 Principal 必须先 supersede 该 ADR。」相对路径 `../../docs/adr/`(plan 在 harness/docs/,回根 ../../)
- [x] AC1.5 **改动 5**(4 helper docstring 5 处口子):「future architecture reviews」统一改为「intentionally retained/pinned by ADR-0001; do NOT extend Principal without superseding that ADR」。grep 验证 5 → 0 处 ✅
- [x] AC1.6 **改动 6**(booking_service 4 处 `# Note(principal-scope)` 注释):每处加第二行「边界由 ADR-0001(docs/adr/0001-principal-scope-boundary.md)钉死,扩展需先 supersede ADR。」
- [x] AC1.7 **改动 7**(4 非采用 service docstring):conversation/dashboard 加「intentionally bypasses Principal (read pattern doesn't fit panorama/scope dichotomy)」;device_model/group 加「platform-level service (no tenant concept), outside Principal's applicable domain」。均指向 ADR-0001
- [x] AC1.8 **验证**:`./init.sh` 全绿 **783 passed**(零代码改 → 零回归,244.76s)+ ruff clean + grep 验证「future architecture reviews」从 5 → **0 处** + ADR-0001 引用 **23 处**(超出预期,含 4 service 新加)
- [x] AC1.9 **feature 收尾**:feature_list.json status `in_progress → passing` + evidence 写入 + `./scripts/sync-active-features.sh` 刷新 + progress.md 顶部「最高优先级未完成」+ plan status `draft v1 → passing` + 切片标题 ✅ + AC 勾选(本步执行中)
- [x] AC1.10 **文档影响评估**:① feature_list.json ✅ / ② progress.md ✅ / ③ CONTEXT.md ✅(本任务核心)/ ④ plan → passing;**新建 `docs/adr/` 目录 + 项目第一个 ADR**(范式建立,影响未来所有 ADR)

---

## 6. 切片依赖图

```
切片 01(单切片 = 末切片,7 改动绑一个 commit)
```

无依赖图(单切片)。

## 7. 测试策略

- **零代码改 → 零测试改**:`./init.sh` 必须仍 783 passed
- **docstring 改动不影响 ruff**:ruff 只查代码不查 docstring 文案,但仍需 clean
- **引用链 grep 验证**:`grep -rn "ADR-0001\|future architecture reviews"` 前后对比,前者从 0 → N,后者从 5 → 0
- **手动核对**:CONTEXT / principal docstring / ADR-0001 三处对读,确认口径一致(都说不扩,都说见 ADR)

## 8. Out of Scope

- **不改任何代码逻辑** —— 即使发现 booking 的 4 不迁方法其实可以走 Principal(违反 plan §4.2),本任务也不动,留给未来 supersede ADR 的任务
- **不补 plan §4.2 漏列的 2 个 customer super_admin 方法** —— ADR-0001 会列(作为「plan §6 隐含覆盖但 §4.2 未显式列」的事实记录),但 plan §4.2 表格不补(避免改历史 plan)
- **不做候选 2(配置范式 leverage)/ 候选 4(union cast)等其他巡检候选** —— 那些是独立 feature

## 9. 文档影响评估

| 文档 | 影响 | 说明 |
|---|---|---|
| `feature_list.json` | ✅ | 新增 feature `principal-scope-doc-alignment` priority 71 + 完成后 status→passing + evidence |
| `progress.md` | ✅ | 顶部「最高优先级未完成」+ 切片 Session 记录 |
| `CONTEXT.md` | ✅ | 本任务核心改动之一(Principal 条目修订) |
| `docs/adr/` | ✅ | **新建目录 + 项目第一个 ADR**(范式建立,影响未来所有 ADR) |
| `项目指南/` | ❌ | 不需补(纯文档债,现有架构文档完全覆盖 Principal 范围) |
| README.md | ❌ | 不动 |

## 10. 参考

- [codebase-health-log.md](./codebase-health-log.md) 2026-07-27 第 4 次巡检
- [plan-principal-module.md](./plan-principal-module.md) §4.2 不迁清单 + §6 非采用 service 清单
- opus 子智能体审查报告(2 份,本会话内)
