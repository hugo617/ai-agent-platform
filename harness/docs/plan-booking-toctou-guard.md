# 计划:预约时段 TOCTOU 竞态 DB 兜底(booking-toctou-guard)

> **id**: booking-toctou-guard
> **状态**: in_progress(EP2 完成 2026-08-15;切片 01 开工 2026-08-15,与 feature_list.json 同 commit 翻页)
> **优先级**: 95(feature_list.json,第 10 次巡检业务风险 R2 🔴)
> **创建日期**: 2026-08-15
> **最后修订**: 2026-08-15(v2:对抗式审查回写)
> **来源**: [plan-risk-hardening-overview.md](./plan-risk-hardening-overview.md) §2(形态 EP2 烤定)
> **EP2 回环**: grill(2026-08-15,**8 项决策全部用户逐项拍板**,AskUserQuestion 2 轮,无「按推荐默认采纳」——系列铁律,见 §4.5 D1-D8)→ to-spec(v1)→ 对抗式审查(双轴并行)→ to-tickets(v2,§6)

---

## 0. v1 → v2 变更摘要(对抗式审查回写,2026-08-15 双轴并行)

| v1 问题 | 严重度 | v2 处理 |
|---|---|---|
| §4.6 迁移步骤 4 downgrade 约束名笔误 `no_overflow`(双轴一致抓获):`IF EXISTS` + 错名 = 静默 no-op,downgrade 假成功,re-upgrade 报 duplicate constraint,钦定的 upgrade→downgrade→upgrade 验证路径断裂 | 🔴 | 改正为 `excl_bookings_active_no_overlap`;切片 01 AC ③ 补「downgrade 后确认约束确已消失(pg_catalog 查询)」防同类静默失效 |
| 流程项:feature_list.json 的 `plan` 字段未回填本文档(three-tier §3 EP2 收尾要求;R1 同类遗漏先例被其审查记为流程 🔴) | 🔴 | §0 记此行,v2 交付时执行回填(`plan` 字段指向本文档;`status` 按用户既定指令保持 `not_started`) |
| 「竞态 → 400」端到端链路在真 PG 上零证明:约束拒绝(裸 INSERT)与映射判别(SQLite 构造异常单测)各自有测,但「IntegrityError 在预期捕获点抛出 + `e.orig` 带真 23P01 + 映射成 BizError」全链从未在真 PG 验证——若 psycopg async 包装形态不符预期,映射静默失效且无测试能发现 | 🟡 | §4.6 PG 门控用例加第 ⑥ 条(切片 02 落地):conn1 插未提交 active 行 → 另一 session 实例化 `BookingService.create`(read committed 下应用层检查看不见未提交行 → 通过)→ INSERT 阻塞 → commit conn1 → 断言抛 **BizError** 而非 IntegrityError——确定性复现服务路径竞态,字面满足 verification 1 的「两请求」措辞 |
| 预检漏退化区间:存量 `scheduled_end_at <= scheduled_start_at` 的 active 行不被 v1 预检捕获,但建 GiST 索引求值 `tstzrange` 会抛原生错误,违反「不用原生报错挡门」承诺(s==e 空区间行为两难) | 🟡 | 预检并列第二条计数(`scheduled_end_at <= scheduled_start_at`,与 `_assert_window_valid` 的 `end > start` 不变式同口径)→ 同款 RuntimeError 提示修正数据 |
| alembic check 反射预判**方向反了**(Spec 轴对实装 SQLAlchemy 2.0.36 + alembic 1.14.0 核实):PG 方言 `get_indexes` 对 exclusion 背书索引打 `duplicates_constraint` 标,alembic PG impl 主动剔除 → check 天然干净,按 v1 字面会浪费 EP3 精力甚至为不存在的问题改 env.py | 🟡 | §4.6/§9/切片 01 AC 改写:已核实预期干净;env.py `include_object` 仅当未来升级 SQLAlchemy/alembic 后实测报 drift 才落地 |
| 「拒迁路径实测」无可重复命令(v1 AC 只说实测,EP3 要自己发明步骤) | 🟡 | 切片 01 验证命令补显式序列:downgrade → 手插重叠对 → upgrade 断言失败且报文含数量 → 清理 → upgrade 成功 |
| 状态清单三处同源(`_ACTIVE_STATES`/约束谓词/预检 SQL)只有注释互指的软守护,无机械防线;迁移 import 应用代码做单源属反模式(冻结历史依赖活代码) | 🟡 | 切片 01 AC 加同源防漂移测试(SQLite 常驻):读迁移源码断言两处状态字面量与 `_ACTIVE_STATES` 一致,进 CI |
| §8「届时需 eval¾」乱码 + 「未用状态(confirmed/in_service)」失准(`booking_state._TRANSITIONS` 里 in_service 在用,未用占位只有 confirmed);判别单测落点两可与切片 02 验证命令不一致;迁移文件头 docstring 未要求对齐先例;§4.4 checklist 缺租户归属/命名两条 N/A;§4.6「无一等 ExcludeConstraint op」措辞不准(SQLAlchemy 有该构造,是 alembic autogen 不支持) | 🟢 | 全部吸收:乱码句重写(补 lock_timeout 备注)/ 改「未用占位态(confirmed)」/ 判别单测钉死挂靠 `tests/test_bookings_api.py` / 迁移头 docstring 对齐 `b3f7a2c91d4e` 先例 / checklist 补两行 / 措辞改「alembic autogenerate 不支持 ExcludeConstraint,迁移内用 raw SQL」 |

