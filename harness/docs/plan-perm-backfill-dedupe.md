# 计划:permission backfill 参数化去重(消解逐字节镜像函数)— 切片 1 ✅ PR #151

> **id**: `perm-backfill-dedupe`
> **状态**: not_started v2(经 opus 对抗式审查修订,规划就绪待实施)
> **优先级**: 77(当前最高 passing = union-cast-split 75,本任务与 chat-page-split 76 / devices-page-split 78 同批;第 7 次巡检候选 ③)
> **创建日期**: 2026-07-30
> **最后修订**: 2026-07-30(v2)
> **来源**: 第 7 次代码健康度巡检候选 ③(Strong + WORSENED)+ grill 4 决策共识

---

## 0. v1 → v2 变更摘要(对抗式审查修订)

opus 双轴审查(真相核查 + 设计质量)发现 v1 多处事实错误与安全测试空窗,本轮修订:

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| **caller 计数「14 处(测试 10 + scripts 2 + import 2)」虚假精度** —— 真实 grep 是 18 处代码引用(含 import)/ 10 处纯调用 | 🔴 RED | §4.1 改为真实口径「4 文件 18 处引用」,删除虚假精度 |
| **新建 `scripts/backfill_perms.py` 与已有 `scripts/backfill_permissions.py`(不同逻辑)命名碰撞** —— 一字之差极易误执行 | 🔴 RED | 改名为 `scripts/backfill_obj_perms.py`;§9 列入风险 |
| **Ticket 1 删 K chapter 留安全代码测试空窗** —— backfill 是权限敏感代码,T1 完成到 T2 完成间零测试保护 | 🔴 RED | Ticket 1 改为「临时改调新函数」保留 6 测试绿;删 K chapter 移到 Ticket 2 |
| body 差异计数「4 处」不精确(实际 6 处:2 功能 guard + 4 注释) | 🟡 YELLOW | §1 修正为 6 处 |
| **循环变量 `obj` 会 shadowing 函数参数 `obj`**(L781 `for obj, act in perms`) | 🟡 YELLOW | §4.5 显式标注:循环变量重命名为 `perm_obj` |
| **测试 helper `_seed_backfill_target_tenant` 需参数化**(seed 哪个「其他 perm」取决于 obj) | 🟡 YELLOW | §5 补 helper 参数化说明 |
| 断言 `5+4+2` 硬编码,未来 obj perm 数不同会坏 | 🟡 YELLOW | §5 改为从 DEFAULT_*_PERMS 动态算期望值 |
| AC「grep 旧函数名归 0」在 Ticket 1 不成立(scripts 临时调用) | 🟡 YELLOW | AC 区分「定义归 0」(T1)vs「引用归 0」(T2) |
| 白名单保护对象未说明(argparse choices 已限制,白名单保护非 script 调用) | 🟡 YELLOW | §4.5 补:白名单主要保护测试/其他 service 直接 import 调用 |

---

## 1. Problem Statement(对齐 to-spec)

**问题**:`app/services/permission_service.py` 有两个 backfill 函数,**逐字节相同**,唯一差异是字面量字符串 `"devices"` → `"bookings"`:

- `backfill_devices_perms_for_existing_tenants`(`backfill_devices_perms_for_existing_tenants` 函数,~90 行)
- `backfill_bookings_perms_for_existing_tenants`(`backfill_bookings_perms_for_existing_tenants` 函数,~90 行)

模块自己在第二个函数前的注释标注了:`# Structural mirror of backfill_devices_perms_for_existing_tenants`。

**镜像扩散到三层**(不只是 service):
1. **service 层**:2 个函数 body 逐行对应。obj 字面量在 body 出现 **6 处**(v2 修正:v1 说「4 处」不精确):**2 个功能 scope guardrail**(`if obj != "X"` api 区 + `if code != "X"` menu 区)+ **4 个注释**(api 区 header 注释 + api 区 guardrail 注释 + menu 区 header 注释 + menu 区 guardrail 注释)。归一化替换 obj 名即可消除。
2. **scripts 层**:`scripts/backfill_devices_perms.py` + `scripts/backfill_bookings_perms.py` 也几乎相同(thin async main + argparse + dry-run)
3. **测试层**:`test_devices_api.py` 的 K chapter(3 test)+ `test_bookings_api.py` 的 K chapter(3 test)结构镜像,只是 obj 名不同

