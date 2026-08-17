# 计划:SSE 钱包门口径统一(chat-stream-wallet-gate)

> **id**: chat-stream-wallet-gate
> **状态**: in_progress(EP3 切片 01 开工 2026-08-17,与 feature_list.json 同 commit 翻页)
> **优先级**: 94(feature_list.json,第 10 次巡检业务风险 R3 前半 🔴)
> **创建日期**: 2026-08-16
> **最后修订**: 2026-08-16(v2:对抗式审查回写)
> **来源**: [plan-risk-hardening-overview.md](./plan-risk-hardening-overview.md) §3(总纲 D5 已拍板:先钱包门止血后对账兜底,不动 TurnAccountant)
> **EP2 回环**: grill(2026-08-16,**8 项决策全部用户逐项拍板**,AskUserQuestion 3 轮,无「按推荐默认采纳」——系列铁律,见 §4.5 D1-D8)→ to-spec(v1)→ 对抗式审查(双轴并行)→ to-tickets(v2,§6)

---

## 0. v1 → v2 变更摘要(对抗式审查回写,2026-08-16 双轴并行)

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| verification 第 2 条「现有 chat SSE 测试全绿」的前提未钉死:既有流式测试因改严挂 `funded_wallet` fixture 时,可能被顺手放宽断言冒充全绿 | 🟡 | 切片 01 AC 明确:挂 fixture 修复**不得放宽任何既有断言**,只补钱包前置条件 |
| D4「完整对齐 composite UI」的清除时机只写了重试前清除,漏 composite 先例的另一半:切换会话时清除(useEffect on selectedConversationId) | 🟡 | §4.6 前端设计 + 切片 02 AC 补齐:发送前 + 切换会话双清除 |
| 「被拦不再建会话/落用户消息」只有一句带过,未拆场景:v1 未区分「新会话被拦(两者都为 0)」与「续问已有会话被拦(messages 计数不变)」两个断言 | 🟡 | 切片 01 测试矩阵拆成两条独立断言(矩阵 ② 与 ⑥) |
| 风险表漏运营侧风险:存量无钱包租户(预计费时代建租户/异常态)上线即被拦,D2 拍板了口径但 v1 未列缓解 | 🟡 | §9 首行补:上线前 SQL 盘点无 live wallet 租户交运营甄别;生产正常路径出生即建钱包不触此态 |
| 切片 01 文件清单漏注释债:`chat.py` 内 composite docstring「Stricter than /chat/stream's "no wallet = allow" degradation」段与 event_source 旧检查注释,行为统一后即成谎言 | 🟡 | 切片 01 AC 补「chat.py 相关注释/docstring 口径同步」 |
| 切片 02 文件清单漏前端过时注释:`composite-chat.ts` 头部「strict, unlike /chat/stream's … SSE error frame」注释同理失真 | 🟡 | 切片 02 AC 补一行修正(同域注释,不算越界) |
| 「既有流式测试挂 fixture」清单写死 4 个文件有预判风险:是否每个都走 happy path 未逐一核实 | 🟢 | AC 措辞改「以 `./init.sh full` 红灯为准,因改严而红的统一挂 funded_wallet」,清单作预期参考不作承诺 |
| 一致性断言(verification 第 3 条)v1 只说「断言一致」,未定断言强度与挂靠文件 | 🟢 | 定为:同一 broke 租户两路径均 402 且 `json()["detail"]` **逐字相等**,挂 `tests/test_billing.py` SSE 门测试旁(R2 判别单测挂靠先例) |
| 状态行约束未记录:CI backend job 已常驻 `check_plan_status_sync.py`(ci.yml),状态行与 feature_list 不同步会红 CI | 🟢 | 状态行钉 not_started;EP3 开工同 commit 翻页(用户指令,R1 同款先例) |
| E2E/CLI 零影响结论缺证据锚点 | 🟢 | §10 记锚点:E2E 用种子 super_admin 登录(frontend/e2e/main-flow.spec.ts:15-17,两路径门都 bypass);CLI `stream_sse` ≥400 → ApiError 透 detail(cli/client.py:89-95) |
| helper 的 import 形态未定(模块级 vs 函数内延迟) | 🟢 | 钉死:沿用本文件 billing 延迟 import 惯例(chat.py 现两处均函数内 import,helper 内 import 一处) |