## 1. Problem Statement

预约时段冲突检测是纯应用层 check-then-insert(第 10 次巡检 R2 🔴):

`BookingService.create` 先 `find_overlap`(active 态 + 左闭右开 SQL)再 INSERT,两步之间无锁、无事务隔离强化——**两个并发请求同时通过检查后双双落库**,同一设备同一时段出现两条 active 预约。`update`(reschedule)同理。模型层刻意无任何约束兜底(`app/models/booking.py` 注释自认 "deliberately no partial unique index")。

**考古(EP2 任务要求,为何当时刻意不加)**:device-booking 的 D8 决策(用户拍板「不软删,只用 cancelled 态」)连带写明「无 is_deleted/deleted_at 列,无部分唯一索引」——仓库既有的部分唯一索引范式(devices serial / user_tenants SCD2 / wallet)**全都靠 `WHERE is_deleted = false` 排除软删行**,bookings 没有软删列,该范式无锚点。模型注释「overlap 是运行时业务规则,不是静态列不变式」对**普通唯一索引**成立(唯一索引只能挡同键值重复,挡不住区间部分重叠)。**当时的决策并不是「考虑过 DB 级 TOCTOU 兜底后拒绝」——TOCTOU 根本不在 device-booking 范围**。本 feature 不与 D8 冲突:cancelled 行经 WHERE 谓词排除,与既有「排除软删行」范式同构。

**关键事实(EP2 取证)**:普通部分唯一索引 `UNIQUE(device_id, scheduled_start_at) WHERE active` 只能挡「同一开始时刻」的完全重复,挡不住 `[10:00,12:00)` vs `[11:00,13:00)` 的部分重叠——它不是结构性拒绝。对区间重叠做真·DB 层结构性拒绝的形态是 **PG 的 EXCLUDE 约束**(btree_gist + `tstzrange &&`)。

## 2. Solution

给 `bookings` 表加 **PG EXCLUDE 排他约束**:`(device_id WITH =) + (tstzrange(scheduled_start_at, scheduled_end_at, '[)') WITH &&)`,WHERE 谓词排除非占坑态(cancelled/done/no_show)——语义与应用层 `_ACTIVE_STATES` 逐字对齐,左闭右开边界一致(back-to-back 不冲突)。约束由迁移持有(`CREATE EXTENSION IF NOT EXISTS btree_gist` 前置),对 INSERT 与 UPDATE 天然生效;迁移内先做存量脏数据预检(镜像 knowledge-foundation 拒迁先例)。

应用层 `find_overlap` 检查**保留**为第一道防线(友好文案含冲突 booking id);DB 兜底只在竞态漏网时命中,服务层把 exclusion violation(sqlstate 23P01)映射回与现役冲突**同款 400**。并发竞态回归测试为 **PG 门控测试文件**,常驻 CI Migrations job(该 job 已起真 PG 并跑完迁移链,测到的就是真迁移产物);SQLite 常规套件零影响。

## 3. User Stories

1. 作为门店员工,我和同事并发为同一设备同时段下单时,后到的请求收到明确「设备时段冲突」错误,而不是双双成功、到店才发现撞车。
2. 作为门店员工,一条预约被取消(cancelled)或完结(done/no_show)后,它让出的时段能**立即**被重新预约——排除态语义与现状零变化。
3. 作为门店员工,我把 pending 预约改期(reschedule)到已被占用的时段时,同样被拒——update 路径不留盲区。
4. 作为前端用户,冲突错误仍是熟悉的 400 `{"detail": "设备时段冲突:…"}` 形态——前端零改动。
5. 作为平台运维,生产库加约束时若已存在历史双订脏数据,迁移**拒绝执行并列出重叠对数量**,人工处置后重跑;不会静默改业务数据,也不会用原生报错把我挡在门外。
6. 作为开发者,SQLite 测试链(create_all 建 schema)完全不受影响;PG 门控测试在 CI 常驻防回归,本地 docker PG 可复跑。