**恶化点**:第 5/6 次巡检时只有 1 个 backfill 函数(待迁移),现在**多了第二个近乎复制品**。如果不处理,下次再加 tenant-scoped 业务记录(如第 3 个 obj)会复制第三份 service + 第三份 script + 第三份测试 —— 镜像扩散。

**friction**(对照 `/codebase-design` 词汇):
- **无 leverage**:两个函数唯一变化的是 obj 名字符串,其余 ~85 行 body 完全相同。snapshot existing grants / per-tenant loop / scope-guardrail `continue` / casbin resync / `db.flush()` 这些步骤必须逐字保持同步。
- **不变式散落**:scope guardrail(只触碰一个 obj 的 perms)是 load-bearing 安全契约(K6:不误改 customers:read 等),但它靠两个函数各自内联的 `if obj != "devices"` 表达 —— 改一处忘了改另一处就会破坏不变式。

**deletion test**:**浓缩**。参数化合并为 `backfill_perm_set_for_existing_tenants(db, obj)` 后,body 只此一份,snapshot/resync/flush 顺序不变式表达一次。下次加 obj 只需在白名单加一项 + DEFAULT_*_PERMS 加条目,不再 copy-paste。删除这个合并会让不变式重新散落到 N 份副本。

**为什么现在做**:第 7 次巡检(2026-07-30)候选 ③,**Strong + WORSENED**(从单函数恶化成镜像函数对)。是本轮唯一「恶化」的候选,且修复机械、风险有界(diff 确认仅字面量差异,合并后行为等价)。

---

## 2. Solution(对齐 to-spec)

把三层的镜像统一参数化:

1. **service**:2 个函数 → 1 个 `backfill_perm_set_for_existing_tenants(db, obj: str)`,obj 用白名单 `BACKFILLABLE_OBJS` frozenset 约束(防误用)。
2. **scripts**:2 个 script → 1 个 `scripts/backfill_perms.py`,接 `--obj devices|bookings` 参数。
3. **测试**:2 个 K chapter → 1 个 `tests/test_permission_backfill.py`,用 `@pytest.mark.parametrize("obj", ["devices", "bookings"])` 覆盖 3 场景 × 2 obj。

**核心洞察**:backfill 的 body 是「给一个 obj 的 perm 集做幂等补齐」的通用算法,obj 只是参数。把它显式参数化 + 白名单约束,既消解镜像又把 scope guardrail 不变量从「散落在 N 个函数体内联」提升到「类型/校验层单一推理点」。

---

## 3. User Stories(对齐 to-spec)

- 作为 **平台运维**,我跑 `python scripts/backfill_perms.py --obj devices` 给老租户补 devices 权限,行为与之前完全一致(零运行时变化)
- 作为 **平台运维**,我跑 `--obj bookings` 补 bookings 权限,同样幂等、安全(scope guardrail 保留)
- 作为 **开发者**,我加第 3 个 tenant-scoped 业务记录的权限 backfill 时,只需在 `BACKFILLABLE_OBJS` 加一项 + DEFAULT_*_PERMS 加条目,不再 copy-paste 90 行 body + 一个 script + 3 个测试
- 作为 **开发者**,我改 backfill 算法(如调整 snapshot 策略)只改一处,不必同步改两份镜像
- 作为 **安全审查者**,scope guardrail 不变量现在由白名单 + ValueError 兜底,传非法 obj(如 `obj="users"`)会显式报错而非静默 no-op
- 作为 **未来巡检 agent**,我看到的是「已参数化的通用 backfill」而非「散落的镜像函数对」,不再标为候选

---

## 4. Implementation Decisions(对齐 to-spec + 项目特化)