## 1. Problem Statement

同一钱包契约,两条对话路径两套口径(第 10 次巡检 R3 前半 🔴):

- **composite 路径**(`/POST /chat/composite`)严格:干活前 `BillingService.has_balance` 预检,不通过 → HTTP 402。
- **SSE 路径**(`/POST /chat/stream`)宽纵:HTTP 200 + SSE 头**已发出后**才在 `event_source` 开头查,且口径是「**有钱包**且 balance ≤ 0 才拦」——**无钱包租户永久放行**,流式全程免费,是持续性资损口。零余额租户虽被拦,但拦之前会话已建、用户消息已落(垃圾数据),且只能发 SSE error 帧不能发真状态码。

生产上 `create_tenant` 同事务建零余额钱包(billing_service docstring:「every tenant has a wallet from birth」),「无钱包」本身是异常态(预计费时代存量/测试环境),不该由代码永久兜底免费。

## 2. Solution

SSE 路径补与 composite **同一函数、同一口径、同一错误体**的钱包预检:抽共享门 helper(`super_admin` 直返;`has_balance` 为假 → `HTTPException(402, detail="token 余额不足,请联系总部充值")`),SSE 在 `_load_agent`(404)之后、建会话之前调用——被拦请求收到真 402,且不再白建会话/落用户消息;composite 内联预检替换为同一 helper(行为零变化);`event_source` 内旧检查整段移除(含 fail-open except)。「同口径」从注释约定变成**结构事实**(两路径调同一函数)。前端对齐 composite 先例:402 → 专用错误类 → chat 页充值引导面板(「前往充值」CTA)。

不动 TurnAccountant、不动 charge/计费编排(总纲 D5);对账兜底是下一条 billing-reconciliation-job(R3b)的事。

## 3. User Stories

1. 作为门店员工,我的钱包余额不足(或无钱包)时,发起流式对话**立即**收到明确的 402「token 余额不足,请联系总部充值」——不再流到一半才收到 error 帧,更不再永久免费白嫖(平台资损)。
2. 作为有余额的门店员工,流式对话体验零变化(预检只是一次毫秒级 DB 查询,无感知)。
3. 作为被拦的门店员工,chat 页看到「余额不足」引导面板,一键「前往充值」,充值后重试即可继续——与 composite 路径体验一致(对齐先例 AC4.8)。
4. 作为 super_admin(平台级身份),流式与复合对话都不受钱包门影响(永不计费,既有行为延续)。
5. 作为平台运营,同一钱包契约只有一套口径(两路径共用同一门函数),资损口关死;被拦请求不再留下垃圾会话与用户消息。
6. 作为 CLI 用户(`agenthub agents chat`),402 的 detail 文案经 ApiError 既有映射原样透出,无需升级 CLI。
7. 作为开发者,SSE 门的回归测试常驻 CI(SQLite 套件),两路径 402 错误体一致性有机械断言防漂移。

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 1 | `app/api/v1/chat.py`(共享 helper + SSE 预检 + 移除流内旧门 + composite 改调 helper + 注释/docstring 口径同步) |
| 数据库迁移 | 0 | 无任何 schema 改动 |
| 前端文件改动 | 2-3 | `frontend/src/api/endpoints/search.ts`(402 → 专用错误类)/ `frontend/src/pages/chat/index.tsx`(充值引导面板 + 双清除)+ 可选面板小组件;`composite-chat.ts` 过时注释一行修正 |
| 新增测试 | 2 | `tests/test_billing.py` 扩 SSE 门 402 矩阵(SQLite 常驻)+ `frontend/src/pages/chat/__tests__/` 前端测试 |
| 测试基建 | 1 | `tests/conftest.py` 新 `funded_wallet` opt-in fixture + 既有流式测试文件挂接(test_chat / test_multi_agent / test_usage_tracking / test_customer_conversation,以全量红灯为准) |
| CI | 0 | 零改动(E2E 走种子 super_admin 天然绕过;check_plan_status_sync 已常驻) |
| CLI | 0 | 零改动(ApiError ≥400 映射已透 detail) |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**(零 schema 改动)
- 是否修改现有租户隔离逻辑? **NO**(`has_balance` 按 tenant_id 查询,单租户作用域不变)
- 是否引入跨租户访问点? **NO**
- 验证:多租户既有测试零回归(`./init.sh full`)

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 require_permission caller? **NO**(钱包门是计费预检,不是权限;router 级 `conversations:chat` 检查位置不动)
- 是否影响 graph.py 工具内 check? **NO**
- super_admin bypass:既有行为延续(两路径现状都 bypass,helper 原样收编)