## 4. Implementation Decisions

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 2 | `app/models/booking.py`(docstring 更新,`__table_args__` **不动**)/ `app/services/booking_service.py`(create/update 两路径 IntegrityError → BizError 映射,~15 行) |
| 数据库迁移 | 1 | alembic 新版本(接 `b3f7a2c91d4e`):脏数据预检拒迁 → `CREATE EXTENSION IF NOT EXISTS btree_gist` → ADD CONSTRAINT EXCLUDE |
| CI | 1 | `.github/workflows/ci.yml` migrations job +1 step(跑 PG 门控测试,env 对齐 backend job) |
| 新增测试 | 2 | `tests/test_booking_overlap_pg.py`(新,PG 门控)+ 映射判别单测(SQLite 常驻,挂靠既有 bookings 测试文件或新小文件) |
| 文档 | 2 | `CONTEXT.md`(术语「占坑态」)+ `项目指南/02-后端架构/03-数据库与ORM.md`(PG-only 约束范式段)——EP3 落地时执行 |
| 前端 | 0 | 零改动(400 同款,前端无需感知) |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**(仅加约束,无新表无新列)
- 是否修改现有租户隔离逻辑? **NO**(约束键是 `device_id`——设备全局唯一、归属唯一租户,与应用层 `find_overlap` 的 tenant_id+device_id 双条件等价;租户过滤路径零变化)
- 是否引入跨租户访问点? **NO**
- 验证:多租户既有测试零回归(`./init.sh full`)

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 require_permission caller? **NO**(约束在 DB 层,任何写路径的最终落库点)
- 是否影响 graph.py 工具内 check? **NO**

### 4.4 数据库表设计 checklist(AGENTS.md 铁律 6:不加表,仅加约束)

- [x] 无新表无新列:只加 EXCLUDE 约束(自带 gist 索引)+ btree_gist 扩展
- [x] 租户归属 / 命名:不涉及(无新表;约束名 `excl_bookings_active_no_overlap`,excl_ 前缀区别于 idx_/ck_)
- [x] 双库兼容:**迁移链本就 PG-only**(ci.yml 明注 JSONB/vector 先例);约束不进模型 `__table_args__`(ExcludeConstraint 是 PG 方言构造,SQLite `create_all`(测试套件建 schema 方式)无法编译),迁移内用 `if bind.dialect.name != 'sqlite'` guard 镜像 `f2b3c4d5e6f7` vector 先例——两全:PG 得到结构性拒绝,SQLite 测试链零感知
- [x] 软删除:不涉及(bookings 本就无软删,D8;排除态用 status 谓词,与本仓库「排除软删行的部分唯一索引」范式同构)
- [x] timestamp/外键/index 策略:不动任何既有列与索引;EXCLUDE 约束自带 `(device_id, tstzrange)` gist 索引
- [x] 历史维度:约束失败不写 SystemLog(罕见兜底路径,异常即 400 返回;应用层检查照旧是常态防线)

### 4.5 用户拍板决策(D1-D8,2026-08-15 AskUserQuestion 2 轮逐项拍板,无默认采纳)

**兜底形态与语义(D1-D4)**

| # | 决策点 | 拍板结果 |
|---|---|---|
| D1 | 兜底形态 | **PG EXCLUDE 约束**(btree_gist + `tstzrange &&`):唯一能对区间重叠做真·结构性拒绝的形态;create/update 天然全覆盖;迁移链本就 PG-only 落地无障碍;约束不进模型,SQLite pytest 不受影响。**否决**:advisory lock(拒绝仍表现为应用层 400,不满足 verification「非应用层 if 拦截」字面;两路径都要显式加锁)/ 部分唯一索引(只挡同一开始时刻,挡不住部分重叠,是窄化非拒绝) |
| D2 | 排除态语义 | **与应用层 `_ACTIVE_STATES` 严格对齐**:pending/confirmed/in_service 占坑;cancelled/done/no_show 释放(时段立即复用)。DB 守卫与应用层检查永远同口径,不偷偷改业务规则 |
| D3 | DB 兜底命中的错误语义 | **同款 400**:IntegrityError 映射回「设备时段冲突:…」BizError,延续 device-booking D1「400 非 409」既定决策;UX 单一口径,前端零改动 |
| D4 | 并发竞态回归测试落点 | **PG 门控测试 + CI Migrations job**:skipif 非 PG 的 pytest 文件,Migrations job(已起真 PG、已跑迁移链)加一步;SQLite 侧保留排除态语义/路径零回归测试。满足收官标准「回归测试常驻 CI」 |

**存量数据与收尾细节(D5-D8)**

| # | 决策点 | 拍板结果 |
|---|---|---|
| D5 | 存量脏数据(历史双订) | **预检拒迁**:迁移内扫 active 态重叠对,发现即 RuntimeError 拒迁并列出数量,人工处置后重跑(镜像 knowledge-foundation group_tenants 先例);不静默改业务数据。干净库(全新部署/CI)零成本通过 |
| D6 | 守卫覆盖面 | **create + update 全覆盖**:EXCLUDE 约束对 INSERT/UPDATE 天然生效,reschedule 改时段撞重叠同样被拦,不留盲区;PG 门控测试两条都覆盖 |
| D7 | 应用层 `_assert_no_overlap` 去留 | **保留**:应用层检查是第一道防线(文案含冲突 booking id、信息友好);DB 兜底只在竞态漏网时命中(罕见路径)。双防线分工清晰 |
| D8 | 兜底文案 | **简文不带 id**:exclusion violation 拿不到冲突行 id,兜底文案「设备时段冲突:该时段已被并发预约占用」即可,不回查;正常路径(99.9%)仍走应用层检查带 id 文案 |

