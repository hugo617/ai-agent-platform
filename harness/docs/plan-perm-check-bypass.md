# 计划:permission check() bypass 判定链结构化

> **id**: perm-check-bypass
> **状态**: passing(EP2 完成:plan draft v2 对抗式审查 2🔴+5🟡+3🟢 回写,见 §0;EP3 切片 01 ✅ PR #162 + 切片 02 ✅ PR #163,feature 收尾 2026-08-14)
> **优先级**: 86(建议,登记 feature_list.json 时定)
> **创建日期**: 2026-08-14
> **最后修订**: 2026-08-14(v2:对抗式审查 2🔴+5🟡+3🟢 全部回写)
> **来源**: 第 10 次代码健康巡检候选 ①(Top/Strong,报告 `~/.cache/ai-agent-platform-architecture-reviews/2026-08-14.html`)
> **EP2 回环**: grill(2026-08-14,关键决策见 §4.5 D1-D7,提问未获回复按推荐项采纳)→ to-spec(本文)→ to-tickets(§6)

---

## 0. v1 → v2 变更摘要(对抗式审查回写)

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| §12 CONTEXT.md 术语与「累计 git diff 仅 2 文件」AC 自相矛盾(按字面实施必挂其一) | 🔴 | 验收改为**显式 3 文件白名单**(permission_service.py + test_permission_service.py + CONTEXT.md 术语条目);「调用点零改动」审计锚定为白名单外零改动 |
| §4.6 骨架 `CheckRule` 字段顺序非法 Python(无默认的 predicate 排在默认字段后,import 即 TypeError) | 🔴 | 骨架改为**全字段必填**(安全关键注册表,显式优于隐式),并写明 section 位置约束(必须在 `is_platform_writer`/`_is_group_admin_of` 之后,否则 import 期 NameError) |
| CheckContext 缺 `token_ctx` 字段,rule① 谓词隐式读 ContextVar,等价性靠「构造与求值间无 await」的偶然事实 | 🟡 | D3 修订:check() 入口一次性捕获 `current_token_ctx.get()` 装进 CheckContext;等价成结构性保证,rule① 可脱离 ContextVar 直测 |
| 不变式 4「obj 域互不重叠」守卫能力被高估(objs=None 的新全域豁免不会被捕获) | 🟡 | 措辞修订:**顺序/元数据快照是主守卫,互不重叠断言是补充性保守约束**(有意 friction,非安全必要条件) |
| 「87 调用点」硬数字与现状有漂移(实测 .check/.require 88 + require_permission 使用 99) | 🟡 | AC 措辞改为「全部调用点零改动,以累计 git diff 白名单为证」;数字仅作描述(沿用巡检报告口径)不作验收 |
| §5 缺「谓词异常传播语义不变」不变式(若实施时统一包 try/except 即行为变更) | 🟡 | 新增不变式 7:谓词不包 try/except,异常原样传播(尤其 ⑤ 的 GroupRepository 反查) |
| 判定语义行文「三态」与两态 verdict 枚举不一致,实施者会找不存在的 NEXT | 🟢 | D2 统一措辞:**两态 verdict(allow/deny)+ 不命中即继续链**;「三态」指表达的三种控制流走向 |
| needs_db 是声明式信任,非 needs_db 谓词误用 ctx.db 无机制拦截 | 🟢 | §4.6 CheckRule docstring 约定纪律 + 切片 01 谓词逐字搬运(谓词体里只有 ⑤ 用 db)兜底 |
| 切片 02 verdict 短路直测缺「DENY 规则不命中→继续链」反向用例 | 🟢 | 切片 02 AC 补该用例(restricted + scope 满足 → 继续链落后续 rule/casbin) |

---

## 1. Problem Statement

`PermissionService.check()` 是全平台 87 个 `require/check` 调用点的安全单点,其函数体内长着一条 **5 层顺序敏感的 bypass 判定链**:

| 序 | 层 | 语义 | 适用域 |
|---|---|---|---|
| ① | API token scope gate(restricted 模式) | **DENY**(不满足→拒绝) | 全部 obj/act |
| ② | super_admin | ALLOW | 全部 obj/act |
| ③ | hq_staff + read | ALLOW | 全部 obj 的 read |
| ④ | is_platform_writer + obj∈(devices,bookings) | ALLOW | 仅 devices/bookings |
| ⑤ | group_admin + obj=knowledge + 可选 db | ALLOW | 仅 knowledge |
| 终 | casbin enforce(threadpool) | 兜底授权 | 其余一切 |

问题在于这条链以「if 链 + 大段注释」的形态存在:

1. **顺序即安全,但顺序无守护**:①必须先于②(restricted token 即使 super_admin 签发也要被 scope 收敛)——这一条恰好有测试锁住;但②③④⑤之间的层间顺序契约**没有任何穷举测试**,顺序错换 = 静默权限漏洞。第 10 次巡检判定「安全单点,且在恶化」:knowledge-tiered 刚为 ⑤ 开了带可选 `db` 参数的口子(签名都为此改动),platform-cross-tenant-write 又加了 ④ —— 每次「X 角色对 Y 对象豁免」都往同一函数体塞分支。
2. **边界契约在注释里不在代码里**:§4.8「四 bypass 边界表」(plan-knowledge-tiered-foundation,各 bypass 的 obj 域互不重叠)是 plan 文档里的 Markdown 表格,实现处只靠注释提醒,注释与实现可能漂移。
3. **判定不可穷举直测**:现有测试是行为级的(构造角色×对象×动作组合跑 check()),无法回答「链上一共有几条规则、各自声明了什么适用域、obj 域是否仍然互不重叠」这类结构问题。

## 2. Solution

把 check() 内的 if 链重构为**显式注册的有序判定链(谓词表)**:模块级 `CHECK_RULES` 有序元组,每条 rule 是一个不可变 dataclass,声明式携带 `name / objs / acts / needs_db / decision(ALLOW|DENY)` 元数据 + 一个独立 async 谓词函数;check() 变成「构造上下文 → 依序遍历 → 命中即按 verdict 短路 → 全部不适用落 casbin」的循环。casbin 是授权引擎本体,留在循环外作为显式终点,不进注册表。

**interface 不变**:`check()` / `require()` 签名零改动,87 个调用点零改动,运行时行为逐字节等价(零行为变更)。新 bypass = 在注册表加一条 rule(声明适用域),不再改 check() 函数体;判定表可被测试穷举断言(顺序快照、obj 域互不重叠、needs_db 一致性)。

## 3. User Stories

1. 作为**后端开发者**,我想新增一条 bypass 时只需在 `CHECK_RULES` 加一条 rule(声明适用域 + 谓词 + verdict),以便不改 check() 函数体、不必靠读注释判断该插在第几层。
2. 作为**平台安全运维**,我想要判定表可穷举直测(顺序快照 + obj 域互不重叠断言),以便任何层序错换或越界扩域的改动一进 CI 就测试红。
3. 作为**平台安全运维**,我想让 §4.8「四 bypass 边界表」从 plan 注释变成代码里的声明式元数据,以便边界与实现永不漂移。
4. 作为**super_admin / hq_staff / group_admin / owner / member 用户**,我的权限判定结果与重构前完全一致,以便升级无感知(零行为变更)。
5. 作为**API Token 使用者**,restricted token 的 scope 闸门仍然是链上第 0 条规则(先于一切 ALLOW 豁免),以便 super_admin 签发的受限 token 依然被 scope 收敛。
6. 作为**调用方开发者**(87 个 require/check 调用点的维护者),check()/require() 签名不变,以便零改动、零回归风险。
7. 作为**未来维护者**,我想从 `CHECK_RULES` 一眼读出全部闸门/豁免规则及其优先级与适用域,以便不再通读 100 行 if 链 + 大段注释才能理解判定顺序。

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 1 | `app/services/permission_service.py`(判定链 section + check() 改循环;~949 → ~1030 行,+9%,仍在巡检容忍带内) |
| 数据库迁移 | 0 | 无 |
| 前端文件改动 | 0 | 无 |
| 测试文件 | 1 | `tests/test_permission_service.py` 扩展(既有 seam,不新开测试文件) |
| 文档 | 1 | `CONTEXT.md` 新增术语「判定链(Decision Chain)」(glossary 级,切片 02) |
| Skill / Hook / 配置 | 0 | 无 |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**
- 是否修改现有租户隔离逻辑? **NO**(check() 判定路径逐字节等价,租户过滤仍在 Repository 层不动)
- 是否引入跨租户访问点? **NO**(④⑤ 的跨租户语义原样保留:platform writer 仍限于 devices/bookings、group_admin 仍限于 knowledge + db 反查)
- 验证:既有全量测试(1004 passed 基线)零回归 = 多租户行为不变的证据;不新增租户隔离用例(行为没变)。

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS / 种子数据 / backfill? **NO**(只动 check() 判定形态)
- 是否影响 87 处 `require/check` caller(巡检报告口径,描述性数字)? **NO —— 全部调用点零改动是本 feature 的硬验收项**(git diff 白名单外零改动,见 §10)
- 是否影响 graph.py 工具内 check(Agent 工具二次校验)? 走同一 check() 入口,零行为变更 → 零影响
- scope 闸门(API Token):① 从「循环前置 if」变为「注册表第 0 条 DENY 型 rule」,**语义逐字等价**(restricted + scope 不满足 → False;restricted + 满足 → 继续链;非 restricted → 继续链);「闸门必须最先」从注释契约变成「注册表下标 0」这一可断言事实。

### 4.4 数据库表设计 checklist

不适用(零 schema 变化)。

### 4.5 关键决策(grill 产出;提问未获回复,按推荐项采纳,可在 plan 评审时否决)

- **D1 判定链形态 = 轻量有序注册表**:`CHECK_RULES: tuple[CheckRule, ...]` 模块级有序元组;每条 rule = frozen dataclass(声明式元数据)+ 独立 async 谓词函数。顺序即元组下标。**不采用**类层级 Strategy(5 条规则上个类层级偏重)也**不采用**「if 链抽具名函数」的最小改名(顺序契约仍是注释,判定表不可穷举直测,报告核心 win 落空)。
- **D2 判定语义 = 两态 verdict + 不命中继续链**(表达三态控制流:ALLOW 短路 / DENY 短路 / 继续链):`RuleDecision = Literal["allow", "deny"]`,rule 命中时按声明的 verdict 短路终止,不适用(applies 不过)或谓词不命中则继续下一条;全链不命中 → casbin。**没有 NEXT 枚举值**——「继续」是不命中的缺省走向。scope gate 声明为 **DENY 型 rule 进链**(链才完整,「gate 最先」成为链内可断言事实),4 条 bypass 是 ALLOW 型。
- **D3 rule 输入 = 打包上下文(含 token_ctx)**:`CheckContext` frozen dataclass 一次性携带 user_id / tenant_id / obj / act / platform_role / db / **token_ctx**(check() 入口一次性捕获 `current_token_ctx.get()`,rule① 谓词读 ctx 字段而非再触 ContextVar)。等价性从「构造与求值之间无 await」的偶然事实升级为结构性保证;rule① 可脱离 ContextVar 直测。加第 6 条 rule 不改任何谓词签名(避免参数签名传染)。
- **D4 casbin 不进注册表**:casbin enforce 是授权引擎本体(默认判定)不是豁免规则,留在 check() 内作为「全链不命中后的显式终点」。注册表 = 闸门/豁免链,casbin = 兜底授权,概念不混。
- **D5 适用域 = 声明式元数据**:每条 rule 携带 `objs: frozenset[str] | None`(None=全部)、`acts: frozenset[str] | None`(None=全部)、`needs_db: bool`、`decision: ALLOW|DENY`、`name: str`;`applies(ctx)` 由 dataclass 方法统一按元数据计算,objs/acts/needs_db 都过→ 谓词才被调用。谓词只写不可静态声明的身份逻辑(super_admin 判等、is_group_admin 反查、scope 集合运算)。**§4.8 边界表因此变成数据**:测试可遍历 CHECK_RULES 做顺序/元数据快照(主守卫)与 obj 域互不重叠断言(补充性保守约束,见不变式 4)。
- **D6 rule 定义位置 = 同文件单 section,置于模块底部 helper 之后**:用户红线「不要重新拆模块」;谓词依赖同模块符号(`is_platform_writer` / `GroupRepository` / `_is_group_admin_of`),**section 必须放在这些 helper 定义之后**(CHECK_RULES 是 import 期求值的模块级元组,前向引用会 NameError),即靠近 `_is_group_admin_of`(~L793)之后的文件底部;check() 在运行时引用全局 CHECK_RULES,不受定义顺序影响。零新文件、零 import 变化,+~80 行在巡检容忍带内。若未来出现第 6 条 bypass 再评估外移。
- **D7 测试策略 = 既有 seam 扩展 + 注册表级穷举断言**:唯一测试 seam = `tests/test_permission_service.py`(service 层直测,真 casbin enforcer fixture,对齐既有范式)。切片 02 新增「判定表穷举测试」:顺序快照(name 序列逐一断言)+ ALLOW 型 rule 的 objs 域两两互不重叠 + needs_db rule 在 db=None 时 applies=False + verdict 短路语义。**不新开测试文件、不加 API 层测试**(interface 没变,最高可用 seam 就是 service 直测)。

### 4.6 结构骨架(决策的精确形态,实施时允许微调命名)

```python
RuleDecision = Literal["allow", "deny"]          # rule 命中时的短路判定(无 NEXT:不命中即继续链)
@dataclass(frozen=True)
class CheckContext:                              # D3:rule 的统一输入(token_ctx 入口一次性捕获)
    user_id: str; tenant_id: str; obj: str; act: str
    platform_role: str | None; db: AsyncSession | None
    token_ctx: "TokenCtx | None"                 # check() 入口 current_token_ctx.get() 的结果

@dataclass(frozen=True)
class CheckRule:                                 # D1/D2/D5:全字段必填(安全关键注册表,显式优于隐式)
    name: str
    objs: frozenset[str] | None                  # None = 全部 obj
    acts: frozenset[str] | None                  # None = 全部 act
    needs_db: bool
    decision: RuleDecision
    predicate: Callable[[CheckContext], Awaitable[bool]]  # 命中判定(True=命中→按 decision 短路)
    def applies(self, ctx) -> bool: ...          # 元数据统一计算;全过才调 predicate
    # docstring 纪律:needs_db=False 的 rule 谓词不得读 ctx.db(声明式信任,无机制拦截)

# —— 判定链 section 置于模块底部(is_platform_writer/_is_group_admin_of 之后),
#    CHECK_RULES 是 import 期求值的模块级元组,前向引用会 NameError(D6)——
CHECK_RULES: tuple[CheckRule, ...] = (           # 顺序即数组下标 = 判定链唯一真相源
    CheckRule(name="api_token_scope_gate", objs=None, acts=None, needs_db=False, decision="deny",  predicate=...),
    CheckRule(name="super_admin",           objs=None, acts=None, needs_db=False, decision="allow", predicate=...),
    CheckRule(name="hq_staff_read",         objs=None, acts=frozenset({"read"}), needs_db=False, decision="allow", predicate=...),
    CheckRule(name="platform_writer",       objs=frozenset({"devices","bookings"}), acts=None, needs_db=False, decision="allow", predicate=...),
    CheckRule(name="group_admin_knowledge", objs=frozenset({"knowledge"}), acts=None, needs_db=True, decision="allow", predicate=...),
)

async def check(self, user_id, tenant_id, obj, act, platform_role=None, *, db=None) -> bool:
    # 签名与 docstring 契约不变(内层实现细节注释随规则迁走)
    ctx = CheckContext(..., token_ctx=current_token_ctx.get())
    for rule in CHECK_RULES:
        if rule.applies(ctx) and await rule.predicate(ctx):
            return rule.decision == "allow"
    return await run_in_threadpool(_casbin_enforce, ...)   # D4:显式终点
```

5 条谓词逐字搬运现有 5 个 if 分支的判定逻辑(含 ① 的 required 集合构造与 act=="read" 扩集、④ 的 `is_platform_writer(platform_role)`、⑤ 的 group 反查 + `_is_group_admin_of`),**只搬运不改写**。

## 5. 不变式契约(实施必须守住)

1. **零行为变更**:对任意 (user_id, tenant_id, obj, act, platform_role, db, token_ctx) 输入组合,新旧 check() 返回值逐一相同。既有 1004 条后端测试零回归是最强证据。
2. **签名冻结**:`check()` / `require()` / `require_permission()` 及所有导出符号签名零改动;全部调用点零改动(git diff 白名单验证,见 §10)。
3. **闸门在链首**:`CHECK_RULES[0].name == "api_token_scope_gate"` 且 decision == "deny"(测试快照锁死)。
4. **obj 域互不重叠(补充性保守约束)**:ALLOW 型 rule 中声明 objs 的(platform_writer、group_admin_knowledge)两两交集为 ∅。**主守卫是切片 01 的顺序/元数据快照**(加规则或扩域必改快照→CI 红);本断言捕获「两条声明 objs 的 ALLOW 规则意外重叠」这类保守 friction,不是安全必要条件(objs=None 的角色型全域豁免依 §4.8 表不属于 obj 域划分对象,由快照守卫)。
5. **db=None 安全降级**:needs_db=True 的 rule 在 db=None 时不适用(继续链)→ 落 casbin,与现状「不传 db 不触发 group_admin bypass」逐字等价。
6. **casbin 终点不动**:`_do()`/`run_in_threadpool` 的 enforce 路径原样保留(锁语义不变)。
7. **谓词异常传播语义不变**:谓词不包 try/except、「安全降级」等兜底(尤其 ⑤ 的 `GroupRepository` 反查)——现状异常原样传播给调用者,重构后必须一致。

## 6. 切片(to-tickets 产出,EP2 单回环)

### 切片依赖图

```
01 结构迁移(全 5 条 rule + check() 改循环)──→ 02 判定表穷举直测 + 收尾(末切片)
```

### 切片 01 — 判定链结构迁移:CheckRule + CHECK_RULES 全 5 条 + check() 改遍历循环 ✅(2026-08-14 Session 206,commit db06891,PR #162)

**What it delivers**:check() 的 5 层 if 链全部迁移为 `CHECK_RULES` 有序注册表(含 DENY 型 scope gate),check() 变成遍历循环 + casbin 终点;行为逐字节等价,既有测试全绿。附带最小注册表存在性测试(顺序 + name 快照),让结构迁移本身有直测锚点。

**Blocked by**: 无(frontier,可立即开工)

**文件清单**:`app/services/permission_service.py`(改)+ `tests/test_permission_service.py`(扩展)

**验证命令**:`pytest tests/test_permission_service.py tests/test_knowledge_foundation.py tests/test_hq_platform_role.py -q` + `./init.sh`(冒烟)

**Acceptance criteria**:

- [x] `app/services/permission_service.py` 新增判定链 section:`RuleDecision` 字面量 + `CheckContext` frozen dataclass + `CheckRule` frozen dataclass(name/objs/acts/needs_db/decision/predicate + `applies()` 元数据统一计算)—— D1/D2/D3/D5
- [x] `CHECK_RULES` 有序元组恰好 5 条,顺序与名称:api_token_scope_gate(deny)→ super_admin → hq_staff_read(acts={"read"})→ platform_writer(objs={"devices","bookings"})→ group_admin_knowledge(objs={"knowledge"}, needs_db=True)—— §4.5 D1/D2
- [x] 5 条谓词逐字搬运原 if 分支逻辑(① 的 required 集合 + read 扩集 / ②③ 角色判等 / ④ is_platform_writer / ⑤ GroupRepository 反查 + `_is_group_admin_of`),只搬运不改写
- [x] `check()` 改为「构造 CheckContext → 遍历 CHECK_RULES(applies→predicate→按 decision 短路)→ 全不适用落 casbin(threadpool 路径原样)」;签名与 docstring 的对外契约不变
- [x] `require()` 及其余全部方法零改动;文件内其余 section(种子数据/标签表/backfill/SCD2/helper)零改动
- [x] `tests/test_permission_service.py` 新增注册表存在性测试:顺序快照(`[r.name for r in CHECK_RULES]` 断言)+ 每条 rule 的 objs/acts/needs_db/decision 元数据快照
- [x] `pytest tests/test_permission_service.py` 既有测试 + 新增全绿;`./init.sh` 冒烟绿
- [x] git diff 只含 `app/services/permission_service.py` + `tests/test_permission_service.py` 两个文件(本切片零文档改动)

**完成证据(2026-08-14 Session 206)**:commit `db06891`(分支 refactor/perm-check-bypass-slice-01,**PR #162**)。验证:`pytest tests/test_permission_service.py` 20 passed(18 既有 + 2 新增注册表快照)+ `tests/test_knowledge_foundation.py` + `tests/test_hq_platform_role.py` 53 passed;`./init.sh` 冒烟 201 passed(ruff + smoke);commit 前全量 pytest **1006 passed**(1004 基线零回归 + 新增 2);`git diff --stat` 仅两代码文件(全部 require/check 调用点零改动)。/code-review 双轴 0 硬违规:Standards 三点特别核查全过(谓词逐字忠实搬运 / require() byte-identical / section 位于 is_platform_writer 与 _is_group_admin_of 之后);Spec 8 AC 全绿,等价性逐层推演无分叉点。2 留痕:① check() docstring 与 CHECK_RULES 注释双述判定顺序 → 切片 02 AC(docstring 瘦身指向 CHECK_RULES)本就是处理点,本切片 AC 要求 docstring 契约不变;② ⑤ 谓词新增 `assert ctx.db is not None` 类型收窄(applies()[needs_db=True] 保证恒真,`-O` 下剥离,非语义偏移,已注释)。非末切片:feature_list.json status/evidence 未动(切片 02 收尾)。

### 切片 02 — 判定表穷举直测 + 不变式契约锁定 + feature 收尾(末切片)✅(2026-08-14 Session 207,commit fc46275,PR #163)

**What it delivers**:把 §5 的 7 条不变式契约全部变成常驻测试(顺序快照已在 01,补 obj 域互不重叠、needs_db 降级、verdict 短路含 DENY 不命中反向、casbin 终点);check() docstring 瘦身核对(注释随规则归位);CONTEXT.md 术语条目;全量验证 + 调用点零改动审计 + feature 收尾仪式。

**Blocked by**: 切片 01

**文件清单**:`tests/test_permission_service.py`(扩展)+ `app/services/permission_service.py`(至多 docstring/注释归位)+ `CONTEXT.md`(术语条目)

**验证命令**:`./init.sh full` + `git diff main --stat`(全 feature 累计仅白名单 3 文件)

**Acceptance criteria**:

- [x] 新增穷举断言:遍历 `CHECK_RULES`,ALLOW 型 rule 中声明 objs 的两两交集为 ∅(§4.8 边界表代码化;主守卫是 01 的快照,本断言是保守补充)
- [x] 新增 `applies()` 直测:needs_db rule 在 db=None → False;objs/acts 不匹配 → False;全匹配 → True(不触谓词)
- [x] 新增 verdict 短路直测:命中 DENY 型 rule → check 返回 False 且不触 casbin;命中 ALLOW 型 → True 且不触 casbin(mock/monkeypatch enforcer 验证未触);**DENY 型不命中(restricted + scope 满足)→ 继续链落后续 rule/casbin** 的反向用例
- [x] check() docstring 更新:指向 CHECK_RULES 作为判定顺序唯一真相源,层间长注释迁移到各 rule 定义处
- [x] `CONTEXT.md` 新增「判定链(Decision Chain)」术语条目(glossary 级,不含实现细节)
- [x] `./init.sh full` 全量绿(1004+ 基线零回归 + 新增测试)
- [x] 全 feature 累计 `git diff --stat` 仅白名单 3 文件:`app/services/permission_service.py` + `tests/test_permission_service.py` + `CONTEXT.md` —— 全部 require/check 调用点零改动的审计证据(白名单外零改动)
- [x] feature 收尾仪式(three-tier §4 第 1-8 步):feature_list.json status→passing + evidence + sync-active + progress.md + 文档影响评估 + 依赖解锁扫描 + 分支清理

**完成证据(2026-08-14 Session 207)**:commit `fc46275`(分支 refactor/perm-check-bypass-slice-02,**PR #163**,merge commit a537f36)。验证:`pytest tests/test_permission_service.py` 26 passed(20 既有 + 6 新增:objs 域两两互不重叠穷举断言 / applies() 边界哨兵谓词直测 / ⑤ needs_db 无 db 安全降级 / DENY 命中短路不触 casbin / ALLOW 命中短路不触 casbin / DENY 不命中反向三段证据[落 ② ALLOW → 落 casbin False → 落 casbin True])+ 联动 `test_knowledge_foundation.py` + `test_hq_platform_role.py` 79 passed;`./init.sh full` 本地全量绿(exit 0)+ CI Backend 同码 **1012 passed**(1006 基线零回归 + 新增 6)、Migrations/Frontend/E2E 4/4 绿;`git diff origin/main --stat` 仅白名单 3 文件(permission_service.py + test_permission_service.py + CONTEXT.md)。/code-review 双轴:Spec 轴 7 条代码 AC 全绿无越界;Standards 轴 0 硬违规,1 条采纳(docstring/内联注释双述 → 内联注释瘦身),4 条 judgement call 按 plan 明文保留。feature 收尾:feature_list.json status→passing + evidence 登记 + sync-active + progress.md Session 207 + 依赖解锁扫描(depends_on 空、无人依赖本 feature)+ 分支清理(slice-01/slice-02 已合并即删)。

## 7. 测试策略

- **测试 seam**:单一 = `tests/test_permission_service.py`(service 层直测,真 casbin enforcer fixture `enforcer`,对齐既有 `test_super_admin_short_circuits_before_casbin` 范式)。**不新开测试文件**。
- **测试金字塔**:unit/集成混合(SQLite 内存 + 真 casbin),无 E2E、无 API 层测试(interface 未变)。
- **既有行为测试是零行为变更的主证据**:`test_permission_service.py`(super_admin 短路 / require bypass / restricted gate 先于 super_admin / full mode 放行)+ `test_knowledge_foundation.py`(group_admin bypass + D9 devices 不放行)+ `test_hq_platform_role.py` + token scope 相关测试,全部必须原样绿。
- **新增两类**:①注册表存在性/顺序快照(切片 01);②判定表穷举断言 + applies()/verdict 直测(切片 02)。
- **覆盖率**:不低于项目基线 93%;新增代码(CheckRule/CheckContext/谓词)全覆盖。

## 8. Out of Scope

- ❌ **拆 permission_service 模块**(第 7/8 次巡检已判 deep 关闭:SCD2↔casbin 宪法是 depth;本 feature 只重构 check() 单函数内的判定形态)
- ❌ 改 `check()` / `require()` / `require_permission()` 签名或任何调用点
- ❌ 改 `is_platform_writer` / `is_cross_tenant_viewer` / `GROUP_ADMIN_HQ_ROLES` / `PLATFORM_WRITER_ROLES` 等既有 helper 的语义或位置
- ❌ 新增/扩展任何 bypass 的适用域(不给人新豁免)
- ❌ Principal / ADR-0001 边界、ADR-0002
- ❌ 第 10 次巡检业务功能风险 Top5(super_admin 跨租户写零审计、dev 后门等)—— 另立项
- ❌ 前端、schema、迁移、种子数据

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 迁移中顺序错换 → 静默权限漏洞 | 高 | 既有行为测试(1004 基线)+ 切片 01 顺序快照 + 切片 02 obj 域互不重叠断言;谓词逐字搬运不改写 |
| 谓词 async 语义错(漏 await / 误同步调用) | 中 | 谓词签名统一 `Callable[[CheckContext], Awaitable[bool]]`,ruff + 类型检查;短路直测覆盖每条 rule |
| group_admin 的 db=None 语义漂移(如误判为 deny) | 中 | 不变式 5:applies() 直测锁死 db=None → 继续链 → casbin |
| scope gate 语义漂移(required 集合构造错) | 中 | 谓词逐字搬运;既有 restricted gate 测试原样必须绿 |
| 「同文件膨胀」恶化 god file 趋势 | 低 | +~80 行(+9%)在巡检容忍带内;D6 已评估,第 6 条 bypass 出现时再议外移 |

## 10. 验收标准(同步 feature_list.json verification)

1. `CHECK_RULES` 注册表就位:5 条 rule、顺序快照测试锁死、DENY gate 在下标 0(切片 01/02 测试)
2. 全量 `./init.sh full` 绿(基线 1004 passed 零回归 + 新增测试)
3. 全 feature 累计 `git diff --stat` 仅白名单 3 文件:`app/services/permission_service.py` + `tests/test_permission_service.py` + `CONTEXT.md`(术语条目)—— 全部 require/check 调用点零改动 = 白名单外零改动(审计锚)
4. 判定表穷举断言常驻 CI:顺序快照 + obj 域互不重叠 + applies() 边界 + verdict 短路
5. §4.8 四 bypass 边界表以代码元数据 + 穷举断言双形态存在(注释契约→代码契约)

## 11. 不越界声明

本次改动**只**涉及 `app/services/permission_service.py` 内 check() 函数的判定形态(if 链 → 有序注册表)及其测试;**不**触碰:模块内其他 section(种子/标签/backfill/SCD2)、任何调用方文件、check/require 签名、casbin 模型与策略、前端、数据库 schema。

## 12. Further Notes

- **与第 7/8 次巡检关闭判决的关系**:已关闭的是「拆 permission_service 为 5 cluster」(wide split);本 feature 是 check() 单函数内的判定形态重构(deepen),二者不冲突——报告原文「本候选不拆模块,只重构 check() 单函数内的 bypass 判定形态,是新切口」。
- **CONTEXT.md**:新增术语「判定链(Decision Chain)」——check() 内有序规则表,每条 rule 声明适用域与 verdict(ALLOW/DENY),命中短路,全部不适用落 casbin 兜底。glossary 级描述,不含实现细节。
- **不提 ADR**:三条件不满足「难逆转」(interface 冻结,内部形态可再改);决策记录在本 plan §4.5 即可。