### 4.4 数据库表设计 checklist(AGENTS.md 铁律 6)

- 无新表无新列无索引无迁移 — **全部 N/A**。本条是纯 API 行为统一,是系列里唯一零 schema 零迁移的 feature。

### 4.5 用户拍板决策(D1-D8,2026-08-16 AskUserQuestion 3 轮逐项拍板,无默认采纳)

**总纲既定三项(第 1 轮)**

| # | 决策点 | 拍板结果 |
|---|---|---|
| D1 | 预检时点 | **建立连接前,真 402**:endpoint 体内、`create_or_get` 之前查,无余额直接 `HTTPException(402)`,与 composite 同时序(agent 404 → 钱包 402 → 建会话)。附带收益:被拦请求不再白建会话 + 落用户消息;CLI 天然透出 detail。**否决**:首 token 前流内查(200 已发出只能发 error 帧,「同口径 402」名不副实,验收项无法满足) |
| D2 | 余额判断口径 | **逐字对齐 composite**:直接复用 `BillingService.has_balance` —— 无钱包=拦(资损口关死)、余额 >0 才放、0/负=拦、inactive 钱包=拦(`get_for_tenant` 滤 is_active,等价无钱包)。生产租户出生即建零余额钱包,「无钱包」是异常态,预计费存量属运营甄别个案,不由代码永久兜底免费。**否决**:保留无钱包放行(资损口只关一半,口径仍不一致) |
| D3 | 402 错误体 | **复用 composite 现有格式**:`HTTPException(402, detail="token 余额不足,请联系总部充值")`,同状态码同文案;verification 第 3 条「两路径错误体一致性断言」可直接写成对比测试 |

**烤问新发现三项(第 2 轮)**

| # | 决策点 | 拍板结果 |
|---|---|---|
| D4 | 前端范围 | **完整对齐 composite UI**(用户选了比「最小适配」推荐更大的面):chat 页 402 → 专用错误类 → 充值引导面板(Wallet icon + 后端 detail + 「前往充值」CTA),对齐 composite AC4.8 先例;不是仅 toast |
| D5 | 流内旧门去留 | **移除,抽共享 helper**:预检成为唯一门,两路径调同一函数——「同口径」从约定变结构,双门漂移永不复发;钱包查询异常时与 composite 对齐(500,**fail-open 移除**——现状查询失败静默放行也是资损口的一部分) |
| D6 | 测试地基 | **conftest 提供 opt-in `funded_wallet` fixture**:需要走通流式路径的测试显式启用;「无钱包→402」新测试与 composite 现有 no-wallet 测试零波及。**否决**:test_env 默认建钱包(击穿 composite no-wallet 测试 + 同租户重复插钱包冲突风险)/ 逐文件自抄 seed(重复代码,新文件还会踩坑) |

**seam 与切片确认(第 3 轮)**