### 4.6 技术设计细节(实施层约定)

**EXCLUDE 约束 DDL(迁移内 raw SQL——alembic autogenerate 不支持 ExcludeConstraint(SQLAlchemy 有该 PG 方言构造),迁移手写 DDL)**

```sql
ALTER TABLE bookings ADD CONSTRAINT excl_bookings_active_no_overlap
  EXCLUDE USING gist (
    device_id WITH =,
    tstzrange(scheduled_start_at, scheduled_end_at, '[)') WITH &&
  )
  WHERE (status IN ('pending', 'confirmed', 'in_service'));
```

- **`'[)'` 左闭右开**与 `find_overlap` 的 D4 语义一致:back-to-back(一个 11:00 结束、下一个 11:00 开始)的 `&&` 为 false,不冲突。
- **NULL `device_id` 永不冲突**:exclusion 比较含 NULL 即满足约束,与 `find_overlap` 的 `Booking.device_id == device_id`(NULL 不等)一致——设备软删置 NULL 的历史行不占坑。
- **状态机迁移自动退出约束集合**:cancel/done/no_show 的 UPDATE 使行退出 WHERE 谓词,时段立即释放,无需任何额外代码。
- **约束名** `excl_bookings_active_no_overlap`(excl_ 前缀区别于 idx_/ck_,一眼可辨形态)。

**迁移文件(接 alembic 头 `b3f7a2c91d4e`,命名风格 `2026_08_15_HHMM_<rev>_add_bookings_overlap_exclude.py`,文件头 docstring 对齐 `b3f7a2c91d4e` 先例:Revision ID / Revises: b3f7a2c91d4e / Create Date / 指向本 plan)**

1. **预检拒迁**(D5,镜像 knowledge-foundation `05fa069297cc` 先例;两条并列,任一 > 0 即拒):
   ```sql
   -- ① active 态重叠对(与约束谓词逐字镜像)
   SELECT COUNT(*) FROM (
     SELECT a.id FROM bookings a JOIN bookings b
       ON a.id < b.id AND a.device_id = b.device_id
      AND a.status IN ('pending','confirmed','in_service')
      AND b.status IN ('pending','confirmed','in_service')
      AND a.scheduled_start_at < b.scheduled_end_at
      AND b.scheduled_start_at < a.scheduled_end_at
   ) AS _overlap
   -- ② 退化区间(end <= start;建 GiST 索引求值 tstzrange 会抛原生错误,
   --    口径与 _assert_window_valid 的 end > start 不变式一致)
   SELECT COUNT(*) FROM bookings
    WHERE status IN ('pending','confirmed','in_service')
      AND scheduled_end_at <= scheduled_start_at
   ```
   计数 > 0 → `RuntimeError("Refusing to add exclusion constraint: found %d overlapping active booking pair(s) / %d degenerate window(s) ... 人工处置(取消/修正其一)后重跑")`。
2. `if bind.dialect.name != 'sqlite': op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist;")`(镜像 `f2b3c4d5e6f7` vector 先例;pgvector/pg16 镜像自带 contrib)。
3. `op.execute` 上述 ALTER TABLE(同样在 dialect guard 内)。
4. `downgrade()`:`ALTER TABLE bookings DROP CONSTRAINT IF EXISTS excl_bookings_active_no_overlap`;btree_gist 扩展**保留不卸**(库级共享组件,卸载影响面大于收益,注释声明)。

**alembic check 反射问题(Spec 轴已对实装版本核实:SQLAlchemy 2.0.36 + alembic 1.14.0)**:EXCLUDE 约束在 PG 里同时物化为同名 gist 索引,但 PG 方言 `get_indexes` 对约束背书索引(contype ∈ p/u/x)打 `duplicates_constraint` 标,alembic PG impl 的 `correct_for_autogen_constraints` 把带此标的索引从比较集合剔除 → **`alembic check` 预期天然干净**,不需要 env.py 改动。兜底预案仅记录备用:若未来升级 SQLAlchemy/alembic 后实测 check 报该索引幽灵 drift,在 `alembic/env.py` 加 `include_object` 钩子对 `type_ == "index"` 且 `name == "excl_bookings_active_no_overlap"` 返回 False(带注释指向本 plan)。约束不在模型 `__table_args__` 中,模型侧永远无 drift。

**服务层映射(create + update 双路径,D3/D6/D8)**