### 4.0 grill 4 决策汇总(一次一问共识)

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| **D1** | 参数化策略 | **合并 + 改所有 caller**(删旧两函数名) | 最干净;14 处 caller(测试 10 + scripts 2 + import 2)同步改,一次性彻底消除镜像 |
| **D2** | scripts 去留 | **合并 scripts**(`backfill_perms.py --obj`) | 对称 D1;两个 script 也是镜像(thin wrapper),合并后防第三份 script |
| **D3** | 测试 K chapter | **parametrize 抽到独立文件**(`tests/test_permission_backfill.py`) | 两个 K chapter 各 3 test 镜像,合并成 parametrize 覆盖 3 场景 × 2 obj;逻辑唯一一份 |
| **D4** | obj 参数约束 | **Literal/白名单约束**(`BACKFILLABLE_OBJS` frozenset + ValueError) | scope guardrail 不变量进约束层;防误用(obj="users" 静默 no-op → 显式报错) |

### 4.1 影响面清单(项目特化,v2 修正 caller 口径)

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | **1 改** | `app/services/permission_service.py`(2 函数合并为 1 + BACKFILLABLE_OBJS 常量 + 删旧两函数) |
| 数据库迁移 | **0** | 无(纯代码重构,数据行为零变化) |
| scripts 改动 | **2 删 + 1 新** | 删 `scripts/backfill_devices_perms.py` + `scripts/backfill_bookings_perms.py`;新建 `scripts/backfill_obj_perms.py`(**v2 改名**:原拟 `backfill_perms.py` 与已有 `scripts/backfill_permissions.py` 命名碰撞) |
| 测试文件改动 | **2 改 + 1 新** | 改 `tests/test_devices_api.py`(删 K chapter)+ `tests/test_bookings_api.py`(删 K chapter);新建 `tests/test_permission_backfill.py` |
| 前端文件改动 | **0** | 无 |
| Skill / Hook / 配置 | **0** | 无 |

> **caller 真实口径**(v2 修正):v1 说「14 处(测试 10 + scripts 2 + import 2)」是虚假精度。真实 grep(排除 plan 文档与 feature_list):**4 个文件,18 处代码引用**(含 import),其中 **10 处纯调用**(devices 4 + bookings 4 + 2 script)。
> - `tests/test_devices_api.py`:9 处引用(3 import + 4 call + 2 注释)
> - `tests/test_bookings_api.py`:9 处引用(3 import + 4 call + 2 注释)
> - `scripts/backfill_devices_perms.py` + `scripts/backfill_bookings_perms.py`:各 2 处(1 import + 1 call)

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**
- 是否修改现有租户隔离逻辑? **NO**(backfill 只补权限,不改隔离;权限补齐仍按 tenant_id 遍历)
- 是否引入跨租户访问点? **NO**
- 验证:parametrize 测试覆盖 devices + bookings 两个 obj,每个 obj 的 backfill 在多租户 fixture(test_env)下验证 per-tenant 幂等 + scope 隔离(不误改其他 obj perms)

### 4.3 权限影响评估

- 是否新增 permission code? **NO**(只是 backfill 现有 devices/bookings perms 的代码重构)
- 是否修改 DEFAULT_*_PERMS? **NO**(表内容不变,只是 backfill 函数读它的方式参数化)
- 是否影响 60+ 处 require_permission caller? **NO**(backfill 是离线运维路径,不影响运行时鉴权)
- 是否影响 graph.py 工具内 check? **NO**
- **scope guardrail 保留**:参数化后,白名单 `BACKFILLABLE_OBJS = frozenset({"devices", "bookings"})` + body 内 `if obj_pair != obj: continue` 仍只处理指定 obj 的 perms,不误碰其他 obj。这是 K6 契约的延续。

### 4.4 数据库表设计 checklist

**N/A** —— 无表改动。

### 4.5 其他实施决策