| # | 决策点 | 拍板结果 |
|---|---|---|
| D7 | 测试 seam | **后端全走 HTTP 层**(app_client + 内存 SQLite;402 预检在 LLM 调用前触发,新测试无需 mock 流式;沿用 test_billing.py 既有 SSE 门测试与 test_composite_chat.py 402 测试范式);共享 helper 不单独单测(3 行转发,`has_balance` 已有单测,HTTP 测试全覆盖);**前端 vitest + testing-library 组件级**(沿 chat/__tests__ 既有范式 + R1 rate-limited-toast 真链路先例) |
| D8 | 切片粒度 | **2 片线性**:01 后端门(frontier,可独立交付)→ 02 前端体验收口 + feature 收尾(末切片) |

### 4.6 技术设计细节(实施层约定)

**共享门 helper(`app/api/v1/chat.py` 模块级私有)**

- 签形:`async def _require_wallet_balance(db: AsyncSession, user: CurrentUser) -> None`
- 逻辑:`user.platform_role == "super_admin"` 直接返回;否则(函数内延迟 import `BillingService`,沿用本文件 billing 延迟导入惯例)`await BillingService(db).has_balance(user.tenant_id)` 为假 → `raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="token 余额不足,请联系总部充值")`
- **无 try/except**:钱包查询异常即 500,与 composite 现状逐字对齐(fail-open 随旧门一并移除,D5)
- SSE 调用点:`_load_agent`(404)之后、`conv_service.create_or_get` **之前**;composite 调用点:替换现有「Wallet pre-check」内联三行为 helper 调用,行为零变化

**SSE 端点内的移除项**

- `event_source` 开头的旧检查整段删除:`platform_role != "super_admin"` 分支、`get_wallet` + `balance <= 0` 判断、SSE error 帧 yield、fail-open `except Exception: pass`、及其上方解释注释块(「missing wallet is intentionally NOT blocked」段随行为废止)
- 模块顶部 `json` import 保留(delta 帧序列化仍用);`_load_agent` 等其余逻辑零改动

**前端(`sendChatStream` 402 分支 + chat 页面板,D4)**

- `search.ts`:`export class ChatInsufficientBalanceError extends Error`(镜像 `CompositeInsufficientBalanceError` 形态);`sendChatStream` 的 `!resp.ok` 分支:401 特判**不动**;402 → `await resp.json()` 容错取 `detail`(取不到用兜底文案)→ throw `ChatInsufficientBalanceError(detail)`;其余非 200 维持泛化错误现状
- `chat/index.tsx`:`balanceError` state;`catch` 中 `instanceof ChatInsufficientBalanceError` → `setBalanceError(err.message)`(其余错误维持 `toast.error("对话失败", ...)` 现状);面板对齐 composite 先例:Wallet icon + 标题「余额不足,无法发起对话」+ 后端 detail + 一行说明 +「前往充值」Button → `navigate("/billing")`(chat 页现无 useNavigate,新增;router 与 /billing 路由均已存在)
- **双清除**(composite 先例):发起下一次发送前 `setBalanceError(null)`;切换会话(useEffect on selectedConversationId)清除
- 面板可抽为 chat/ 目录下小组件便于 vitest(该目录已有 conversation-list-panel.tsx 抽件先例),也可内联——实施时按测试便利定,不强制

**测试基建(conftest `funded_wallet`,D6)**

- `async def funded_wallet(db_session, test_env)` opt-in fixture:插 `Wallet(tenant_id=test_env.tenant_id, balance=1_000_000)`(余额给足,不与具体消费量耦合),返回 Wallet 实例;docstring 注明镜像「生产租户出生即带钱包」语义、opt-in 是为了不击穿 no-wallet 语义测试
- 挂接对象:因 SSE 改严而红的既有流式测试(预期 test_chat / test_multi_agent / test_usage_tracking / test_customer_conversation 中的 happy path 用例),**以 `./init.sh full` 红灯为准**,挂 fixture 修复时不得放宽任何既有断言

**SSE 门测试矩阵(挂 `tests/test_billing.py` 既有 SSE 门测试旁,SQLite 常驻)**