- `repo.add` 内部 flush → create 路径 IntegrityError 在 `repo.add(booking)` 处抛;update 路径在 `db.flush()` 处抛。两处包捕获。
- 判别 helper(booking_service 私有):捕 `sqlalchemy.exc.IntegrityError` 后 `getattr(e.orig, "sqlstate", None) == "23P01"`(exclusion_violation;psycopg3 异常带 sqlstate 属性)→ `await self.db.rollback()` + `raise BizError("设备时段冲突:该时段已被并发预约占用")`;**非 23P01 一律 re-raise**(其他完整性问题不吞,如未来唯一索引违规仍按现状 500/既有路径)。无 sqlstate 属性(如测试构造的异常对象)→ getattr 默认 None → re-raise(安全侧)。
- 映射 helper 设计为可单测的纯判别函数(传异常对象,返回 BizError 或 None),SQLite 常驻套件用构造异常对象直测,不需要真 PG。

**PG 门控测试(`tests/test_booking_overlap_pg.py`)**

- **门控**:module 级 `pytest.mark.skipif("postgresql" not in os.environ.get("DATABASE_URL", ""), reason=...)`——SQLite 常规套件自动跳过,收集零报错。
- **schema 来源**:直连 `DATABASE_URL` 的 async engine,表由**迁移链**建好(CI Migrations job 顺序 upgrade → check → pytest,测到的就是真迁移产物,模型 create_all 不参与);种子最小行 tenants → device_models → devices → bookings 直插(唯一 serial 前缀标记,finally 清理)。
- **确定性并发模式**(PG 唯一/排他约束并发语义的标准测法,不靠时序赌博):conn1 开事务 INSERT A 不提交 → conn2 INSERT 重叠 B(**阻塞**在约束等待)→ commit conn1 → conn2 抛 IntegrityError。断言「恰一成功、一被 DB 拒」。
- 用例清单:①并发重叠双插恰一成功 ②back-to-back `[10,12)+[12,14)` 双双成功(边界语义)③cancelled/done/no_show 排除(重叠可插,时段可复用)④UPDATE 改时段撞重叠被拒(update 路径覆盖)⑤NULL device_id 不冲突 ⑥**服务路径竞态全链证明**(切片 02 落地):conn1 插未提交 active 行 → 另一 session 实例化 `BookingService.create`(read committed 下应用层 `find_overlap` 看不见未提交行 → 检查通过)→ INSERT 阻塞 → commit conn1 → 断言 service 抛 **BizError「设备时段冲突」而非 IntegrityError**——覆盖捕获点 + rollback + sqlstate 判别 + 映射全链,字面满足 verification 1 的「两请求」措辞。
- **CI wiring**:migrations job 加 step `pytest tests/test_booking_overlap_pg.py -q`(该 job 已装 requirements-dev);step env 补齐与 backend job 相同的测试变量(JWT_SECRET/SALT_ROUNDS/OPENAI_API_KEY/CORS_ORIGINS——`app.core.database` import 期拉 settings,防导入校验失败的双保险)。
- **本地复跑**:`docker-compose up -d` + `alembic upgrade head` + `DATABASE_URL=postgresql+psycopg://aap:aap_secret@localhost:5433/aap pytest tests/test_booking_overlap_pg.py`(5433 = docker-compose 宿主端口映射;5432 是 CI 容器网内端口)。

**模型 docstring 更新(`app/models/booking.py`)**

替换「There is deliberately no partial unique index…」段:保留考古事实(D8 无软删列 + 区间重叠非唯一索引可表达),增写 DB 兜底现状——EXCLUDE 约束 `excl_bookings_active_no_overlap` 由迁移持有、模型不声明的原因(SQLite create_all 无法编译 PG 方言构造 + alembic check 模型侧无 drift)、占坑态谓词与 `_ACTIVE_STATES` 同源约束(两处状态清单必须同步改,注释互指)。`__table_args__` 与列定义**零改动**。

**同源防漂移机械防线**(审查 🟡 采纳):状态清单存在于三处(`_ACTIVE_STATES` / 约束谓词 / 预检 SQL)——迁移文件是冻结历史,**不 import 应用代码做单源**(反模式:活代码重构会破坏旧迁移);改为 SQLite 常驻小测试读迁移源码,断言约束谓词与预检 SQL 的状态字面量与 `_ACTIVE_STATES` 一致,进 CI(切片 01 AC)。

## 5. Testing Decisions

- **测试 seam**:PG 门控测试直连 engine 走 SQL/ORM INSERT(守卫是 DB 层,直测 DB 层最诚实,不借 HTTP/app 装配);服务层映射走函数直测(SQLite 常驻);既有 bookings API 测试(HTTP + 内存 SQLite)零改动零回归。
- **PG 门控用例**(见 §4.6 清单 ①-⑤,常驻 CI Migrations job;⑥ 在切片 02 落地);**SQLite 常驻用例**:映射判别(23P01 → BizError / 23505 或无 sqlstate → re-raise)+ 同源防漂移(迁移源码状态清单 vs `_ACTIVE_STATES`)+ 既有排除态应用层测试(取消后重订)零回归即覆盖 verification 第 2 条的应用层半边。
- **迁移用例**:本地 docker PG 实测 upgrade → downgrade(确认约束消失)→ upgrade;预检拒迁双路径实测(重叠对 + 退化区间,序列见切片 01 验证命令);`alembic check` 干净(预期天然干净,见 §4.6)。
- **覆盖率目标**:不低于项目基线;新增映射 helper 分支全覆盖(一正一反)。
- **回归基线**:`./init.sh full` 全量(当前 1038 passed)零回归是硬门槛。