- **新函数签名**:`async def backfill_perm_set_for_existing_tenants(db: AsyncSession, obj: str) -> dict[str, int]`,开头校验 `if obj not in BACKFILLABLE_OBJS: raise ValueError(...)`。
- **⚠️ 循环变量重命名(v2 关键)**:原 body 的 api perms 循环是 `for obj, act in perms:`(循环变量也叫 `obj`),**会 shadowing 函数参数 `obj`**。参数化后必须把循环变量重命名为 `perm_obj`(即 `for perm_obj, act in perms:`),否则循环内 `obj` 是 perm 的 obj 而非函数参数,scope guardrail `if perm_obj != obj: continue` 才正确。这是 v1 完全没提的实现陷阱。
- **白名单常量**:`BACKFILLABLE_OBJS: frozenset[str] = frozenset({"devices", "bookings"})`,放函数定义前,注释说明「只含需要 backfill 的 tenant-scoped 业务记录 obj;其他 obj(agents/customers/users 等)在 `seed_tenant_defaults` 里从建租户第一天就 seed,无需 backfill」。
- **白名单保护对象说明(v2 补)**:script 路径下 argparse `choices=["devices","bookings"]` 已做第一道校验(传非法值 argparse 先报错),所以 script 调用永远不会触发函数内 ValueError。**白名单 ValueError 的真正保护对象是「非 script 调用方」**——测试代码直接 import 调函数、或其他 service 直接调用时,白名单是唯一防线。两者不冗余,各守一道关。
- **body 复用**:原 body 的 scope guardrail `if obj != "devices"` 改为 `if perm_obj != obj: continue`(api 区,循环变量已改名);`if code != "devices"` 改为 `if code != obj: continue`(menu 区)。
- **docstring**:新函数 docstring 说明「参数化自原 devices/bookings 两个 backfill;obj 必须在 BACKFILLABLE_OBJS 内;幂等三层不变」。
- **scripts 改名(v2)**:新 `scripts/backfill_obj_perms.py`(原拟 `backfill_perms.py` 改名,避与已有 `scripts/backfill_permissions.py` 碰撞)。接 `--obj` 必填参数(argparse choices=["devices", "bookings"] 做第一道校验),保留 `--dry-run`。
- **零行为变更约束**:参数化后函数行为与原两个函数逐字等价(同一 db 传入同一 obj,产出同一 stats)。由 parametrize 测试 + 现有全量测试保护。
- **符号名锚定**(v2,呼应铁律 #5):本 plan 引用代码用符号名(`backfill_devices_perms_for_existing_tenants` 函数 / `_upsert_permission` 方法 / `sync_role_permissions_to_casbin` 等),不用行号(行号会随编辑漂移)。grill 阶段的行号仅作定位辅助。

---

## 5. Testing Decisions(对齐 to-spec)

### 测试 seam

| Seam | 层级 | 测什么 | 先例 |
|---|---|---|---|
| **seam: `backfill_perm_set` 函数** | 函数级(最高) | parametrize obj ∈ {devices, bookings},断言幂等 + scope 隔离 + 正确补齐 | 原 test_devices_api/test_bookings_api 的 K chapter(合并) |

**seam 总数 = 1**(局部最高点,backfill 是纯函数式 db 操作,无更高 seam)。

### tests/test_permission_backfill.py 覆盖(parametrize,v2 补 helper 参数化)

继承原 K chapter 的 3 场景,每个场景 parametrize 2 个 obj:

1. **test_backfill_grants_perms_correctly[obj]**:backfill 后 owner/admin/member 持有该 obj 的正确 perm 子集。**期望值从 DEFAULT_OWNER_PERMS/DEFAULT_ADMIN_PERMS/DEFAULT_MEMBER_PERMS + DEFAULT_MENU_PERMS 动态计算**(v2 修正:v1 硬编码 `5+4+2`,未来某 obj perm 数不同会坏;devices/bookings 恰好都是 owner 4 api + 1 menu = 5、admin 3+1=4、member 1+1=2,但断言应从数据源算而非硬编码)
2. **test_backfill_idempotent[obj]**:连续跑两次,第二次 stats 全 0(已 grant 的 no-op)
3. **test_backfill_preserves_other_perms[obj]**:backfill 指定 obj 后,**其他 obj 的 perms 不变**(scope guardrail 契约)。**helper `_seed_backfill_target_tenant` 需参数化**(v2 补):原 K chapter 里 devices 版用 `customers:read` + `menu:agents` 当「其他 perm」,bookings 版用 `customers:read` + `devices:read` —— 合并时 helper 要能 seed 一个「!= 当前 obj」的 perm 作对照。参数化 helper 签名如 `_seed_backfill_target_tenant(db, tenant_id, other_obj="customers")`,确保 other_obj != 当前测试 obj。

**额外加 1 个边界**(D4 白名单):
4. **test_backfill_rejects_unknown_obj**:传 `obj="users"`(不在白名单)→ 抛 ValueError(防误用契约。注:这条不经 parametrize,固定 obj="users")

### 测试金字塔

- **unit 1 文件**:`test_permission_backfill.py`(3 parametrized × 2 obj + 1 边界 = 7 test cases)
- **integration 0**:不新增
- **E2E 0**:不新增

### 覆盖率目标

- 后端覆盖率不受影响(零行为变更,现有 840 passed 保护 + 新 parametrize 测试覆盖重构后的函数)
- 项目后端基线:840 passed;本任务后预期 840 - 6(删原 K chapter 6 test)+ 7(新 parametrize)= 841 passed

---

## 6. 切片规划(对齐 to-tickets,v2 修正测试空窗)

> **切片策略**:纯代码重构,非功能开发。按「依赖顺序」分 2 片:先合并 service 函数(核心)+ 改所有 caller(**临时保留测试绿**)→ 再合并 scripts + 测试 parametrize(收尾验证)。

### Ticket 1: service 函数参数化合并 + caller 改造(**临时保留测试绿**) ✅

- **What to build**:在 `permission_service.py` 新增 `BACKFILLABLE_OBJS` 常量 + `backfill_perm_set_for_existing_tenants(db, obj)` 函数(body 从原两函数合并,obj 用参数替换硬编码 + 开头白名单校验 + **循环变量改 `perm_obj`**);删旧 `backfill_devices_perms_for_existing_tenants` + `backfill_bookings_perms_for_existing_tenants`。所有 caller 同步改调新函数 + 传 obj。**v2 关键:测试 K chapter 临时改调新函数(`backfill_perm_set(db, "devices")`),不删** —— 保留 6 个测试绿,避免安全代码测试空窗(删 K chapter 移到 Ticket 2)。scripts 也临时改调新函数(Ticket 2 删)。
- **Blocked by**: 无(可立即开始)
- **文件清单**(5 改):
  - 改 `app/services/permission_service.py`(新增函数 + 常量 + 删旧两函数 + 循环变量改名)
  - 改 `tests/test_devices_api.py`(K chapter **临时改调新函数**,保留 3 测试绿)
  - 改 `tests/test_bookings_api.py`(K chapter **临时改调新函数**,保留 3 测试绿)
  - 改 `scripts/backfill_devices_perms.py` + `scripts/backfill_bookings_perms.py`(临时改调新函数 —— Ticket 2 会删它们)
- **验证命令**:
  - `python -c "from app.services.permission_service import backfill_perm_set_for_existing_tenants, BACKFILLABLE_OBJS; print(BACKFILLABLE_OBJS)"`(import 成功)
  - `pytest tests/test_devices_api.py tests/test_bookings_api.py -k "backfill" -v`(**6 测试临时改调后仍绿**,行为等价验证)
  - `./init.sh`(冒烟:全量绿,确认 caller 改造无遗漏)
- **AC**:
  - [x] `backfill_perm_set_for_existing_tenants(db, obj)` 函数就位,签名含 obj: str
  - [x] `BACKFILLABLE_OBJS` frozenset 常量就位,含 devices + bookings
  - [x] 非法 obj 抛 ValueError
  - [x] **循环变量已改名为 `perm_obj`**(无 shadowing)
  - [x] 旧两函数已删,grep 无残留**定义**
  - [x] **6 个 K chapter 测试临时改调新函数后仍全绿**(无测试空窗)
  - [x] `./init.sh` 冒烟绿(无 import error / 无 NameError)

> **完成证据(2026-07-30)**:`./init.sh` 冒烟绿(ruff + 42 smoke passed);`pytest -k backfill` 6 passed(devices 3 + bookings 3);两个 script dry-run 在真实 DB 上 import + 执行新函数正常;`BACKFILLABLE_OBJS = frozenset({'devices','bookings'})`;`ValueError` 对 `obj="users"` 触发验证 OK。双轴 code-review 通过(Standards 0 硬违例 / Spec 0 偏差,K6 scope guardrail 由 `if perm_obj != obj` + `if code != obj` 保持)。

### Ticket 2: scripts 合并 + 测试 parametrize 收尾

- **What to build**:删 `scripts/backfill_devices_perms.py` + `scripts/backfill_bookings_perms.py`,新建 `scripts/backfill_obj_perms.py`(接 `--obj` 必填 + `--dry-run`);删两个 test 文件的旧 K chapter(已被 Ticket 1 临时改调),新建 `tests/test_permission_backfill.py`(parametrize 3 场景 × 2 obj + 1 边界);feature 收尾。
- **Blocked by**: Ticket 1
- **文件清单**(2 删 + 2 新 + 2 改):
  - 删 `scripts/backfill_devices_perms.py` + `scripts/backfill_bookings_perms.py`
  - 新建 `scripts/backfill_obj_perms.py`
  - 新建 `tests/test_permission_backfill.py`
  - 改 `tests/test_devices_api.py` + `tests/test_bookings_api.py`(删 K chapter —— 临时调用已被新 parametrize 测试接管)
- **验证命令**:
  - `python scripts/backfill_obj_perms.py --obj devices --dry-run`(dry-run 正常)
  - `python scripts/backfill_obj_perms.py --obj invalid`(argparse 报错 choices)
  - `pytest tests/test_permission_backfill.py -v`(7 cases 绿)
  - `./init.sh full`(全量 841 passed,零回归)
  - `grep -rn "backfill_devices_perms\|backfill_bookings_perms" app/ scripts/ tests/`(**引用**归 0,无残留旧名)
- **AC**:
  - [ ] 新 script `backfill_obj_perms.py --obj devices|bookings [--dry-run]` 工作
  - [ ] argparse choices 限制 obj 为 devices/bookings
  - [ ] `test_permission_backfill.py` 7 cases 全绿(3 场景 × 2 obj + 1 边界)
  - [ ] 旧两 script 已删
  - [ ] grep 旧函数名**引用**归 0(定义在 Ticket 1 已删,此处确认引用也清)
  - [ ] `./init.sh full` 全量绿(841 passed)
  - [ ] feature 收尾:feature_list.json status → passing + evidence + sync-active + progress.md
  - [ ] 文档影响评估执行

---

## 7. v1 → v2 对抗式审查段

**触发条件评估**:
- 改动文件 1 service + 2 scripts + 2 tests + 1 新 test = 6(< 10)✓ 不触发
- 涉及鉴权/权限/数据迁移/跨服务? **边界情况** —— 涉及权限 backfill(离线运维路径,非运行时鉴权),但是纯参数化重构,权限行为零变化
- 涉及安全敏感操作(token/密钥/支付)? **NO**
- 涉及不可逆操作? **NO**

**结论**:**不触发对抗式审查**(纯参数化重构,权限行为零变化,scope guardrail 由白名单强化而非削弱)。走单模型 `/code-review` 双轴即可。但 `/code-review` 时**重点审查 scope guardrail 保持**(K6 契约:不误改其他 obj perms)。

---

## 8. Out of Scope(对齐 to-spec)

- ❌ **不迁移 backfill 到独立模块**:backfill 仍留在 `permission_service.py`(与 PermissionService 同模块,因为依赖其 `_upsert_permission` / `sync_role_permissions_to_casbin` / `add_policy` 私有方法)。巡检曾提「迁移到 scripts/」但实际它需要 service 的私有方法,留在 service 模块合理。
- ❌ **不重构 PermissionService 类本身**:第 7 次巡检已关闭「拆 5 cluster」候选(not-shallow,SCD2↔casbin 宪法是 depth)。本任务只动 backfill 函数。
- ❌ **不加新的 backfill obj**:只参数化现有 devices/bookings,不主动加第 3 个 obj(那是未来 feature 的事)。
- ❌ **不改 DEFAULT_*_PERMS 表内容**:表不变,只是 backfill 读它的方式参数化。
- ❌ **不碰候选① chat-page / 候选② devices-page**:独立 feature,本轮不碰。

---

## 9. 风险与缓解(v2 补遗漏项)

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 参数化后 scope guardrail 失效,误改其他 obj perms | **高** | D4 白名单 + ValueError;body 内 `if perm_obj != obj: continue`(循环变量已改名)+ `if code != obj: continue` 双 guard 保留;`test_backfill_preserves_other_perms` 覆盖(scope guardrail 契约测试)|
| **循环变量 `obj` shadowing 函数参数**(v2 新增) | **高** | §4.5 显式:循环变量改名为 `perm_obj`;Ticket 1 AC 含「循环变量已改名」检查 |
| **script 命名碰撞**(v2 新增):`backfill_perms.py` vs 已有 `backfill_permissions.py` | 中 | 改名为 `backfill_obj_perms.py`;§4.1/§6 已用新名 |
| caller 改造遗漏,运行时 NameError | 中 | Ticket 1 AC 含 `./init.sh` 冒烟 + grep 残留**定义**;CI 兜底 |
| Ticket 1 完成时安全代码测试空窗(v1 已修正) | ~~高~~ → 已消除 | v2:Ticket 1 **保留** K chapter(临时改调新函数),6 测试绿;删 K chapter 移到 Ticket 2(由 parametrize 测试接管) |
| parametrize 测试与原 K chapter 行为不等价(漏断言) | 中 | 复制原 K chapter 的断言逻辑,只改 obj 参数化;期望值动态算(§5) |
| scripts 合并后运维文档过时(若有 README 提到旧 script 名) | 低 | grep README/docs 提及旧 script 名,同步更新 |

---

## 10. 验收标准(同步 feature_list.json verification,v2 script 改名)

1. `grep -rn "backfill_devices_perms_for_existing_tenants\|backfill_bookings_perms_for_existing_tenants" app/ scripts/ tests/` —— 归 0(无残留旧函数名,含定义+引用)
2. `python scripts/backfill_obj_perms.py --obj devices --dry-run` —— 正常运行(dry-run 报告)
3. `python scripts/backfill_obj_perms.py --obj invalid` —— argparse 报错(choices 限制)
4. `pytest tests/test_permission_backfill.py -v` —— 7 cases 全绿
5. `./init.sh full` —— 后端 841 passed(840 - 6 删 + 7 新),零回归
6. `grep -n "BACKFILLABLE_OBJS\|def backfill_perm_set_for_existing_tenants" app/services/permission_service.py` —— 新函数 + 常量就位
7. `grep -n "for perm_obj" app/services/permission_service.py` —— 循环变量已改名(无 shadowing)
8. ruff clean + oxlint(若涉及)0 warning

---

## 11. 不越界声明

本次改动**只**涉及 `permission_service.py` 的 backfill 函数参数化(2 → 1)+ 对应 scripts 合并(2 → 1)+ 测试 K chapter 合并(2 → 1 parametrize);

**不**触碰:
- PermissionService 类本身的任何方法(`check`/`require`/`seed_tenant_defaults`/`sync_role_permissions_to_casbin` 等零改动)
- DEFAULT_*_PERMS / DEFAULT_MENU_PERMS 表内容
- 任何运行时鉴权路径(backfill 是离线运维,不影响 require_permission)
- 数据库 / schema / migration
- 候选① chat-page / 候选② devices-page(独立 feature)