| # | 场景 | 断言 |
|---|---|---|
| ① | 无钱包(翻转 `test_chat_allowed_when_no_wallet_exists`) | 402,detail 含「余额不足」 |
| ② | 零余额(翻转 + 强化 `test_chat_blocked_when_wallet_balance_is_zero`) | 402;conversations 与 messages 计数均为 0(不再白建会话/落消息) |
| ③ | 负余额(直插 balance=-5) | 402 |
| ④ | inactive 钱包(is_active=False) | 402(get_for_tenant 滤掉,等价无钱包) |
| ⑤ | super_admin 无钱包(super_admin_client + mock 流) | 流式放行(bypass 回归) |
| ⑥ | 续问已有会话被 402 | 该会话 messages 计数不变 |
| ⑦ | 两路径一致性(verification 第 3 条) | 同一 broke 租户分别 POST /chat/stream 与 /chat/composite:均 402 且 `json()["detail"]` 逐字相等 |
| ⑧ | 有余额 happy path(既有 `test_chat_allowed_when_wallet_has_balance`) | 零变化零改动 |

## 5. Testing Decisions

- **测试 seam(D7)**:后端全走 HTTP 层(app_client + 内存 SQLite)——最高既有 seam,402 预检在 LLM 调用前触发,矩阵 ①-④⑥⑦ 无需 mock 流式(⑤⑧ 沿用 `_mock_chat` 既有 mock 范式);helper 不单独单测。前端 vitest + testing-library 组件级。
- **既有范式**:SSE 门测试 = `tests/test_billing.py` 既有三条(371/386/405);composite 402 测试 = `tests/test_composite_chat.py`(289/301/311);前端 = `chat/__tests__/` 组件测试 + R1 `rate-limited-toast.test.tsx` 真链路先例。
- **前端测试最少两条**:402 → `ChatInsufficientBalanceError`(detail 透传,401 行为不回归);面板渲染(detail 文案 + 前往充值 CTA)。
- **零影响面已论证**:E2E(frontend/e2e/main-flow.spec.ts:15-17 种子 super_admin 登录,两路径门都 bypass)、CLI(cli/client.py:89-95 ≥400 → ApiError 透 detail)——两者不在改动清单,靠此论证 + CI 复验。
- **回归基线**:`./init.sh full` 全量(当前 1043 passed)零回归是硬门槛。

## 6. 实施切片(to-tickets 产出,EP2 单回环;粒度与阻塞边已经用户确认)

### 切片依赖图

```
01 后端统一钱包门(helper + SSE 预检 402 + 移除流内旧门 + funded_wallet + 测试矩阵)──→ 02 前端 402 充值引导 + feature 收尾(末切片)
```

> 顺序理由:门先行——没有真 402,前端 402 处理是死代码;切片 01 落地后资损口即关死(402 生效 + 全量零回归),可独立交付;切片 02 把用户体验收口到 composite 同级并收官。前端中间态窗口(切片 01 合入后、02 合入前,零余额租户看到泛化 402 toast)见 §9,两切片 EP3 连续交付。

### 切片 01 — 后端统一钱包门:SSE 预检 402 + 共享 helper + 移除流内旧门 + 测试地基

**What it delivers**:无钱包/零余额/负余额/inactive 钱包的租户调 `/chat/stream` 在建立连接前收到 402(与 composite 同函数、同口径、同错误体);被拦请求不再创建会话、不落用户消息;有余额租户流式零变化;super_admin 照旧绕过;两路径口径一致性有常驻 CI 断言——资损口(无钱包免费流式)关死。

**Blocked by**: 无(frontier,可立即开工)

**文件清单**:`app/api/v1/chat.py` / `tests/conftest.py`(funded_wallet)/ `tests/test_billing.py`(矩阵 ①-⑧)/ `tests/test_chat.py`、`tests/test_multi_agent.py`、`tests/test_usage_tracking.py`、`tests/test_customer_conversation.py`(挂 funded_wallet,以红灯为准)

**验证命令**:`pytest tests/test_billing.py tests/test_composite_chat.py -q` + `./init.sh full`

**Acceptance criteria**:

- [ ] `chat.py` 新增 `_require_wallet_balance(db, user)` helper:super_admin 直返;延迟 import 惯例;`has_balance` 为假 → `HTTPException(402, detail="token 余额不足,请联系总部充值")`;无 try/except(查询异常 500,与 composite 对齐)
- [ ] SSE endpoint 在 `_load_agent` 之后、`create_or_get` 之前调用 helper
- [ ] `event_source` 内旧钱包检查整段移除(判断 + SSE error 帧 + fail-open except + 相关注释块);delta 帧的 json.dumps 序列化不受影响
- [ ] composite 现有内联「Wallet pre-check」替换为 helper 调用,行为零变化(既有 composite 402/bypass 测试全绿)
- [ ] `chat.py` 相关注释/docstring 口径同步(composite docstring「Stricter than /chat/stream's "no wallet = allow" degradation」段改写为统一口径表述)
- [ ] conftest 新增 opt-in `funded_wallet` fixture(余额给足);因改严而红的既有流式测试统一挂它修复,**不放宽任何既有断言**
- [ ] `tests/test_billing.py` SSE 门矩阵 ①-⑧ 全落地(无钱包 402 / 零余额 402 + 会话消息计数均 0 / 负余额 402 / inactive 402 / super_admin 无钱包放行 / 续问被 402 后 messages 不变 / 两路径 402 detail 逐字一致 / 有余额 happy path 零改动)
- [ ] `./init.sh full` 全量零回归(基线 1043 passed)

### 切片 02 — 前端 402 充值引导 + feature 收尾(末切片)

**What it delivers**:零余额/无钱包租户在 chat 页收到「余额不足」引导面板(后端 detail 文案 + 一键「前往充值」),体验对齐 composite 路径;重试与切换会话自动清除;其余错误与 401 行为不回归;feature 收官。

**Blocked by**: 切片 01

**文件清单**:`frontend/src/api/endpoints/search.ts`(错误类 + 402 分支)/ `frontend/src/pages/chat/index.tsx`(面板 + 双清除;可抽小组件)/ `frontend/src/pages/chat/__tests__/`(新测试)/ `frontend/src/api/endpoints/composite-chat.ts`(过时注释一行)/ 文档影响评估 + progress.md

**验证命令**:`cd frontend && npm run test && npm run build && npx oxlint` + `./init.sh full`(收尾全量)

**Acceptance criteria**:

- [ ] `search.ts`:`ChatInsufficientBalanceError` 错误类;`sendChatStream` 非 200 分支——401 特判不动,402 → 容错解析 body detail → 抛 `ChatInsufficientBalanceError`,其余维持泛化错误
- [ ] chat 页:`catch instanceof ChatInsufficientBalanceError` → balanceError state + 充值引导面板(Wallet icon + 标题「余额不足,无法发起对话」+ 后端 detail + 说明行 +「前往充值」→ /billing);其余错误维持 toast 现状;发起发送前与切换会话双清除
- [ ] vitest 至少两条:402 → `ChatInsufficientBalanceError`(detail 透传)+ 面板渲染(detail 文案与 CTA);401 既有行为不回归
- [ ] `composite-chat.ts` 头部过时注释修正(「strict, unlike /chat/stream's … SSE error frame」段)
- [ ] `cd frontend && npm run test && npm run build && npx oxlint` 全绿;`./init.sh full` 全绿
- [ ] 文档影响评估(4 行格式;预判仅代码注释级,无 项目指南 改动)
- [ ] feature 收尾仪式(three-tier §4 第 1-8 步):feature_list `in_progress → passing` + evidence + sync-active + progress.md + 依赖解锁扫描(billing-reconciliation-job 93 无硬依赖,为新 frontier:EP2 未做过,not_started + plan 指总纲,下一条走各自 EP2)+ 分支清理

## 7. 对抗式审查段(复杂任务:计费/支付敏感 → 已执行)

**触发条件**(prd-template §7「涉及安全敏感操作(token / 密钥 / 支付)」):本条直改钱包门的放行/拦截语义,资损相关。**方式**:单模型双轴(Standards + Spec)并行,2026-08-16 执行;产出 Standards 0🔴/3🟡/3🟢 + Spec 0🔴/4🟡/1🟢,全部回写 §0 变更摘要,v1 → v2。无 🔴 的原因:本条形态已在同文件被 composite 路径验证过(同款 HTTPException/同款 has_balance),且 v1 起草前已完成全部代码事实取证(两路径现状、前端消费链、CLI/E2E 零影响、测试爆炸半径),不存在 R1/R2 那类「库行为预判失真」风险面。

## 8. Out of Scope

- ❌ TurnAccountant 计费编排下沉(总纲 D5;第 10 次巡检架构候选 ②,独立立项时消化)
- ❌ 对账 job / charge 失败处理(下一条 billing-reconciliation-job R3b)
- ❌ 预检通过后流式中途余额被并发扣穿的二次拦截(D5 拍板移除双门;窗口语义与 composite 一致,兜底归 R3b 对账)
- ❌ 低额预警 / 自动充值 / 钱包计费语义与定价(本条只读余额门)
- ❌ composite 前端 402 UI(已存在,不动)
- ❌ CLI / E2E 改动(已论证零影响)
- ❌ 限流 / 权限 / 审计 / 配置守卫(R1/R4/R5 域)

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 存量无钱包租户(预计费时代/异常态)上线即被拦 | 中(预期内收紧) | D2 既定取舍(feature_list user_visible_behavior 已声明「系列内唯一收紧用户行为的点」);上线前 SQL 盘点无 live wallet 的租户交运营预甄别/充值;生产正常路径出生即建钱包,不触此态 |
| 第三方 API token 集成方调 /chat/stream 开始收 402 | 中(预期内收紧) | 402 语义标准、响应体带明确 detail;属本条止血目标本体,不是副作用 |
| 切片 01→02 合入窗口内,零余额租户前端看到泛化「对话失败: 402」toast | 低 | 两切片 EP3 连续交付,窗口短;文案含状态码可辨识,不算静默 |
| 既有流式测试挂 funded_wallet 有遗漏 → CI 红 | 低 | `./init.sh full` 硬门槛;修复策略已定(挂 fixture,不放宽断言) |
| 预检与流式扣费间的并发扣穿窗口(两并发对话各剩少量余额都放行) | 低 | 与 composite 现状同窗口语义;负余额后续请求照样被 has_balance 拦;少扣/扣穿兜底归 R3b 对账 |
| 前端面板实现体积失控(chat/index.tsx 已较大) | 低 | 可抽小组件(chat/ 目录有抽件先例);AC 只钉行为不钉形态 |

## 10. 验收标准(同步 feature_list.json verification)

1. **无钱包租户 /chat/stream 收 402(与 composite 口径一致)的回归测试**:切片 01 矩阵 ①-④(无钱包/零/负/inactive),SQLite 常驻 CI
2. **有余额租户流式路径零回归**:全套件 funded_wallet 挂接 + `./init.sh full`(基线 1043)零回归;E2E/CLI 零改动零影响(super_admin bypass:main-flow.spec.ts:15-17;ApiError 透 detail:cli/client.py:89-95)
3. **两路径 402 错误体格式一致性断言**:矩阵 ⑦,同 broke 租户两路径均 402 且 detail 逐字相等
4. (D4 追加)前端 402 充值引导面板对齐 composite 体验,重试/切换会话清除,401 不回归

## 11. 不越界声明

本次改动**只**涉及:`chat.py` 的钱包门逻辑统一(共享 helper + SSE 预检 402 + 移除流内旧门 + composite 改调 helper + 相关注释同步)、conftest 一个 opt-in fixture 与既有流式测试挂接、test_billing.py 的 SSE 门测试矩阵、前端 `sendChatStream` 402 分支与 chat 页充值引导面板及其测试、composite-chat.ts 一行注释修正。

**不**触碰:TurnAccountant 与计费编排 / charge·recharge·对账·低额预警逻辑 / `has_balance` 本体与 wallet 仓储 / 权限与限流 / CLI / E2E / 数据库 schema 与迁移链 / composite 前端既有 UI。