## 6. 实施切片(to-tickets 产出,EP2 单回环)

### 切片依赖图

```
01 DB 层结构性兜底(迁移:预检+btree_gist+EXCLUDE + PG 门控测试 + CI wiring)──→ 02 服务层 400 映射 + 术语/文档 + 全量验证 + feature 收尾(末切片)
```

> 顺序理由:结构先行——没有约束,映射是捕获不到任何东西的死代码;切片 01 落地后竞态已被 DB 拦下(裸 IntegrityError → 500,严格优于静默双订落库),切片 02 把罕见兜底路径的错误体验收口到 400 并收官。切片 01 自含迁移正确性验证(预检/upgrade/check + PG 测试),可独立交付。

### 切片 01 — DB 层结构性兜底:EXCLUDE 约束迁移 + 脏数据预检 + PG 门控测试 + CI ✅(PR #167,merge 596dccd,CI 4/4 绿,2026-08-15)

**What it delivers**:并发(或直插)两条 active 预约重叠落在同一设备上时,数据库结构性拒绝第二条——`[10,12)` 已提交则 `[11,13)` INSERT/UPDATE 抛 exclusion violation;back-to-back 不误伤;cancelled/done/no_show 让出的时段立即可复用;生产库若有历史双订,迁移拒迁并列出重叠对数量;该防护有 PG 门控测试常驻 CI Migrations job。

**Blocked by**: 无(frontier,可立即开工)

**文件清单**:`alembic/versions/`(新迁移,接 `b3f7a2c91d4e`)+ `app/models/booking.py`(docstring)+ `tests/test_booking_overlap_pg.py`(新)+ 同源防漂移小测试(SQLite 常驻)+ `.github/workflows/ci.yml`(migrations job +1 step;`alembic/env.py` **不预期改动**,见 §4.6 兜底预案)

**验证命令**:`alembic upgrade head && alembic check`(docker PG)+ 预检拒迁实测序列(`alembic downgrade b3f7a2c91d4e` → 手插一对重叠 active bookings + 一条退化区间行 → `alembic upgrade head` 断言失败且报文含数量 → 清理 → upgrade 成功)+ `DATABASE_URL=postgresql+psycopg://aap:aap_secret@localhost:5432/aap pytest tests/test_booking_overlap_pg.py -v` + `./init.sh`(SQLite 冒烟)

**Acceptance criteria**:

- [x] 新迁移(文件头 docstring 对齐 `b3f7a2c91d4e` 先例,Revises: b3f7a2c91d4e + 指向本 plan):①预检拒迁**两条并列**(active 重叠对 + 退化区间 `scheduled_end_at <= scheduled_start_at`,任一 > 0 → RuntimeError 带数量与处置指引;按上述序列实测验证)②`bind.dialect.name != 'sqlite'` guard 内 `CREATE EXTENSION IF NOT EXISTS btree_gist` + ADD CONSTRAINT `excl_bookings_active_no_overlap`(DDL 按 §4.6,`'[)'` 边界 + 排除态谓词与 `_ACTIVE_STATES` 逐字一致)③downgrade `DROP CONSTRAINT IF EXISTS excl_bookings_active_no_overlap`,downgrade 后经 pg_catalog 确认约束确已消失(防 `IF EXISTS` 错名静默 no-op);btree_gist 扩展保留,注释声明
- [x] `tests/test_booking_overlap_pg.py`:skipif 非 PG;§4.6 用例 ①-⑤ 全落地(并发恰一成功 / back-to-back 双成功 / cancelled+done+no_show 排除 / update 改期被拒 / NULL device 不冲突);种子带唯一标记 + finally 清理
- [x] `.github/workflows/ci.yml` migrations job 加 step 跑 PG 门控测试(在 `alembic upgrade` + `alembic check` 之后;env 对齐 backend job 的测试变量);CI 实测绿
- [x] `alembic upgrade head && alembic check` 干净(预期天然干净,见 §4.6 核实结论;**不预期需要 env.py 改动**,仅当未来升级后实测报 drift 才落地 include_object 兜底)
- [x] 同源防漂移测试(SQLite 常驻):读迁移源码断言约束谓词与预检 SQL 的状态清单与 `_ACTIVE_STATES` 一致
- [x] `app/models/booking.py` docstring 更新(考古结论 + 约束由迁移持有的原因 + 状态清单同源互指注释);`__table_args__`/列零改动
- [x] `./init.sh` 冒烟绿;全量 pytest 零回归(SQLite 链对约束零感知)

**切片 01 完成证据(2026-08-15,Session 214)**:commits `4ced028`(实施)+ `50eaa67`(双轴审查回写),PR #167(merge `596dccd`,CI 4/4 绿:Migrations 46s 含新 step「Postgres-gated booking-overlap tests: success」/ Backend 7m23s / E2E 1m45s / Frontend 34s)。实测:迁移 `9a8b7c6d5e4f`(预检两条经 `_ACTIVE_STATES_SQL` 常量单源插值 4 处 SQL 站点)/ TDD 红证(约束缺失时用例①④ DID NOT RAISE)/ `alembic upgrade head && alembic check` 干净(反射预判实证,env.py 零改动)/ PG 门控 7/7(①并发恰一成功含 sqlstate 23P01 断言 + 事后计数 / ②back-to-back / ③cancelled+done+no_show 三态 parametrize / ④UPDATE 改期被拒 / ⑤NULL device 含计数断言)/ 拒迁实测(手插 1 重叠对 + 1 退化区间 → exit 1 报文含两数量+处置指引,版本未动;清理后 upgrade 成功)/ downgrade 后 pg_catalog 确认约束消失(count=0)/ `./init.sh full` **1040 passed**(基线 1038 + 新增 2 防漂移)+ 7 skipped 零回归。审查:Standards 0🔴/3🟡(1 修:PG 测试第四处手写状态清单 → import `_ACTIVE_STATES` expanding bindparam;2 留痕:防漂移正则防呆不防恶、`_EXPECTED_CONSTANT_SITES=4` 有意 tripwire)/ Spec 7/7 无越界(plan §4.6 本地复跑端口笔误 5432→5433 已回写)。

### 切片 02 — 服务层 400 映射 + 判别单测 + 术语/文档同步 + feature 收尾(末切片)

**What it delivers**:竞态漏网被 DB 兜底拦下时,客户端收到与现役冲突同款的 400 `{"detail": "设备时段冲突:该时段已被并发预约占用"}`(而非裸 500);其他 IntegrityError 不被吞;术语与数据库文档同步;全量验证收官。

**Blocked by**: 切片 01

**文件清单**:`app/services/booking_service.py`(create/update 两路径捕获映射 + 判别 helper)+ 判别单测(SQLite 常驻,挂靠 `tests/test_bookings_api.py`)+ `tests/test_booking_overlap_pg.py`(补用例 ⑥)+ `CONTEXT.md`(术语)+ `项目指南/02-后端架构/03-数据库与ORM.md`(PG-only 约束范式段)

**验证命令**:`pytest tests/test_bookings_api.py -q`(含新单测零回归)+ `./init.sh full` + `alembic upgrade head && alembic check` + PG 门控测试复跑(含用例 ⑥)

**Acceptance criteria**:

- [ ] `booking_service` create 路径(`repo.add` 包捕获)与 update 路径(`db.flush` 包捕获)双双映射:sqlstate 23P01 → rollback + `BizError("设备时段冲突:该时段已被并发预约占用")`(400,不带 id,D8);判别 helper 为可直测函数
- [ ] 判别单测(SQLite 常驻,挂靠 `tests/test_bookings_api.py`):23P01 → BizError;23505(唯一违规)→ re-raise;无 sqlstate 属性 → re-raise
- [ ] PG 门控用例 ⑥(服务路径竞态全链证明):conn1 未提交 + 另一 session `BookingService.create` → 断言 BizError 而非 IntegrityError——「竞态 → 400」在真 PG 端到端证明
- [ ] `CONTEXT.md` 术语:「占坑态(Slot-Holding States)」= pending/confirmed/in_service 三态,应用层 `_ACTIVE_STATES` 与 DB EXCLUDE 谓词同源;cancelled/done/no_show 即时释放
- [ ] `项目指南/02-后端架构/03-数据库与ORM.md` 补 PG-only 约束范式段:EXCLUDE 形态、迁移持有/模型不声明的取舍、SQLite 测试链的关系(EP3 落地时执行)
- [ ] `./init.sh full` 全绿零回归(基线 1038)+ alembic 干净 + PG 门控测试绿 + 前端 build 零改动确认
- [ ] feature 收尾仪式(three-tier §4 第 1-8 步):feature_list.json `not_started → passing` + evidence + sync-active + progress.md + 文档影响评估 + 依赖解锁扫描 + 分支清理

## 7. 对抗式审查段(复杂任务:涉及数据迁移 → 已执行)

**审查方式**:单模型双轴(Standards + Spec)并行,2026-08-15 执行;产出 Standards 2🔴/2🟡/4🟢 + Spec 1🔴/4🟡/3🟢(Spec 轴含对实装依赖版本的源码级核实:psycopg 3.2.3 sqlstate 属性、SQLAlchemy 2.0.36 + alembic 1.14.0 的约束背书索引剔除机制、种子链必填列、settings 导入链),全部回写 §0 变更摘要,v1 → v2。

## 8. Out of Scope

- ❌ advisory lock / 部分唯一索引形态(D1 拍板 EXCLUDE,前两者否决)
- ❌ 409 Conflict(D3 拍板同款 400,延续 device-booking D1)
- ❌ 移除/降级应用层 `_assert_no_overlap`(D7 保留双防线)
- ❌ find_overlap 查询计划优化 / 用 EXCLUDE 索引服务读路径(顺带收益不承诺,不越界)
- ❌ `CONCURRENTLY` 无锁加约束路径(平台未上生产无存量规模;将来大表加约束时再评估——注意 PG 的 `ADD CONSTRAINT EXCLUDE` 不支持 CONCURRENTLY,届时需改走 validation-scan/停机窗口等方案;被阻塞 INSERT 无默认超时,依赖应用事务毫秒级收口,长事务场景可评估会话级 `lock_timeout`)
- ❌ 其他表推广排他约束(将来需求独立立项)
- ❌ 前端任何改动
- ❌ booking 状态机扩展(device-poweron 域)/ 未用占位态(confirmed)的语义调整(D2 对齐现状)

## 9. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| 未来升级 SQLAlchemy/alembic 后 EXCLUDE 背书索引反射行为变化 → `alembic check` 幽灵 drift | 低 | Spec 轴已核实当前版本(SQLAlchemy 2.0.36 + alembic 1.14.0)`duplicates_constraint` 剔除机制下 check 天然干净;env.py `include_object` 兜底方案已预设计(§4.6),仅实测报 drift 才落地 |
| btree_gist 扩展不可用(非标准 PG 镜像部署) | 低 | pgvector/pg16 = 官方 postgres + contrib 自带;CI 两 job 与本地 docker 同源;`CREATE EXTENSION IF NOT EXISTS` 幂等 |
| 预检 SQL / 约束谓词 / `_ACTIVE_STATES` 三处状态清单未来漂移 | 中 | 同源防漂移测试进 CI(切片 01 AC:读迁移源码断言字面量一致)+ 模型 docstring 与迁移注释互指;将来改状态机时该测试红灯拦截 |
| psycopg 异常 sqlstate 属性形态差异(psycopg3) | 低 | 判别 helper 用 getattr 宽取,缺失 → re-raise(安全侧);单测锁定 23P01 正例 |
| ADD CONSTRAINT EXCLUDE 建索引锁表(大存量表) | 低 | 平台未上生产、bookings 量级小,一次 ALTER 接受;Out of Scope 记录将来大表路径 |
| 并发 INSERT 阻塞等待对方事务(commit 前)造成延迟尖峰 | 低 | 正常并发窗口毫秒级;排他等待与唯一索引同机制,PG 标准行为 |
| PG 门控测试在 Migrations job 引入 app settings 导入失败 | 低 | CI step env 对齐 backend job(JWT_SECRET 等);测试文件自身只 import models/SQLAlchemy,不 import app 装配 |
| 既有 bookings 测试受影响 | 低 | 模型/应用层检查零改动(SQLite 链对约束零感知);`./init.sh full` 零回归硬门槛 |

## 10. 验收标准(同步 feature_list.json verification)

1. **并发竞态回归测试**(PG 门控,常驻 CI Migrations job):重叠双插恰一成功、一 IntegrityError 被 DB 拒(非应用层 if 拦截);update 改期撞重叠同样被拒(切片 01);**服务路径竞态全链**:真 PG 上应用层检查被并发绕过后,DB 兜底命中映射为同款 400(用例 ⑥,切片 02)
2. **排除态语义测试**:cancelled/done/no_show 时段可被重新预约——PG 约束级(切片 01)+ 既有应用层重订测试零回归(切片 02)
3. **存量数据迁移**:预检拒迁实测(重叠对 + 退化区间 → RuntimeError 带数量;清干净 → 通过);`alembic upgrade/downgrade`(确认约束消失)+ `alembic check` 干净(切片 01)
4. **DB 兜底命中 → 同款 400**:sqlstate 23P01 判别单测常驻 SQLite 套件;其他 IntegrityError 不被吞(切片 02)
5. `./init.sh full` 全量零回归(基线 1038 passed)(切片 02)

## 11. 不越界声明

本次改动**只**涉及:bookings 表加 EXCLUDE 排他约束(迁移持有:btree_gist 扩展 + 预检拒迁 + DDL)、模型 docstring 考古更新、booking_service create/update 两路径的 IntegrityError→BizError 映射、PG 门控测试文件与 CI migrations job 一步、判别单测、CONTEXT.md 术语与数据库文档一段。

**不**触碰:应用层 `find_overlap`/`_assert_no_overlap` 逻辑 / booking 状态机与任何端点行为语义 / 任何其他表的约束与索引 / 计费钱包(R3 域)/ 审计埋点(R4 域)/ 配置守卫(R5 域)/ 前端 / 迁移链既有版本(只追加新版本)。
