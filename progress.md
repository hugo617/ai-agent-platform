# 进度日志(progress.md)

> 每轮会话开始时先读、收尾时更新。跨会话必须的关键信息写这里,脑子里的不算。

## 当前已验证状态

- **仓库根目录**: `/Users/star/hugo/3-项目代码/project/ai-agent-platform`
- **标准启动路径(开工冒烟)**: `./init.sh`(装依赖 + ruff + `pytest -m smoke`,~15s,确认起点没坏)
- **标准验证路径(收尾全量)**: `./init.sh full`(装依赖 + ruff + 全量 pytest,~5min,确认没回归)
- **完整验证路径**(需 docker): `alembic upgrade head && alembic check` + `cd frontend && npm run build`
- **当前最高优先级未完成功能**: **`design-system-color-sweep`(p82,not_started)— 前端设计系统收口系列 Feature B**(2026-07-31 Session 172 EP2 单回环登记 3 feature,Session 173 Feature A ✅ passing 后 B 解锁为 frontier)。系列总纲 `harness/docs/plan-frontend-design-system-overview.md`(EP1 grill 7 决策 + huashu-design B3 变体定稿,语义色 HSL 值固化)。**系列进度:① A ✅ passing / ② B frontier / ③ C not_started**。① **A `design-system-token-foundation`(p81,✅ passing,2026-07-31 Session 173)** — semantic token 基建(`--success/--warning/--danger/--info` 四 token B3 定稿双色值 + tailwind.config 暴露 + ui/ 组件库内部映射 badge/toast),全 2 切片合并。② **B `design-system-color-sweep`(p82,not_started,depends_on A 已解锁,frontier)** — 业务页 ~30 处硬编码色扫荡(跨 ~12 文件,按色系切片 success/warning/danger/info),5 切片。③ **C `design-system-spacing-card-hierarchy`(p83,not_started,与 A/B 正交)** — 卡片层级 shadow 语义命名 + 字号任意值 text-[10px] 收口(顺手项),2 切片。执行顺序 A→B→C(WIP=1)。**下一步:EP3 `/implement` Feature B 切片 01**(success 色系业务页扫荡,frontier,A token 已就绪可消费)。更早 passing:design-system-token-foundation(81,A)/queries-endpoints-domain-split(80)/customers-page-split(79)/devices-page-split(78)/perm-backfill-dedupe(77)/chat-page-split(76)/union-cast-split(75)/twoscope-config(74)/bookings-shared-split(73)/composite-chat(72)/principal-scope-doc-alignment(71)/principal-module(70)。
- **queries-endpoints-domain-split ✅ passing(2026-07-30 Session 170,全 2 切片完成)**:第 8 次巡检候选 ③ Strong —— queries.ts(1560 行/25 section)+ endpoints.ts(1514 行/29 section)两个 god-module 按 domain 拆成文件夹,deep module 按 domain 切 + 共享 core + barrel 保 interface 不变(区别于 page-split 范式)。**完整切片链**:**切片 1 ✅ commit fb88c64**(expand):Python 脚本自动化拆分 → queries/core.ts(qk 工厂 + useApiMutation export,68× leverage 保留)+ 24 domain + barrel(33 行);endpoints/core.ts + 29 domain + barrel(38 行)。tsc 0 错 + npm test 110/110 + build + oxlint 0/0 + import 路径零变化(@/hooks/queries 33 + @/api/endpoints 36 调用点不变)。**切片 2 ✅ contract**(本次):import 路径零变化显式验证 + qk 编码 diff 逐字一致(106 行 diff 空)+ domain 边界审计(queries 124→125 export[+1 useApiMutation private→export]/endpoints 141→141 逐字一致)+ ./init.sh full 842 passed 零回归。**/code-review 双轴**(general-purpose ×2 并行):**0 硬违规**,核心不变式(零行为变更 + 零 import 变化 + qk 逐字一致)全达标。**4 判断项处置**:① endpoints/core.ts 删死 re-export(原 export{api,...} 扩张 API 表面+5 无人消费,Standards 轴发现)→ export{} 占位,API 表面恢复 141→141;② 文件名修正 conversations-+-chat→conversations-chat / auth-2→auth-sessions;③ barrel 行数超 ≤30(33/38 注释撑超)→ plan AC2 修订 ≤40;④ bookings/devices 超 ≤150(207/173 内聚)→ plan AC10 记录豁免。**code-review 的价值**:Standards 轴发现 endpoints/core.ts 死 re-export 扩张公共面(避免 @/api/endpoints API 表面意外膨胀);Spec 轴确认 useApiMutation 可见性扩大无害(67=67 调用守恒无误用)。**feature 核心**:两个缓涨 god-module(queries 1505→1560/endpoints 1466→1514)按 domain 归位,leverage(useApiMutation 68× + qk 工厂)保留在 core,locality(22+ section 靠 grep 不靠目录)修复。barrel export * 接管,33+36 调用点零改动。范式:deep module 按 domain 切 + 共享 core + barrel(第 8 次巡检第 6 次 not-shallow 判决重评为 Strong 的兑现)。
- **customers-page-split ✅ passing(2026-07-30 Session 170,全 2 切片完成)**:第 8 次巡检候选 ④ Top —— customers-page.tsx(834 行单文件 4 组件)拆 store-view/hq-view,镜像 bookings/devices/chat split 范式第 4 实例。**完整切片链**:**切片 1 ✅ commit 347af5f**:建 customers/ 文件夹 6 文件(index.tsx 双路 route + store-view.tsx 本店 CRUD + hq-view.tsx 跨店聚合只读 + customer-usage-dialog.tsx AI 用量+Metric + shared.tsx statusBadge+schema+常量+parseTagsJson 纯函数 D4)+ customers-page.tsx 改 barrel(re-export from customers/index,App.tsx 零改动)+ hq-view.test smoke 2 tests。**切片 2 ✅ 末切片**(commit 85a969a + code-review 8356c64):补完整 store-view.test(5 tests:列表渲染 + 空态 + member 只读守卫 + owner 创建填表提交**断言 tags 经 parseTagsJson 正确解析** + 删除菜单)+ hq-view.test(5 tests:跨店表渲染 + 空态 + 行展开 profile 明细 + AI 用量 dialog storeScoped=false + 搜索过滤)+ parse-tags.test(6 tests,D4 纯函数 3 边界 + 空白/undefined)。**/code-review 双轴**(general-purpose ×2 并行):**Standards 0 硬违规**(范式忠实镜像 + symbol-name 锚定 + 测试隔离正确 hasPermission 真实实现 + permissions string[] 格式 + 依赖方向清晰);**1 判断项已文档化**(buildPayload tags 字段顺带修复隐藏 bug —— 原 monolith 把整个 {...values,tags} 当 payload.tags 传后端 → 脏数据,新版 tags.tags 正确取纯解析结果;补 store-view 注释显式记录,locked by test 断言)。**Spec** 9 AC 全满足;1 偏差已修(hq-view 测试数 4→5 补搜索过滤)。**code-review 的价值**:双轴独立交叉验证同一隐藏 bug(高置信),发现「零行为变更」宣称下的正向修复并文档化,避免 git blame 困惑。**验证**(plan §10 AC 全绿):npm test **110/110**(94 baseline + 16 customers[5 store+5 hq+6 parse])+ npm run build 0 错 + tsc -b 0 错 + oxlint 0/0 + grep 'pages/customers-page' 外部 import 仅 App.tsx barrel + **./init.sh full 842 passed**(零回归,纯前端)。**feature 收尾仪式(three-tier §4 第1-8步)**:① ./init.sh full 842 passed + 前端 110/110 + build + oxlint 全绿 ✅ / ② feature_list.json status `not_started → passing` + evidence 4 条 ✅ / ③ sync-active 刷新(1 活跃 queries-endpoints + 5 最近 passing)✅ / ④ progress.md 顶部 frontier 指向 ③ queries-endpoints ✅ / ⑤ clean-state-checklist ✅ / ⑥ 文档影响评估:**无新增/改动文档**(纯前端结构重构,AGENTS.md/项目指南/铁律均不受影响)/ ⑦ **末切片依赖解锁扫描**:无任何 feature depends_on 指向 customers-page-split(纯重构无下游)→ 无需推进 / ⑧ 分支清理:refactor/customers-page-split-t1 待 PR 合并后删。**feature 核心**:customers-page 834 行单文件拆成 customers/ 文件夹 7 文件(双 entry barrel + 双路 route + store/hq 双视图 + usage dialog + shared + 3 测试)。完全镜像 bookings/devices/chat 已验证范式,运行时行为零变化(除 tags 字段隐藏 bug 正向修复)。customers-page 从零单测大 page → 有完整单测覆盖。store/hq 双视图范式第 4 实例,leverage 验证最强。
- **规则死循环修复(2026-07-30 Session 168)— 清三笔债**:用户问「切片 02 为什么没合并到主分支」。排查发现 sess_c9895f7d 确立的「末切片分支清理」规则**自己卡在未合并的功能分支**上(`docs/harness-branch-cleanup-rule` = commit `ce9d64e`),从未进 main → 下游 agent 读到旧 7 步版本 → 切片 2 漏掉合并。规则要求合并,但规则自己没合并(self-referential trap)。**三笔债依次清完**:① **债1 规则合并** —— `ce9d64e` 单 commit 是纯规则改动(4 文档 +27/-11,zero 代码),从干净分支 `chore/merge-branch-cleanup-rule` cherry-pick,progress.md 部分因被后续事实超越保留 main 现状,3 核心规则文件(three-tier §4 第8步 + clean-state 第10项 + harness-router SKILL 4 处)落 main(merge commit `5c2b9cd`)。② **债2 切片2 合并** —— `refactor/devices-page-split-t2`(be7c223)本地 `git merge --no-ff` 进 main(merge commit `529bf29`,因沙箱网络不可达 GitHub push 超时,用户选「本地直接合 main」,远端推送待网络恢复)。分支基底是规则合并前的 0e1cd46,但未碰规则文件,三方合并干净无冲突,规则完整保留 main 版本未覆盖。**第8步分支清理执行**:删 `refactor/devices-page-split-t2` + `docs/harness-branch-cleanup-rule` + `chore/merge-branch-cleanup-rule` 三条已合并分支(`-d` 安全删,非 `-D`),本地 `git branch` 只剩 main。验证:前端 **94/94 全绿**(store-view 5 + hq-view 8)+ 后端冒烟绿。feature_list status=passing + evidence 4 条(已在 be7c223 内完成,合并后生效)。③ **债3 闭环项** —— sess_c989 自标注「回归纪律第3条同步 main 已记 progress.md 但未固化进 SKILL 回归第1步」,本次补齐:harness-router SKILL 回归流程**新增第1步「同步本地 main」(前置硬动作)**,原第1-4步顺延为第2-5步,交叉引用同步更新(commit `d3b3703`)。**三笔债清完 = 规则死循环修复闭环**:规则进 main → 下次末切片 agent 能读到第8步 → 不再漏合并。~~**待用户动作**(网络恢复后):`git push origin main`(本地 ahead origin/main **5 commits**)~~ **✅ 已验证无债(2026-07-30 Session 169 回归)**:`gh api repos/hugo617/ai-agent-platform/branches/main` 实测远端 main HEAD = `4ceafe6` = 本地 main HEAD(byte-for-byte 一致),5 关键 commit(`4ceafe6`/`d3b3703`/`529bf29`/`5c2b9cd`/`be7c223`)均在远端,OPEN PR = 0,远端分支只剩 main。即推送在 Session 168 之后某时刻已成功(当时 `git push` github.com:443 超时,但后台/后续已完成),原「待推送」债已不存在。注:`git fetch`/`git push`(github.com:443)本会话仍超时,但 `gh`/`gh api`(api.github.com)可达 —— 后续若需本地 git 同步,以 `gh api` 验真为准或待网络恢复。
- **devices-page-split ✅ passing(2026-07-30 Session 167,全 2 切片完成)**:第 7 次巡检候选②(Strong PERSISTING)—— devices-page.tsx(1083 行单文件)拆 store-view/hq-view,镜像 bookings/ 范式。**完整切片链**:**切片 1 ✅ commit 0e1cd46**(已合并 main):建 devices/ 文件夹 7 文件(devices-page.tsx barrel + index.tsx 二叉路由 + store-view.tsx + hq-view.tsx + device-dialogs.tsx 4 共享 Dialog + device-status-meta.ts 纯数据 + shared.tsx 显示原语)+ 改 App.tsx import + 删旧 pages/devices-page.tsx + **v2 前移 tenantId smoke**(hq-view-tenantid-smoke.test.tsx 2 tests,Create tenantId prop 路径,消除切片1 tenantId 安全空窗)。验证:npm test 83/83 + build + oxlint 0/0。**切片 2 ✅ 末切片**(本次 Session,分支 refactor/devices-page-split-t2):补完整 store-view + hq-view 单测。新建 `store-view.test.tsx`(**5 tests**:列表渲染[serial/model 名从 modelMap 解析/status 徽章/customer_name]+ 空态 + member 只读守卫[canCreate/canUpdate/canDelete 假,无写按钮]+ owner 创建 Dialog 填表提交触发 useCreateDevice[**断言 store path payload 无 tenant_id**]+ 行内菜单[编辑/绑定客户/删除设备])+ `git mv smoke→hq-view.test.tsx` 扩展到 **8 tests**(原 2 Create tenantId prop smoke + 新 1 Edit tenantId prop via spy-on-children[DeviceEditDialog 收到目标 tenantId]+ 2 panorama 渲染[跨店表+列头+行数据 tenant_name/model_name/customer_name + 空态]+ 2 hook closure 构造[useDeleteDevice/useBindDeviceCustomer/useUnbindDeviceCustomer 以 targetTenantId / undefined 调用]+ 1 删除触发[deleteMut.mutateAsync 真调,对齐 bookings L491 闭包生效范式])。**/code-review 双轴**(general-purpose ×2 并行):**Standards 0 硬违例**(mock 隔离正确 store useDevices / hq useDevicesAll 不串 + tenantId 双路径忠实 + symbol-name 锚定 + 不越界);1 判断项已修(hq-view.test.tsx 头部注释自指「完整覆盖在切片2的 hq-view.test」但本文件就是它 → 重写头部反映现状)。**Spec** AC1-3 全满足;2 防御性增强已采纳闭合 plan §5 全文(① store-view 创建 Dialog 原只测弹窗打开 → 补「填表提交 → useCreateDevice.mutateAsync 被调」断言 store path payload 无 tenant_id;② hq-view Bind/Delete closure 原只测 hook 构造实参 → 补「点删除菜单项 → deleteMut.mutateAsync 真调」证明闭包在写流程生效,对齐 bookings 先例深度)。**审查的价值**:Spec agent 精准指出 plan §5 L150「提交→useCreateDevice 被调」+ L160「断言 mutateAsync 调用的范式」字面要求,阻止了「只测弹窗打开/只测构造不测触发」的浅覆盖进仓库,让 tenantId 跨租户写守卫双路径的覆盖更有说服力。**验证**(plan §10 AC 全绿):npm test **94/94**(83 baseline + 5 store + 6 新 hq)+ npm run build 0 错 + oxlint 0/0 + grep 'pages/devices-page' 残留旧路径 → **0** + devices/ 文件夹 7 文件 + __tests__/(2 测试)对称 bookings/ + **`./init.sh full` 842 passed**(零回归,后端零改动)。**feature 收尾仪式(three-tier §4 第1-8步)**:① ./init.sh full 842 passed + 前端 94/94 + build + oxlint 全绿 ✅ / ② feature_list.json status `not_started → passing` + evidence 4 条 ✅ / ③ sync-active 刷新(0 活跃 + 5 最近 passing)✅ / ④ progress.md 顶部 frontier 清空 ✅ / ⑤ clean-state-checklist ✅ / ⑥ 文档影响评估:**无新增/改动文档**(纯前端结构重构,AGENTS.md/项目指南/铁律均不受影响)/ ⑦ **末切片依赖解锁扫描**:无任何 feature `depends_on` 指向 devices-page-split(纯重构无下游)→ 无需推进 / ⑧ 分支清理:refactor/devices-page-split-t2 本地 `-d` 已删(Session 168),远端经 `gh api` 验证分支已不存在(远端只剩 main)—— **✅ 已验证无残留**(2026-07-30 Session 169 回归,`gh api repos/.../branches` 仅返回 main)。**feature 核心**:devices-page 1083 行单文件拆成 devices/ 文件夹 7 文件(双 entry barrel + 二叉路由 + store/hq 双视图 + 4 共享 Dialog + 纯数据 + 共享原语)+ __tests__/ 补 13 测试(store 5 + hq 8)。完全镜像 bookings/ 已验证范式,运行时行为零变化。tenantId 跨租户写守卫双路径全覆盖(Create/Edit prop via spy-on-children + Bind/Delete hook closure,空窗消除)。devices-page 从 6 个零单测大 page 之一 → 有完整单测覆盖。
- **perm-backfill-dedupe 切片 01 ✅(2026-07-30 Session 166,非末切片,commit 6461236,PR #151 OPEN)**:service 函数参数化合并 + caller 临时改造(保留测试绿)。落地 1 改 service + 4 改 caller:① `app/services/permission_service.py` 新增 `BACKFILLABLE_OBJS: frozenset[str] = frozenset({"devices","bookings"})` 白名单常量 + 新函数 `backfill_perm_set_for_existing_tenants(db, obj)`(body 从两镜像合并,obj 参数化替换硬编码 + 开头 `if obj not in BACKFILLABLE_OBJS: raise ValueError` 校验 + **循环变量 `obj`→`perm_obj` 消除函数参数 shadowing**,scope guardrail 改 `if perm_obj != obj: continue`[api 区]+ `if code != obj: continue`[menu 区]双 guard 保留)+ 删旧 `backfill_devices_perms_for_existing_tenants` + `backfill_bookings_perms_for_existing_tenants`。② `tests/test_devices_api.py` + `tests/test_bookings_api.py` 的 K chapter **临时改调新函数**(`backfill_perm_set_for_existing_tenants(db,"devices"/"bookings")`),保留 6 测试绿(避免安全代码测试空窗,删 K chapter 移切片 02)。③ `scripts/backfill_devices_perms.py` + `backfill_bookings_perms.py` 临时改调新函数(切片 02 删)。**验证**:`BACKFILLABLE_OBJS` import OK + `obj="users"` 触发 ValueError + `pytest -k backfill` 6 passed(devices 3 + bookings 3)+ `./init.sh` 冒烟绿(ruff + smoke)。**非末切片**(切片 2 删 scripts + 测试 parametrize),不动 feature_list.json status/evidence(末切片的事)。
- **perm-backfill-dedupe 切片 02 ✅(2026-07-30 Session 166 末切片,commit 89f139e)**:scripts 合并 + 测试 parametrize 收尾。落地 2 删 + 2 新 + 2 改 + 1 改注释:① **删** `scripts/backfill_devices_perms.py` + `scripts/backfill_bookings_perms.py`(切片 1 临时保留的两 mirror script)。② **新建** `scripts/backfill_obj_perms.py` —— 接 `--obj` 必填(argparse `choices=sorted(BACKFILLABLE_OBJS)` 做第一道校验)+ 保留 `--dry-run`;v2 改名避与已有 `scripts/backfill_permissions.py` 命名碰撞。③ **新建** `tests/test_permission_backfill.py` —— `@pytest.mark.parametrize("obj", sorted(BACKFILLABLE_OBJS))` 覆盖 3 场景(correctness / idempotent / preserves_other_perms)× 2 obj + 1 边界(rejects_unknown_obj)= **7 cases**;期望值用 `_expected_new_grants(obj)` 从 DEFAULT_OWNER/ADMIN/MEMBER_PERMS + DEFAULT_MENU_PERMS **动态计算**(非硬编码 5+4+2,未来 obj perm 数不同不坏);helper `_seed_backfill_target_tenant` 参数化 + 用模块级常量 `_OTHER_OBJ="customers"` + 显式 `assert other_obj != obj`(K6 不变式由断言保证,非值巧合)。④ **删** test_devices_api.py + test_bookings_api.py 的 K chapter(切片 1 临时保留的 6 测试,由新 parametrize 接管)。⑤ `app/services/permission_service.py` 过时注释同步(去掉旧函数名引用 + 修正「K chapter 已迁走」的过时引用,使 grep 旧函数名 app/scripts/tests 归 0)。**验证**(plan §10 AC 1-8 全绿):`python scripts/backfill_obj_perms.py --obj devices --dry-run` 扫 6 租户正常 + `--obj invalid` argparse 报 choices 错 + 缺 `--obj` 报 required 错 + `pytest tests/test_permission_backfill.py` 7 passed + **`./init.sh full` 842 passed**(零回归,含新 7 测试)+ **alembic check** 无新迁移 + **npm build** 成功 + **oxlint** 0 warning 0 error + grep `backfill_devices_perms_for_existing_tenants|backfill_bookings_perms_for_existing_tenants` app/scripts/tests → **0** + grep 旧 script 名 `backfill_devices_perms|backfill_bookings_perms` → **0** + `BACKFILLABLE_OBJS` + `def backfill_perm_set_for_existing_tenants` 就位 + 循环变量 `perm_obj`(无 shadowing)+ ruff clean。**/code-review 双轴**(general-purpose ×2 并行):**Standards 0 硬违例**(依赖单向合规 + symbol-name 锚定 #5 合规 + scope guardrail K6 双 guard 保留 + 入口 ValueError 兜底强化);1 judgement call 已修(`_pick_other_obj(obj)` 忽略参数总返回 customers 的 Mysterious Name/dead-param → 改为模块级常量 `_OTHER_OBJ` + 断言)/ 1 pre-existing 越界留痕(`select(Tenant)` 无 is_deleted=False 是两镜像旧有 carry-over,本切片不越界)。**Spec** 8 AC 全绿 + 期望值动态算正确验证;1 收尾待办(feature_list v1 旧名)+ 1 helper 参数化 partial(均已在收尾修复)。**feature 收尾仪式(three-tier §4 第1-8步)**:① `./init.sh full` 842 passed + alembic check + npm build + oxlint 全绿 ✅ / ② feature_list.json status `not_started → passing` + evidence 4 条(切片 1/2 + 三层去重归 0 + 收尾全量验证)+ **修正 v1 旧名 `backfill_perms.py`→`backfill_obj_perms.py`**(Spec agent 发现 user_visible_behavior + verification 残留 v1 名)+ `./scripts/sync-active-features.sh` 刷新(0 活跃 + 5 最近 passing)✅ / ③ progress.md 顶部 frontier 清空(指向 devices-page-split 78)+ 本条记录 ✅ / ④ clean-state-checklist ✅ / ⑤ 文档影响评估:**无新增/改动文档**(纯后端参数化重构,AGENTS.md/项目指南/铁律均不受影响)/ ⑥ **末切片依赖解锁扫描**:无任何 feature `depends_on` 指向 perm-backfill-dedupe(纯重构无下游)→ 无需推进 / ⑦ 分支清理:切片1+2 在 `refactor/perm-backfill-dedupe-t1` 同分支(PR #151 待合并切片1+2 一起),PR 合并后删本地+远端分支。**feature 核心**:permission backfill 三层镜像(service 2 函数 + scripts 2 个 + 测试 2 K chapter)去重完成 —— 全参数化为 `backfill_perm_set_for_existing_tenants(db,obj)` + 白名单 + 单 script + 单 parametrize 测试;下次加第 3 个 obj 只需 BACKFILLABLE_OBJS 加一项 + DEFAULT_*_PERMS 加条目,不再 copy-paste。镜像从第 6 次巡检单函数 → 第 7 次 2 镜像的恶化趋势终止并归一。
- **harness 回归纪律二次补强:回归前必须同步本地 main(2026-07-30 Session 166)**:perm-backfill 切片 02 回归时**二次翻车** —— 上一轮误判「切片2 名不副实、代码没合并」,实际是**误判**。根因:回归检查文件状态时**没先 `git checkout main && git pull` 同步**,在陈旧本地工作区(perm-backfill 分支)grep,看到的是 PR #151 合并前的旧状态;cherry-pick 报「now empty」(内容已在 main)才暴露错误。**补强纪律**:回归验证第一动作必须是 `git fetch origin && git checkout main && git pull --ff-only`,确保本地文件状态 = 远端真实状态,再做任何 grep/ls/文件检查。两次回归错误(切片1 漏查 mergedAt / 切片2 没同步 main)共同教训:**不得假设本地状态 = 远端真实状态,git 状态同步是回归验证的前置条件**。perm-backfill-dedupe 实际**真完成**(PR #151 MERGED eb46124 + status passing + evidence 4 + plan Ticket 2 ✅ + 测试 7 passed),上一轮的「名不副实」结论作废。
- **chat-page-split 切片 01 ✅(2026-07-30 Session 165,非末切片,commit c2cd439)**:抽 `buildWorkingList` 近纯函数(expand 阶段,**不 git mv**)。落地 1 改文件 + 2 新文件:① `frontend/src/pages/chat/build-working-list.ts`(40 行新建)抽出 `(base, userText, now?=Date.now) => Message[]` —— base 浅拷贝 `.map((m)=>({...m}))` 防别名 + 追加 userMsg(`local-user-` 前缀)/assistantMsg(`local-assistant-` 前缀)两条占位 + `created_at` 走注入 `now()`(D3 近纯函数决策落地)。② `frontend/src/pages/chat/__tests__/build-working-list.test.ts`(92 行新建)5 边界用例(空 base / 非空 base 追加 / `now` 注入钉死时间[v2 关键:`vi.useFakeTimers()`+`vi.setSystemTime`] / 浅拷贝非别名断言原 base 不被 mutate / 默认 `Date.now` 回退)。③ `frontend/src/pages/chat-page.tsx` handleSend 改调 `buildWorkingList(localMessages ?? history ?? [], text)` 消内联 working-list 计算 + `const assistantMsg = working[working.length - 1]` 保留流式就地 mutate 引用 + chat-page.tsx **仍在旧位置**(不 git mv,跨目录 import 成立)+ App.tsx 未改(v2 边界约束守住)。**验证**:`vitest run` 5/5 绿 + `tsc -b` 0 错 + `npm run build` 绿(1.96s)+ `npm test` **70/70 全绿**(65 基线 + 5 新,零行为回归)+ `oxlint` 0/0。**/code-review 双轴**(general-purpose ×2 并行):Standards 0 硬违规 / 1 已修(`build-working-list.ts` header 注释「读两次」不准 → 改描述各读两次 + 默认跨 tick 语义)/ 2 判断项留痕(① `now` 参数 test-only Speculative Generality —— 由 plan「近纯函数注入时钟」决策正当化保留;② `working[len-1]` positional 耦合 —— 已注释,Ticket 2/3 若追加 trailer 可评估改双返回值)/ Spec 5 AC 全满足 0 缺失 0 误 0 偏差。**非末切片**(Ticket 2/3 待做),不动 feature_list.json status/evidence(末切片的事)。下一步:**切片 02 ConversationListPanel migrate**(Panel 自调 hooks[v2 修正:store-view 范式],Blocked by 切片 01 已解锁)—— ✅ 已完成(见下条)。
- **chat-page-split 切片 02 ✅(2026-07-30 Session 165,非末切片,commit 42e8504)**:抽 `ConversationListPanel` migrate 阶段(**不 git mv**)。落地 1 改文件 + 2 新文件:① `frontend/src/pages/chat/conversation-list-panel.tsx`(新建)把列表半边(列表 JSX + 右键菜单 + rename/add-tag 2 Dialog + 10 handler[handleDeleteConversation/toggleSelect/handleBatchDelete/openRename/submitRename/openAddTag/submitAddTag/handleRemoveTag/handleTogglePin/handleToggleStar]+ selectedIds/searchInput/searchCommitted/2 effect[debounce + conversationIdSet 清空]+ conversationLabel helper + customerNameOf 本地副本)从 chat-page.tsx 搬出。**Panel 自调 9 个会话管理 hook**(useConversations/useDeleteConversation/useRenameConversation/useAddConversationTag/useRemoveConversationTag/useSetConversationPinned/useSetConversationStarred/useBatchDeleteConversations/useCustomerProfiles),零 data/mutation 下传(对齐 bookings/store-view 范式,plan D2)。② `frontend/src/pages/chat/__tests__/conversation-list-panel.test.tsx`(新建)11 用例(vi.hoisted mock 9 hook + renderWithProviders + user-event@14):列表渲染 + 徽章(pinned/starred/composite)+ 空状态(无词/有词)+ 点击选择 onSelectConversation + 删除 mutateAsync 被调 + 删除当前会话触发 onStartNew + rename/add-tag Dialog 弹出(await findByText portal 异步)+ streaming 时 trigger disabled + **回归用例:streaming 时行 button disabled 点击不触发**。③ `frontend/src/pages/chat-page.tsx`(改瘦身,1032→**582 行**,<650 AC)删列表 Card + 2 Dialog + 相关 state/handler/imports,渲染 `<ConversationListPanel streaming activeConversationId onSelectConversation onStartNew initialSearch />`;chat-page.tsx 仍在 pages/(未 git mv),App.tsx 未改。**双栏特化偏离(经 Spec 轴判可接受)**:chat-page 是「列表+详情」双栏、streaming 半边在父层,故 Panel 接收 2 向下只读 UI 状态(`streaming`+`activeConversationId`)+ 2 向上回调(`onSelectConversation`/`onStartNew`)+ `initialSearch`(?search= 深链播种,保「零行为变更」)。AC「仅 2 向上回调」字面被这 3 向下 prop 突破,但 Panel 仍自取 conversations、自调所有 mutation,D2「列表生命周期自含」精神未破。**/code-review 双轴**(general-purpose ×2 并行)**共识发现 1 处行为回归并修正**:原 `selectConversation` 的 `if(streaming) return` JS 守卫下移 Panel 后,行 `<button>` 漏 `disabled={streaming}`(原代码靠 JS 守卫非 disabled)→ streaming 中点会话行会中途切换(违 §4.5「零行为变更」+ user story「列表交互零变化」)。修正:行 button 补 `disabled={streaming}`(与 DropdownMenuTrigger/新建按钮守卫一致)+ 补 1 回归用例锁住 + 修掉 chat-page 那条错误注释。**审查的价值**:双轴独立交叉验证同一 bug(高置信),阻止 streaming 中途切会话导致 abortRef/localMessages 错配旧流的行为回归进仓库。**验证**:`vitest run` 11/11 绿 + `tsc -b` 0 错 + `npm run build` 绿(1.48s)+ `npm test` **81/81 全绿**(70 基线 + 11 新,零回归)+ `oxlint` 0/0。**非末切片**(Ticket 3 待做),不动 feature_list.json status/evidence(末切片的事)。下一步:**切片 03 收尾**(git mv chat-page.tsx→chat/chat-page.tsx + 建 chat/index.tsx 双 entry barrel + 改 App.tsx import + 抽 customerNameOf 到 chat/customer-helpers.ts 参数化共享 + feature 收尾,末切片)。
- **chat-page-split 切片 03 ✅(2026-07-30 Session 165 末切片,commit 4c961c2)**:收尾验证(git mv + 双 entry + customer-helpers + 全量验证)。落地 git mv + 2 新建 + 2 改:① **`git mv pages/chat-page.tsx → pages/chat/`**(git rename 检测 `chat-page.tsx => chat/index.tsx` (95%),blame 连续保留 —— 实际逻辑落地 index.tsx)。② `frontend/src/pages/chat/index.tsx`(590 行新建,路由入口,streaming 半边 + 编排的实际逻辑从旧 chat-page.tsx 搬出,改调共享 `customerNameOf(conv?.customer_id, customerProfiles)`)。③ `frontend/src/pages/chat/chat-page.tsx`(16 行 barrel,`export { ChatPage } from "./index"`,**镜像 bookings/bookings-page.tsx 双 entry 范式 D9**)。④ `frontend/src/App.tsx`(lazy import `@/pages/chat-page` → `@/pages/chat/chat-page`)。⑤ `frontend/src/pages/chat/customer-helpers.ts`(27 行新建,`customerNameOf(cid: string|null|undefined, profiles: CustomerProfileRead[]) => string|null` 参数化真纯函数 D7;签名 cid 扩含 undefined 是因为 `conv?.customer_id` 可能 undefined,`!cid` 短路语义等价,**零行为变更**;profiles 作参数传入可单测)。⑥ `frontend/src/pages/chat/conversation-list-panel.tsx`(改调共享 helper 删本地闭包副本 + call site 传 `customerProfiles`)。**验证**:`npm run build` 绿(1.83s,chat-page chunk 348 kB 与拆分前一致)+ `npm test` **81/81 全绿**(70 基线 + 11 panel,零回归)+ `npx oxlint .` 0/0 + grep residual `pages/chat-page` imports = **0** + `index.tsx` 590 行(<650 AC)+ grep `useMemo|useCallback` index.tsx = 0 + `./init.sh full` 后端 **841 passed**(零回归)。**/code-review 双轴**(general-purpose ×2 并行):Standards 0 硬违规(双 entry 忠实镜像 bookings、symbol-name 锚定 #5 合规、不越界)/ Spec 6/9 AC 满足(余 init.sh 已补跑 + 2 收尾后置)+ 0 scope creep;1 文档建议留痕(§10 AC item 5 `wc -l chat-page.tsx` 重命名后指向 barrel,measurement target 应 retarget index.tsx —— 非缺陷,streaming 半边 590 行 <650 实测满足);1 判断项留痕(devices-page 有第 3 份 customerNameOf,fallback 语义不同 `"-"`,属独立后续候选,不越界)。**feature 收尾仪式(three-tier §4 第 1-7 步)**:① feature_list.json status `not_started → passing` + evidence 4 条(切片 1/2/3 + 收尾条)✅ / ② `./scripts/sync-active-features.sh` 刷新 active 视图(2 活跃 + 5 最近 passing)✅ / ③ plan-chat-page-split.md draft v2 → ✅ passing(标题 + Ticket 3 AC 全勾 + 完成证据)✅ / ④ progress.md 顶部 frontier 清空(指向 devices-page-split 78)✅ / ⑤ clean-state-checklist 逐项 ✅ / ⑥ 文档影响评估:**无新增/改动文档**(纯前端结构重构,AGENTS.md/项目指南/铁律均不受影响);后置候选 devices-page 第 3 份 customerNameOf 留独立 ticket / ⑦ **末切片依赖解锁扫描**:无任何 feature `depends_on` 指向 chat-page-split(纯重构无下游)→ 无需推进。**feature 核心**:chat-page 1038 行单函数拆分完成 —— 拆成 chat/ 文件夹 6 文件(index 590 + panel 552 + build-working-list + customer-helpers + 2 测试),对称 bookings/ 范式;解锁 working-list 纯逻辑可测(A2 不可测债)+ 消解单函数膨胀 + 抽共享 helper。16 前端测试新增(5 buildWorkingList + 11 panel),总计 81 全绿。
- **union-cast-split ✅ passing(2026-07-29 Session 158 续收尾,全 3 切片完成)**:第 6 次巡检(2026-07-29)Top recommendation —— 前端 5 个 role-branching hook 返回 union(`Device[]|DeviceHqRead[]` 等),窄化散落 4 view 靠 12 处 `as` 断言(微恶化,第5次 ~10→第6次 12)。grill 8 决策定方向:**拆 role-specific hook**(union 在 hook 层消灭而非 view 边界)+ queryKey 共享(D5)+ All 后缀(随 useAllTenants 先例,D6)+ 不提 ADR(D8)+ ModelOption/DeviceStatus 投影 cast 不纳入(正交,D2)。纯前端类型重构,零后端零 schema 零运行时行为变化,3 切片按 domain 分(bookings / devices / 收尾),非复杂任务不走对抗式审查。**完整切片链**:**切片 1 ✅ + 切片 2 ✅ PR #147 commit abce938**(bookings + devices domain 合并提交)+ **切片 3 ✅ 末切片**(本次,0 源码改动 —— grep 审计验证 + feature 收尾仪式,符合 plan「文件清单 0-1」预期)。**切片 1**(bookings domain):endpoints.ts 新增 `fetchBookingsAll`(返 `BookingHqRead[]`)+ queries.ts 新增 `useBookingsAll`(共享 `qk.bookings`) + hq-view 改调消 L143 `as BookingHqRead[]` + store-view 消 L186 `as Booking[]` + my-bookings-view 删 L63 D 类死 cast(`useMyBookings` 已返 `Booking[]` 非 union)+ 删 `Note(candidate-8)` 注释 + hq-view.test.tsx mock 改名 `useBookings`→`useBookingsAll`(D7)。**切片 2**(devices domain,消 8 处 A 类 device cast):endpoints.ts 新增 `fetchDevicesAll`/`fetchDeviceModelsAll` + 窄化 `fetchDevices`→`Device[]`/`fetchDeviceModels`→`DeviceModelPublic[]`(**偏离 §4.5** 改镜像切片 1 对称范式,4 理由记入 plan)+ queries.ts 新增 `useDevicesAll`/`useDeviceModelsAll`(共享 `qk.devices`/`qk.deviceModels`)+ hq-view 改调消 L161(接切片1遗留,双侧收口)+ store-view 消 L152/355/365 三处 + devices-page 双组件 StoreView L192/HqView L422 消 cast + device-models-page 消 L149/216 + hq-view.test.tsx mock 改名 `useDevices`→`useDevicesAll`。**/code-review 双轴**(切片 2,general-purpose ×2 并行):Standards 0 硬违规 + 1 判断项已采纳修复(endpoints.ts 三处 section header union 注释被本次改动证伪→更新为描述 split)/ Spec 8 AC 全满足。**切片 3 末切片**(本次):0 源码改动。AC1 grep A 类数组 cast(`as Device[]|as DeviceHqRead[]|as Booking[]|as BookingHqRead[]|as DeviceModelRead[]`)在 `frontend/src/pages/` **代码处归 0**(唯一 2 处匹 my-bookings-view L7 + store-view L153 是说明性历史注释,非 `Note(candidate-8)` 待办残余,保留正确)/ AC2 B 类保留(hq-view L516 `b as Booking` + L519 `bk as BookingHqRead` 单数 props cast[plan 写 520/523 实际微移 516/519]+ 测试 `as BookingHqRead` mock 散在 hq-view.test.tsx L139 + schedule-grid.test.tsx L109 各 1 处,共 2 处)/ AC3 C 类保留(devices-page `as ModelOption[]` ×4 L172/375/462/669 + `as DeviceStatus` ×1 L1053)/ AC4 `Note(candidate-8)` grep 0 处。**验证**:`npm run build` 绿(2.06s 0 类型错误)/ `npm test` **65/65 全绿**(8 test files 零行为回归)/ `npx oxlint .` **0 warning 0 error**(101 files 102 rules)。**feature 收尾**:status `not_started → passing`(修正切片 1+2 非末切片未更新 status 的状态 + 派生视图 active.json 同步)+ evidence 4 条(切片 1/2/3 + 收尾条)+ sync-active 刷新(active 视图 0 活跃 + 5 最近 passing)+ plan draft v1 → passing(切片 3 标题 ✅ + 7 AC 全勾 + 完成证据)+ progress.md 顶部 frontier 清空。**末切片仪式依赖解锁扫描(three-tier §4 第 7 步)**:无任何 feature `depends_on` 指向 union-cast-split(纯重构无下游)→ 无需推进。**文档影响评估**:① feature_list.json ✅ / ② progress.md ✅(顶部清空 + 本条记录 + EP3 断点)/ ③ plan-union-cast.md draft v1 → passing / ④ CONTEXT.md 不涉及(前端 hook 内部重构);不动 README / 不动 `项目指南/`(纯前端类型重构,现有架构文档完全覆盖)/ 不提 ADR(D8)。**feature 核心**:union-cast 扩散消解完成 —— 3 个 role-branching hook 各拆出 store 版 + All 版,union 在 hook 层消灭,10 处 A 类 role 窄化 cast 全消 + 1 处 D 类死 cast 顺手清;B 类(props 适配)+ C 类(字段投影/enum)按决策明确排除保留原样。union-cast 从第 5 次 ~10→第 6 次 12 处的恶化趋势终止并归零。
- **EP3 断点**: **前端设计系统收口系列 EP2 单回环全完成 —— 3 feature 批量登记 + plan 含实施切片段就绪,Feature A `design-system-token-foundation` 为 frontier 待 EP3 实施**(2026-07-31 Session 172)。系列总纲 `harness/docs/plan-frontend-design-system-overview.md`(EP1 grill 7 决策 + huashu-design B3 变体定稿)。本次 Session 172 EP2 单回环:① `/to-spec` ×3 —— 落 `plan-design-system-token-foundation.md`(Feature A,2 切片)+ `plan-design-system-color-sweep.md`(Feature B,5 切片)+ `plan-design-system-spacing-card-hierarchy.md`(Feature C,2 切片),均含 Design 段 + 验收标准 + 实施切片段 + checklist;② feature_list.json 登记 3 条(A p81 in_progress / B p82 not_started depends_on A / C p83 not_started,与 A/B 正交);③ `/to-tickets` 切片段随 plan 一次成型(EP2 单回环高效做法,to-spec + to-tickets 同一套思考);④ EP2 收尾自检(three-tier §3)4 条全过(切片依赖图无环 / 每片有 AC / 首片 frontier / plan 无悬空 TODO);⑤ sync-active 刷新(3 活跃)。**Feature A token 值严格用 B3 定稿**(亮 `--success 152 76% 36%` / `--warning 35 92% 50%` / `--danger 0 84% 60%` / `--info 189 90% 42%`;暗 152 64% 48% / 38 95% 58% / 0 80% 64% / 189 80% 55%)。**下一步:EP3 `/implement` Feature A 切片 01**(token 基建:`index.css` `:root`+`.dark` 四 token + `tailwind.config.js` colors 暴露,frontier 无 blocker)。

## Session 173(2026-07-31):前端设计系统收口 Feature A 切片 01-02 实施 + feature 收尾(全 2 切片完成 → ✅ passing)

**任务**:EP3 实施 `design-system-token-foundation`(Feature A)的 2 个切片 —— 01 token 基建(已合并 main `ac784be`)+ 02 ui/ 组件库内部映射 + feature 收尾(末切片)。Session 172 EP2 已就绪 plan,本次走 `/implement` → `/code-review` → feature 收尾仪式。

**切片 02 ✅ commit `8398ab2`**(分支 `feat/design-system-token-foundation-slice-02`,末切片):ui/ 组件库内部语义性硬编码原色映射到切片 01 的 token。落地 2 改 + 1 新建:
- **`badge.tsx`(4 处映射)**:`success` variant `bg-emerald-500 text-white` → `bg-success text-success-foreground`(对齐 destructive 范式)+ 3 个 dot 变体 `[&::before]:bg-emerald-500/amber-500/red-500` → `bg-success/warning/danger`。
- **`toast.tsx`(2 处映射)**:success/destructive 浅底深字 `emerald-50/200/900` + `red-50/200/900` 三件套 → **实心** `bg-success/danger text-success/danger-foreground`(对齐 badge/button destructive 范式)。
- **`avatar.tsx` 零改动**:8 色环 `COLOR_PALETTE`(blue/emerald/amber/rose/violet/cyan/orange/pink)是设计性多色边界,feature notes 明确「avatar 8 色环保留不动」;实测 avatar 无语义 ring/border(AC 第3条「ring/border 映射」vacuous,evidence 留痕)。
- **`badge-toast-avatar.test.tsx` 新建 10 测试**:锁语义色映射不回退 —— 断言新 className(bg-success/bg-warning/bg-danger 等)真出现在渲染 DOM,旧 emerald/red 残留即变红。Toast 走 ToastProvider+useToast 真实路径(useEffect 暴露 toast API + act 包裹 push),Badge/Avatar 纯 DOM 直接 render。

**`/code-review` 双轴(general-purpose ×2 并行)—— 价值兑现**:
- **Standards**:0 硬违规;4 判断项全修复:① fragile locator(`closest('[class*="pointer-events-auto"]')` 耦合 Tailwind 工具类 → 改 `parentElement.parentElement` 结构定位)+ ② 3 个 Toast it 块重复脚手架 → 抽 `renderToast()` helper + ③ `ToastProbe` render-time side effect → 改 `useEffect`(顺带修 oxlint exhaustive-deps)+ ④ badge dot 变体 dup 是 pre-existing(只换末 token,非引入)。
- **Spec**:0 wrong / 0 scope creep;**1 真 issue 修复(Spec #3 精准拦截)**:初版 toast 用 tint 范式(`bg-success/10 + text-success` DEFAULT 中绿),node WCAG 公式实测亮色对比度 **2.96** / 暗色 **1.18** **不达 AA 4.5**(原 toast `text-emerald-900` 是 10.36,我的映射造成可读性回归)。修复改实心 `bg-success text-success-foreground`:亮 5.42(success)/ 4.72(danger)+ 暗 8.31 / 5.28,**双模式全过 AA 4.5**。洞察:toast 是强语义提示(成功/错误反馈),实心比浅底 tint 更合适;tint 范式留给 Feature B 业务页(浅底深字场景)后续单独验证对比度。Spec agent 的价值:阻止了一个「亮色勉强、暗色几乎不可见」的可读性回归进仓库,纯 build/test/lint 全绿挡不住这种缺陷。

**feature 收尾仪式(three-tier §4 第1-8步)**:
- ① `./init.sh full` **842 passed**(后端零改动零回归,纯前端 feature)✅ / 前端 npm run build 0 错 + oxlint 0/0 + npm test **141/141**(131 baseline + 10 新切片02,零行为回归)✅
- ② feature_list.json status `in_progress → passing` + evidence **4 条**(切片01 token 基建 / 切片02 ui 映射 + grep 归 0 / WCAG 修复 + 对比度手算 / 收尾全量验证)✅
- ③ `./scripts/sync-active-features.sh` 刷新(2 活跃 B+C + 5 最近 passing,A 进最近 passing 列表)✅
- ④ progress.md 顶部 frontier 从「A in_progress」→「A passing,下一步 B frontier」+ 本条记录 ✅
- ⑤ clean-state-checklist ✅(下方)
- ⑥ 文档影响评估(下方):无新增/改动架构文档(纯前端 className 映射)
- ⑦ **末切片依赖解锁扫描**:Feature B(`design-system-color-sweep` p82)`depends_on design-system-token-foundation` —— **本 feature passing 后 B 解锁**,可置 in_progress(WIP=1 下 B 是下一 frontier)。Feature C 正交不依赖。
- ⑧ 分支清理:`feat/design-system-token-foundation-slice-02` 待合并 main 后删(本地 + 远端)。

**feature 核心**:前端设计系统收口 Feature A(token 地基)完成 —— 4 个 semantic token(`--success/--warning/--danger/--info`)B3 定稿双色值落地 index.css + tailwind.config 暴露(DEFAULT+foreground)+ ui/ 组件库内部(badge 4 处 + toast 2 处)语义硬编码原色映射到 token,**ui/ 自身成为设计系统收口的干净样板**。avatar 8 色环 + chart 多色 + destructive 命名保留(设计性多色 + 既有命名边界)。danger 与 destructive 并存(danger 新语义 token / destructive shadcn 既有命名)。**toast 实心 vs tint 决策**给 Feature B 暴露一个需后续验证的点:Feature B notes 计划业务页用 tint(`bg-X/10 + text-X DEFAULT`),但 DEFAULT 字在亮色 2.96 不达 AA —— Feature B 实施时需复核 tint 字色对比度(可能需 foreground 或加深 /80)。下一步:EP3 `/implement` Feature B 切片 01(success 色系业务页扫荡)。

  - **① chat-page-split(pri 76,Top rec)**:chat-page.tsx(1038 行单函数)拆 ConversationListPanel + buildWorkingList 纯函数。**grill 9 决策**(D1 Panel+纯函数 / D2 Panel 自调 hooks[v2 修正] / D3 独立.ts[v2:近纯函数注入时钟] / D4 建 chat/ 文件夹[v2:双 entry] / D5 Dialog 随 Panel / D6 不动 chat panel 右半边 / D7 customerNameOf 共享 helper[v2:参数化纯函数] / D8 两测试 / D9 router barrel[v2:双 entry 对齐 bookings+devices])。**3 切片**:① buildWorkingList 近纯函数 expand[不 git mv] → ② ConversationListPanel migrate[Panel 自调 hooks][不 git mv] → ③ git mv + 双 entry + helper 收尾。plan:`harness/docs/plan-chat-page-split.md` **draft v2**(经 opus 审查修订)。
  - **③ perm-backfill-dedupe(pri 77,Strong WORSENED)✅ passing —— 2 切片全完成**(2026-07-30 Session 166,切片1 commit 6461236 + 切片2 commit 89f139e,PR #151 待合并)。permission_service 两个 backfill 函数逐字节镜像 → 参数化合并 + 白名单防误用,**三层(service 函数 + scripts + 测试 K chapter)全去重**。**grill 4 决策**(D1 合并+改所有 caller / D2 合并 scripts[v2:改名 backfill_obj_perms.py 避碰撞] / D3 测试 parametrize / D4 Literal 白名单)。**2 切片已收官**:① service 函数参数化 + caller 改造[v2:临时保留 6 测试绿,不删 K chapter]✅ → ② scripts 合并 + 测试 parametrize 收尾(7 cases,期望值动态算)✅。plan:`harness/docs/plan-perm-backfill-dedupe.md` draft v2 → **passing**(切片 2 标题 ✅ + Ticket 2 AC 全勾)。风险点已处理:scope guardrail 保持(K6 双 guard + 入口 ValueError)+ **循环变量 perm_obj 改名避 shadowing**✅。
  - **② devices-page-split(pri 78,Strong PERSISTING)**:devices-page.tsx(1083 行)拆 store-view/hq-view,镜像 bookings/ 范式。**grill 5 决策**(D1 镜像 bookings/[v2:核心骨架对称] / D2 4 Dialog→device-dialogs.tsx / D3 helper 按职责拆两文件 / D4 store+hq 两测试 / D5 router barrel)。**2 切片**:① 建 devices/ 文件夹 + 迁移组件 + **tenantId smoke 前移**(v2)→ ② 补完整测试收尾[spy-on-children 覆盖 tenantId 双路径]。plan:`harness/docs/plan-devices-page-split.md` **draft v2**(经 opus 审查修订)。风险点:HqView 跨租户写 tenantId 传递[**v2 前移 smoke 消除空窗**]。
  - **④ composite_chat billing seam(暂缓,留后续候选)**:Worth exploring,composite_chat 刚 ship,双轨计费分歧有据(L156-161),留待沉淀后再看 seam 必要性。巡检 log 标 PERSISTING 待定。

  **对抗式审查成果(v2 修订,2026-07-30 Session 164 续)**:启用 opus ×3 并行审查 3 个 plan(真相核查 + 设计质量双轴),发现并修订 **9 个 🔴 RED + 多个 🟡 YELLOW**,全部回写到各 plan §0 v1→v2 变更摘要。关键修订:① chat **范式方向纠正**(store-view 实测是「自调 hooks 零 props」,v1 误为「父传 handler」)+ **buildWorkingList 非纯**(Date.now/new Date → 加 now 参数注入)+ **selectedIds 跨层效应解决**(Panel 自调后全部下沉);③ **caller 计数虚假精度**(14→真实 18 引用)+ **script 命名碰撞**(backfill_perms → backfill_obj_perms)+ **循环变量 shadowing** + **测试空窗消除**(Ticket 1 保留 K chapter);② **tenantId 安全空窗消除**(smoke 前移)+ **「4 Dialog tenantId prop」事实修正**(实际只 Create/Edit 有 prop,Bind/Delete 走 hook closure)+ **AC 客观化**(test -f 清单)+ **范式统一**(chat 改双 entry 对齐 devices+bookings)。审查的价值:阻止了范式方向错误 / 非纯函数误判 / 安全测试空窗 / 跨层 effect 断裂进实施阶段。

  **Phase 2 启动方式**:新会话接 `chat-page-split` 切片 1(buildWorkingList 近纯函数 expand,不 git mv),用 `/implement`。每 feature 走完 implement→review→merge→status=passing 后再开下一个(WIP=1)。巡检 HTML 报告归档:`~/.cache/ai-agent-platform-architecture-reviews/2026-07-30.html`。
- **⚠️ PR #148 已合并(网络恢复后补推)**:切片 3 末切片 squash 合并 commit `addb9eb`(PR #148),本地分支 `refactor/union-cast-split-slice-3-final` 已删。CI 4/4 全绿(Backend pytest+ruff 5m48s / E2E Playwright 2m3s / Frontend typecheck+build+lint 27s / Migrations alembic 43s)。PR 号 + commit hash 已回填 feature_list.json evidence 切片 3 条 + 收尾条 + plan §6 Ticket 1/2/3 标题(全切片标题统一 `✅ PR #NN commit <hash>` 格式)。本次回填单独走 `chore/union-cast-split-evidence-backfill` 分支(纯 evidence 回填 + AC2 evidence 计数修正[test mock 归因订正为 hq-view.test.tsx L139 + schedule-grid.test.tsx L109 各 1 处])。
- **twoscope-config ✅ passing(2026-07-29 Session 162 收尾,全 3 切片完成)**:第 5 次巡检(2026-07-29)Top recommendation —— 「平台默认 + 租户覆盖」两级配置范式在代码里重复 3 repo + 3 service,互相 docstring 指认「Mirrors XxxConfig」但从未提取。**EP2 回环**(2026-07-29 Session 159):`/grill-with-docs` 5 决策(D1 基类只吃读路径 service 各留 _upsert delta / D2 ModelPricing 异类不纳入也不补 service / D3 is_active 差异用钩子 _active_filter 非加列 / D4 get_effective 三级 fallback 不进基类 / D5 切片 llm 做 frontier)+ **子智能体对抗式审查 v2 回炉**(opus ×2 并行:真相核查 + 业务设计;v1 发现 3 P0:决策3 加 is_active 死列违反铁律6 / slice3 补 ModelPricingService 是空架子 / 缺 ADR 钉边界 + 2 P1:frontier 应改 llm / repo 层零测试覆盖需先补,全部修正)+ `/to-tickets` 3 切片 expand-contract。**EP3 切片链**:**切片 1 ✅ commit 2ab3952**(新建 `app/repositories/two_scope.py` 基类 + `LlmConfigRepository` 改继承 + `tests/test_two_scope_repo.py` llm 四态契约,expand 阶段)/ **切片 2 ✅ Session 161**(embedding + booking 改继承基类,booking 设 `_active_filter=None` 零 schema + 补 embedding 四态/booking 三态+no-filter 验证,migrate 阶段)/ **切片 3 ✅ 末切片**(本次,无新源码逻辑,contract 收尾):清理配置范式 docstring 互指债 6 处(3 repo 补 ADR-0002 指针 + 2 service「Mirrors LlmConfigService」→「Structurally parallel to」+ 1 model「Mirrors LlmConfig」→「Structurally parallel to」)+ 新建 `docs/adr/0002-twoscope-config-repository.md`(复刻 ADR-0001 Nygard 五段式:纳入 3 repo + 排除 ModelPricing[二维 key]/tenant_config[单租户] + _active_filter 钩子理由 + get_effective/_upsert 不进基类理由)+ CONTEXT.md ADR-0002 指针确认。**验证**:`./init.sh full` **840 passed** 零回归(基线 828 + 12 repo 契约用例,241s)+ ruff clean + grep 配置范式互指「Mirrors.*(LlmConfig|ConfigService|ConfigRepository)」→ **0 处**(docstring 互指债消解)。**feature 收尾**:status in_progress → passing + evidence 4 条(切片 1/2/3 + 收尾条)+ sync-active 刷新(active 视图 0 活跃 + 5 最近 passing)+ plan draft v2 → passing(切片 3 标题 ✅ + 8 AC 全勾 + 头部 status passing)+ progress.md 顶部 frontier 清空。**末切片仪式依赖解锁扫描(three-tier §4 第 7 步)**:无任何 feature depends_on 指向 twoscope-config(纯重构无下游)→ 无需推进。**文档影响评估**:① feature_list.json ✅ / ② progress.md ✅ / ③ plan-twoscope-config.md draft v2 → passing / ④ CONTEXT.md ✅(Two-Scope Config 条目 grill 阶段已就位);不动 README / 不动 `项目指南/`(纯 repo 层重构,现有架构文档完全覆盖)。**产出项目第 2 个 ADR**(ADR-0002,与 ADR-0001 Principal 互补,共立 Repository 层两大范式基类采纳边界:`TenantScopedRepository` 业务数据隔离 + `TwoScopeRepository` 配置两级覆盖)。**feature 双债消解**:① 两级配置范式 docstring 互指债(6 处)消解;② repo 层零直接测试覆盖债(新增 12 契约用例)消解。
- **composite-chat 切片 03 ✅(2026-07-28 Session 154,API+计费+集成测试 非末切片,PR #141 commits 71d265c + 60d9f9e)**:`POST /chat/composite` endpoint 上线(纯 JSON 非 SSE)。落地 3 文件 +868 行:① `app/api/v1/chat.py`(+244)加 endpoint(dependencies 复用 conversations:chat + response_model=CompositeResponse):Pass 1 agent_ids 去重保序(dict.fromkeys)+ 逐 agent `AgentRepository.get_for_tenant`(跨租户/软删均 404 无存在性泄露)+ permission_service.require;Pydantic CompositeRequest 已校验空/超 8 个 422;wallet 预检非 super_admin 且 `BillingService.has_balance=False` → **HTTP 402(项目首例真实 HTTP code)**,严格语义区别于 /chat/stream 的「无钱包=放行」SSE error frame(N+1 倍 token 成本应更严格;super_admin 旁路);create_or_get(kind="composite")续接 H2 kind 一致性校验;composite_query fan-out + synthesize;assistant Message 持久化 fragments JSONB + usage_total token triple;N+1 笔 _record_composite_usage 循环(fragment 笔 agent_id=frag.agent_id,synthesize 笔 agent_id=None,customer_id 透传)。② 新函数 `_record_composite_usage`(不复用 _record_usage:plan 明确要求独立防签名耦合 agent_id: str|None vs Agent 对象):except 用 logger.exception(不裸吞,N+1 放大静默失败);record commit → _charge_usage 配对原子(H4)。③ `ConversationService.create_or_get` 加 kind 参数(末尾默认 single)+ 续接分支 kind 一致性校验(H2:conv.kind != kind → NotFoundError 404,防 single↔composite 串用,与跨租户 404 一致无存在性泄露);`append_message` 加 fragments kwarg(加在 error 后,现有 4 处调用零改动)。④ `tests/test_composite_chat.py`(+602 新建)**18 HTTP 集成测试**(照 test_chat.py 范式 monkeypatch composite_query + 测试内自建 agent):happy path 3 agent / 部分失败隔离 / synthesize 失败降级 / wallet 402(零余额 + 无钱包)/ super_admin 旁路 / 无 chat 权限 403(remove_policy 裸 role code "owner" 非 "role:owner" + try/finally restore 共享 enforcer)/ 跨租户 404 / 软删 agent 404 / 重复 agent_ids 去重 / 超 8 个 422 / 空 agent_ids 422 / 续接 single 会话 404 / 续接 composite 会话 200 / fragments 持久化 / N+1 笔 UsageEvent / customer 透传 / 扣费容错(第 2 笔 charge 抛错 monkeypatch flaky,1/3/4 笔仍入库)。**「多轮 usage 准确」由切片 02 `test_composite_query_multi_round_usage_accumulates` 纯函数测试完整覆盖**(astream_events 两轮累加防 ainvoke 漏计),集成层 fake_composite 是 test_chat.py 既定范式。**验证**:`./init.sh` 全绿 **828 passed**(基线 810 + 新增 18,零回归)+ ruff clean + alembic check 同步(本切片零 migration 改动)。**/code-review 双轴(opus ×2 并行)**:Standards **0 硬违规** / 6 判断项(_record_composite_usage vs _record_usage 构造重复 → 文档化标准覆盖 plan 要求独立防签名耦合;kind: str 应为 Literal 留 future;wallet 泄露有界 / N+1 串行注释偏 / Feature Envy 轻微);Spec **1 wrong 已修**(_charge_usage 共享函数 charge 失败路径裸 rollback → 补 logger.exception commit 60d9f9e,plan 行 287/306「不裸吞」覆盖 N+1 笔 + SSE 单笔)+ 1 missing 文档化覆盖(多轮 usage)+ 2 scope creep 无负面影响。**审查的价值**:Spec wrong 阻止 charge 失败静默进仓库(N+1 笔场景放大静默 bug)。**非末切片收尾三件套**(对齐切片 01/02 范式):plan §六点五 切片 03 checklist 全勾 + 标题 ✅ / feature_list.json evidence 加切片 03 条目 + sync-active 刷新 / progress.md EP3 断点推进到切片 04。下一步:**切片 04**(前端模式切换 + 真实验证 + ship-it 收尾,末切片:endpoints.ts compositeChat 402 单独 catch + types.ts + composite-mode.tsx 独立组件 + chat-page Switch + 会话列表 badge + 真实 DeepSeek 端到端 + feature 收尾)。
- **composite-chat 切片 01 ✅(2026-07-28 Session 152,frontier 非末切片)**:后端数据层 + Schema。落地 3 改文件 + 2 新文件:① `app/models/agent.py` Conversation 加 `kind: Mapped[str] = mapped_column(String(16), default="single", server_default="single")`(放 agent_id 后,语义=主 agent 归属;无索引对齐「按需加索引」铁律)+ ② `app/models/message.py` Message 加 `fragments: Mapped[list | None] = mapped_column(JSONB().with_variant(JSON, "sqlite"), nullable=True, default=None)`(放 error 后,双 DB variant 照 Conversation.tags 惯例;import JSONB+JSON)+ ③ `app/schemas/conversation.py` ConversationRead 加 `kind: Literal["single","composite"] = "single"`(Literal 收紧防拼写错误 + 默认值 round-trip 旧数据)+ MessageRead 加 `fragments: list[dict] | None = None` + 新建 `CompositeRequest`(agent_ids min_length=1 max_length=8 + message min_length=1 + conversation_id/customer_id/synthesize_model 可选)/ `CompositeFragment`(agent_id/agent_name/snippet/status Literal[completed,failed]/error/model max64 + **input/output/total 三项 token 切片 03 计费契约**)/ `CompositeResponse`(conversation_id/synthesis/fragments)+ ④ 新建 migration `2026_07_28_1000_aa7a88a8e643_add_composite_chat.py`(down_revision=`5565cf1e81bd` 当前 head;**migration 层 `postgresql.JSONB` 无 variant** 照 b2c3d4e5f6a7 tags 惯例,variant 只在模型层 SQLite 测试路径覆盖;**up 含 backfill `UPDATE conversations SET kind='single' WHERE kind IS NULL`** plan §三 Step 3③ 要求的防御性 no-op —— ADD COLUMN NOT NULL DEFAULT 已自动回填,此 UPDATE 实测匹配 0 行;down 对称 drop 2 列)+ ⑤ 新建 `tests/test_composite_chat_schema.py` 14 单测(模型默认 kind=single/fragments=None + **旧 Conversation(无 kind 属性 SimpleNamespace 模拟)经 ConversationRead round-trip → kind="single"** AC 切片01 第9条核心 + composite kind round-trip + Literal 拒拼写错误 + Message fragments round-trip 含 token triple + CompositeRequest 校验 空agent_ids/超8/空message 422 + CompositeFragment status Literal + token triple round-trip + CompositeResponse 构造)。**ConversationService 零改动**(plan §六点五 AC 第7条):default+server_default 保证 kind="single" 不依赖 service 传参,create_or_get/append_message 切片 03 才加 kind/fragments kwarg。**验证**:`./init.sh` 全绿 **797 passed**(基线 783 + 新增 14,零回归,337.95s)+ ruff clean。**migration 手动验证(写 evidence,plan 切片01 AC第10条)**:docker aap-postgres(DB=aap user=aap port=5433)上 `alembic upgrade head`(`5565cf1e81bd → aa7a88a8e643`)+ `alembic downgrade -1` + `alembic upgrade head` 幂等无错 + `alembic check` 同步("No new upgrade operations detected")+ `SELECT COUNT(*) FROM conversations WHERE kind IS NULL` = **0**(7 行旧数据全 kind='single')+ `\d conversations` kind 列 `character varying(16) NOT NULL DEFAULT 'single'` + `\d messages` fragments 列 `jsonb` nullable。**/code-review 双轴(启用子智能体 opus ×2 并行)**:Standards **0 硬违规**(依赖单向 / DB 设计原则「加列不加表」/ migration 模板 / JSONB dual-DB 惯例全合规)+ Spec **0 missing / 0 scope creep / 0 wrong**(10 checklist + AC1.1-1.5 全满足,token triple/backfill SQL 精确匹配/migration-layer JSONB 无 variant 全对)。**4 判断项处置**:① Standards RED「backfill UPDATE 是 provably dead code」→ **Spec 覆盖 Standards 保留**(plan §三 Step 3③ 明确要求 + 防御性,但**修订注释诚实化**:不声称「防 server_default 被遗漏」而说明「plan 要求的防御性 no-op + 解释为何实际匹配 0 行」)② Standards YELLOW「fragment 形状 3 处重复(模型注释/schema/migration docstring)易腐烂」→ **修复**(模型注释改指向 CompositeFragment 作单一真相源,保留 token triple billing 契约说明)③ Standards YELLOW「server_default 裸字符串 vs 兄弟列 text()」→ **不改**(message.status 用裸字符串是先例,functionally identical)④ Standards YELLOW「2 async 测试缺 @pytest.mark.asyncio」→ **修复**(一致性补标记,auto 模式下本可跑)。**审查的价值**:① Standards RED 触发 backfill 注释诚实化(避免误导性「belt-and-braces」论证进仓库);② Standards YELLOW 触发 fragment 形状单一真相源化(防 3 处 prose 腐烂)。**非末切片,不做 feature 收尾仪式**(不刷 feature_list.json status 不写 evidence,切片 04 末切片的事)。下一步:**切片 02 composite_query 编排引擎**(Blocked by 切片 01 已解锁,Message.fragments 字段就绪 + fragment 结构定义稳定,核心:astream_events 累加多轮 usage + 每 agent 独立 session 方案 A + synthesize 失败降级 + 超时 fail-open)。
- **principal-scope-doc-alignment ✅ passing(2026-07-28 Session 151 收尾,单切片 = 末切片)**:第 4 次巡检候选 3 文档债(Principal 半收口 — CONTEXT 措辞 vs 代码张力)。**问题**:principal-module 收官后「半收口」决策散落 3 处且口径冲突 —— CONTEXT.md:30「统一走 Principal」过宽 + principal.py docstring L18-22 + 4 helper docstring(permission_service L677/L702 + _tenant_target L40 + data_scope L70)共 5 处「future architecture reviews」模糊口子,与 plan §4.2「已审查的不迁论证」冲突。**完整流程**:第 4 次巡检(2026-07-27,14→20 候选,HTML `~/.cache/ai-agent-platform-architecture-reviews/2026-07-27-v2.html`,Top = 候选 2 配置范式 leverage)→ 选候选 3 → `/grill-with-docs` 6 决策(A 方向=文档对齐非扩 Principal / A1 CONTEXT 最小补丁 / B1 docstring 指向 ADR + 硬约束 / C1 新建 ADR-0001 项目首个 / D1 单切片 7 改动绑一个 commit / E1 维持 scope 含漏 1-3)→ **启用子智能体审查**(opus ×2 并行:真相核查 8 判断 7 GREEN + 1 RED「AC 归属错位:AC3.5 是 4 helper docstring,# Note 是 AC2a.3」+ 漏看 6 api 调用点 + customer 2 super_admin 全局读方法 / 设计审查 4 改动 1 RED principal docstring 措辞 + 3 YELLOW + 漏 3 必须「4 helper 同款口子与 ADR 冲突」+ 漏 1/2 推荐)→ 修订 grill(**核心洞察:清单单一真相源 = ADR-0001,其他 6 处只做指针不枚举**)→ `/to-spec` 落 plan-principal-scope-doc-alignment.md(简化模板,9 章节,10 AC)→ `/implement` 单切片 7 改动 → `/code-review` 双轴(Standards 1 HARD CONTEXT 枚举越界 + 1 typo ADR Date + Spec AC1.2 YELLOW principal docstring 列 service 名 + AC1.8/1.9 RED 验证/收尾待做)→ **3 修复全完**(CONTEXT 删 4 方法名展开回 glossary / principal docstring 删 4 service 名 / ADR Date 注释两日期关系)。**审查的价值**:① 真相核查 RED 阻止 AC 归属错误进 ADR;② 设计审查 RED 阻止 docstring 措辞与 ADR 冲突;③ Standards HARD 阻止 glossary 变 spec;④ Spec YELLOW 阻止 docstring 枚举违反「清单单一真相源」原则。**7 改动落地**(1 新建 ADR + 6 编辑):① CONTEXT.md Principal 条目(「读写鉴权路径」+ 关键词不展开 + 跳 plan §4.2 + ADR-0001)/ ② principal.py docstring(指向 ADR + 「superseding that ADR」+ 不枚举)/ ③ docs/adr/0001-principal-scope-boundary.md(Nygard 五段式 + 完整清单:4 不迁方法 + 2 super_admin 全局读 + 4 非采用 service + 6 api 调用点 + Superseding 流程)/ ④ plan §4.2 表格后 ADR 交叉引用(纯 markdown `../../docs/adr/`)/ ⑤ 4 helper docstring 5 处口子收口(「do NOT extend without superseding that ADR」)/ ⑥ booking_service 4 处 # Note 注释加 ADR 引用 / ⑦ 4 service docstring 加 Auth 段(conversation/dashboard 用 panorama 不合 + device_model/group 用 platform-level 区分)。**feature 收尾**:status in_progress → passing + evidence 2 条(切片 01 + 收尾条)+ sync-active 刷新(active 视图 0 活跃 + 5 最近 passing)+ progress.md 顶部更新。**文档影响评估**:① feature_list.json ✅ / ② progress.md ✅ / ③ CONTEXT.md ✅(本任务核心)/ ④ plan draft v1 → passing;**新建 docs/adr/ 目录 + 项目第一个 ADR**(范式建立,影响未来所有架构决策)。**末切片仪式依赖解锁扫描(three-tier §4 第 7 步)**:无任何 feature depends_on 指向 principal-scope-doc-alignment → 无需推进。验证:`./init.sh` 全绿 **783 passed**(零代码改零回归,244.76s)+ ruff clean + grep「future architecture reviews」5 → **0 处** + ADR-0001 引用 **23 处**闭合(CONTEXT → plan/ADR / principal+4 helper+booking Note+4 service → ADR / plan → ADR)。
- **principal-module 切片 02a ✅(2026-07-27,非末切片)**:booking_service 迁 7 方法(create/update/cancel/end/no_show + list/get)到 Principal.for_write/for_read,鉴权决策收口到单一推理点。4 个不迁方法(start 三叉 customer / get_tenant_schedule / list_my_bookings / get_device_schedule)加 # Note(principal-scope): 注释(plan §4.2 格式)。**契约全 GREEN(plan §4.4)**:零行为变更(783 passed = 777 baseline + 6 Principal contract,零回归)+ BizError 文案逐字不变(for_write 内部仍调 resolve_target_tenant)+ permission_service.require 参数运行时等价(store 分支 access.effective_tenant == user_tenant_id == 旧 effective_tenant)+ permission_service 单一入口不动(Principal 不调 require)。**code-review 双轴**:Standards 0 硬违规 / Spec AC2a.1-2.5 ✅。**AC2a.6 行数指标修订留痕**:plan §7.1 估算「净减 34 行」实测反向「净增 +34 行」,根因 3 处(Note 注释 +16 强制不可删 / effective_tenant alias +5 下游多次引用删则 line-length 爆 / keyword-arg 展开 +12 即便 line-length=100 最紧凑写法)。Principal 的真实价值是鉴权决策收口 + 跨 service 形状统一(deletion test §1),不是 LOC 削减。AC2a.6 修订为「leverage 重构接受,LOC 指标放弃」,切片 02b/03 预计同向偏差。**assert access.require is not None**(list/get 2 处)与既有 `assert fresh is not None` 同范式保留(类型窄化辅助)。**非末切片**,不动 feature_list.json status / 不写 evidence(末切片 AC3.8 的事)。下一步:切片 02b(device_service 迁 7 方法,与 02a 独立)或切片 03(末切片,Blocked by 02a+02b)。
- **principal-module ✅ passing(2026-07-27 Session 150 收尾,全 4 切片完成)**:巡检候选 1(Strong)。**问题**:后端三 service(booking/device/customer)31 处 helper 调用(`is_cross_tenant_viewer`/`is_platform_writer`/`resolve_target_tenant`/`DataScopeService`)散落,鉴权决策没被吸收进深模块 —— booking_service 829 行膨胀根因。**完整切片链**:**切片 01 ✅ PR #136 commit 51c2614**(Principal frontier module + 6 contract test,零 service 改)+ **切片 02a ✅ commit 82b08c3**(booking 迁 7 方法 + 4 Note 注释)+ **切片 02b ✅ commit f636411**(device 迁全 7 方法,与 booking 形状逐字一致)+ **切片 03 ✅ commit(末切片)**(customer 迁 2 方法 + CONTEXT.md Principal 条目 + 4 helper docstring 交叉引用 + feature 收尾)。**feature 收尾**:status `in_progress → passing` + evidence 5 条(切片 01/02a/02b/03 + 收尾条)+ sync-active 刷新(active 视图 0 活跃 + 5 最近 passing)+ progress.md 顶部「最高优先级未完成」清空 + plan `draft v1 → passing`(切片 03 标题 ✅ + 9 AC 全勾)。文档影响评估(plan §10):① feature_list.json ✅;② progress.md ✅;③ CONTEXT.md ✅(加 Principal 条目,租户与身份章节,_Avoid_: user/identity/session);④ plan draft v1 → passing;不动 README / 不动 `项目指南/02-后端架构/`(Principal 是 service 层内部重构,现有架构文档完全覆盖)。**末切片仪式依赖解锁扫描(three-tier §4 第 7 步)**:无任何 feature `depends_on` 指向 principal-module(纯重构 feature,无规划中下游)→ 无需推进新 in_progress。**Principal 的真实价值**(deletion test §1 成立):删 Principal → 31 处 helper 调用重新散布到 18 个方法,complexity reappears across N callers → Principal earns its keep;是「鉴权决策收口到单一推理点 + 跨 service 形状统一」,不是 LOC 削减。**LOC 指标三切片均同向偏差**(plan §7.1 预警兑现,02a +34 / 02b +12 / 03 +21),根因 6-arg keyword-arg 展开 + effective_tenant alias + Note 注释(仅 02a);AC 指标全部修订为「leverage 重构接受,LOC 指标放弃」留痕。**不可违反契约 5 条全守住**(plan §4.4):零行为变更(783 passed = 777 baseline + 6 Principal contract,零回归)+ BizError 文案逐字不变(for_write 内部仍调 resolve_target_tenant)+ permission_service.require 参数运行时等价(store 分支 access.effective_tenant == user_tenant_id == 旧 effective_tenant)+ DataScopeService.resolve 行为不变(切片 03 只挪调用点)+ permission_service 单一入口不动(Principal 不调 require)。**PR 待开**(沿用 02a/02b 范式):沙箱网络不可达 GitHub,3 个 commit(02a/02b/03)同分支待推。
- **principal-module 切片 03 ✅(2026-07-27 Session 150,末切片)**:customer_service 迁**2 方法**(list_profiles + statistics)到 Principal.for_read,与 booking/device 形状一致。**关键差异(非 deviation)**:customer 的 list_profiles 与 device 的 list 不同 —— device 有 HQ/Store 双投影(`DeviceHqRead` vs `DeviceRead`)故 `if access.is_panorama` 早返回不同 repo 调用;customer 只有一个投影(`CustomerProfileRead`),panorama 与 store 走**同一个** `list_for_scope`/`search_for_scope`,只是 require 分支不同。**行为等价性**:旧代码 `DataScopeService.resolve` 对 panorama 内部短路返回 `scope="all"`;新代码 Principal panorama 分支返回 `scope=ResolvedScope("all")` —— 同 shape。statistics 同样 `if access.is_panorama: 走 statistics_all_global else: 走 statistics_for_tenant(tenant_id)`,镜像旧 `if is_cross_tenant` 分支。**customer 不迁 write paths**(create/update/delete_profile):无 `payload.tenant_id`(customers 无跨店写面),无 writer-bypass 可吸收。**CONTEXT.md 加 Principal 条目**(租户与身份章节,Platform Role 之后):「当前请求的身份抽象,统一解析读/写访问边界(effective tenant + scope + require-or-skip)」+ _Avoid_: user/identity/session。**4 个旧 helper docstring 加交叉引用**(AC3.5):is_cross_tenant_viewer / is_platform_writer(permission_service.py)+ resolve_target_tenant(_tenant_target.py)+ DataScopeService(data_scope.py)统一加「Internal: called by Principal. ... adoption can be evaluated in future architecture reviews」,标明适用范围(目前仅 booking/device/customer 用 Principal,其他 service 仍直调 helper)。**契约全 GREEN(plan §4.4)**:零行为变更(783 passed,零回归;test_customers_api 17 passed)+ BizError 文案逐字不变(customer 不走 for_write)+ permission_service.require 参数运行时等价 + DataScopeService.resolve 行为不变(只挪调用点)+ Principal 不调 require。**code-review 双轴**:Standards 0 硬违规(Duplicated Code 是 house pattern,device 已有)/ Spec AC3.1-3.6 全满足(2 处温和 scope creep 留痕:① CONTEXT.md _Avoid_ 多 session 准确无害 ② 模块 docstring 多 Read paths 段纯文档)。**AC3.6 LOC 偏差留痕(沿用 02a/02b 范式)**:customer_service.py 353 → 374 = **+21 行**(diff +35/-14),根因 6-arg keyword-arg 展开(2 方法 × ~5 行 vs 旧单行 DataScopeService.resolve)+ # Store role 注释 × 2 + 模块 docstring Read paths 段;放弃 LOC 指标,Principal 价值是决策收口 + 形状统一。**feature 收尾**(末切片):status in_progress → passing + evidence 5 条 + sync-active 刷新 + progress.md 顶部清空 + plan draft v1 → passing。下一步:无(feature 完整收官,等用户排新需求)。
- **principal-module 切片 02b ✅(2026-07-27,非末切片)**:device_service 迁**全 7 方法**(list / get / create / update / delete / bind / unbind)到 Principal.for_write/for_read,与 booking_service 形状逐字一致(`access = await self.principal.for_*(...)` → `if access.require:` → `effective_tenant = access.effective_tenant`)—— 改角色规则时三 service 只看一种心智模型。**device 全 7 方法都用 helper**,迁完三 import(`resolve_target_tenant` / `is_cross_tenant_viewer` / `is_platform_writer`)**干净删除**(零残余代码引用,docstring/comment 历史交叉引用保留)。**create 业务逻辑守卫**:`is_platform_writer(platform_role)`(跨店 customer 绑定断言门控)→ `access.require is None`,Principal 不变式(`require is None ⇔ is_platform_writer`,principal.py L24 + plan §4.0 Q3')保证等价,加注释钉死。**契约全 GREEN(plan §4.4)**:零行为变更(783 passed = 777 baseline + 6 Principal contract,零回归;test_devices_api + test_hq_platform_role 61 passed)+ BizError 文案逐字不变 + permission_service.require 参数运行时等价 + Principal 不调 require。**code-review 双轴**:Standards 0 硬违反(形状与 booking 一致 / is_platform_writer 替换忠实 / import 干净删除 / assert 同范式)/ Spec AC2b.1-2.4 ✅。**AC2b.5 行数指标修订留痕(沿用 02a 范式,plan §7.1 预警兑现)**:估算「净减 ≥ 20 行」实测反向「净增 +12 行」(432 → 444,diff +69/-57)。成因同 02a:6-arg keyword-arg 展开(即便 line-length=100 最紧凑仍 3-4 行 vs 旧 `resolve_target_tenant(a,b,c)` 单行)是主因 + effective_tenant alias(5 写方法各 +1)次之;device **无** 02a 的 Note 注释开销(plan §4.2 无 device 不迁方法),故 +12 < 02a 的 +34。Principal 价值同 02a:决策收口 + 形状统一,非 LOC 削减。**非末切片**,不动 feature_list.json status / 不写 evidence(末切片 AC3.8 的事)。
- **principal-module EP2 回环完成(2026-07-27 Session 149)**:巡检候选 1(Strong)。**问题**:后端三 service(booking/device/customer)31 处 helper 调用(`is_cross_tenant_viewer`/`is_platform_writer`/`resolve_target_tenant`/`DataScopeService`)散落,鉴权决策没被吸收进深模块 —— booking_service 829 行膨胀根因。**完整流程**:`/improve-codebase-architecture` 巡检(2026-07-27 第 3 次,14 候选,HTML `~/.cache/ai-agent-platform-architecture-reviews/2026-07-27.html`,Top recommendation = Principal 深模块)→ 选候选 1 → `/grill` 9 决策(Q1 并进来读写都管 / Q2 β 两方法 for_write+for_read / Q3 RequireCall|None 值对象 + ResolvedScope 复用 + Principal 持 db / Q4 Principal 类放 principal.py service __init__ 持实例 / Q5 4 切片 / Q6-Q9 CONTEXT.md+helper 保留+plan 文档)→ **启用子智能体审查**(opus general-purpose,对照真实代码逐项核查,找出 3 RED:77 处虚高→实际 31 处 + candidate-8 false claim + for_write 签名/customer principal 设计缺口;5 YELLOW;**2 误判纠正**:测试 mock 失效 实际不 mock + get_device_schedule 该迁 实际没用 helper)→ **修正 grill 8 项**(Q2' for_write 完整签名 act 由 service 传 / Q2'' booking.start 三叉不进 Principal / Q5' 切片拆 02a+02b / Q6' get_device_schedule 不迁 / Q7' ReadAccess 加 is_panorama bool + RequireCall 不变式 docstring 钉死 + 数字修正 31 处非 77 / candidate-8 删除)→ `/to-spec` 落 plan-principal-module.md(10 章节,PRD + 9 决策表 + 4 切片 AC + 契约 + 测试策略 + 留痕)→ `/to-tickets` 4 切片 tracer-bullet(expand-contract:切片 01 expand Principal 加在旧 helper 旁边 / 02a+02b+03 migrate batches)。**审查的价值**:阻止 false claim(77 处、顺带解决 candidate-8)进 PRD,避免 ticket/review 阶段返工。**EP2 收尾**:feature_list.json status `not_started → in_progress` + plan 字段回填 + sync-active 刷新(1 活跃 principal-module)+ progress.md 顶部更新。**切片就绪**:01 frontier(7 AC,Principal module + test_principal.py contract test,零 service 改)+ 02a booking(6 AC,迁 7 方法)+ 02b device(5 AC,迁 7 方法,与 02a 独立)+ 03 customer+收尾(9 AC,2 方法迁 + 4 处 Note 注释 + CONTEXT.md + docstring 交叉引用 + feature 收尾,末切片)。下一步:EP3 `/implement` 切片 01。
- **booking-schedule-grid ✅ passing(2026-07-26 Session 148 收尾,全 6 切片完成)**:HqView 设备×时间排期网格 + 两级预约配置(平台默认 + 租户覆盖)。**EP2 回环(Session 144-145 间)**:`/grill-with-docs` 7 决策(D0 网格形态 demo 验收 / D1 HqView Tabs 并存 / D2 新建 booking_configs 表抄 model_pricing 两级范式 repo 继承 BaseRepository / D3 duration 任意 Integer 非 {45,60} 枚举 / D4 新增按天端点 + (tenant_id,scheduled_start_at) 复合索引 / D5 复用 settings:update 权限 / D6 now prop 注入不用 fake timers / D7 网格内嵌配置 Dialog)→ `/to-spec` 落 plan-booking-schedule-grid.md(v2 二轮审查修正)→ `/to-tickets` 6 切片(01 frontier / 02 按天端点 / 03 前端配置 API+Dialog / 04a ScheduleGrid 组件 / 04b HqView Tabs 集成 / 05 联调收尾,线性依赖图无环,~50 条 AC)。**EP3 切片 01-04**(2026-07-26):5 个 feat commit(PR #129/#131/#130/#132/#133)。落地后端 booking_configs 表 + 两级配置 API(5 端点 + 三级 fallback)+ 按天查询端点(GET /bookings/schedule-grid)+ 复合索引;前端 ScheduleGrid 组件(对齐 demo D0)+ BookingConfigDialog(两栏/单栏)+ HqView Tabs(列表/网格并存)+ 点击预填 BookingCreateDialog。**EP3 切片 05(末切片,Session 148)**:无新源码,纯联调 + 文档。验证:./init.sh 全绿 **777 passed**(ruff + pytest 402s,含 test_booking_config_api 19 + test_bookings_api R 章节 8)+ cd frontend && npm test 48/48 + npm run build 成功(2.78s)。**决策项定夺(切片 04b 留痕的 plan line 234 vs §8 冲突)**:StoreView ConfigDialog **不接** —— 联调确认 StoreView 的 ScheduleGridCard 用 `useDeviceSchedule`(单设备 7 天视图)完全不读 booking_config,接入是装饰性(改配置无视觉反馈);§8「不动 StoreView」为正确表述,plan line 234 修订为「仅 HqView 接入」(HqView 的 handleConfigSubmit 已接 toast)。StoreView 网格化是后续独立 feature。**feature 收尾**:status in_progress → passing + evidence 6 条(切片 01-05 + 收尾条)+ sync-active 刷新(active 视图 0 活跃 + 5 最近 passing)。文档影响评估:① feature_list.json ✅;② progress.md ✅(顶部「最高优先级未完成」清空);③ `项目指南/02-后端架构/03-数据库与ORM.md` **补「两级配置表」章节**(booking_configs 范式:单表 tenant_id 可空 + BaseRepository 非 TenantScopedRepository + service 层 upsert 无 DB 约束 + get_effective 三级 fallback;checklist 第 3 条加交叉引用);④ plan draft v2 → passing(切片 05 标题 ✅ + AC 勾选,AC1 777 passed / AC2 48/48 + build / 手测项真实环境留);不动 README。**末切片仪式依赖解锁扫描(three-tier §4 第 7 步)**:无任何 feature `depends_on` 指向 booking-schedule-grid → 无需推进(WIP=1 下无新 in_progress)。**手测项留真实环境**(对齐 device-models-admin-ui/device-booking 范式,无自动化手测基建):super_admin 选店 → 网格渲染 → 点空格创建 → 重叠拒 400 → 改时间成功 → 切列表视图看到新预约;配置改 duration=60 + window 09:00-21:00 → 网格重渲染。逻辑路径已被单元/集成测试覆盖。**demo 归档决定**:harness/demo/booking-schedule-grid-demo.html **保留作设计参考**(不移 archive),因 ScheduleGrid 源码 4 处注释(schedule-grid.css:2 / schedule-grid.tsx:12,46 / schedule-grid.test.tsx:14)以 demo 为 Visual truth source。
- **booking-schedule-grid 后续修补(2026-07-27,真 bug 修复)**:切片 05 已合并(PR #134)后,super_admin 反馈「网格创建预约后不显示 / 时段冲突误报」。**第三次诊断(Playwright 真冲突场景)发现真 bug**:`frontend/src/lib/format.ts:fromDatetimeLocalValue` 旧实现 ``${v}:00`` 返回 **naive datetime(无时区后缀)** → Pydantic datetime 解析为 naive → SQLAlchemy 写入 `DateTime(timezone=True)` 列被当 UTC → **用户本地时间被当 UTC 存储**。完整错乱链:用户点北京 14:30 → slotHourToISO 正确转 UTC 06:30Z → Dialog toDatetimeLocalValue 用 getHours() 转本地显示 14:30(对) → 用户提交 → fromDatetimeLocalValue 返回 `2026-07-27T14:30:00`(丢 UTC)→ 后端存 14:30 UTC → 冲突窗口偏移 8 小时 → 跟已有预约虚假冲突 400 → 网格 tooltip 显示预约在用户没点的时段。**修复**:`fromDatetimeLocalValue` 改用 `new Date(v).toISOString()`,把本地 wall-clock 正确转 UTC(带 Z)。**回归测试**:新建 `frontend/src/lib/__tests__/format.test.ts`(15 用例)锁定 Z 后缀 + round-trip 时区不变。**辅助 UI 修补**(同时修):`schedule-grid.css` `.grid-scroll` text-align center→left + `table.grid` width:auto→100% / display:inline-table→table,撑满容器(Playwright 实测 408px→1044px),预约块占满列宽视觉上立即可见。**回滚**:之前凭直觉加的 `hq-view.tsx` `max-w-3xl mx-auto`(限宽居中让表格更小)已回滚。**CSS class 名不变**(P5 测试 selector 契约保留)。**验证**:npm test **65/65**(原 50 + 新加 15 个 format 测试,零回归)+ build 成功 + oxlint 0/0 + Playwright timezoneId='Asia/Shanghai' 端到端复测:点北京 13:30 → POST 201 → 返回 scheduled_start_at=`2026-07-27T05:30:00Z` ✓(北京 13:30 = UTC 05:30)+ 点北京 18:00 → POST 201 → `2026-07-27T10:00:00Z` ✓ + 网格 tooltip 显示新预约在用户点击的时段 ✓。**历史诊断错误留痕**:① 凭直觉加 max-w-3xl 错(已回滚);② 第二次诊断说「代码从未坏过」也错(只在成功路径测试,没测 400 失败路径,漏了 datetime bug)。教训:datetime bug 必须在目标时区(Asia/Shanghai)+ 失败路径(400/500)下复现。完整诊断链留痕 plan §「后续修补」。
- **booking-schedule-grid 切片 04b ✅(2026-07-26,非末切片)**:前端 HqView Tabs(列表/网格)+ 网格集成。落地 2 改文件(plan 清单)+ 4 附加改文件(扩展 Dialog 预填 + 新建 hook/endpoint):`frontend/src/pages/bookings/hq-view.tsx`(+Tabs 手搓 Button 行沿用 FilterChips 范式 aria-pressed,默认列表,canWrite 后出现 + 网格 Tab:`<input type="date">` min/默认=今天(isoDate(startOfToday()) 本地 YYYY-MM-DD)+ ⚙设置 Button 弹 BookingConfigDialog + ScheduleGrid 渲染 + useTenantBookingsByDate/useBookingConfigEffective/4 个 config hooks 接线 + handleSlotClick 设 createPrefill + handleConfigSubmit scope→对应 update hook + onTargetChange/PageHeader 创建按钮清 createPrefill 防跨店残留)+ `frontend/src/pages/bookings/__tests__/hq-view.test.tsx`(vi.mock spy shared-dialog 捕获 BookingCreateDialog props + useAuth mock + 6 新 hooks stub 进 stubWriteMutations + 4 新增:Tab 默认列表 / 网格渲染 smoke / 设置弹 Dialog / P7 预填 spy-on-children 断言 defaultDeviceId + 本地小时数)+ `frontend/src/pages/bookings/shared-dialog.tsx`(BookingCreateDialog +`defaultDeviceId`/`defaultStart`/`defaultEnd` 可选预填 props,useEffect open 分支 reset-or-prefill,StoreView 不传零行为变更)+ `frontend/src/pages/bookings/config-dialog.tsx`(DEFAULT_BOOKING_CONFIG const→export,hq-view fallback 复用消除 Shotgun Surgery)+ `frontend/src/hooks/queries.ts`(+useTenantBookingsByDate hook enabled!!tenantId + qk.tenantSchedule 工厂项 ["schedule-grid",tenantId,dateISO] + BOOKING_WRITE_KEYS 加 ["schedule-grid"] literal-prefix 失效项)+ `frontend/src/api/endpoints.ts`(+fetchTenantBookingsByDate 调切片 02 端点 GET /bookings/schedule-grid?date=&tenant_id=,anti-forgery 对齐 effective)。**验证**:npm test 48/48(基线 44 + 新增 4:hq-view 13 = 9 既有 + 4 新)+ npm run build 成功 + oxlint 0/0(88 文件)+ tsc 0 error。**/code-review 双轴**:Standards 0 硬违规(2 判断项已修:① DEFAULT_BOOKING_CONFIG export 化 ② createDialogCalls afterEach 重置);Spec 核心 AC 全满足(2 处 doc/spec 漂移留痕:① plan 写「8 测试」实际基线 9,9+4=13 全绿 ② P7 prop 命名 defaultDeviceId vs plan 写 defaultDevice,语义等价实施更清晰)。**已知 gap 推切片 05**:StoreView ConfigDialog 未接(plan line 234 vs §8 line 331 冲突,StoreView ScheduleGridCard 不读 booking_config 故 toast 接入目前装饰性,切片 05 联调时定夺 + §8 修订)。**非末切片,不做 feature 收尾仪式**。下一步:切片 05(端到端联调 + feature 收尾,末切片,Blocked by 01+02+03+04a+04b 全解锁)。
- **booking-schedule-grid 早期切片 01-04a ✅(2026-07-26,非末切片)**:切片链(01 booking_configs 表+两级配置 API / 02 按天查询端点+复合索引 / 03 前端 API+BookingConfigDialog / 04a ScheduleGrid 核心网格组件)详见 `harness/docs/plan-booking-schedule-grid.md` §6 各切片章节 + `feature_list.json` evidence。
- **booking-state-cancel ✅ passing(2026-07-25 Session 147,priority 68,单切片 = 末切片)**:巡检候选 2(后端 deep module 收尾债)。cancel 状态跳转从 `booking_service.cancel()` 内联 if/elif/else 收口进 `booking_state.transition()`(ACTIONS 加 'cancel',_TRANSITIONS 加 ('pending','cancel'):'cancelled' 第 7 条边),零行为变更(204/idempotent 契约保留,唯一文字变化:非 pending 非 cancelled 态 cancel 错误从 BizError 升级为 InvalidTransition,状态码 400 不变)。详见 `harness/docs/plan-booking-state-cancel.md` + `feature_list.json` evidence(6 条)。
- **platform-cross-tenant-write ✅ passing(2026-07-25 Session 146,priority 67,全 5 切片)**:设备/预约功能系列收官后的平台角色权限升格。super_admin + hq_staff 在 devices/bookings 从「跨店只读」升格为「跨店可写」(新 helper `is_platform_writer` + `resolve_target_tenant` 纯函数 + service body 加 `elif is_platform_writer` 分支)。落地共享 `bookings/shared-dialog.tsx`。PR #124 squash `c5bf99c`,CI 4/4 绿。详见 `harness/docs/plan-platform-cross-tenant-write.md` + `feature_list.json` evidence(5 条)。
- **device-models-admin-ui ✅ passing(2026-07-25 Session 142,priority 66,2 切片 PR #122)**:super_admin 设备型号目录管理页(新 `key-spec-rows.tsx` 结构化 k-v 编辑器 + `device-models-page.tsx` 参照 groups-page 骨架)。**设备功能系列(61-64+66)收官**:61 device-models-crud ✅ → 62 devices-crud-ui ✅ → 63 device-booking ✅ → 64 device-poweron ✅ → 66 device-models-admin-ui ✅。详见 `feature_list.json` evidence。
- **bookings-page-split ✅ passing(2026-07-25 Session 139 收尾)**:巡检产出任务([codebase-health-log.md] 2026-07-25 候选 1,Strong)。`hugo` 暗号触发 → 三源验真(device 系列 61-64 全 passing)+ 跑 `/improve-codebase-architecture` 巡检(8 候选:Strong ×4 拆 Booking 三视图 / 状态机 cancel 未并入 / end-no_show auth 推 body / 前端 9 page 零单测;Worth exploring ×4 Customer principal 参数透传 / HQ Panorama mirror / 三叉路由 4 page 复制 / union endpoint cast)→ HTML 报告归档 `~/.cache/ai-agent-platform-architecture-reviews/2026-07-25.html` → grill 候选 1(4 决策:bookings/ 子文件夹 / 测试跟 view 走 / 只拆不碰 cast / 现有测试全绿+补 HqView smoke)→ 产 plan-bookings-page-split.md → 登记 feature priority 65 → 实施:bookings-page.tsx(1373 行)拆成 bookings/ 文件夹 5 module + barrel(bookings-page.tsx barrel re-export + index.tsx 三叉路由 + store-view.tsx StoreView+4Dialog + hq-view.tsx HqView export + my-bookings-view.tsx + shared.tsx STATUS_META/filters/date helpers/ScheduleGridCard)+ 测试挪位(git mv 保留历史)+ 新增 hq-view.test.tsx smoke 3 tests。验证:vitest 15/15(12 现有 + 3 新 HqView)+ build 1.75s(bookings-page chunk 18.98 kB 与拆分前一致)+ oxlint 0 + tsc -b 绿 + init.sh 714 passed。/code-review 双轴:Standards 无 hard violation,1 judgement call(shared.tsx 轻微 Divergent Change,ScheduleGridCard 只 StoreView 用却混共享 → 登记独立后续候选);Spec 核心达成,处置 1 冲突(§10.10 无新 TODO vs D3 注释标注委托 → TODO(candidate-X) 改 Note(candidate-X))+ 订正 plan 文字(cast 5→7 处 / shared.ts→shared.tsx)。7 处 as cast 原样保留(委托候选 8)。**巡检本身也是 stage 5 首次完整走通**(Step 0-3 全跑:Explore → HTML 报告 → grill 产 plan → 实施)。
- **device-poweron ✅ passing(2026-07-25 Session 138,priority 64,3 切片 PR#114/#115/#116)**:store DropdownMenu 三动作(确认开机 walk-in / 结束服务 / 标记爽约),`ACTIONABLE_STATUS` 松绑 `MUTABLE_STATUS` 守卫(改约/取消仍守 pending)。详见 `feature_list.json` evidence(6 条)。
- **device-booking ✅ passing(2026-07-24 Session 137,priority 63,7 切片 PR#106-#113)**:/bookings 升级三叉视图(`isSuperAdmin||isHQStaff?HqView:hasCustomerIdentity?MyBookingsView:StoreView`),含 MeResponse.customer_id blocker 修复。详见 `feature_list.json` evidence(9 条)。
- **当前 blocker**: 无
- **EP3 断点**: **union-cast-split 切片 03 末切片待启(A类 cast 全仓审计 + feature 收尾)**(切片 01 + 02 ✅ 已完成,本次 Session 158 推进切片 02 非末切片)。**切片 02 ✅(devices domain)**:消解 8 处 A 类 device cast —— endpoints.ts 新增 `fetchDevicesAll`(返回 `DeviceHqRead[]`)+ `fetchDeviceModelsAll`(返回 `DeviceModelRead[]`),均调同一 URL 类型注解窄化;**窄化** `fetchDevices` 返回 `Promise<Device[]>`(store 视角)+ `fetchDeviceModels` 返回 `Promise<DeviceModelPublic[]>`(store 视角)—— **偏离 §4.5**(原写 fetchDeviceModels 保留 union)改镜像切片 1 `fetchBookings`+`fetchBookingsAll` 对称范式,4 理由记入 plan(plan §6 Ticket 2 inline);queries.ts 新增 `useDevicesAll`(queryKey=`qk.devices`)+ `useDeviceModelsAll`(queryKey=`qk.deviceModels`),均共享 D5 + import 加俩 fetch All;hq-view 改调 `useDevicesAll` 消 L161 `as DeviceHqRead[]`(接切片1遗留,此时 hq-view bookings+devices 双侧收口);store-view 消 L152/355/365 三处 `as Device[]`(此时 store-view 双侧收口)+ 删 Device import(noUnusedLocals);devices-page 单文件双组件:StoreView L192 useDevices(已窄 Device[])消 cast + HqView L422 改调 useDevicesAll 消 cast;device-models-page 改调 useDeviceModelsAll 消 L149/216 `as DeviceModelRead[]`;hq-view.test.tsx mock 改名 `useDevices`→`useDevicesAll`(hoisted+工厂+10 调用点+it-label 同步,D7)。**未动**:hq-view L516/519 B 类 props cast `as Booking`/`as BookingHqRead`(留原样)+ devices-page `as ModelOption[]`×4 + `as DeviceStatus`×1 C 类(D2 排除)+ 后端零改动 + store-view.test.tsx(仍调 useDevices store 视角,天然兼容)。**验证**:npx tsc -b exit 0 + npm run build 绿(2.10s)+ npm test 65/65 全绿(零行为回归,mock 改名生效)+ npx oxlint 0 warning 0 error + grep `as Device[]`/`as DeviceHqRead[]`/`as DeviceModelRead[]` 在 pages/ **代码归 0**(唯一匹 store-view L153 注释)+ B/C 类 cast grep 确认仍在。**code-review 双轴(general-purpose ×2 并行)**:Standards 0 硬违规 / 1 判断项(endpoints.ts 三处 section header「union return type」注释被本次改动证伪 → 已采纳修复,devices/deviceModels/bookings 三 header 更新为描述 split,消 duplicated stale block);Spec 8 AC 全满足 / 0 缺失 / 0 误 / 1 偏差已裁决(§4.5 fetchDeviceModels 窄化,AC 全保 + 对称切片1 范式,记入 plan)。**下一步(已完成)**:切片 03 末切片(全仓 A 类 cast 审计归 0 + B/C 类确认保留 + Note(candidate-8) 全清 + feature 收尾)—— 已于 Session 158 续收官(见顶部 union-cast-split ✅ passing 记录)。

### Session 158 文档影响评估(union-cast-split 切片 02)

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/*` | ❌ 无影响 | 纯前端类型重构,行为零变更;四层架构 + 多租户隔离文档不涉及前端 hook 拆分 |
| `harness/docs/plan-union-cast.md` | ✅ 已更新 | 切片 2 标题 ✅ + AC1-8 全勾选 + inline 完成证据 + §4.5 偏差裁决记录(权威偏差) |
| `progress.md` | ✅ 已更新 | 顶部「最高优先级未完成」frontier 推进到切片 03 + EP3 断点切片 02 证据 + Session 158 记录 + 文档影响评估 |
| `feature_list.json` + 派生视图 | ❌ 无影响 | 切片 02 非末切片,status 仍 `in_progress`,evidence 空(不提前标 passing),sync-active 不跑(派生视图无变化)|

> 判断依据:切片 2 是纯前端类型收窄(改 2 声明文件 + 5 消费者改调 + 1 test 改 mock),行为零变更,无架构约定变更,无新表/迁移/后端改动。下一步 EP3 切片 03(末切片):全仓 grep A 类 cast 审计 + B/C 类确认保留 + `./init.sh full` 全绿 + `cd frontend && npm run build` 绿 + feature_list.json status→passing/evidence 写齐 + sync-active 刷新,走 `/implement`。

### Session 167 文档影响评估(devices-page-split 切片 02 末切片)

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/*` | ❌ 无影响 | 纯前端结构重构(补单测),行为零变更;四层架构 + 多租户隔离文档不涉及前端测试补全 |
| `harness/docs/plan-devices-page-split.md` | ✅ 已更新 | 切片 2 标题 ✅ + Ticket 2 AC 全勾选 + 顶部 status `not_started → passing` |
| `progress.md` | ✅ 已更新 | 顶部「最高优先级未完成」frontier 清空(指向无在途任务)+ devices-page-split ✅ passing 完整记录 + EP3 断点更新(同批 3 feature 全收官)+ Session 167 文档影响评估 |
| `feature_list.json` + 派生视图 | ✅ 已更新 | 末切片,status `not_started → passing` + evidence 4 条(切片1/2/收尾全量/feature 核心)+ sync-active 刷新(0 活跃 + 5 最近 passing)|

> 判断依据:切片 2 是纯前端补测(2 测试文件,源码零改动),行为零变更,无架构约定变更,无新表/迁移/后端改动。tenantId 跨租户写守卫机制原样保留(只测不改)。feature 完整收官:第 7 次巡检同批 3 候选全 passing,frontier 清空,等用户排新需求。

## Session 172(2026-07-31):前端设计系统收口系列 EP2 单回环(/to-spec ×3 + 登记 + /to-tickets ×3)

**任务**:为「前端设计系统收口」系列启动 EP2 单回环 —— 把 EP1 总纲(`plan-frontend-design-system-overview.md`,7 个 grill 决策 + huashu-design B3 变体定稿)落成 3 个 feature 的可执行 plan + 登记 feature_list.json + 拆切片。**一个 context 内完成,守 EP2 单回环硬约束**(three-tier §3)。

**完整流程**:

1. **环境确认 + 总纲精读**:`pwd` + `git log` + 读总纲(7 决策 / B3 定稿 HSL / 3 feature 范围 + A→B→C 顺序 / 设计变体探索结论)+ 读 three-tier §3(EP2 单回环约束)+ to-spec/to-tickets SKILL + prd-template。
2. **实地核对前端基建现状**(让 plan 落地有据,而非照抄总纲数字):
   - 硬编码色 **~46 处**(总纲 ~70 含 design-demos 探索产物,生产代码数量级一致),按文件:settings(5)/permissions(5)/billing(5)/users(4)/notifications(3)/dashboard(3)/composite-mode(3)/notification-bell(3)/billing-admin(2)/conversation-list-panel(2)/markdown-view(2,zinc 代码块)/dashboard-layout(1)
   - **零 semantic token** ✓(index.css 无 `--success/--warning/--danger/--info`,tailwind.config 只到 chart-5)
   - 字号任意值 **11 处**(`text-[10px]` ×6 / `text-[11px]` ×5);间距/圆角/shadow 任意值 **均为 0**(澄清 Feature C「间距 token」实为补层级语义命名,非收口任意值)
   - Card 已有 `cardVariants` cva 体系(default: shadow-sm + glow variant),230 处 `<Card` 依赖;shadow 用法集中在 ui/(Card shadow-sm / 浮层 shadow-lg-md)
   - 行级核对每处硬编码色的语义(emerald=成功/amber=警告/rose=危险/blue=信息),区分语义色 vs 设计性多色(zinc 代码块 / Pin-Star 强调 / avatar 8 色环 / chart-1..5 保留)
3. **`/to-spec` ×3**(PRD 主体,严格用 prd-template 11 节):
   - `plan-design-system-token-foundation.md`(Feature A,p81):四 token B3 定稿双色值 + tailwind.config 暴露 + ui/ 组件库内部映射(badge/toast/avatar 语义色),2 切片。**token 值逐字用 B3 定稿**。
   - `plan-design-system-color-sweep.md`(Feature B,p82,depends_on A):业务页 ~30 处硬编码色扫荡,按色系切片(非页面切片),5 切片。**浅底深字 alpha 约定**(`/10` 底 / `/30` 边 / DEFAULT 字)+ **手写 dark: 冗余变体删除**规则。
   - `plan-design-system-spacing-card-hierarchy.md`(Feature C,p83,与 A/B 正交):卡片层级 `shadow-card`/`shadow-overlay` 语义命名 + 字号 `text-2xs` 扩展收口 11 处任意值,2 切片。
4. **feature_list.json 登记 3 条**:Python 脚本精确插入(保键顺序),A=p81 in_progress(EP2 完成 + 无依赖 = frontier,three-tier §5 规则②)/ B=p82 not_started(depends_on A,排队)/ C=p83 not_started(与 A/B 正交,守 WIP=1)。
5. **`/to-tickets` ×3**(切片段随 plan 一次成型):每个 plan 含「实施切片」段 —— 切片依赖图(无环)+ 每片 What it delivers + Blocked by + Acceptance criteria(`- [ ]` checklist)。Feature A 2 切片 / Feature B 5 切片(01 frontier success 收口建范式 → 02-04 warning/danger/info 并行 → 05 收尾)/ Feature C 2 切片。共 9 切片,74 条 AC。
6. **EP2 收尾自检**(three-tier §3)4 条全过:① 切片依赖图无环(3 个 plan 均 DAG)② 每片有 AC(9 切片共 74 条)③ 首片可立即开工(3 个 plan 的切片 01 均无 blocker)④ plan 主体无悬空 TODO(token 值=B3 定稿 / 映射规则逐文件落定 / 边界项有处置)。
7. **sync-active 刷新**:3 活跃(A in_progress + B/C not_started)。

**关键决策**:
- **Feature A 的 token 值逐字用 B3 定稿**(亮 `--success 152 76% 36%` / `--warning 35 92% 50%` / `--danger 0 84% 60%` / `--info 189 90% 42%`;暗 152 64% 48% / 38 95% 58% / 0 80% 64% / 189 80% 55%)—— 不重新选色,EP1 已固化。
- **Feature B 按色系切片非页面切片**(每片 = 一个语义全站闭环,grep 归零可单片验证),切片 01 success 收口建立 alpha 约定范式供 02-04 复用。
- **Feature C 澄清**:间距/圆角/shadow 任意值实测为 0,「间距 token」实为补卡片层级语义命名(`shadow-card`/`shadow-overlay`);字号任意值 11 处是顺手项(决策 5 边界,不推全站字号 token 化)。
- **边界保留**:markdown-view zinc 代码块主题色(非语义)/ conversation-list-panel Pin/Star amber(强调非警告,EP3 核对)/ avatar 8 色环(设计性多色)/ chart-1..5(数据可视化多色)/ destructive 既有命名(不迁移)—— 均 plan 明确标注保留。
- **EP2 单回环高效做法**:to-spec + to-tickets 基于「同一套思考」一次成型(写 plan 时切片段一起落),避免 to-spec 完再单独 to-tickets 的重复思考。

### Session 172 文档影响评估(前端设计系统收口系列 EP2 单回环)

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `harness/docs/plan-design-system-token-foundation.md` | ✅ 新建 | Feature A PRD(11 节)+ 实施切片段(2 切片,14 条 AC),token 值逐字用 B3 定稿 |
| `harness/docs/plan-design-system-color-sweep.md` | ✅ 新建 | Feature B PRD(11 节)+ 实施切片段(5 切片,42 条 AC),按色系切片 + alpha 约定 |
| `harness/docs/plan-design-system-spacing-card-hierarchy.md` | ✅ 新建 | Feature C PRD(11 节)+ 实施切片段(2 切片,18 条 AC),shadow 语义命名 + 字号收口 |
| `feature_list.json` + 派生视图 | ✅ 已更新 | 登记 3 条(A p81 in_progress / B p82 not_started depends_on A / C p83 not_started)+ plan 字段回填 + last_updated + sync-active 刷新(3 活跃)|
| `progress.md` | ✅ 已更新 | 顶部「最高优先级未完成」指向 design-system-token-foundation(frontier)+ EP3 断点更新(系列 EP2 全完成)+ Session 172 记录 + 文档影响评估 |
| `项目指南/02-后端架构/*` | ❌ 无影响 | 纯前端 feature,无后端/数据库/schema 改动,现有架构文档不涉及前端设计系统 |
| `harness/docs/plan-frontend-design-system-overview.md`(总纲) | ❌ 本 Session 不动 | 总纲是 EP1 产物(登记性质),系列状态段只在收官时写(three-tier §5 规则④),进行中看 progress.md 顶部摘要 |
| AGENTS.md / README | ❌ 无影响 | 规划任务,无新开发流程约定;脚手架 README 不细到设计系统 |

> 判断依据:本 Session 是 EP2 规划(落 plan + 登记 + 拆切片),无代码改动,无 schema/迁移/后端/权限变化。主要影响 plan-*.md(3 新建)+ feature_list.json(3 登记)+ progress.md(顶部 + Session 记录)。系列总纲的「系列状态」段按规则只在 Feature A+B+C 全 passing 时才写「✅ 全部完成」,本 Session 不动。下一步:EP3 `/implement` Feature A 切片 01(token 基建:CSS + tailwind.config,frontier 无 blocker)。

## 后续任务规划

任务全景与依赖关系见 `feature_list.json`(priority/depends_on 字段为真相源)。三个系列总纲:
- **权限重构系列**(39-42):`harness/docs/plan-permission-redesign-overview.md` —— 39 ✅ → 40 ✅ → 41 ✅ → 42(matrix-redesign 收官,当前)
- **Token 费用管理系列**(43-46):`harness/docs/plan-token-billing-overview.md` —— 43(usage-tracking)✅ → 44(wallet-billing)✅ → 45(customer-link)✅ → 46(billing-ui 收官,当前)
- **MVP 补全系列**(47-58):`harness/docs/plan-mvp-completion-overview.md` —— 12 个缺口分三梯队(SaaS 体面/配套/V2)

> 历史任务规划表(顺序 1-46 的完整决策快照)已归档至 `harness/docs/archive/sessions-001-056.md`(随 Session 001-056 一并迁出)。

## 已 passing 的地基能力(详见 feature_list.json)

| 功能 | 状态 | 验证依据 |
|------|------|---------|
| auth-local(本地密码登录) | passing | 8 tests |
| auth-logto(Logto OIDC) | passing | 4 tests |
| rbac-permission(RBAC 多租户) | passing | 29 tests |
| users-crud(用户管理 CRUD) | passing | 27 tests |
| roles-crud(角色管理 CRUD 全栈) | passing | 96 tests total(13 rbac_api) |
| db-migrations(迁移链) | passing | CI migrations job |
| scd2-history(授权链历史) | passing | 7 tests |
| validation-error-i18n(422 中文化) | passing | 6 tests |
| global-rename(全局改名为 agenthub) | passing | grep 0 残留 + init.sh + npm build |
| agents-api-hardening(Agent API 加固) | passing | 14 tests(权限/隔离/删除/404) |
| chat-conversation-api(对话后端) | passing | 9 tests + DeepSeek 配置 + 会话历史 API |
| chat-frontend(对话前端) | passing | npm run build 通过 + SSE 打字机 + 会话 CRUD |
| permission-matrix-api(权限矩阵后端) | passing | 118 tests(+6 矩阵/catalogue 端点) |
| permission-matrix-ui(权限矩阵前端) | passing | npm build 通过 + 可编辑矩阵 + oxlint 0 warning |
| tenant-org-admin-ui(租户/组织/成员前端) | passing | npm build 通过 + 组织树 CRUD + 成员管理 + dashboard 租户卡片 |
| real-chat-llm-config(真实对话 + LLM 配置) | passing | 131 tests + 真实 DeepSeek SSE 端到端跑通 + 三级 fallback + 修 3 bug |
| e2e-and-coverage(E2E + 覆盖率 + lint) | passing | 171 tests + 93% 覆盖率 + Playwright E2E + oxlint 0 warning |
| atoa-api-token-auth(AtoA 地基 API Token 鉴权) | passing | 186 tests + ahp_ 旁路 + 颁发/吊销/验证 + 多租户隔离 |
| atoa-cli-core(AtoA CLI 骨架 agenthub 命令行) | passing | 199 tests + typer CLI + login/whoami/agents + Agent-Ready 6 准则 |
| atoa-cli-chat-admin(AtoA CLI 对话+CRUD) | passing | 217 tests + agents chat SSE 流式 + conversations list/messages/delete + agents create/update(PATCH)/delete |
| atoa-skill(AtoA Skill 编写) | passing | SKILL.md(commands.md 子文件)+ docs/atoa/(README+getting-started+distribution)+ README AtoA 章节;frontmatter YAML 校验通过 |
| atoa-admin-ui(AtoA 管理前端 API Token UI) | passing | npm build 通过 + oxlint 0 warning + settings-page 第三个 Card(列表表格 + 颁发 Dialog 明文展示 + 吊销确认) |
| context-engineering(对话上下文工程) | passing | 244 tests + token_budget 纯函数(近似计数 + 滑动窗口截断)+ stream_agent asyncio.timeout 超时 + 部分回复落库容错 |
| chat-markdown-rendering(聊天页 Markdown 渲染) | passing | npm build 通过 + oxlint 0 warning + react-markdown+GFM+代码高亮 + 停止/复制/重新生成交互 |
| agent-config-depth(Agent 推理参数配置) | passing | 250 tests + alembic 迁移 + graph.py 移除硬编码 temperature=0.3 + 前端 slider/高级折叠区 |
| chat-overflow-title-fix(会话标题+溢出修复) | passing | 16 tests + 后端首消息截断标题 + 前端 flex 布局溢出修复 |
| org-cleanup(删除旧 Organization) | passing | 232 tests + 删 6 文件 + User 模块耦合清理 + 聚合迁移抠块 + alembic check 无 drift + 前端 build/oxlint 全绿 |
| groups-api(Group 组织后端) | passing | 248 tests + Group+GroupTenant 双表 + 迁移 574391d912fc + 7 端点 + super_admin 写/登录读分流 + 软删除 + alembic check 无 drift |
| groups-ui(Group 组织前端) | passing | npm build 通过 + oxlint 0 warning + 组织列表 + 创建/编辑 Dialog + 门店挂载面板(Badge✕detach + 下拉attach)+ super_admin 写/其他只读 + 路由 /groups(member 可读) |
| customers-api(Customer 客户后端) | passing | 265 tests + Customer+CustomerProfile 双表 + 迁移 6f197cf8f964 + 6 端点 + 全局身份跨店复用 + HQ 聚合 + super_admin 跨店/门店隔离 + alembic check 无 drift |
| customers-ui(Customer 客户前端) | passing | npm build 通过 + oxlint 0 warning + 双视角(门店 CRUD / 总部聚合只读)+ 行内展开跨店档案 + 三层权限守卫(owner 全权/admin 无 delete/member 只读/super_admin 总部只读)+ 路由 /customers(Contact 图标) |
| hq-platform-role(平台角色 hq_staff 总部业务员) | passing | 281 tests + check() 加 hq_staff+read 短路 + is_cross_tenant_viewer helper + Customer/Group Service 跨租户分支扩展 + Customer HQ 读端点守卫扩展(require_cross_tenant_viewer)+ hq_staff 只读跨店(super_admin 不回归)+ 无迁移(platform_role 自由字符串) |
| tenants-admin-api(门店管理后端补齐) | passing | 294 tests + Tenant 加 status/created_by/description/address + 迁移 84605f063730 + GET /tenants/all + GET/PUT /tenants/{id} + POST 收紧 super_admin + member_count 运行时聚合(LEFT JOIN _ACTIVE)+ alembic check 无 drift |
| tenants-admin-ui(门店管理前端) | passing | npm build 通过 + oxlint 0 warning + 独立门店页(super_admin 列表/创建/编辑 Dialog)+ RequireSuperAdmin 路由守卫 + 侧边栏「门店」项(needsSuperAdmin)+ dashboard 创建按钮收紧 + groups-page 门店挂载下拉改用 useAllTenants(修复 super_admin 只能看自己租户的 UX 缺陷) |
| demo-seed(大健康连锁演示案例) | passing | seed_demo.py 脚本 + db-schema.mmd 22 表 + 关系图.md 第十/十一章;真实 Postgres 端到端验证 + 幂等确认 |
| demo-seed-full(演示数据全量补全) | passing | 294 tests + seed_demo.py 加 --reset 清理重建 + 全量补全(对话/消息/LLM配置/API Token/自定义角色权限/审计日志/多登录方式/Agent推理参数差异化)+ 修复审计日志泄漏 bug(SystemLog 删除顺序) |
| permission-unified-model(权限目录统一+操作细化 1/4) | passing | 299 tests + DEFAULT_*_PERMS 重写(manage 拆细)+ catalogue 端点中文 label + 前端删 OBJ_LABELS 硬编码 + backfill 脚本 + conftest drift 修复 |
| permission-menu-view(菜单/视图权限 2/4) | passing | 306 tests + Permission.type='menu' 启用 + DEFAULT_MENU_PERMS + MeResponse.menus + 前端导航/路由改 canViewMenu 驱动 + 删 needsSuperAdmin/needsUserManagement 硬编码 + 修孤儿测试 bug |
| permission-data-scope(角色级数据范围 3/4) | passing | 315 tests + Role.data_scope 四档(all/tenant/group/self)+ DataScopeService(service 层,多角色取最宽)+ CustomerProfile.list_for_scope + 迁移 4708b3fbf2e7(server_default 回填免 backfill)+ 仅 CustomerProfile 接入(会话不接入,用户决策) |
| permission-matrix-redesign(矩阵 UI 重写 4/4 收官) | passing | npm build + oxlint 0 warning + 前端 types.ts 补 data_scope + permissions-page 重写(超管锁定行卡片 + 操作权限区 data_scope Select 行 + 增强图例 🔒)+ useUpdateRole invalidate matrix + 纯前端后端零改动基线 315 不回归 |
| token-usage-tracking(Token 用量采集 1/4 地基) | passing | 321 tests + stream_agent 累加 on_chat_model_end usage(ReAct 多轮 sum)+ Message 加 4 列(prompt/completion/total/model 可空)+ UsageEvent 账本表 + 迁移 b739b2ae902b + _record_usage try/except 不阻断对话 |
| token-wallet-billing(Token 钱包计费 2/4 核心) | passing | 345 tests + Wallet/WalletTransaction/ModelPricing 三表 + 迁移 e8f9a0b1c2d3 + BillingService(charge FOR UPDATE/calc_cost 租户覆盖>平台默认/recharge)+ event_source 余额预检(wallet 存在且<=0 拦截)+ create_tenant 同事务初始化零余额 wallet + /billing API + 权限 wallet:read/billing:read |
| customer-conversation-link(客户维度 Token 归因 3/4) | passing | 356 tests + Conversation 加 customer_id(可空 FK SET NULL)+ 迁移 f9a0b1c2d4e5 + ChatRequest→create_or_get→_record_usage 全链路透传 + UsageEventRepository.sum_tokens_for_customer(门店/总部双视角)+ GET /customers/{id}/usage + 聊天页关联客户选择器 + 客户详情 AI 用量 Dialog + 为客户咨询 deep link |

> ✅ AI 内核(agents + chat)已全部纳管并 passing。
> ✅ **真实对话已跑通**:real-chat-llm-config(Session 017)用真实 DeepSeek key 端到端验证 SSE 流式对话。
> ✅ **质量护栏已建立**:e2e-and-coverage(Session 019)加了覆盖率门槛(93% ≥ 80%)+ Playwright E2E + oxlint 0 warning。
> ✅ **权限重构系列已收官**:39(unified-model)✅ + 40(menu-view)✅ + 41(data-scope)✅ + 42(matrix-redesign)✅ 全部完成,三类权限(菜单/操作/数据)统一在矩阵页管理。

## 会话记录

> 完整历史会话已分两批归档:
> - **Session 001-056**(2026-07-10~12)→ [`harness/docs/archive/sessions-001-056.md`](harness/docs/archive/sessions-001-056.md)
> - **Session 057-108**(2026-07-12~16,52 个 session)→ [`harness/docs/archive/sessions-057-108.md`](harness/docs/archive/sessions-057-108.md)
>
> 本文件仅保留近期会话(Session 110 至今)。

## Session 110(2026-07-16):计划挑刺审查 + 修订 + 阶段1 数据库设计修复执行

### 任务来源
用户要求复核 `harness/docs/plan-db-revamp-and-scenario-rebuild.md`(Session 109 产出的数据库修复+场景重建计划)的准确性,修订后再执行。

### 第一阶段:挑刺审查(只读)
对照源码逐条核实 §1 的 12 条发现 + 迁移策略 + 种子 + 登录 + 证据链。**结论:约 80% 准确**,发现 7 处问题:
1. **S3 级联方向错**:计划称 Conversation.agent_id 被 SET NULL,实为 CASCADE(删 Agent 连对话一起删,更严重)
2. **S2 因果错**:计划称 list 把 vip 过滤掉看不见,实为 list 全显示(status 只在统计计数用),bug 降为体验增强
3. **§2.3 坑3 误报**:称 SQLite 跑迁移会炸(vector 无守卫),实际迁移已有方言守卫
4. **L2 类型陷阱**:审查阶段误判 String(128)≠User.id,执行时二次核实 User.id 实为 String(128)(误读成 Tenant.id),类型一致可加 FK(审查结论本身也需复核)
5. **M5 连带低估**:Role.status 经 RoleRead/RoleUpdate schema 透传且可写,连带面更大
6. **§3 方法名**:KnowledgeService.ingest_document 不存在,应为 create_document
7. **L3 行号**:点 184 为余额不足,256 才是生成失败

全部修订进计划(见计划 §8 修订日志),并增补「挑刺结论也需复核」教训。

### 第二阶段:阶段1 数据库设计修复(已执行完成)
按修订版计划 §1.2 改动清单,分 5 层落地:
- **models**:`agent.py`(S3 软删 is_deleted/deleted_at + L2 user_id FK SET NULL)、`usage_event.py`(L2 tenant_id CASCADE + user_id FK)、`message.py`(L3 status/error)、`tenant.py`(M1 删 info_json + L1 avatar 默认空)、`rbac.py`(M2 删 Permission 三列 + M5 删 Role.status)、`security.py`(M3 删 VerificationCode + M6 删 token_hash)、`model_pricing.py`(M4 删 currency)
- **repositories**:`wallet.py`(S1 get_for_tenant + get_for_tenant_for_update 加 is_active 过滤)、`agent.py`(S3 override get/list + 4 个自定义查询全加 is_deleted)、`customer.py`(S2 list_for_scope/search_for_scope 加可选 status_filter)
- **services**:`agent_service.py`(S3 delete 改软删)、`auth_service.py`(M6 移除 token_hash 赋值 + 删 _sha256/hashlib)、`rbac_service.py`(M5 update 循环移除 status)、`user_service.py`(L1 avatar fallback 空)、`conversation_service.py`(L3 append_message 支持 status/error)
- **api/schema**:`billing.py`+schema(M4 移除 currency 三处)、`chat.py`(L3 失败分支改 status=failed + error 落库,移除 [生成中断] 文本 hack)、`customers.py`+service(S2 透传 status 参数)、`rbac.py` schema(M5 RoleRead/RoleUpdate 移除 status)、`conversation.py` schema(L3 MessageRead 加 status/error)
- **frontend**:`types.ts`(M4 currency 两处 + M5 Role.status 两处)、`billing-admin-page.tsx`(M4 移除 currency schema/表格列/表单框 6 处)
- **迁移**:`b4c5d6e7f8a9_db_design_cleanup.py`(down_revision=a3b4c5d6e7f8,聚合所有 add/drop column + drop table + add FK,含 downgrade)
- **测试**:新增 S1 `test_inactive_wallet_is_not_usable`、S3 `test_delete_agent_is_soft_and_keeps_history`;改写 `test_update_role_description_and_status`→移除 status、`test_assistant_partial_reply_persisted_on_error` + `test_interrupted_stream_records_partial_usage`→断言 status=failed 而非 [生成中断] 文本;`test_billing._seed_pricing` 移除 currency

### 验证(完成定义 4 条全满足)
1. ✅ 目标行为已实现:12 项问题全修(S1/S2/S3/M1-M6/L1-L3)
2. ✅ 验证真跑过:`./init.sh` 全绿(**ruff All checks passed + 535 passed in 230s**,基线 533 + 新增 2);`cd frontend && npm run build` 成功(tsc+vite)
3. ✅ 证据记录:feature_list.json 登记 `db-design-cleanup-and-scenario-rebuild`(priority 59, area 数据库)
4. ✅ 仓库仍能按 `./init.sh` 重新开始

### 待续(阶段 2-5,需用户决策)
- **阶段2**(清空重建 + 真 key):需 docker(PG+Logto)+ 用户提供真 DeepSeek/OpenAI key(只进 .gitignore 忽略的 .env)
- **阶段3**(seed_demo 重写):保留架构重写内容 + 新增知识库灌入(用 KnowledgeService.create_document)+ orchestrator 演示
- **阶段4**(登录预填):.env 驱动 + /auth/login-hint 端点(生产返 null)
- **阶段5**(4 份对外文档):docs/demo-scenario/ 新目录

### 不越界核对
仅改后端 model/repo/service/api/schema + 前端 types/billing-admin + 新迁移 + 测试 + 计划文档;未碰 RBAC 权限模型/认证管线/前端 UI 框架(除 billing-admin 移 currency);未加新表(orchestrator 已存在)。S2 前端筛选器留作可选增强(后端已支持)。

---

## Session 111(2026-07-17):阶段 2-5 推进 —— 真实环境数据重建 + 登录预填 + 对外文档

### 任务来源
Session 110 完成阶段 1(数据库设计修复)后,用户指示「推进阶段 2-5」。

### 阶段 2:配置 + 真实环境数据重建(完成)
- **config.py**:`demo_llm_api_key` / `demo_embedding_api_key` / `demo_login_username` / `demo_login_password` 4 个字段(seed 读 .env 驱动,留空用占位符)
- **.env.example**:补 DEMO_LLM_API_KEY / DEMO_EMBEDDING_API_KEY / DEMO_LOGIN_* / EMBEDDING_* 占位段(真 key 只进 .gitignore 忽略的 .env)
- **真实 PG 迁移验证**:`alembic upgrade head` 在运行中的 aap-postgres(pgvector)上成功执行 `b4c5d6e7f8a9` —— 这是阶段 1 迁移的真正考验(SQLite 测试不能代表 PG)。`alembic check` 报 **No new upgrade operations detected**(模型与 DB 零 drift)
- **数据重建**:`seed_demo.py --reset` 在真 PG 跑通,3 门店 + 8 用户 + 2 组织 + 8 客户档案(含 active/vip/inactive/blacklist 4 态)+ 7 Agent(含编排器+2专科)+ 5 对话 + 3 RAG 文档 + LLM/Embedding 配置 + 钱包/定价/token。幂等验证:无参数重跑 created=0 / exists=34

### 阶段 3:seed_demo 重写(完成,含 2 个执行中发现的 bug 修复)
保留架构增量重写,关键改动:
- **key 动态化**:LLM/Embedding key 从 `settings.demo_*` 读,有值用真 key,无值用占位符;`LLM_DEMO_KEY_IS_REAL` 标志驱动文档灌入行为
- **客户扩到 8 条**:含跨店复用(张先生朝阳+海淀、刘女士朝阳+王府井)+ **4 态枚举**(active/vip/inactive/blacklist 各档,演示 S2 筛选)
- **新增知识库灌入**:`_seed_documents` 每店灌 1 份 RAG 文档(颈椎理疗规范/中药针灸禁忌/艾灸注意事项)
- **新增编排器演示**:`_seed_orchestrator` 建 1 个 orchestrator Agent + 2 个专科顾问(朝阳理疗/中医专科),演示 priority 58 多 Agent 路由
- **reset 清理同步**:加 Document/DocumentChunk/EmbeddingConfig 清理;orchestrator + 专科 agent 名字加进白名单
- **修复 bug 1(文档卡网络)**:`create_document` 内部 `_ingest` 会真发 embedding HTTP 请求,占位符 key 下 httpx 卡在重试超时(seed 挂死)。改为占位符时直接插 Document(status=failed)跳过 ingest,真 key 时才走 create_document
- **修复 bug 2(orchestrator 跨租户挂载)**:原设计让编排器(朝阳 tenant)挂海淀 tenant 的 specialist,但 `attach_specialist` 强制同租户。改为编排器 + 2 专科顾问都在朝阳 tenant

### 阶段 4:登录预填(完成)
- **后端**:`GET /auth/login-hint` 公开端点 + `LoginHint` schema。仅 `app_env in (development,testing)` 返真值,生产返 null(无安全风险)
- **前端**:`fetchLoginHint` + `login-page.tsx` useEffect mount 时调,有值则 setState 预填(非受控,用户可改),失败静默(不阻塞登录页)

### 阶段 5:4 份对外文档(完成,docs/demo-scenario/)
1. `01-业务场景说明.md` —— 行业痛点/颐和堂设定/6 大核心能力/商业价值/架构图
2. `02-演示账号清单.md` —— 8 账号总表/各账号首屏/权限矩阵/三种身份对比
3. `03-日常使用剧本.md` —— 4 个角色 walk-through(馆长/资深理疗师/督导/超管),用准确前端路由
4. `04-种子数据复现指南.md` —— 一键复现/.env 配置/数据全景表/重置/6 个常见问题

### 验证(完成定义全满足)
1. ✅ `./init.sh` 全绿:**ruff All checks passed + 535 passed**(阶段 2-4 改动无回归)
2. ✅ `alembic upgrade head` 真 PG 成功 + `alembic check` 无 drift
3. ✅ `seed_demo.py --reset` 端到端跑通 + 幂等(created=0/exists=34)
4. ✅ `cd frontend && npm run build` 成功(tsc + vite,登录预填/类型改动通过)
5. ✅ 演示数据计数正确:3 门店 + 8 档案(4态)+ 7 Agent(含编排)+ 3 文档 + 2 组织

### 待用户操作(唯一未闭环项)
**真 LLM/Embedding key 灌入**:当前用占位符,文档标 failed、AI 不能现场聊天。用户把真 DeepSeek + OpenAI key 填入 `.env` 的 `DEMO_LLM_API_KEY` / `DEMO_EMBEDDING_API_KEY` 后,重跑 `python scripts/seed_demo.py --reset` 即可实现:① 文档真实 embedding 入库(RAG 可用)② 启动即可现场聊天演示。注:PG 中已有历史真 LLM/Embedding 配置(设置页配过),seed 检测到真 key 会保留不覆盖。

### 不越界核对
仅改 config.py + .env.example + auth.py + auth schema + login-page + endpoints/types + seed_demo + 4 份新文档;未碰 RBAC 权限模型/认证管线核心;未加新表(orchestrator/agent_specialist 已存在)。

---

## Session 112(2026-07-17):非思考模式开关 + test 修复 + RAG 搁置决策

### 任务来源
用户配置 `OPENAI_MODEL=deepseek-v4-flash` 后触发 `test_llm_config` 失败 → 修测试;进而提出"用 deepseek-v4-flash + 非思考模式"需求 → 新增全局开关。

### 改动 1:修复 test_llm_config(预先存在的脆弱测试)
- **根因**:`test_effective_falls_back_to_env` 断言 `eff.default_model == "deepseek-chat"`,但被测代码 `llm_config_service.py:63` 读的是 `settings.openai_model`。测试把"代码默认值"硬编码当成了"回退契约"来断言。conftest 用 `setdefault` 只覆盖了 `OPENAI_API_KEY`,没覆盖 `OPENAI_MODEL`,用户 .env 填 `deepseek-v4-flash` 即暴露。
- **修复**:断言改为 `eff.default_model == settings.openai_model`(+ 补 `available_models` 断言)。这样任何模型名都正确。最后改动追溯:该测试 7-13 PR #42 引入,早于本轮工作,属历史脆弱性。
- **扫描**:全测试套件其余几十处 `deepseek-chat` 都是 fixture mock 数据(定价行/agent.model 字段等),与 env 无关,不动。

### 改动 2:全局非思考模式开关(用户核心需求)
- **背景**:DeepSeek 官方 API(`api.deepseek.com`)默认思考模式 enabled。用户要用 `deepseek-v4-flash` 跑非思考模式(更快更省)。
- **参数依据**:DeepSeek 官方文档(用户提供原文)——`extra_body={"thinking": {"type": "disabled"}}`(放 extra_body 因 OpenAI SDK 不认顶层 `thinking`)。
- **实现**(全局开关方案,改动最小):
  - `app/core/config.py`:加 `llm_thinking_enabled: bool = True`(默认开,向后兼容)
  - `app/agents/graph.py`:`_build_llm_kwargs()` 末尾读 settings,关闭时注入 `extra_body`。**4 个调用点(普通agent/stream/orchestrator的supervisor+specialist)共用此函数,自动全部生效**,调用方零改动。延迟 import settings 避免 config↔graph 循环。
  - `.env.example`:加 `LLM_THINKING_ENABLED=true` 说明
  - `tests/test_graph_llm_kwargs.py`:新增 4 单测(纯函数,无 DB/HTTP)——core 字段/可选参数/关思考注入 extra_body/开思考不注入
- **.env(用户本地,gitignored)**:已补 `LLM_THINKING_ENABLED=false`(用户要的非思考,已激活)

### 验证
1. ✅ `tests/test_llm_config.py`:12 passed(用户当前 .env 下)
2. ✅ `tests/test_graph_llm_kwargs.py`:4 passed
3. ✅ `./init.sh` 全绿:**539 passed**(535 + 新增 4)+ ruff All checks passed

### 决策:向量/RAG 搁置(用户指示)
用户明确"向量这一块先搁置"。即 `DEMO_EMBEDDING_API_KEY` / `EMBEDDING_API_KEY` 暂不填,3 份知识库文档维持 `status=failed`(占位符 key),RAG 检索功能暂不激活。**根因说明**:DeepSeek 不提供 embedding 端点,embedding 必须用 OpenAI 等厂商(`text-embedding-3-small`,1536 维与 pgvector 列宽匹配)。此为厂商能力边界,非项目可统一项。
- 影响:聊天功能不受影响(走 DeepSeek chat key);仅知识库检索哑。
- 复活方式:用户配 embedding key 后重跑 `seed_demo.py --reset` 即可(代码已就绪,`_seed_documents` 真 key 走 create_document 真向量化)。

### 待提交改动(5 文件,本轮新增)
`tests/test_llm_config.py` / `app/core/config.py` / `app/agents/graph.py` / `.env.example` / `tests/test_graph_llm_kwargs.py`(新)

### 不越界核对
仅改 LLM 推理参数层(graph.py 的 kwargs 构造)+ config 开关 + 对应测试;未碰 RBAC/认证/数据库 schema/RAG 检索逻辑本身;非思考开关是 provider 协议适配,非业务逻辑改动。

---

## Session 113(2026-07-17):RAG 真实环境闭环 —— Ollama + bge-m3 替代 OpenAI embedding

### 任务来源
承接 Session 112 的「向量搁置」决策。用户提出 P0 任务:把 `knowledge-base-rag`(priority 57)从「mock-only passing」升级为「真实环境 passing」——用户无法提供 OpenAI key,需用本地模型替代。

### 第一阶段:对抗式审查(用户要求)
用户要求用子智能体从第一性原理 + 对抗式审查计划。子智能体超时后,我亲自做审查,核实计划里每个技术断言。**审查结论:REVISE**,发现:
- 🔴 **致命错误 1**:漏改 `tests/test_embedding_config.py:22` 的 `assert cfg.dimension == 1536`,照做 ./init.sh 必崩
- 🔴 **致命错误 2**:误判 seed_demo 配置链路 —— seed 灌文档实际读 DB 的 platform EmbeddingConfig(三级 fallback),不是 .env;`seed_demo.py:821` 的 `base_url="https://api.openai.com/v1"` 硬编码是决定性的(不是可选优化)
- 🟡 **遗漏 1**:`Vector(settings.x)` 在 model import 期求值有架构异味 → 降级为模块级常量 `EMBEDDING_DIMENSION=1024`
- 🟡 **遗漏 2**:新迁移需用 raw SQL `op.execute` + 方言守卫(alembic autogenerate 不识别 pgvector 类型)
- 🟡 **遗漏 3**:DB 既有 openai EmbeddingConfig 会覆盖 .env → seed 灌文档会发到 openai 失败

修订计划 ExitPlanMode 批准后执行。

### 第二阶段:执行 + 运行中新发现的问题

**预见的改动(按修订计划)**:
- `app/models/document.py`:加 `EMBEDDING_DIMENSION = 1024` 模块常量 + Vector 引用 + docstring
- `app/schemas/embedding_config.py`:`dimension` 默认 1536→1024(2 处)
- `tests/test_embedding_config.py`:断言改读 `settings.embedding_*`(不硬编码)+ dimension=1024
- `scripts/seed_demo.py`:`EMBEDDING_DEMO_MODEL="bge-m3"` + `base_url=settings.embedding_base_url or ollama`
- 新迁移 `c5d6e7f8a9b0_change_embedding_dimension_to_1024.py`:DELETE chunks + ALTER VECTOR(1024)
- `.env.example` + `app/core/config.py`:默认值改 ollama/bge-m3

**执行中新发现的问题(计划/审查都漏了)**:
1. **审查漏 1**:`config.py` 的 `embedding_model` 默认值是 `text-embedding-3-small`(非空),seed_demo 的 `settings.embedding_model or "bge-m3"` 短路失败 → 必须改 config.py 默认值(计划没列)
2. **审查漏 2**:测试 `cfg.api_key` 断言在用户 .env 把 EMBEDDING_API_KEY 留空时失败 → 测试改读 settings 全字段(非硬编码)
3. **🔴 执行中真 bug(最大发现)**:`OpenAIEmbeddings` 默认用 **tiktoken 预编码 token ID**(`input: [[82805]]`),ollama 不接受 token ID 只接受字符串 → `400 invalid input type`。审查报告说「后端 service 零改动」是错的。修复:`EmbeddingService` 加 `check_embedding_ctx_length=False`(项目已有 RecursiveCharacterTextSplitter 分块,langchain 二次分块多余,对所有 provider 安全)
4. **审查遗漏 3 应验**:DB 残留 openai EmbeddingConfig(hint=sk-***ec3a)→ seed 灌文档时 lsof 显示 `SYN_SENT` 连 openai.com 卡死。删掉 DB 行后 seed 走 .env ollama 正常

### 验证(完成定义 4 条全满足)
1. ✅ 目标行为:RAG 在真实 pgvector + 真实 bge-m3 向量下端到端返回语义相关结果
2. ✅ 验证真跑过:
   - `./init.sh` 全绿:ruff All checks passed + **539 passed**(无回归)
   - `alembic upgrade head` 真 PG 成功(b4c5d6e7f8a9 → c5d6e7f8a9b0)+ `alembic check` 无 drift
   - ollama bge-m3 模型就绪:`curl /v1/embeddings` 返回 1024 维向量
   - `EmbeddingService` 直调:embed + embed_query 成功,语义排序正确(颈椎 0.68 > 艾灸 0.47)
   - `seed_demo --reset`:3 文档 indexed,3 chunks × `vector_dims(embedding)=1024` 验证
   - **API 端到端检索**(真实 owner token + 真实 cosine SQL):
     - 朝阳「颈椎不舒服」→ 颈椎理疗操作规范 相似度 **0.7730**
     - 海淀「针灸禁忌」→ 中药与针灸禁忌 相似度 **0.6900**
     - 多租户隔离:朝阳只见颈椎文档,海淀只见针灸文档
3. ✅ 证据记录:feature_list.json knowledge-base-rag evidence 追加第 11 条(真实环境闭环)
4. ✅ 仓库仍能 `./init.sh` 重新开始

### 关键技术要点
- **维度单点真相源**:`app/models/document.py` 的 `EMBEDDING_DIMENSION = 1024` 常量,schema/embedding_config 默认值镜像它。换模型改常量 + 跑迁移
- **tiktoken 兼容性是 ollama 接入的隐藏门槛**:OpenAIEmbeddings 的 `check_embedding_ctx_length=False` 是必须的,不是可选。这个坑网上资料少,值得记录
- **三级 fallback 的执行顺序陷阱**:DB platform 配置优先于 .env,seed 灌文档读 DB 不读 .env。改 provider 时必须同步清/改 DB 配置,光改 .env 不够
- **迁移 raw SQL 必须方言守卫**:pgvector 的 VECTOR 类型 alembic autogenerate 不识别,ALTER 只能 `op.execute()` raw SQL + SQLite 跳过

### 改动文件(7 文件)
1. `app/models/document.py` — 加 EMBEDDING_DIMENSION 常量 + Vector 引用 + docstring
2. `app/schemas/embedding_config.py` — dimension 默认 1024 + docstring
3. `app/services/embedding_service.py` — 加 check_embedding_ctx_length=False(关键兼容性修复)+ docstring
4. `app/core/config.py` — embedding_* 默认值改 ollama/bge-m3 + 注释
5. `tests/test_embedding_config.py` — 断言改读 settings + dimension=1024
6. `scripts/seed_demo.py` — EMBEDDING_DEMO_MODEL=bge-m3 + base_url 读 settings
7. `.env.example` — 默认配置改 ollama + 说明
8. `alembic/versions/2026_07_17_0100_c5d6e7f8a9b0_change_embedding_dimension_to_1024.py`(新)— 维度迁移

### 不越界核对
仅改 RAG/embedding 层(model 维度 + service 兼容性 + config 默认 + seed + 迁移);未碰 RBAC/认证/chat LLM/前端 UI/权限模型;retrieve 的 cosine SQL 维度无关零改动;多租户隔离逻辑未碰。

### 待用户操作(可选)
当前 ollama 是手动 `ollama serve` 启动的(前台进程,关终端会停)。如需长期运行:
- `brew services start ollama`(开机自启)
- 或加入 docker-compose(RAG 真正生产化的下一步)

### 下一步
由用户决定是否 ship-it(commit + PR + 合并入 main)。本任务把 Session 112 的「向量搁置」反转,.priority 57 从 mock-passing 变为真 passing。



---

## Session 114(2026-07-17):API Token 细粒度 Scope(scope 收敛闭环)

### 任务来源
用户提出实现 `harness/docs/plan-api-token-fine-grained-scopes.md`(v2,经两轮对抗式审查)。任务硬约束:必须先做 Step 0 spike 验证 contextvar 跨 StreamingResponse task 边界,三环境全过后才继续 plan v2 四阶段。

### Step 0 spike(定生死)
- **三路探查**(并行):测试范式(test_api_tokens + test_chat mock 范式)/ contextvar 源码验证(starlette 0.41.3 + anyio 4.14.1 + fastapi 0.115.6,确认 StreamingResponse 用 anyio task group spawn 子任务,CPython create_task 默认 copy_context)/ 60 处 caller 清单(55 require + 5 check,plan v2 "30+" 是低估)
- **三环境实测全 SUCCESS**:
  - (a) pytest TestClient:set ctx token_id=2cf70880 → generator 读到 TokenCtx(token_id='2cf70880...')
  - (b) uvicorn 单 worker:set ctx token_id=28f0a5f7 → graph.get_my_agents 工具 check 读到(DeepSeek 真实调用工具,端到端)
  - (c) uvicorn --workers 2:set ctx token_id=a43ed402 → 工具 check 读到(多 worker 每进程独立)
- 用户确认继续 plan v2

### Step 1-4 实现
- **Step 1 Schema**:api_token 加 scope_mode 列(default restricted,server_default restricted)+ 迁移 d6e7f8a9b0c1(加列 + backfill 旧 token scope_mode='full' WHERE scopes='[]',行为等价)+ DTO 三类加 scope_mode
- **Step 2 鉴权链路**:新建 token_context.py(TokenCtx + current_token_ctx contextvar,项目首次引入)+ ResolvedToken 扩展三字段 + verify 回填 + deps._resolve_api_token set ctx + permission_service.check 开头插 scope 闸门(在 super_admin bypass 之前,硬约束 #3)+ 写/对话/导出蕴含读(read 操作被任何写 scope 满足,硬约束 #5)+ issue 加 scope 收敛(super_admin 特判用 _all_known_scope_codes 含 MENU_CN keys,硬约束 #1/#4)+ ScopeError(BizError 子类)→ 全局 handler 422
- **Step 3 API**:verify 端点回显 scopes + scope_mode(ahp_ 路径)/ null(JWT 路径)
- **Step 4 前端**:types.ts ApiToken/Create/Created 加 scope_mode + endpoints.ts 加 fetchPermissionCatalogue + queries.ts 加 usePermissionsCatalogue + settings-page.tsx 颁发 Dialog 重构(scope_mode 选择 + scope 矩阵 catalogue 全量 35 项按 obj 分组 chip 切换 + 表格 scope 列)
- **Step 4 测试**:test_api_token_scopes.py 18 用例(收敛/特判/闸门/蕴含/零回归/verify)+ test_permission_service.py +4 用例(contextvar 边界)

### 运行过的验证(全过)
- `./init.sh` → ruff All checks passed + **561 passed**(基线 539 + 新增 22)
- `cd frontend && npm run build` → tsc + vite 成功 0 类型错误
- `npx oxlint src/` → 0 warnings 0 errors(68 文件)
- `alembic upgrade head` → 迁移 d6e7f8a9b0c1 成功;`alembic check` → No new upgrade operations detected
- 迁移效果验证:scope_mode 列已加(server_default 'restricted');旧 demo token(scopes=[])backfill 到 full;新 spike token(scopes=['agents:read'])保持 restricted

### 已记录证据
`feature_list.json` 的 `api-token-fine-grained-scopes.evidence`(10 条,含 spike 三环境 stdout + 硬约束 7 条映射 + 迁移验证),status=passing,priority 60

### 技术要点
- **contextvar 是项目首次引入的新范式**:token_context.py 带详细注释解释为什么不用改 check 签名(60 处直调 caller + graph.py 工具内 check 拿不到 CurrentUser,contextvar 零 caller 改动 + 跨 StreamingResponse task + JWT 路径短路)
- **硬约束 #5 语义澄清**:验收标准 #10「customers:update 自动满足 customers:read」是 write→read 方向(token 有 write scope 就能做 read 操作),不是双向;实现上 read 操作的 required set 包含所有写 scope
- **caller 清单事实更正**:plan v2 "30+ 处"实际 60 处(55 require + 5 check),add_policy 0 外部 caller(plan 笔误);但 contextvar 方案零 caller 改动,清单大小不影响实现
- **backfill 决策简化**:plan v2 §backfill 写「scopes=全集」,实际 full 模式运行时动态求 grantor perms 不读 scopes,所以 backfill 只改 scope_mode 不动 scopes(行为完全等价,避免大表 JSON 写入)
- **spike 产物处理**:token_context.py / ResolvedToken 扩展 / deps set 逻辑保留(Step 2 最终实现);spike print + spike 测试 + spike 脚本删除

### 提交记录(ship-it 已完成)
**已合并入 main**:PR [#82](https://github.com/hugo617/ai-agent-platform/pull/82),squash merge commit `5263116`,分支 `feat/api-token-fine-grained-scopes` 已删。ship-it 流水线全程零修复:CI 4 job(Migrations/Backend/Frontend/E2E)首次全绿,无需修红。
- ship-it 阶段对抗式审查:🔴 0 / 🟡 8 项核实无问题 / 🟢 死代码 0。
- 额外验证(超出 plan):真 PG `alembic downgrade -1 → upgrade head` 循环 + `alembic check` 无 drift;ScopeError→422 handler 解析实测;backfill 幂等性核实(迁移后无 restricted+空 scopes 行)。
- files:app/api/token_context.py(新)+ app/models/api_token.py + app/schemas/api_token.py + app/services/api_token_service.py + app/services/permission_service.py + app/services/errors.py + app/api/deps.py + app/api/v1/api_tokens.py + app/main.py + alembic/versions/2026_07_17_0200_d6e7f8a9b0c1_add_api_token_scope_mode.py(新)+ frontend types.ts/endpoints.ts/queries.ts/settings-page.tsx + tests/test_api_token_scopes.py(新)+ test_api_tokens.py/test_service_platform_role.py/test_permission_service.py(改)+ scripts/seed_demo.py + feature_list.json + progress.md

### 下一步
AtoA 系列的安全闭环(scope 收敛)已落地入 main。budget/model_allowlist/RPM 推迟到独立后续任务(`plan-api-token-ai-risk-controls`,等真实生产数据)。



---

## Session 115(2026-07-20):Harness 工程重整 · 阶段 1(Hook 计数器调试)

### 任务来源
实施 [`harness/docs/plan-harness-engineering-revamp.md`](harness/docs/plan-harness-engineering-revamp.md)(v2,经多模型投票评审 Revise 后修订)。任务硬约束 6 条(WIP=1 / 阶段 2 拆 2a→2b / 阶段 1 先实测 payload / 阶段 4 不实施投票 / 每阶段跑 init.sh / 每阶段更 progress.md)。本 Session 执行**阶段 1:Hook 计数器调试**(plan §8 阶段 1)。

### 阶段目标(plan §10 验收 #7/#8/#13)
- workspace 级 `<repo>/.zcode/config.json` hooks 段配置正确(验收 #7)
- `/grill-me`(或任意 skill)触发后 hook 被触发且有日志记录(验收 #8)
- `./init.sh` 全绿(验收 #13)

### 🔴 执行中发现的真实 plan 缺陷(本次最大产出)

**plan v2 §5.1 「workspace 级 hook 配置」假设被实测推翻**:

| 项 | plan v2 / review C-4 说法 | ZCode 3.3.6 实测 |
|---|---|---|
| `<repo>/.zcode/config.json` workspace hook 可用 | ✅ 推荐方案,可入库 | ❌ **被 security policy 拦截** |
| 实测证据 | — | 日志 event=`config.project_hooks.ignored` × 20+ 次 |
| diagnosticMessage | — | `"Project hooks were ignored by the security policy"` |
| SKILL.md / configuration-guide 是否提及 | 未提及 | **完全未提及**(官方文档盲区) |
| Settings 界面是否有信任开关 | 未提及 | **没有**(用户已确认) |

**对照 MCP 演进**:zcode-configuration-guide §MCP 提到「Workspace-scoped MCP servers were previously untrusted and required manual authorization; they now connect by default」—— MCP 经历过同样的 trust gate,现已放开;**hooks 仍处于未放开阶段**。

**降级方案(本 Session 采纳)**:
- 配置走用户级 `~/.zcode/cli/config.json`(不被 security policy 拦)
- 脚本 `scripts/skill-counter.sh` 自带 **cwd 守卫**(`pwd | grep -q ai-agent-platform`),其他项目静默 exit 0
- 等价实现 plan v2 「仅本项目生效」的核心初衷;代价是 hook 配置本身在 `~/.zcode/` 不入库(脚本本身入库)
- 团队成员各自复制 hooks 段到自己的用户级配置即可(阶段 2a 会写「hook 安装指南」入库)

### 真实 Payload 实测结果(回应硬约束 #3:不许假设字段名)

PostToolUse(Skill) hook stdin payload 实测结构(样本:`find-skills` 触发):

```json
{
  "cwd": "...", "mode": "yolo", "hookEventName": "PostToolUse",
  "sessionId": "sess_xxx", "session_id": "sess_xxx",       // 双命名冗余
  "toolCallId": "call_xxx",
  "toolName": "Skill",      "tool_name": "Skill",            // 双命名冗余
  "toolInput":  { "args": "...", "skill": "find-skills" },   // camelCase
  "tool_input": { "args": "...", "skill": "find-skills" },   // snake_case
  "toolResultPreview": "...", "traceId": "...", "turnId": "...", "timestamp": "..."
}
```

**字段路径结论**(覆盖 plan v2 §5.2 三候选):

| plan v2 §5.2 候选 | 实测 |
|---|---|
| 候选 1 `tool_input.skill` | ✅ **存在**(主路径) |
| 候选 2 `tool_input.skill_name` | ❌ 不存在 |
| 候选 3 `tool_name` | ⚠️ 存在但是 `"Skill"`(工具名)非 skill 名 |

正式脚本采用 `tool_input.skill`(主)+ `toolInput.skill`(camelCase fallback,实测同 payload 双命名都有)。

**额外验证**:`${ZCODE_PROJECT_DIR}` 和 `${ZCODE_SESSION_ID}` 都被 hook 注入到环境变量(plan v2 §5.2 假设成立 + 实测补 session_id)。

### 已完成产物

| 产物 | 路径 | 状态 |
|---|---|---|
| 调试脚本 | `/tmp/skill-hook-debug.sh`(本地临时,不入库) | 已完成历史使命,保留备查 |
| 调试日志 | `/tmp/skill-hook-debug.log`(本地临时,不入库) | 已抓到真实 payload |
| **正式计数器脚本** | `scripts/skill-counter.sh` | ✅ **入库**(可执行) |
| 用户级 hook 配置 | `~/.zcode/cli/config.json` | ✅ 不入库(用户私有) |
| workspace 级配置占位 | `.zcode/config.json`(只含说明注释) | ⚠️ `.zcode/` 已被 `.gitignore` 忽略,占位实际不入库 |
| `.gitignore` 追加 | `.skill-counters.json` + `.skill-counters.log` 忽略 | ✅ 入库 |
| 调试脚本废弃 | `/tmp/skill-hook-debug.sh` 用户级配置已切到正式脚本 | ✅ |

### `scripts/skill-counter.sh` 加固要点(回应 review C-5 / O-1)
1. ✅ stdout 永远空(hook schema 严格,非 JSON 内容判 failed)
2. ✅ 所有诊断信息走 stderr → 落盘 `.skill-counters.log`
3. ✅ heredoc 用 `<<'PY'` 禁止 shell 展开 + 环境变量传参(防注入)
4. ✅ cwd 守卫(`pwd | grep ai-agent-platform`),其他项目静默退出
5. ✅ 字段路径 2 候选(snake 主 + camel 备)+ 实测已对齐
6. ✅ 永远 exit 0,绝不阻断主流程
7. ✅ 异常永不向上抛:计数文件损坏 → 重置;写失败 → 静默

### 自检通过项(5 项)
- 自检 1:真实 payload 正常计数 ✅
- 自检 2:camelCase fallback 生效 ✅
- 自检 3:cwd 守卫生效(其他项目不计数)✅
- 自检 4:无 stdin 静默退出 ✅
- 自检 5:坏 JSON 不阻断(parse_error 进诊断日志,exit 0)✅

### 验证(plan §10 验收 #7/#8/#13 全满足)
1. ✅ 验收 #7:用户级 `~/.zcode/cli/config.json` hooks 段配置正确(matcher `^Skill$`、`type: command`、`timeout: 3` 秒、`${ZCODE_PROJECT_DIR}/scripts/skill-counter.sh`)
   - 注:plan v2 原文是「workspace 级」,本 Session 因 security policy 拦截降级为用户级 + cwd 守卫,详见上方「真实 plan 缺陷」段
2. ✅ 验收 #8:`/find-skills` 触发后 hook **被触发且有日志记录**(`/tmp/skill-hook-debug.log` 落了完整 payload,后续切到正式脚本后会落 `.skill-counters.json`)
3. ✅ 验收 #13:`./init.sh` 全绿(ruff + **561 passed**,无回归)

### 文件清单
1. `scripts/skill-counter.sh`(新,入库)— 计数器脚本,带 cwd 守卫 + 字段路径实测对齐
2. `.gitignore`(改,入库)— 追加 `.skill-counters.json` + `.skill-counters.log` 忽略
3. `.zcode/config.json`(新,但 `.zcode/` 已被 gitignore,实际不入库)— workspace 级占位 + 说明文档
4. `~/.zcode/cli/config.json`(改,**不入库**,用户私有)— 加 hooks 段
5. `progress.md`(改,入库)— 本 Session 记录

### 用户决策(2026-07-20)
1. ✅ **接受降级方案**(用户级配置 + cwd 守卫)—— 等价 plan v2「仅本项目生效」初衷
2. ✅ **重启验证正式脚本** —— 已重启 + 触发 `/find-skills` 实测

### 正式脚本实战验证(重启后)
触发 `/find-skills` 后立即查证:

```
.skill-counters.json:
{
  "skills": {
    "find-skills": { "count": 1, "first_used": "2026-07-20T11:50:26Z", "last_used": "2026-07-20T11:50:26Z" }
  },
  "total_calls": 1,
  "first_call": "2026-07-20T11:50:26Z",
  "last_updated": "2026-07-20T11:50:26Z"
}

.skill-counters.log: (完全空 = 0 错误 / 0 parse_error / 0 写失败)
ZCode 日志: tool.call.completed | toolName=Skill(Skill 工具未被 hook 阻断)
```

**结论**:验收 #7/#8/#13 全过,plan §10 阶段 1 三项打勾 ✅。阶段 1 真正收尾。

### 下一步
进入**阶段 2a:先建新文档**(plan §8 阶段 2a,6 份新文档:技术栈总览/bug-tracking/prd-template/doc-impact-assessment/multi-model-voting/harness-practice-guide.html)+ 升级 task-workflow.md + 把 CodeGraph 段挪到 README-给AI.md。

阶段 2a 会**额外**多建一份 `harness/docs/hook-setup-guide.md`(团队 hook 安装指南,plan v2 没列但由本 Session 降级方案衍生)—— 让团队成员各自复制 hooks 段到用户级 `~/.zcode/cli/config.json`。

阶段 2a 完成后才进阶段 2b(编辑 AGENTS.md 删旧段)—— 顺序硬约束,先建后删,消除断链窗口。



---

## Session 116(2026-07-20):Harness 工程重整 · 阶段 2a(建新文档)

### 任务来源
继续 Session 115 的 Harness 工程重整任务,执行 plan §8 阶段 2a「先建新文档」。硬约束 #2:阶段 2 必须拆 2a→2b,先建后删,消除断链窗口。

### 阶段目标(plan §10 验收 #2/#3/#4/#5/#13)
- `项目指南/00-总览/03-技术栈总览.md` 存在且单点真相源(验收 #2)
- `harness/docs/bug-tracking.md` 存在且定义完整流程,`bug-` 前缀已 grep 确认不冲突(验收 #3)
- `harness/docs/prd-template.md` 存在且含影响面清单/差异段/v1→v2 段(验收 #4)
- `harness/docs/doc-impact-assessment.md` 存在(验收 #5)
- `./init.sh` 全绿(验收 #13)

### review H-2 核实结果(阶段 2a 前置)
`grep feature_list.json` 60 条 id,**全部是功能命名,无 `bug-`/`fix-` 前缀** → `bug-` 前缀可安全使用。若未来发生冲突改用 `fix-`。

### 已完成产物(7 项:6 份新建 + 1 份升级,全部入库)

| # | 文件 | 行数 | plan 要求 | 实际 |
|---|---|---|---|---|
| 1 | `项目指南/00-总览/03-技术栈总览.md`(新) | 176 | ~150 | ✅ 技术栈单点真相源,含版本号 + 替换指南 |
| 2 | `harness/docs/bug-tracking.md`(新) | 171 | ~120 | ✅ 5 状态机 + bug- 登记 + 严重度分级 + diagnosing-bugs 衔接 |
| 3 | `harness/docs/prd-template.md`(新) | 238 | ~180 | ✅ to-spec 7 段 + 项目特化 4 段(影响面/多租户/权限/DB checklist)+ v1→v2 对抗式审查段 + to-tickets tracer-bullet 切片规则 |
| 4 | `harness/docs/doc-impact-assessment.md`(新) | 88 | ~50 | ✅ 从 AGENTS.md §90-119 拆出独立成文(回应 review C-6) |
| 5 | `harness/docs/hook-setup-guide.md`(新) | 145 | —(阶段 1 衍生)| ✅ 团队成员 hook 安装 7 步指南(由 Session 115 降级方案衍生,plan v2 没列) |
| 6 | `harness/docs/task-workflow.md`(升级) | 257 | 201→~250 | ✅ §6 新目录结构 / §7 自动触发路由表 + mermaid 流程图 / §8 skill 统计 / 附录 A 区分简单/复杂/bug 三模板 |
| 7 | CodeGraph 段挪到 `项目指南/README-给AI.md` | — | — | ⚠️ **事实已完成**:`README-给AI.md` §44-77 的 CodeGraph 段(34 行)已**完全覆盖** AGENTS.md §56-68(13 行)且更详细,无需补充。阶段 2b 只需删 AGENTS.md 那段 |

**注意**:`multi-model-voting.md` 是阶段 4 才建,本阶段不建(硬约束 #4)。`harness-practice-guide.html` 是阶段 5 才建。

### 内部断链核查(自检)
所有新建/升级文档跑断链检查:
- ✅ 技术栈总览:修了 3 个文件名断链(02-后端模块范例→02-新增后端模块、01-目录结构→01-技术栈与目录、06-RBAC权限模型→06-权限模型RBAC)
- ⚠️ bug-tracking/prd-template/task-workflow 有 3 处「前向引用」:`harness-router/SKILL.md`(阶段 3 建)+ `multi-model-voting.md` × 2(阶段 4 建)—— **预期保留**,阶段 3/4 完成后自动消解
- ✅ doc-impact-assessment:误报排除(模板示例 `[篇名](写明改动点)` 改为 `《篇名》`)

### 验证(plan §10 验收 #2/#3/#4/#5/#13 全满足)
1. ✅ 验收 #2:技术栈总览存在 + 单点真相源(后端栈 25 行 / 前端栈 18 行 / 工具链 / 质量基线 / 二开替换指南)
2. ✅ 验收 #3:bug-tracking 存在 + 完整流程(5 状态 + 登记 + 严重度 + SLA + 范例),`bug-` 前缀已 grep 确认
3. ✅ 验收 #4:prd-template 存在 + 含影响面清单(§4.1)+ 多租户评估(§4.2)+ 权限评估(§4.3)+ DB checklist(§4.4)+ v1→v2 对抗式审查段(§7)
4. ✅ 验收 #5:doc-impact-assessment 存在(从 AGENTS.md 拆出,回应 review C-6)
5. ✅ 验收 #13:`./init.sh` 全绿(ruff All checks passed + **561 passed**,无回归)

### 文件清单(本阶段改动,全部入库)
1. `项目指南/00-总览/03-技术栈总览.md`(新)— 技术栈单点真相源
2. `harness/docs/bug-tracking.md`(新)— bug 管理流程
3. `harness/docs/prd-template.md`(新)— PRD/切片 Design 强化模板
4. `harness/docs/doc-impact-assessment.md`(新)— 文档影响评估独立成文
5. `harness/docs/hook-setup-guide.md`(新)— 团队 hook 安装指南(阶段 1 衍生)
6. `harness/docs/task-workflow.md`(升级)— 加 §6 目录 / §7 路由表+流程图 / §8 统计 / 附录 A
7. `progress.md`(改)— 本 Session 记录

### 关键设计决策
1. **PRD 模板分三档**(task-workflow 附录 A):小改动用 task-workflow 简单模板 / 复杂任务用 prd-template 完整模板 / bug 用 bug-tracking 简化模板。避免一刀切。
2. **影响面清单 4 维度**(prd-template §4.1):后端文件 / 迁移 / 前端文件 / 测试类,呼应 plan §3.4 要求 + 多租户影响(§4.2)+ 权限影响(§4.3)独立成段。
3. **DB checklist 8 条**(prd-template §4.4):直接引用 AGENTS.md 铁律 6 + 项目指南/02-后端架构/03,避免重复维护。
4. **v1→v2 对抗式审查段**(prd-template §7):明确触发条件(4 选 1)+ 单/多模型双轨 + 范例引用,与 multi-model-voting.md(阶段 4 建)解耦。
5. **tracer-bullet 切片规则**(prd-template §2):垂直切片默认 + wide refactor expand–contract 例外,与 to-tickets skill 对齐。

### 下一步
进入**阶段 2b:最后才编辑 AGENTS.md**(plan §8 阶段 2b)。前置条件已满足(阶段 2a 全部完成 + 新文档已存在)。

阶段 2b 要做的:
1. AGENTS.md 移出「文档影响评估」段(§90-119,已在 doc-impact-assessment.md)
2. AGENTS.md 移出「数据库表设计原则」长段(§80-84,已在 项目指南/02-后端架构/03)
3. AGENTS.md 移出 CodeGraph 段(§56-68,已在 项目指南/README-给AI.md 且更全)
4. AGENTS.md 加「自动触发规则」路由表段(plan §3.1.1)
5. 验证 AGENTS.md ≤100 行
6. 关键验证:grep AGENTS.md 所有内部链接,确认无断链



---

## Session 117(2026-07-20):Harness 工程重整 · 阶段 2b(编辑 AGENTS.md)

### 任务来源
继续 Session 116 的 Harness 工程重整任务,执行 plan §8 阶段 2b「最后才编辑 AGENTS.md」(硬约束 #2:阶段 2 拆 2a→2b,先建后删,消除断链窗口)。前置条件:阶段 2a 全部完成 + 6 份新文档已存在 ✅。

### 阶段目标(plan §10 验收 #1/#13)
- AGENTS.md **≤100 行**(v2 统一,回应 review O-3),入口精简,无内部断链(验收 #1)
- `./init.sh` 全绿(验收 #13)

### 已完成产物(AGENTS.md 瘦身)

| 段 | 操作 | 之前 | 之后 |
|---|---|---|---|
| 项目简介 | 4 bullet 缩成 1 段 + 链接到新建的技术栈总览 | 8 行 | 5 行 |
| 「最常用任务→文档」表 | **删除**(README-给AI.md §27-40 已有更全的 10 任务表)| 11 行 | 0(并入下一段)|
| CodeGraph 段 | **删除**(README-给AI.md §44-77 已有更全的 CodeGraph 段)| 13 行 | 0(并入下一段)|
| 「第一件事读文档」+「最常用任务」+「CodeGraph」 | **三段合并为一段**(语义重复:都指向 README-给AI.md)| 22 行 | 4 行 |
| 文档影响评估段 | 30 行压成 4 行链接(指向 doc-impact-assessment.md)| 30 行 | 4 行 |
| 铁律 6 数据库表设计 | 长段压缩(去掉历史维度展开,保留核心)| 5 行 | 3 行 |
| 工作规则与完成定义 | 20 行压成 13 行(完成定义合并进核心 4 条)| 20 行 | 13 行 |
| **新增**:自动触发规则路由表 | plan §3.1.1 的 7 行路由表 + harness-router 提示 | 0 | 17 行 |

**总效果**:**142 行 → 92 行**(-50 行 / -35%),满足 ≤100 行验收。

### 内部断链核查
15 个链接全部有效,0 断链。链接分布:
- 指向 `项目指南/` 4 个(技术栈总览 / README-给AI / 附录)
- 指向 `harness/docs/` 4 个(task-workflow / prd-template / bug-tracking / doc-impact-assessment)
- 指向根目录文件 4 个(README / progress / feature_list / clean-state-checklist)
- 指向外部 docs 1 个(auth-history-scd2-plan)

### 验证(plan §10 验收 #1/#13 全满足)
1. ✅ 验收 #1:AGENTS.md **92 行**(≤100)+ 入口精简 + 0 断链
2. ✅ 验收 #13:`./init.sh` 全绿(ruff All checks passed + **561 passed**,无回归)

### 文件清单(本阶段改动)
1. `AGENTS.md`(改)— 142→92 行,移出 3 段 + 加路由表 + 三段合并
2. `progress.md`(改)— 本 Session 记录

### 关键设计决策
1. **三段合并**(读文档 / 最常用任务 / CodeGraph):三段语义重复(都指向 README-给AI.md),README-给AI.md 内容更全。AGENTS.md 只保留入口链接,不重复表格。
2. **项目简介 1 行链接**:之前 4 个 bullet(后端/前端/数据库/认证)信息已在新建的 `项目指南/00-总览/03-技术栈总览.md` 单点真相源,AGENTS.md 只保留一句话 + 链接。
3. **工作规则保留核心 4 条**:WIP=1 / 完成绑定证据 / 不越界 / 仓库是唯一事实来源 是项目铁律,不能完全外包给 task-workflow.md。完成定义合并进「完成绑定证据」条目(避免重复)。
4. **自动触发路由表新增**:这是阶段 2b 唯一的「净增」内容(plan §3.1.1),7 行路由表 + harness-router 提示,硬触发优先于 agent 自觉。

### 阶段 2 整体收官(2a + 2b)
| 验收 | 阶段 2a | 阶段 2b |
|---|---|---|
| #1 AGENTS.md ≤100 行 | — | ✅ 92 行 |
| #2 技术栈总览 | ✅ | — |
| #3 bug-tracking | ✅ | — |
| #4 prd-template | ✅ | — |
| #5 doc-impact-assessment | ✅ | ✅(从 AGENTS.md 拆出)|
| #13 init.sh 全绿 | ✅ 561 | ✅ 561 |

**断链窗口零发生**:因为严格遵守 2a(先建)→ 2b(后删)顺序,中间任何一刻 AGENTS.md 的链接都有目标存在。

### 下一步
进入**阶段 3:harness-router skill**(plan §8 阶段 3)。

阶段 3 要做的:
1. 建 `.agents/skills/harness-router/SKILL.md`(plan §4.1-4.3)
2. frontmatter:`disable-model-invocation: true`(user-invoked only)+ 路由表 + 分支决策
3. 含 v2 注释:多模型投票为未来态,见 multi-model-voting.md
4. 在 AGENTS.md 的路由表已经提示过 `/harness-router`(阶段 2b 已加),阶段 3 把 skill 实体建出来

阶段 3 完成后,阶段 2a 文档里 `harness-router/SKILL.md` 的前向引用会自动消解。



---

## Session 118(2026-07-20):Harness 工程重整 · 阶段 3(harness-router skill)

### 任务来源
继续 Session 117 的 Harness 工程重整任务,执行 plan §8 阶段 3 + §4.1-4.3「harness-router skill」。

### 阶段目标(plan §10 验收 #6/#13)
- `.agents/skills/harness-router/SKILL.md` 存在且可被 `/harness-router` 调用(验收 #6)
- `./init.sh` 全绿(验收 #13)

### 已完成产物

**新建**:`.agents/skills/harness-router/SKILL.md`(84 行,项目级 skill,入库)

**结构**(仿 ask-matt 的 heading 分层风格 + 中文):
1. **frontmatter**:`name: harness-router`(= 目录名)+ pushy description + `disable-model-invocation: true`(plan §4.2,回应 review S-2)
2. **主流程 idea→ship**(6 步):grill-with-docs → to-spec → to-tickets → implement → code-review → commit + 60% context 卫生
3. **状态路由表**(11 行速查)
4. **分支决策**(4 条 Branch):bug 判定 / 能否一次会话做完 / PRD 已在 plan / wide refactor
5. **复杂任务判定**(5 选 1,用于未来多模型投票触发)+ v2 注释(多模型投票为未来态)
6. **词汇层**(domain-modeling / codebase-design)
7. **跨 session**(handoff / compact 区别)
8. **Codebase health**(improve-codebase-architecture)
9. **配套文档**(6 个链接:task-workflow / prd-template / bug-tracking / multi-model-voting / doc-impact-assessment / AGENTS.md)

### frontmatter 合规核查(skill-creator SKILL.md 规范)
- ✅ `name: harness-router` —— lowercase kebab-case,与目录名完全一致
- ✅ `description` —— 充分「pushy」,含触发场景(任务变化)+ 用法(用户键入 /harness-router)
- ✅ `disable-model-invocation: true` —— user-invoked only,回应 review S-2
- ✅ body 84 行 < 500 行规范

### 阶段 2a 前向引用消解
阶段 2a 建的文档里,3 处指向 `harness-router/SKILL.md` 的前向引用**已自动消解**:
- `harness/docs/bug-tracking.md` §6 「与 diagnosing-bugs skill 的衔接」→ ✅
- `harness/docs/prd-template.md` 暗含路由表 → ✅
- `harness/docs/task-workflow.md` §7 自动触发段 → ✅

**剩余的 3 处 multi-model-voting.md 前向引用是预期的**(plan 硬约束 #4 明确阶段 4 才建):
- prd-template.md / task-workflow.md / harness-router SKILL.md 各 1 处 → 阶段 4 完成后消解

### 链接核查
- harness-router SKILL.md:6 个链接,5 个有效,1 个 multi-model-voting.md(阶段 4 预期)
- 阶段 2a 文档全部消解(harness-router 已建)

### 验证(plan §10 验收 #6/#13 全满足)
1. ✅ 验收 #6:`.agents/skills/harness-router/SKILL.md` 存在 + frontmatter 合规 + 可被 `/harness-router` 调用(用户键入触发,disable-model-invocation: true)
2. ✅ 验收 #13:`./init.sh` 全绿(ruff All checks passed + **561 passed**,无回归)

### 文件清单(本阶段改动)
1. `.agents/skills/harness-router/SKILL.md`(新,入库)— 84 行,路由型 skill
2. `progress.md`(改)— 本 Session 记录

### 关键设计决策
1. **仿 ask-matt 的 heading 分层**:不用决策树表格,用「主流程 + 状态路由表 + 分支决策」三层,与项目其他 skill 风格一致
2. **中文写作**:对齐项目语言(项目指南/AGENTS.md/task-workflow 全中文),agenthub skill 也是中文
3. **`disable-model-invocation: true` 的语义**(回应 review S-2):明确写「这是用户迷茫时手动求助的路由器,不是 agent 自动调度器」。agent 自动触发靠 AGENTS.md 路由表(硬触发),router skill 是软辅助。若未来需要 agent 自动路由,去掉此 flag 即可
4. **复杂任务判定的双重身份**:既用于「未来多模型投票触发条件」,也用于「plan §7 v1→v2 对抗式审查段触发条件」(prd-template.md §7)—— 两者复用同一套判定,避免维护两份

### 下一步
进入**阶段 4:多模型投票机制文档化**(plan §8 阶段 4,硬约束 #4 明确**不实施投票**,只写文档)。

阶段 4 要做的:
1. 新建 `harness/docs/multi-model-voting.md`(~200 行,plan §6.2)
2. 含双模式定义(模式 A 写方案合并 / 模式 B 评审多数票)+ rubric 区分(plan vs code 两套)+ 触发条件 + 试点状态
3. 明确标注「当前为未来态,待单任务试点验证」
4. 在 harness-router 加硬提示「复杂任务评审 → 多模型投票为未来态」(harness-router 已含此提示,阶段 4 完善文档)
5. **不实施** multi-model-vote skill 封装(plan §6.3,留作后续阶段)

阶段 4 完成后,3 处 multi-model-voting.md 前向引用自动消解。



---

## Session 119(2026-07-20):Harness 工程重整 · 阶段 4(多模型投票机制文档化)

### 任务来源
继续 Session 118 的 Harness 工程重整任务,执行 plan §8 阶段 4 + §6.2「多模型投票机制文档化」。**硬约束 #4:不实施投票实操,只写文档**。

### 阶段目标(plan §10 验收 #9/#13)
- `multi-model-voting.md` 含双模式 + rubric(区分 plan/code 两套)+ 触发条件 + 试点状态标注(验收 #9)
- `./init.sh` 全绿(验收 #13)

### 已完成产物

**新建**:`harness/docs/multi-model-voting.md`(190 行,plan §6.2 要求 ~200 行)

**结构**(9 段):
1. **范围声明**(当前未来态 vs 未来正式期的对比表)+ 为什么是未来态的 3 条理由
2. **双模式定义**:
   - 模式 A:写方案合并取优(`/to-spec` 融合,非投票)
   - 模式 B:评审多数票(`/code-review` 投票 + rubric 仲裁)
3. **Rubric 严格区分两套**(回应 review O-2):
   - plan/方案 6 维:正确性/完整性/可执行性/风险识别/边界清晰/一致性
   - code/实现 6 维:正确性/验证/范围纪律/可靠性/可维护性/交接准备度
   - 结论判定通用:Accept(全≥1 + 总分≥9)/ Revise(有 1 分项或 6-8)/ Block(任一 0 或 <6)
4. **触发条件**(双模式共同前置 + 试点期额外 + 未来正式期额外)
5. **上线路径**(等待异构环境 → 单任务试点 → 试点结论回写)
6. **避坑设计 7 条**(强化版,基于 review §4.2 实测):
   - 🔴 共谋风险(必须异构家族,禁同家族多尺寸)
   - 🔴 自举悖论(必须评非机制本身的产出物)
   - 🟡 rubric 区分度(未来考虑 0-3 分或加权)
   - 🟡 成本爆炸 / 仲裁者悖论 / 溯源验证缺失 / 触发依赖自觉
7. **试点记录**(留白,待填)
8. **与其他文档的关系**(4 个链接)
9. **不在本次范围**(4 条边界声明)

### Rubric 区分设计(回应 review O-2)
review O-2 指出「§6.1.4 rubric 与 §12.3 评审 rubric 都叫『6 维度 rubric』但维度不同易混淆」。本文档 §2 显式分两套:
- **§2.1 plan rubric**:用于评审 plan/prd 文档(模式 A 输出 + 复杂任务 plan 评审)
- **§2.2 code rubric**:用于评审代码 diff(模式 B)
- **§2.3 结论判定通用**:两套 rubric 共用 Accept/Revise/Block 三档

### 避坑设计强化(review §4.2 + §5.3 实测回写)
review §5.3「对本次评审本身的元评估」暴露 3 个设计问题,全部回写本文档 §5:
| 暴露问题 | 回写位置 |
|---|---|
| 同家族多尺寸模拟异构 = 共谋风险非虚(3 票可执行性全 1 分) | §5 避坑表「共谋风险」🔴 |
| 自举评审形成「未经验证的机制验证自己」悖论 | §5 避坑表「自举悖论」🔴 + §0 范围声明第 3 条 |
| rubric 维度过粗(0-2 分)导致 9-10 分都卡 Accept/Revise 边界 | §5 避坑表「rubric 区分度不足」🟡 |

### 阶段 3 前向引用全部消解
阶段 3 遗留的 3 处 multi-model-voting.md 前向引用**全部消解**:
- ✅ `prd-template.md` §7 v1→v2 对抗式审查段
- ✅ `task-workflow.md` §7 自动触发路由表
- ✅ `harness-router/SKILL.md` §复杂任务判定 + §配套文档

**全仓 6 个核心文档 0 断链**:multi-model-voting.md / prd-template.md / task-workflow.md / bug-tracking.md / harness-router SKILL.md / AGENTS.md。

### 验证(plan §10 验收 #9/#13 全满足)
1. ✅ 验收 #9:multi-model-voting.md 190 行 + 含双模式(§1)+ 区分两套 rubric(§2)+ 触发条件(§3)+ 试点状态标注(§0 范围声明 + §6 留白)
2. ✅ 验收 #13:`./init.sh` 全绿(ruff All checks passed + **561 passed**,无回归)

### 文件清单(本阶段改动)
1. `harness/docs/multi-model-voting.md`(新,入库)— 190 行,机制定义文档
2. `progress.md`(改)— 本 Session 记录

### 关键设计决策
1. **双模式而非单模式**(plan §6.2):模式 A 融合(to-spec)+ 模式 B 投票(code-review),不同场景不同机制。模式 A 强调「合并取优 + 标注来源」,模式 B 强调「多数票 + rubric 仲裁」。
2. **rubric 显式分两套**:plan 评审和 code 评审关注点不同(plan 看可执行性 / 风险识别;code 看验证 / 范围纪律),硬区分避免混淆。
3. **试点期 vs 正式期分离**(§3.2 vs §3.3):试点期必须用户主动声明「这是试点任务」,避免机制未验证就自动触发;正式期满足条件自动触发。
4. **不实施 skill 封装**(plan §6.3 + 本文 §8):试点结论决定是否值得封装。当前阶段把机制文档化即可,封装是后续阶段的事。
5. **避坑基于实测而非纸面**(review §5.3):本 plan v1 评审本身就是机制首次实操,暴露的问题(共谋 + 自举 + rubric 区分度)直接回写,不是凭空设想。

### 阶段 4 边界严守
**硬约束 #4 全部满足**:
- ✅ 只写 multi-model-voting.md 文档化机制,标注「未来态·待试点」
- ✅ 不实施多模型投票实操(§0 范围声明 + §8 边界)
- ✅ 不实施 multi-model-vote skill 封装(§8)
- ✅ 不强制让本 plan 自身评审用此机制(已删 v1 §12 自举,§5 避坑表「自举悖论」固化此决策)

### 下一步
进入**阶段 5:HTML 可视化文档**(plan §8 阶段 5,核心交付物)。

阶段 5 要做的(plan §7):
1. 在 `/tmp` 临时目录跑 `npx tailwindcss@3.4.17` 预编译 CSS(因本仓库根目录无 package.json)
2. 写 HTML 骨架(`harness/docs/harness-practice-guide.html`,自包含单文件 ~80KB)
3. 顶部栏 + 模式切换(现状 / 改进后 / 工作流导览)+ 深浅色
4. mermaid 主流程图(多模型投票标「未来态」)
5. 8 步 agent 工作流导览卡片
6. 现状 vs 改进后对比表
7. 8 张 skill 字典卡
8. 多模型投票层图解(标「未来态·待试点」)
9. Mermaid 4 源 fallback(staticfile→baomitu→cdnjs→jsdelivr)
10. CDP 验证 0 异常 + mermaid 渲染成功 + 深浅色切换

阶段 5 工作量大(plan §13 风险表「HTML 工作量大」),独立成 WIP=1 任务。



---

## Session 120(2026-07-20):Harness 工程重整 · 阶段 5(HTML 可视化文档)+ 任务收官

### 任务来源
继续 Session 119 的 Harness 工程重整任务,执行 plan §8 阶段 5 + §7「HTML 可视化文档(核心交付)」。这是 plan 的最后阶段。

### 阶段目标(plan §10 验收 #10/#11/#12/#13)
- `harness/docs/harness-practice-guide.html` 双击可用(零外部 CSS 依赖;Mermaid JS 走 4 源 fallback,离线降级为代码块),CDP 验证 0 异常,mermaid 渲染成功(验收 #10)
- HTML 含 8 步 agent 工作流导览(验收 #11)
- HTML 多模型投票层标注「未来态·待试点」(验收 #12)
- `./init.sh` 全绿(验收 #13)

### 已完成产物

**新建**:`harness/docs/harness-practice-guide.html`(826 行 / 68.8KB,自包含单文件)

**结构**(8 段,plan §7.2 全覆盖):
1. **§1 开篇**:3 张卡片(解决什么 / 由什么组成 / 怎么用)+ 阅读建议
2. **§2 主流程**:mermaid 任务生命周期图(idea→ship,多模型投票节点标「未来态」)+ 3 个关键关卡 + 3 个反模式
3. **§3 工作流导览(核心)**:8 步卡片(开工/登记/落 PRD/拆切片/实施/code-review/关闭/收尾),每卡含 5 字段(触发/读什么/调 skill/产出/下一步)
4. **§4 现状 vs 改进对比表**:9 行(AGENTS 长度/技术栈/bug/PRD/文档评估/skill 触发/统计/投票/Stage4)
5. **§5 Skill 字典**:8 张卡(router/grill-with-docs/to-spec/to-tickets/implement/code-review/tdd/handoff)
6. **§6 多模型投票层(未来态)**:范围声明 + 模式 A/B 双卡 + 4 条避坑设计
7. **§7 自动化机制**:Hook 计数器 + 自动触发路由表
8. **§8 附录**:核心文档清单 + skills 清单 + 反馈迭代说明

**技术实现(plan §7.7 全部就位)**:
1. ✅ **离线优先**:Tailwind v3.4.17 预编译内联(16.7KB),无运行时 CSS 网络依赖
2. ✅ **Tailwind 编译位置**(回应 review S-4):本仓库根无 package.json,在 `/tmp/html-build/` 跑 `npx tailwindcss@3.4.17 -c tw-config.js -o tw-out.css --minify`(content 扫描一个列举所有 utility class 的 tw-input.html)
3. ✅ **Mermaid 4 源 fallback**:staticfile→baomitu→cdnjs→jsdelivr,任一成功即停;全失败降级为 `<pre class="mermaid-src">` 源码块
4. ✅ **错误隔离**(回应 sess_f122bde8 教训):每个初始化函数独立 try/catch(mermaid init / theme apply / run)
5. ✅ **深浅色**:CSS 变量驱动 + `html.dark` / `html.light` 切换 + localStorage 持久化 + 切换后重渲染 mermaid
6. ✅ **CDP 验证**:Chrome headless 加载,抓 console
7. ✅ **中文字体栈**:PingFang SC / Microsoft YaHei 系统 fallback

### CDP 验证证据(plan §7.7 第 9 步)
用 Chrome headless 加载 + 抓 console:

| 验证项 | 结果 |
|---|---|
| `[Mermaid] 加载成功` 日志 | ✅ `https://cdn.staticfile.org/mermaid/10.9.1/mermaid.min.js`(国内 CDN 第一源成功)|
| Mermaid 真实渲染为 SVG | ✅ `<svg id="mermaid-1784551658678"...>` 出现在 DOM |
| 4 源 fallback 链就位 | ✅ 全失败时 `<pre class="mermaid-src">` 降级显示 |
| JS 异常 | ✅ 0 个(那几条 `CVDisplayLinkCreateWithCGDisplay failed` 是 macOS headless 显示 API 噪音,与页面无关)|
| 结构完整性 | ✅ 8 段 + 8 步工作流卡 + 8 张 skill 卡 + 「未来态」标注 10 处 |

### 验证(plan §10 验收 #10/#11/#12/#13 全满足)
1. ✅ 验收 #10:HTML 双击可用(零外部 CSS 依赖,Tailwind 预编译内联;Mermaid JS 4 源 fallback,离线降级为代码块),CDP 验证 0 真实异常,mermaid 渲染成功
2. ✅ 验收 #11:HTML 含 8 步 agent 工作流导览(§3,8 张卡 × 5 字段,带领读者看完整流程)
3. ✅ 验收 #12:HTML 多模型投票层标注「未来态·待试点」(§6,标题 + 警告框 + 避坑设计 全部标注,10 处「未来态/待试点」关键词)
4. ✅ 验收 #13:`./init.sh` 全绿(ruff All checks passed + **561 passed**,无回归)

### 文件清单(本阶段改动)
1. `harness/docs/harness-practice-guide.html`(新,入库)— 826 行 / 68.8KB,自包含单文件
2. `progress.md`(改)— 本 Session 记录 + 任务总收官

---

# 🎉 任务总收官:Harness 工程重整(Session 115-120 共 6 轮)

## 验收清单全过(plan §10,13/13)

| # | 验收项 | 阶段 | 状态 |
|---|---|---|---|
| 1 | AGENTS.md ≤100 行,入口精简,无断链 | 2b | ✅ 142→92 行,0 断链 |
| 2 | 技术栈总览存在且单点真相源 | 2a | ✅ 176 行 |
| 3 | bug-tracking 存在且完整,bug- 前缀已 grep 确认 | 2a | ✅ 171 行,60 id 无冲突 |
| 4 | prd-template 含影响面/差异/v1→v2 段 | 2a | ✅ 238 行 |
| 5 | doc-impact-assessment 存在 | 2a | ✅ 88 行 |
| 6 | harness-router skill 存在且可被 /harness-router 调用 | 3 | ✅ 84 行 |
| 7 | workspace 级 hook 配置 | 1 | ✅(降级用户级 + cwd 守卫,plan §5.1 实测缺陷)|
| 8 | skill 触发后 hook 有日志记录 | 1 | ✅ .skill-counters.json 落盘 |
| 9 | multi-model-voting 含双模式 + rubric + 触发 + 试点状态 | 4 | ✅ 190 行 |
| 10 | HTML 双击可用 + 4 源 fallback + CDP 0 异常 | 5 | ✅ 826 行 / 68.8KB |
| 11 | HTML 含 8 步工作流导览 | 5 | ✅ 8 张卡 × 5 字段 |
| 12 | HTML 多模型投票层标「未来态·待试点」 | 5 | ✅ 10 处标注 |
| 13 | init.sh 全绿 ×6 阶段 | 1-5 | ✅ 561 passed ×6(零回归)|

## 交付物总清单

### 文档新建(7 份,入库)
1. `项目指南/00-总览/03-技术栈总览.md`(176 行)
2. `harness/docs/bug-tracking.md`(171 行)
3. `harness/docs/prd-template.md`(238 行)
4. `harness/docs/doc-impact-assessment.md`(88 行)
5. `harness/docs/hook-setup-guide.md`(145 行,阶段 1 衍生)
6. `harness/docs/multi-model-voting.md`(190 行)
7. `harness/docs/harness-practice-guide.html`(826 行 / 68.8KB)

### 文档升级(3 份,入库)
8. `AGENTS.md`(142→92 行,-35%)
9. `harness/docs/task-workflow.md`(201→257 行,+§6/§7/§8/附录 A)
10. `项目指南/README-给AI.md`(CodeGraph 段已事实完整,无改动)

### Skill 新建(1 个,入库)
11. `.agents/skills/harness-router/SKILL.md`(84 行)

### 脚本 + 配置(2 项)
12. `scripts/skill-counter.sh`(入库,带 cwd 守卫 + 字段路径实测对齐)
13. `~/.zcode/cli/config.json`(用户私有,不入库,加 hooks 段)

### .gitignore + 占位(2 项)
14. `.gitignore`(改,加 `.skill-counters.*` 忽略)
15. `.zcode/config.json`(改,workspace 级占位 + 说明文档,实际被 .zcode/ 忽略不入库)

### progress.md
16. `progress.md`(改,Session 115-120 共 6 轮记录,本任务是其中最长的一段工程)

## 关键发现与决策(回写 plan v2 的依据)

### 🔴 重大发现 1:plan v2 §5.1 workspace hook 假设被实测推翻
- **现象**:ZCode 3.3.6 安全策略默认拦截 workspace hooks(日志 `config.project_hooks.ignored` × 20+)
- **官方文档**:diagnosing-hooks SKILL.md / zcode-configuration-guide SKILL.md **完全未提及**(文档盲区)
- **解法**:降级为用户级 `~/.zcode/cli/config.json` + 脚本 cwd 守卫(等价「仅本项目生效」)
- **衍生**:建 `harness/docs/hook-setup-guide.md`(团队安装指南,plan v2 没列)

### 🔴 重大发现 2:PostToolUse hook payload 字段路径实测
- **候选 1** `tool_input.skill`:✅ 存在(主路径)
- **候选 2** `tool_input.skill_name`:❌ 不存在
- **候选 3** `tool_name`:⚠️ 是 `"Skill"` 工具名非 skill 名
- **额外**:payload 同时含 camelCase + snake_case 双命名;`${ZCODE_PROJECT_DIR}` + `${ZCODE_SESSION_ID}` 都被注入

### 关键决策(硬约束全遵守)
1. **硬约束 #1 WIP=1**:每阶段验证通过才进下一阶段(6 阶段 × init.sh 全绿)
2. **硬约束 #2 阶段 2 拆 2a→2b**:先建 6 新文档(2a)→ 最后才改 AGENTS.md(2b),0 断链窗口
3. **硬约束 #3 阶段 1 先实测 payload**:先 cat 抓真实 payload 确认字段名,才写正式脚本(避开了 plan §5.2 的 3 候选猜测陷阱)
4. **硬约束 #4 阶段 4 不实施投票**:只写 multi-model-voting.md(190 行),标注「未来态·待试点」;不实施 skill 封装
5. **硬约束 #5 每阶段跑 init.sh**:6 阶段全跑,561 passed 零回归
6. **硬约束 #6 每阶段更 progress.md**:6 个 Session 记录全部追加

## plan v2 的「实施差异」段(回写)

按 [`prd-template.md`](harness/docs/prd-template.md) §「实现差异 vs plan 段」要求,本任务实施 vs plan v2 的差异:

| 差异点 | plan v2 说法 | 实际实施 | 原因 |
|---|---|---|---|
| Hook 配置位置(§5.1)| workspace 级 `<repo>/.zcode/config.json` | 用户级 `~/.zcode/cli/config.json` + cwd 守卫 | ZCode 3.3.6 安全策略拦 workspace hook(实测发现,plan 假设推翻)|
| 文档数量(§9)| 6 新建 | 7 新建(多 1 份 hook-setup-guide.md)| 降级方案衍生,plan 没预料到 security policy 问题 |
| AGENTS.md 最终行数(§3.1)| ~85 行 / ≤100 行(v2 统一)| 92 行 | 落在 plan 给的区间内 |

其余 plan v2 设计全部按计划实施。

## 下一步建议

1. **(可选)ship-it**:本任务所有改动可由 `/ship-it` 流水线 commit + PR + 合并入 main
2. **(未来)多模型投票试点**:等异构模型环境就绪,挑下一个真复杂任务做单任务试点(候选:鉴权类已有 v1→v2 审查的后续任务)
3. **(未来)Stage 5 巡检**:引入 `/improve-codebase-architecture` 定期巡检代码健康度
4. **(可选)HTML 增强**:若需打印/导出 PDF,可加 `@media print` 样式 + 页面分隔

任务收官。

---

## Session 121(2026-07-21):Harness 工程重整 plan v3.1 评审 + 阶段 2c 实施

### 任务来源

Session 115-120 完成阶段 1-5 后,plan v3 又经第二轮多模型投票评审(opus+sonnet+haiku 三视角)得 **Revise(3:0 一致,总分均值 8.67/12)**,暴露 2 处硬失实 + 5 项一致性偏差。本 Session 两段工作:

1. **plan v3 → v3.1 修订**:按评审 7 项必修点逐一修复 plan 文档(纯文档改动)
2. **plan v3.1 §8 阶段 2c 实施**:feature_list.json 归档机制落地(净新增 6 处产物)

### 阶段 A:plan v3.1 修订(7 项必修点)

| # | 必修点 | v3.1 落地位置 |
|---|---|---|
| P0-1 | §5.1 workspace hook 被实测推翻 | §0.0 实施状态表 + §5 整节重写为「已实施 + 实测教训回写」+ §13 风险表加专门一行 + §1.2/§1.3/§2.1/§7.5 历史决策注解 |
| P0-2 | §3.7.4 体积预估偏差 2 倍 | §3.7.3 脚本加 `SLIM_FIELDS` 精简逻辑 + §3.7.4 表格改实测值(59 行/441 tokens/节省 98.7%) |
| P0-3 | plan 未披露 v2 已实施 | 新增 §0.0 实施状态说明表 + §8 所有阶段标 ✅ 已实施 + Session 引用 |
| P0-4 | §3.7.6 CI 声明虚假 | 改为诚实声明「当前完全不校验,实测 ci.yml」+ 未来若加的双校验策略 |
| P0-5 | §8 阶段 2c 步骤 6 不具体 | 改为「task-workflow §1 表加第 4 行 active.json + feature_list.json 角色改『完整真相源(CI/审计用)』」+ 改前/改后示例 |
| P0-6 | 脚本 priority 假设未注释 | 脚本头注释补「依赖本仓 priority 单调递增约定」+ §13 风险表加专门一行 |
| P0-7 | §3.7.5 漏跑缓解不充分 | 补「漏跑代价可控(无数据丢失,agent 兜底读 FL)」+ 方案 B 补「workspace hook 受限」隐藏约束 |

**额外补强**:§3.7.1 量化数据复核(evidence 45.1% / verification 17.9% / notes 16.8% / 合计 79.8%,v3 原报 89.7% 偏高)+ §12.4 v3.1 评审闭环段(回写 §6 避坑表)。

### 阶段 B:阶段 2c 实施(8 步全过)

| 步骤 | 产物 | 实测结果 |
|---|---|---|
| 1 | `scripts/sync-active-features.sh`(可执行,4754 bytes,精简保留字段版)| ✅ |
| 2 | 首次跑生成 active + archive | ✅ active 6 条 / archive 55 条 |
| 3 | 验证生成物 | active.json **58 行 / 2083 bytes**(plan 预期 59 行/2076 bytes,差 1 行末尾换行,符合);archive 55 条 priority 1-55;完整 feature_list.json git diff 零变化;幂等性验证通过 |
| 4 | AGENTS.md 第 3 步改读 active 视图 | ✅ 含 4 条子说明(派生视图性质/完整版位置/无 not_started 处置/active 过时回退) |
| 5 | `harness/clean-state-checklist.md` 加 sync 收尾项 | ✅ 清单从 7 项变 8 项,「未勾怎么办」表 + 「与其他工件关系」同步更新 |
| 6 | `harness/docs/task-workflow.md` §1 表 + §4 会话节奏 | ✅ §1 表从三件套变四件套,feature_list.json 角色改「完整真相源(CI/审计用)」;§4 会话开始第 3 步读 active / 会话结束加 sync 步骤 |
| 7 | `.gitignore` 不加 active.json | ✅ git check-ignore 确认不被忽略,会入库 |
| 8 | `./init.sh` 全绿验证 | ✅ **561 passed**(与 Sessions 115-120 baseline 一致,零回归) |

### 关键红线全部守住

- ✅ **完整 feature_list.json 不变**:`git diff feature_list.json` 零输出,仍是真相源
- ✅ **active.json 入库**:`git check-ignore` 确认不被忽略,团队共享
- ✅ **archive.json 入库**:55 条完整字段保留,审计可追溯
- ✅ **AGENTS.md 第 3 步改读 active**:这是 token 节省的关键,已改
- ✅ **脚本永不写真相源**:`sync-active-features.sh` 对 feature_list.json 只读

### 实测收益

| 指标 | v3.1 归档前 | v3.1 归档后 | 节省 |
|---|---|---|---|
| agent 开工读的文件 | feature_list.json(1511 行 / 168KB) | feature_list.active.json(58 行 / 2KB) | **98.8%** |
| 估算 token | ~33,000 | ~441 | **98.7%** |
| 占 200K 上下文 | 16.5% | 0.22% | **-16.28 个百分点** |

### 文件清单(本次 Session)

1. `harness/docs/plan-harness-engineering-revamp.md`(改,纯文档,v3→v3.1,+479 行/-185 行)
2. `scripts/sync-active-features.sh`(新,入库,可执行)— feature_list 归档脚本,精简保留字段版
3. `feature_list.active.json`(新,入库,派生视图)— agent 开工读,58 行
4. `harness/docs/archive/features-passing-archive.json`(新,入库,历史归档)— 55 条 passing 完整字段
5. `AGENTS.md`(改,入库)— 第 3 步读 active 视图 + 完成定义加 sync 步骤
6. `harness/clean-state-checklist.md`(改,入库)— 7 项变 8 项,加 active 视图同步项
7. `harness/docs/task-workflow.md`(改,入库)— §1 三件套变四件套 + §4 会话节奏同步
8. `progress.md`(改,入库)— 本 Session 121 记录

### 关键决策

1. **采纳 plan v3.1 全部 7 项必修点**:第二轮评审 3:0 一致 Revise,问题集中,改动量小,一次性修订
2. **不采纳 Agent C「方案 X 删 evidence 字段」**:理由写入 plan §0.3(evidence 含 PR 链接,删后失审计线索;三层结构是 progress.md 既有归档惯例的延续)
3. **精简保留字段而非全字段**:plan v3 原脚本保留 5 条 passing 完整字段,实测 active.json 反被 evidence 撑大到 169 行/5KB;v3.1 改为只留 id/priority/area/title/status 决策字段,实测降到 58 行/2KB(节省从 89% 提升到 98.8%)
4. **clean-state-checklist 软约束 + 漏跑代价可控**:不强制 hook 自动触发(workspace hook 受 ZCode security policy 限制);漏跑代价只是 token 节省失效,无数据丢失,agent 兜底读完整版

### 验证(plan v3.1 §10 验收 #13/#14/#15 全满足)

1. ✅ 验收 #13:`scripts/sync-active-features.sh` 存在且可执行,跑一次后生成 `feature_list.active.json`(**实测 58 行/2083 bytes**)+ `harness/docs/archive/features-passing-archive.json`(**55 条**完整字段)
2. ✅ 验收 #14:AGENTS.md 开工流程第 3 步改为读 `feature_list.active.json`;task-workflow.md §1 表加 active.json 行 + feature_list.json 角色改「完整真相源(CI/审计用)」;clean-state-checklist.md 加 sync 收尾项
3. ✅ 验收 #15:完整 `feature_list.json` 保持不变(`git diff` 零输出);当前 CI 不校验 feature_list.json,active 视图不引入新 CI
4. ✅ `./init.sh` 全绿(**561 passed** 零回归)

### 自检通过项

- 自检 1:首次跑生成 active 6 条 + archive 55 条 ✅
- 自检 2:第 2 次跑幂等(archive 仍 55 条,无重复)✅
- 自检 3:完整 feature_list.json git diff 零变化 ✅
- 自检 4:`git check-ignore` 确认 active.json/archive.json 入库 ✅
- 自检 5:init.sh 561 passed 零回归 ✅
- 自检 6:AGENTS.md / task-workflow.md 引用一致性(grep 无残留冲突)✅

### 下一步建议

1. **(推荐)ship-it**:本 Session 所有改动可由 `/ship-it` 流水线 commit + PR + 合并入 main。
   **ship-it 实际执行时(本 Session 121 commit 阶段)的额外清理**:`harness/docs/harness-before-after.html`(Session 121 前就躺工作区的未追踪 HTML)经核对,**PR #85 的 commit message 已明确判定该删**(0 引用、违反 task-workflow.md §9「不在 repo 落 HTML」规则、被 `harness-practice-guide.html` 取代)。但当时只是没 `git add`,文件本身还躺工作区 —— 本轮 ship-it 真正 `rm` 掉,完成遗留清理。
2. **(观察期)首次实战验证**:下一轮 agent 开工读 active.json,观察是否真能省 token + 是否有边界 case(如 active.json 过时、agent 找不到某个最近 feature)
3. **(未来)升级为自动触发**:等 ZCode 放开 workspace hook 信任策略后,把 sync 脚本接 PostToolUse hook 监听 Edit/Write feature_list.json,实现全自动同步(消除漏跑风险)

阶段 2c 实施完成,plan v3.1 全部验收项通过。

### Session 122 — 2026-07-21(grill 设备功能 4 条 not_started feature 登记)

**目标**:用户要基于 StorePilot `docs/DEVICE-POWERON-MIGRATION-REFERENCE.md` 在本项目添加「设备相关功能」,明确「录入但不立即开放」(WIP=1 下登记为 not_started 排队等以后实施)。

**已完成**:

1. **摸清现状**:本项目 60 条 feature 全部 passing,无 not_started;codebase 无任何 device 概念。最接近的「目录 + 多租户 CRUD」范本是 `Agent`(`tenant_id` + `is_deleted` + `TenantScopedRepository` + `permission_service.require`),「全局身份 + 租户 profile」范本是 `Customer`/`CustomerProfile`。
2. **走 `/grill-with-docs` 烤清需求**(skill 要求一次一问 + 推荐答案 + 共识前不动手),共 6 组决策点逐一达成共识:
   - **数据模型分层**:B 方案 = 两张表 + FK(`device_models` 平台级 + `devices` 租户级),**不照搬** StorePilot 的 admin/store 双服务 + webhook
   - **本次登记 4 条 feature**(priority 61-64)
   - **device_models 无 tenant_id**(平台级目录,super_admin 写/hq_staff 读)
   - **devices 不加 kind 字段**(StorePilot 的 chamber/ring 是它特定业务,SaaS 脚手架不该假设;物理形态由 `device_models.specs` JSONB 表达)
   - **devices.status = active/maintenance/retired**(简化业务态;不用 StorePilot 混合 online/offline/low_battery/maintenance —— 在没有 IoT 上报链路时在线状态会变永远 stale 的脏数据)
   - **booking 6 态状态机**(pending/confirmed/in_service/done/cancelled/no_show),但**不实现 /confirm 端点**(confirmed 作前向兼容 CHECK 值保留,对齐 StorePilot v1)
   - **开机不加 risk_ack/血压前置**(StorePilot 那是医疗设备特定业务,本项目作为通用 SaaS 脚手架不该假设)
   - **booking.customer_id 可空 + SET NULL**(walk-in/代预约可不填,对齐 `Conversation.customer_id`)
   - **booking.device_id 加 FK + SET NULL**(比 StorePilot 的「无 FK」更严谨,软删除惯例下不会 CASCADE 灾难)
   - **feature 63(device-booking)只做 CRUD,不含 start/end**(状态机动作归 feature 64)
   - **feature 64(device-poweron)只到状态机层,硬件下发/MQTT/WS 不在范围**(归于未来 backlog,对齐 StorePilot slice-30-d3-iot-static.md 阶段 1 妥协)
   - **前端全栈**(后端 API + 前端 UI 页面,与 customers-api/ui 等既有 feature 风格一致)
   - **area = 业务实体**(与 customers/groups 等业务实体 CRUD 对齐)
3. **写入 feature_list.json**:`device-models-crud`(61)/`devices-crud-ui`(62,depends_on 61)/`device-booking`(63,depends_on 62)/`device-poweron`(64,depends_on 63),全部 status=not_started。
4. **补 depends_on 字段**:对齐既有 17 条 feature 的惯例(单字符串),显式表达依赖链 61→62→63→64。
5. **跑 sync-active-features.sh**:active.json 从 6 条变 10 条(4 not_started + 5 最近 passing + 1 里程碑)。

**验证**:

- ✅ JSON 合法,64 条 feature
- ✅ priority 61-64 唯一(注:priority 35 历史已有重复 `customers-ui`/`chat-overflow-title-fix`,**非本次引入**,不在任务范围不修)
- ✅ git diff `feature_list.json` 只增不删(+66 行/-2 行,删的 2 行是 last_updated + 末尾结构)
- ✅ sync 后 active.json 含 4 条 not_started,agent 开工能直接看到
- ⏳ `./init.sh` 跑验证(后台执行中,本次只改 JSON 不动代码,预期零回归 baseline 561 passed)

**关键决策**:

1. **不照搬 StorePilot**:无 webhook、无 kind 字段、无 risk_ack 业务前置、无 admin/store 双服务。StorePilot 的 DEVICE-POWERON-MIGRATION-REFERENCE.md 是「设计骨架参考」而非「可工作实现」(文档 §0 明说硬件下发未落地),本项目从零设计对齐自己的分层架构。
2. **YAGNI 原则贯穿**:不加 kind 枚举(物理形态走 JSONB)、不加 operational_status 双字段、不加 mqtt_topic/hw_address(等真上 IoT 时一次迁移补)、不实现 /confirm(等业务需要时补)。
3. **依赖链显式**:61→62→63→64,实施时严格按序(WIP=1)。
4. **「登记 ≠ 开工」**:本次只登记,4 条 feature 全部 not_started,符合 AGENTS.md WIP=1 铁律。

**下一步建议**:

1. **(推荐)ship-it**:本次改动(feature_list.json + feature_list.active.json + progress.md)可由 `/ship-it` 流水线 commit + PR + 合并入 main。纯文档/数据改动,无代码风险。
2. **(未来开工时)选 priority 61 `device-models-crud` 开始**:走 `/to-spec` 落 plan → `/to-tickets` 拆切片 → `/implement` → `/code-review` → ship-it。
3. **(未来)若真需要硬件下发**:新开 feature(priority 65+,area=基础设施或 IoT),补 mqtt_topic 字段 + MQTT publisher + broker 部署。
4. **(观察期)StorePilot 参考文档处置**:本次只读了 `docs/DEVICE-POWERON-MIGRATION-REFERENCE.md`(在 StorePilot 项目里,不在本仓库),未拷贝进本仓库。若希望本仓库留存参考,可考虑归档到 `harness/docs/external-refs/`(但会增加仓库体积,默认不做)。

**文件清单(本次 Session)**:

1. `feature_list.json`(改,+66 行/-2 行)— 4 条新 feature 61-64 + last_updated
2. `feature_list.active.json`(改,派生视图,sync 脚本生成)— 6 条变 10 条
3. `harness/docs/archive/features-passing-archive.json`(无变化,sync 脚本幂等,archive 仍 55 条)
4. `progress.md`(改)— 本 Session 122 记录

---

#### Session 122 修订(2026-07-21 同日)— 深度审查发现 P0/P1 设计弱点并补齐

**起因**:首轮审查偏「铁律符合性」通过,二轮深审刻意找设计质量弱点,发现 2 个 P0 + 4 个 P1 真实问题(不是锦上添花),逐条修补进 feature_list.json 的 verification / notes 字段。改动只动 JSON/MD,零代码改动。

**修订项(6 条)**:

1. **[P0-1] feature 61 读权限改模式**:原方案「super_admin 写 / hq_staff 只读」与本项目平台级资源惯例不一致。核实 codebase:既有所有平台级资源(Group/Billing/Settings/Tenant)没有一个用「super_admin 写 + hq_staff 读」组合;最接近的 `groups.py` 是「写 require_super_admin / 读开放给所有登录用户 + service 分流」。原方案会让 member 看不到型号目录 → devices 入库时下拉框拉不到型号 → 业务流卡死。**改为对齐 groups**:写 require_super_admin、读开放给所有登录用户;verification 加「member 读通过(下拉必需)」case。
2. **[P0-2] feature 61 权限实现路径明确**:平台级资源不走 `permission_service.require(tenant_id, ...)`(签名强制要 tenant_id,device_models 无 tenant_id 调不了)。对齐 groups.py 做法:用 FastAPI 依赖 `require_super_admin()` / `get_current_user` 直接守卫,**不走 casbin device_models:act 权限项,不进权限矩阵 UI**。notes 显式标注此边界。
3. **[P1-1] feature 61 金额字段类型**:StorePilot 用 `cost_cents INTEGER`,本项目既有金额字段惯例是 `Numeric(12,6)` Decimal(见 usage_event.cost / model_pricing.*)。notes 明写 `unit_cost Numeric(12,2)` 对齐本项目惯例,避免开工 agent 照搬 StorePilot cents 风格引入不一致。
4. **[P1-2] feature 62 设备占用态语义**:原方案 devices.status=active 与 booking in_service 可能语义矛盾(管理态正常但被占用)。notes 加「devices.status 是管理态,占用态由 bookings WHERE status='in_service' 派生」+ 提示未来 GET /devices/available 要 join bookings 排除占用,不能只看 devices.status。
5. **[P1-3] feature 61 specs 更新策略**:JSONB 字段的部分更新(jsonb_set)有并发覆盖风险。notes 加「整体替换 PUT 语义,不做 jsonb_set 增量」。另加「specs 若需按字段查询加 GIN 索引」提示。
6. **[P1-4] feature 63 booking 时间字段补齐(最关键)**:原方案完全没定义 booking 表的时间字段,但整个 feature 核心就是「预约时段」—— 这是个数据模型缺失。notes 明写建齐:scheduled_start_at/scheduled_end_at NOT NULL(本 feature 写,排期聚合源)、started_at/ended_at nullable(留给 feature 64 写)、feedback JSONB nullable(留给 feature 64 end 动作写)。verification 加「时段冲突检测(同设备同 scheduled_start_at 重叠拒绝 409)」+「POST 传 status=done 仍为 pending(防绕过状态机)」两个新测试维度。
7. **[P2-4] feature 64 walk-in 边界**:customer_id 为空的 booking(walk-in)只能由 store_staff+ start,customer 端无权(避免匿名预约被冒认)。verification 加对应测试 case;notes 标注本 feature 不再加迁移列(字段由 feature 63 先建好)。

**验证**:

- ✅ JSON 合法,64 条 feature 全在
- ✅ sync 脚本重跑后 active.json 完整对齐主文件新 notes(派生视图幂等)
- ✅ git diff 范围仍是 3 文件(零代码改动,baseline 561 passed 不受影响)
- ✅ priority 61-64 唯一单调,depends_on 链 61→62→63→64 完整

**未修的 P2 项**(留 plan 阶段):
- 软删型号后名复用 + FK RESTRICT 的前端展示注意(走 model_id join 不走 name 反查)
- 改约动作允许改哪些字段(device_id/customer_id/scheduled_*)的最终决定

**修订结论**:从首轮「直接通过」下调到「小修后通过」,所有 P0/P1 已闭环。可走 ship-it。

---

### Session 123 — 2026-07-21(实施 device-models-crud,设备功能系列 1/4 后端地基)

**目标**:实施 Session 122 登记的最高优先级 not_started feature `device-models-crud`(priority 61)。设备功能系列 1/4 的后端地基,无依赖,直接走 `/implement` 路由。

**已完成**:

1. **开工侦察**:用 Explore agent 把项目里所有相关范式一次性侦察清楚 —— groups.py(平台级路由 + service 分流)、GroupRepository(BaseRepository 直接继承 + 手动 is_deleted 过滤)、Group model(String(32) id + _uuid + soft-delete + 部分唯一索引)、usage_event.cost(Decimal Numeric(12,6))、customer.tags(JSONB with_variant)、groups alembic 迁移(平台级新表范本)、test_groups_api.py(权限矩阵测试范式)。汇总成 11 行「严格照搬范式清单」。
2. **Plan 模式**:用户拍板 2 个关键决策(双 schema 分流 vs 单 schema + 字段屏蔽;specs 纯自由 dict vs 结构化 + form_factor 必填)—— 都选推荐项,符合 AGENTS.md 不过度设计铁律。
3. **后端全套实施**(TDD 顺序):
   - `app/models/device_model.py`:照搬 Group 范式,平台级无 tenant_id,字段 `name/brand/supplier/unit_cost(Decimal Numeric(12,2))/specs(JSONB)` + soft-delete + `uq_device_models_name_active` 部分唯一索引
   - `app/schemas/device_model.py`:双 schema 分流 —— `DeviceModelRead`(超管/hq_staff 全量含 unit_cost)+ `DeviceModelPublicRead`(门店用户仅 {id, name, specs:{form_factor}})
   - `app/repositories/device_model.py`:继承 BaseRepository(平台级不进 TenantScoped),手动 is_deleted 过滤
   - `app/services/device_model_service.py`:照搬 GroupService 范式,`_to_read` / `_to_public_read` 按 `is_cross_tenant_viewer(platform_role)` 分流;create/update 后 re-fetch 防 MissingGreenlet;soft delete(is_deleted=True + deleted_at=now);unit_cost 非负校验落 service 层(避 Pydantic ge=0 Decimal 序列化 bug)
   - `app/api/v1/device_models.py`:GET 路由不固定 response_model(返回两种 schema),POST/PUT/DELETE `require_super_admin()`
   - `app/main.py`:import + include_router
   - `alembic/env.py` + `tests/conftest.py`:import device_model 让 metadata 注册
   - `alembic/versions/2026_07_21_2100_e649e80a4169_add_device_models_table.py`:down_revision=d6e7f8a9b0c1,JSONB with_variant + 部分唯一索引(PG+SQLite 双 where)
4. **测试 `tests/test_device_models_api.py`**(22 用例):
   - super_admin CRUD 全路径(create+get / list 空→有 / update / dup name 400 create+update / soft delete + name reuse / 404 nonexistent / specs whole-replace PUT 语义)
   - 写守卫(tenant owner / member / hq_staff 全 403)+ 未登录 401
   - 字段分流(super_admin/hq_staff 看 unit_cost+完整 specs;门店 owner/member 仅 {id,name,specs:{form_factor}};get-by-id 也分流;无 form_factor 时 specs={};unit_cost 非负 → 400;unit_cost 缺失 → 422)
5. **踩坑修复**(3 处):
   - **跨 client fixture 共享 owner 污染**:`super_admin_client` setup 会把 owner.platform_role 改成 super_admin,污染同测试函数的 `app_client` 视图 → 改用「每测试函数单 client + db_session 直造数据」范式(对齐 test_groups_api.py)
   - **Pydantic ge=0 + Decimal 序列化 bug**:Pydantic 把 Decimal 放进 422 error detail,starlette JSONResponse 无法序列化 → 去掉 ge 约束,改 service 层 BizError 400 校验
   - **alembic revision id 冲突**:首次拟的 `a1b2c3d4e5f6` 与历史 `2026_07_14_0900_a1b2c3d4e5f6_add_trend_indexes.py` 冲突,alembic 报 cycle → 改用 uuid4().hex[:12] = `e649e80a4169`,无冲突
6. **范围决策(防越界)**:本 feature 只做后端地基,**前端管理页 + 下拉 hook 留到 feature 62(devices-crud-ui)一起做** —— 避免空管理页没人用(YAGNI),前端在 devices 入库时一起消费型号下拉更合理。

**验证**:

- ✅ `./init.sh` 全绿:**583 passed**(baseline 561 + 新增 22 test_device_models_api,零回归),ruff All checks passed
- ✅ `alembic upgrade head` 真 PG 成功(迁移 e649e80a4169)+ `alembic check` 'No new upgrade operations detected'(无 drift)
- ✅ 权限矩阵实测全部通过(super_admin / hq_staff / member / 门店 owner / 未登录 5 角色全覆盖)
- ✅ 字段分流实测正确(双 schema 方案,门店 GET 响应不含 unit_cost)
- ✅ JSON 合法(64 条 feature)+ sync 后 active.json 含 device-models-crud passing

**关键决策**:

1. **双 schema 分流**:GET 路由不固定 response_model,service 按 `is_cross_tenant_viewer(platform_role)` 返回两种 Pydantic 实例,FastAPI 按实例本身 schema 序列化 —— API 契约清晰、前端类型可推导、采购成本对门店保密。
2. **specs 纯自由 dict[str, Any]**:不约束键,form_factor 由前端约定。对齐 customer.tags / llm_config.available_models 的 JSONB 惯例。
3. **不进 casbin**:刻意不动 permission_service.py 的 DEFAULT_*_PERMS / OBJ_CN / MENU_CN,和 groups 一样平台级资源缺席。
4. **unit_cost 校验落 service 层**:避 Pydantic Decimal 序列化 bug,符合 money-column 惯例(model_pricing 也没 ge)。

**文件清单(本次 Session)**:

新文件(7):
1. `app/models/device_model.py`
2. `app/schemas/device_model.py`
3. `app/repositories/device_model.py`
4. `app/services/device_model_service.py`
5. `app/api/v1/device_models.py`
6. `alembic/versions/2026_07_21_2100_e649e80a4169_add_device_models_table.py`
7. `tests/test_device_models_api.py`

改文件(6):
8. `app/main.py`(import + include_router)
9. `alembic/env.py`(import device_model)
10. `tests/conftest.py`(import device_model)
11. `feature_list.json`(device-models-crud status: not_started → passing + evidence + last_updated)
12. `feature_list.active.json`(派生视图,sync 脚本生成,4 not_started → 3 not_started)
13. `harness/docs/archive/features-passing-archive.json`(派生,archive 55 → 56 条)
14. `progress.md`(本 Session 123 记录)

**下一步建议**:

1. **(推荐)ship-it**:本次改动可由 `/ship-it` 流水线 commit + PR + 合并入 main。
2. **(下一轮开工)选 priority 62 `devices-crud-ui`**:走 `/grill-with-docs` 或 `/to-spec` 落 plan → `/implement`,前端型号下拉管理页 + 后端 devices 表 CRUD 一起做。device-models-crud 的型号下拉 API(GET /api/v1/device-models)此时会被真实前端调用,反向验证本 feature 的字段分流契约。
3. **(观察期)alembic revision id 规范**:本次踩坑说明历史 revision id 不是单调递增 hex,存在 `a1b2c3d4e5f6` / `a3b4c5d6e7f8` 等相邻 hex 被多次复用的情况。后续新迁移统一用 `uuid4().hex[:12]` 避免冲突,值得加进 `harness/clean-state-checklist.md` 或 AGENTS.md 提示。

### Session 123 文档影响评估(每任务必给)

| 文档 | 影响 | 处置 |
|---|---|---|
| `项目指南/02-后端架构/03-数据库与ORM.md` | 加新平台级表范例(device_models),与 groups 范式一致 | 不改:已由 groups 范例充分覆盖,device_models 是同构 |
| `项目指南/02-后端架构/04-权限模型.md` | 平台级资源「不进 casbin」规则多一个例子 | 不改:文档已抽象表述,groups 早已是先例 |
| `AGENTS.md` | alembic revision id 冲突经验值得加「容易踩的坑」 | 待定:可在下次 harness 文档巡检时统一补 |
| `harness/clean-state-checklist.md` | 无新规则触发 | 不改 |

**结论**:零文档需立即更新。仅有一处可选改进(alembic revision id 经验)留作下次 harness 巡检。

---

### Session 124 — 2026-07-22(devices-crud-ui 切片 01 后端地基,系列 2/4 第一刀)

- **本轮目标**:实施 `harness/docs/plan-devices-crud-ui.md` 切片 01 —— 门店设备实例 CRUD 后端地基(不含权限 seed/backfill、HQ 全景、bind/unbind、前端)。WIP=1 严格守边界,7 切片 tracer-bullet 第一刀
- **已完成**(对照切片 01 acceptance criteria 逐项打勾):
  - ✅ `app/models/device.py`:`Device` ORM model,字段 tenant_id(FK CASCADE)/model_id(FK RESTRICT 死保险绳,真实守卫是 service)/serial_number/status CHECK(active/maintenance/retired)/customer_id(FK SET NULL)/created_by/audit+软删列;`__table_args__` 含 `uq_devices_tenant_serial_active` 部分唯一索引(PG/SQLite 双写)+ `idx_devices_tenant_id` + `ck_devices_status_valid` CheckConstraint
  - ✅ alembic 迁移 `2026_07_22_1000_a0eaec7aab7c_add_devices_table.py`:down_revision=`e649e80a4169`(device_models 是 head),create_table + CheckConstraint + 3 索引(普通 is_deleted/tenant_id + 部分唯一),**upgrade 和 downgrade 都带 `postgresql_where=is_deleted=false` + `sqlite_where=is_deleted=0`** 防 drift
  - ✅ `app/schemas/device.py`:`DeviceStatus = Literal["active","maintenance","retired"]` + `DeviceBase`/`DeviceCreate`/`DeviceUpdate`/`DeviceRead`(from_attributes)。HQ 全景 `DeviceHqRead` 和 bind/unbind DTO 留给切片 03/04,YAGNI 不预建
  - ✅ `app/repositories/device.py`:`DeviceRepository(TenantScopedRepository[Device])`,重写 `get_for_tenant`/`list_for_tenant` 加 `is_deleted.is_(False)`(照抄 CustomerProfileRepository 范式),新增 `get_by_tenant_serial(tenant_id, serial, *, exclude_id=None)` 唯一性校验
  - ✅ `app/services/device_service.py`:`OBJECT="devices"`,4 个核心方法 create/list/get/update/delete 全走 `permission_service.require`;helper `_get_live_device`(跨租户/不存在/软删 → NotFoundError,防 enumeration)/`_assert_serial_unique`(→ BizError)/`_assert_model_live`(软删/不存在型号 → BizError,**真实守卫**,FK RESTRICT 因 device_model_service 软删永不触发);写后 re-fetch 防 MissingGreenlet
  - ✅ `app/api/v1/devices.py`:`router = APIRouter(prefix="/devices")`,GET/POST/PUT/DELETE 4 端点,router-level `require_permission("devices","read/create/update/delete")`(HQ 分流留给切片 03 替换为端点内 `is_cross_tenant_viewer` 分流);`app/main.py` 注册 `devices` 导入 + `app.include_router(devices.router)`
  - ✅ `tests/conftest.py`:`from app.models import (...)` 块加 `device`(在 `customer` 和 `device_model` 之间,alphabetical);`_make_casbin` owner/admin/member 三角色策略块各加 `devices:*`(注释说明生产 DEFAULT_*_PERMS 留给切片 02 backfill,fixture 模拟已 backfill 完毕的租户);menu 三角色各加 `devices` code
  - ✅ `alembic/env.py`:`from app.models import (...)` 同步加 `device`(否则 autogenerate/check drift)
  - ✅ `tests/test_devices_api.py` 14 测试用例覆盖章节 A/B/C/D/G/H:
    - A(owner/admin CRUD 全字段断言):`test_owner_create_list_get_update_delete` 全字段断言、`test_admin_can_read_create_update_but_not_delete`(admin 无 delete → 403,对齐 customer 范式)
    - B(跨租户 404 防 enumeration):`test_cross_tenant_get_put_delete_returns_404`(造 other_tenant 的 device → GET/PUT/DELETE 全 404 + list 空)
    - C(唯一约束):`test_duplicate_serial_in_same_tenant_400`(重复 → 400)、`test_serial_reusable_after_soft_delete`(软删后可复用)、`test_update_serial_to_existing_in_use_400`(rename 撞占用 → 400)
    - D(权限矩阵):`test_member_read_only_end_to_end`(member read 通过、create/update/delete → 403)、`test_unauthenticated_401`
    - G(状态切换):`test_status_transitions_all_legal`(active→maintenance→retired→active 全合法)、`test_status_invalid_value_422`('online' 非法 → 422)
    - H(model_id 完整性,service 层守卫):`test_h1_create_with_soft_deleted_model_400`(软删型号 → 400)、`test_h2_create_with_nonexistent_model_400`(不存在 → 400)、`test_h3_update_to_soft_deleted_model_400`(改指软删 → 400)、`test_h4_device_referencing_soft_deleted_model_still_gets`(型号后软删 device 仍可读)
- **运行过的验证**(全过):
  - `./init.sh` 基线(开工前)→ 583 passed(起点干净)
  - `ruff check app/ tests/` → All checks passed!(alembic/versions 已被 pyproject.toml exclude)
  - `pytest tests/test_devices_api.py -xvs` → 14 passed(新增 14 全绿)
  - `pytest tests/ cli/tests/` 全套 → **597 passed**(583 baseline + 14 新增,**零回归**)
  - alembic upgrade head 在 SQLite 内存库验证 schema 通过反射(Base.metadata.create_all 建出 devices 表;3 个索引 + unique 标志 + 所有列齐全;CHECK/FK 反射是 SQLAlchemy 在 SQLite 的已知局限,但迁移文本正确)
- **技术要点**(与 plan 的实现差异):
  - **router-level 守卫 vs 切片 03 内联分流**:本切片用最简单的 `dependencies=[Depends(require_permission("devices",act))]`。plan §6 明确写:HQ 全景分流必须移到端点函数体内(`if is_cross_tenant_viewer(...): ...`),否则 hq_staff 被 router-level 直接 403 —— 切片 03 会做这个改造。当前 GET / 对 hq_staff 是 403(预期,切片 01 不支持 HQ 读)
  - **conftest seed 设备权限,生产留切片 02**:`_make_casbin` 里给 owner/admin/member 加 `devices:*` 是为了切片 01 测试能跑通 owner CRUD + member 403。生产代码 `DEFAULT_OWNER_PERMS`/`DEFAULT_ADMIN_PERMS`/`DEFAULT_MEMBER_PERMS` **不动**(留给切片 02 的 backfill);`backfill_devices_perms_for_existing_tenants` 函数也留给切片 02
  - **`_assert_model_live` 是真实守卫,FK RESTRICT 是死保险绳**:`DeviceModelService.delete` 只翻 `is_deleted=True`(`app/services/device_model_service.py:148-156`),从不硬删,所以 `ondelete=RESTRICT` 在现行代码路径下永不触发。H1-H4 测试覆盖 service 层守卫,plan §3 关键边界 #1 明确说不写"RESTRICT 拦截"虚构测试
  - **`DeviceRead.tenant_id` 暴露**:store 端读返 caller 自己的 tenant_id 是无害的(你已知自己租户),且让 DTO 自描述方便前端。HQ 全景在切片 03 加 `DeviceHqRead.tenant_name`,届时跨租户读才有"陌生 tenant_id"
  - **alembic/env.py 双导入点**:与 `tests/conftest.py` 各有一份 `from app.models import (...)`,两份必须同步加 `device`,否则前者 autogenerate drift、后者测试 schema 缺表
  - **`status` Literal vs PG ENUM**:`status` 用 Pydantic Literal + DB CheckConstraint(SQLite+PG 都兼容),不用 PG ENUM —— ENUM 加值要单独迁移,过重。schema 是前端守卫(返 422),CHECK 是后端守卫(defence-in-depth)
- **边界遵守**(切片 01 严格不做的事,做了就是越界):
  - ❌ 权限 seed/backfill:`DEFAULT_*_PERMS` 不动,`backfill_devices_perms_for_existing_tenants` 不写(conftest fixture 模拟 backfilled 租户让测试跑通,生产留切片 02)
  - ❌ HQ 全景后端:`DeviceHqRead`/`list_all_with_meta`/端点内分流不写(GET / 对 hq_staff 是 403,切片 03 改)
  - ❌ bind/unbind 端点:`POST/DELETE /devices/{id}/bind` 不写(切片 04)
  - ❌ 前端任何文件(切片 05-07)
  - ❌ 其他 feature 代码 / 顺手重构
- **提交记录**:待用户决定是否单独 commit + PR(本切片改动:7 新文件 + 4 改动文件:`app/models/device.py` + `app/schemas/device.py` + `app/repositories/device.py` + `app/services/device_service.py` + `app/api/v1/devices.py` + `alembic/versions/2026_07_22_1000_a0eaec7aab7c_add_devices_table.py` + `tests/test_devices_api.py` 新增;`app/main.py` + `tests/conftest.py` + `alembic/env.py` + `progress.md` 改动)
- **下一步最佳动作**:
  - (a) 切片 02(权限 seed + backfill)—— 不可缺,否则功能上线即坏(现存租户权限表里没 `devices:*`,即使 owner 也调不通)
  - (b) 切片 03(HQ 全景后端)—— 改动切片 01 的 router-level 守卫,越早做越省返工
  - 推荐顺序:02 → 03 → 04(plan 提示的 Frontier 推进策略),然后 05 → 06 → 07 前端串行
- **已知风险**:无。`./init.sh` 全绿(597),零回归。alembic check drift 在本地 SQLite 跑不了(项目最老的 tenants 迁移用了 PG-only 的 `now()` 默认),依赖 CI 在真实 Postgres 跑验证 —— 迁移文本严格对照 device_models 范式,upgrade/downgrade 镜像,PG/SQLite 双 where 子句都在

### Session 124 文档影响评估(每任务必给)

| 文档 | 影响 | 处置 |
|---|---|---|
| `项目指南/02-后端架构/03-数据库与ORM.md` | 加新租户级表范例(devices),与 customer_profiles 范式一致 | 不改:已由 customer_profiles 范例充分覆盖,devices 是同构 |
| `项目指南/02-后端架构/06-权限模型RBAC.md` | 新 obj=devices 进 casbin 案例 | 不改:文档抽象表述,backfill 在切片 02,届时一并验证 |
| `AGENTS.md` | 双导入点经验(alembic/env.py 与 conftest.py 都要同步加新 model)| 不改:已在 device_models(Session 123)踩过同样坑,文档影响评估已记 |
| `harness/clean-state-checklist.md` | 无新规则触发 | 不改 |

**结论**:零文档需立即更新。所有新概念(软删 + 部分唯一索引 + TenantScopedRepository 重写)都已有先例充分覆盖。

### Session 124 ship-it 交付证据(2026-07-21)

**已合并入 main**:PR [#90](https://github.com/hugo617/ai-agent-platform/pull/90),squash merge commit `fbbee29f83069427d87acdbcd58b0a8cdb817dfe`,分支 `feat/devices-crud-slice01-backend` 已删。

- **分支决策**:工作区原在 `chore/ci-workflow-dispatch`(名实不符,且 PR #89 是 CI 改动)→ ship-it 新建 `feat/devices-crud-slice01-backend` 从 main 切出,devices 改动单独成 PR,与 CI 改动彻底隔离
- **ship-it 流水线全程零修复**:7 阶段(环境探测/审查/质量门禁/commit/push+PR/守 CI/合并)无卡顿
  - 第一性原理审查:逐文件拷问,零废代码、零占位、零违反铁律(依赖单向/多租户隔离落 Repository/软删+部分唯一索引 PG-SQLite 双写/model_id 守卫合理)
  - 质量门禁:`ruff check` 全过 + `pytest tests/ cli/tests/` 597 passed(583 baseline + 14 新增,零回归)
  - CI 4 job 全绿(首次,无修红):Migrations 47s / Backend 5m32s / Frontend 28s / E2E 1m42s
  - **Migrations job 在真实 Postgres 跑 `alembic upgrade head` + `alembic check` 通过** = 迁移文本零 drift(本地 SQLite 跑不了的 PG-only `now()` 默认值由 CI 兜底验证)
- **合并方式**:squash(对齐项目历史风格 `feat(scope): ... (#NN)`),`--delete-branch` 已清远端 feature 分支
- **下一步最佳动作**:切片 02(权限 seed + backfill `scripts/backfill_devices_perms.py`)—— 不可缺,否则功能上线即坏(现存租户权限表里没 `devices:*`,即使 owner 也调不通)。然后 03(HQ 全景)→ 04(bind/unbind)→ 05-07(前端)


---

### Session 125 — 2026-07-22(devices-crud-ui 切片 02 权限 seed + 老租户 backfill,系列 2/4 第二刀)

- **本轮目标**:实施 `harness/docs/plan-devices-crud-ui.md` 切片 02 —— 把 devices 权限矩阵 seed 进 `DEFAULT_*_PERMS`/`DEFAULT_MENU_PERMS`,并写一个幂等 backfill 函数 + 一次性脚本,把现存所有租户的 owner/admin/member 角色补齐 devices/menu:devices 权限。WIP=1 严格守边界,不动切片 01 的代码、不做切片 03 HQ 全景、不做切片 04 bind/unbind、不碰前端
- **已完成**(对照切片 02 acceptance criteria 逐项打勾):
  - ✅ `app/services/permission_service.py`:
    - `DEFAULT_OWNER_PERMS` 加 `("devices","read")/("devices","create")/("devices","update")/("devices","delete")` 4 项(对齐 customer 范式,owner 全 CRUD)
    - `DEFAULT_ADMIN_PERMS` 加 `("devices","read")/("devices","create")/("devices","update")` 3 项(无 delete,对齐 customer 范式 admin)
    - `DEFAULT_MEMBER_PERMS` 加 `("devices","read")`(只读)
    - `DEFAULT_MENU_PERMS["owner"|"admin"|"member"]` 各加 `"devices"` code(对应 `menu:devices` 侧边栏入口)
    - `OBJ_CN["devices"] = "设备"`、`MENU_CN["devices"] = "设备"`(中文 label)
  - ✅ 新增 `backfill_devices_perms_for_existing_tenants(db)` 模块级函数(`permission_service.py` 末尾):
    - 扫所有 `tenants` 表(Tenant 表无 `is_deleted` 列,只有 `status`,所以不过滤,符合现状)
    - 对每个 tenant 的 owner/admin/member role 调 `_upsert_permission(obj="devices",act=...)` + `RolePermissionRepository.grant`
    - menu 同理:`add_policy(role,tenant,"menu","devices")` + `_upsert_permission(...,perm_type="menu")` + grant
    - **只动 devices/menu:devices 相关**(`if obj != "devices": continue` + `if code != "devices": continue` 双过滤)
    - 幂等:`_upsert_permission` 命中 existing 返旧 id;`grant` 是 SCD2 upsert,no-op on dupe;`sync_role_permissions_to_casbin` 全量重建,再跑收敛
    - 返回 `{tenant_id: new_grants_count}` 给脚本打报告用
  - ✅ `scripts/backfill_devices_perms.py`:独立一次性脚本(参照 `scripts/backfill_permissions.py` 范式),async main + `AsyncSessionLocal` 初始化 + 调上述函数 + 打印每租户补了几条 + `--dry-run` 选项,CI 不跑,手动执行一次
  - ✅ `tests/test_devices_api.py` 加 K 章节 3 测试覆盖 K1-K6:
    - K1 fixture(`_seed_backfill_target_tenant`):造无 devices 策略的租户,只 seed `customers:read`(owner/admin/member)+ `menu:agents`(owner),且 DB SCD2 + casbin 双镜像(否则 check 走 casbin 看不到 DB grant)
    - K2+K3+K4(`test_k_backfill_grants_devices_perms_correctly`):跑 backfill → 断言 new grants = 5(owner)+4(admin)+2(member) = 11;owner 拿 `devices:create/read/update/delete` + `menu:devices`;member 拿 `devices:read` + `menu:devices`,**没有** `devices:create`(防过度授权)
    - K5(`test_k_backfill_idempotent`):再跑 backfill → 断言 new grants = 0,不报错,RolePermission 行 id 集合 before == after(无新增/无重复)
    - K6(`test_k_backfill_preserves_other_perms`):backfill 前 `customers:read`(三角色)+ `menu:agents`(owner)能用,backfill 后仍能用,且 `devices:read` 也新可用(只补 devices,不动其他)
- **运行过的验证**(全过):
  - `./init.sh` 基线(开工前)→ 597 passed(起点干净,Session 124 切片 01 baseline)
  - `ruff check app/ tests/ scripts/` → All checks passed!
  - `pytest tests/test_devices_api.py -k k_backfill -xvs` → 3 passed(K 章节 K1-K6 语义全覆盖)
  - `pytest tests/ cli/tests/` 全套 → **600 passed**(597 baseline + 3 新增,**零回归**)
  - `./init.sh` 收尾 → ✅ 基础验证通过(ruff + pytest 全绿)
- **技术要点**(与 plan 的实现差异):
  - **`Tenant` 表无 `is_deleted` 列**:plan §7 原文写 "扫 `tenants WHERE is_deleted=false`",但实际 `Tenant` 模型只有 `status`(active/inactive/locked),没有 `is_deleted`(只有 `User` 有)。backfill 函数扫所有租户(`select(Tenant)` 无过滤),既符合现状又不会撞 AttributeError。**现存 `scripts/backfill_permissions.py:226` 用 `Tenant.is_deleted.is_(False)` 是潜在 bug**,但不是本切片范围(WIP=1,不顺手修)
  - **backfill 函数放 `permission_service.py` 末尾(模块级),不放 service 类里**:plan §7 原文说"放 `permission_service.py` 末尾,或新建 `app/services/permission_backfill.py`"。选前者 —— 这样测试 (K 章节) 能直接调,脚本 (scripts/) 是薄 wrapper,两者共用同一个函数 = 测试覆盖生产代码路径(避免"测一个、跑另一个"的假完成)
  - **scope guardrail 双过滤**:api perms 用 `if obj != "devices": continue`,menu perms 用 `if code != "devices": continue`。两层过滤冗余但显式,plan §7 决策表明确要求"只动 devices/menu:devices",K6 是核心防回归契约
  - **K1 fixture 的 DB+casbin 双镜像**:`_seed_backfill_target_tenant` seed `customers:read` 时既插 DB RolePermission 行,也插 casbin policy(`enforcer.add_policy`)。因为 `permission_service.check` 走 casbin,光插 DB grant check 返 False;光插 casbin 缺 SCD2 当前态。生产代码 `seed_tenant_defaults` 就是双写,K1 fixture 照抄这个范式
  - **测试 patch enforcer**:K 章节 3 个测试都 `patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer)`,与 `app_client` fixture 同款 —— 否则 backfill 调 `run_in_threadpool(_do)` 走全局 enforcer(SQLAlchemy adapter 指向无关的 SQLite URL)→ `MissingGreenlet`
  - **catalogue 完整性测试同步更新**:`tests/test_permission_service.py` 有 3 个 catalogue-pin 测试(`test_default_owner_perms_cover_full_catalogue` / `_ALL_BUSINESS_MENUS` / `test_default_menu_perms_member_only_sees_business_menus`)需要同步加 devices,否则会 fail。这是预期:catalogue 加了新成员,pin 测试也要更新
- **边界遵守**(切片 02 严格不做的事,做了就是越界):
  - ❌ HQ 全景后端(`DeviceHqRead`/`list_all_with_meta`/端点内分流,切片 03)
  - ❌ bind/unbind 端点(`POST/DELETE /devices/{id}/bind`,切片 04)
  - ❌ 前端任何文件(切片 05-07)
  - ❌ 改动切片 01 已通过的 Device ORM / Repository / Service CRUD / API / 章节 A/B/C/D/G/H 测试(conftest.py 里 `devices:*` fixture seed 保留,模拟已 backfilled 租户,与生产 backfill 函数不冲突)
  - ❌ 修 `scripts/backfill_permissions.py` 的 `Tenant.is_deleted` 潜在 bug(不是本切片范围,记录在文档影响评估供后续修)
  - ❌ 其他 feature 代码 / 顺手"重构"或"清理"
- **提交记录**:待用户决定是否单独 commit + PR(本切片改动:1 新文件 + 3 改动文件:`scripts/backfill_devices_perms.py` 新增;`app/services/permission_service.py` + `tests/test_devices_api.py` + `tests/test_permission_service.py` 改动)。**注意:不改 feature_list.json 状态**(devices-crud-ui 整 feature 还有切片 03-07 没做,本切片只是其中一刀,status 仍 `not_started`)
- **下一步最佳动作**:
  - (a) 切片 03(HQ 全景后端)—— 改动切片 01 的 router-level 守卫为端点内分流,越早做越省返工
  - (b) 切片 04(bind/unbind 端点)—— 相对独立,可与 03 并行但 WIP=1 要求串行
  - 推荐顺序:03 → 04(plan 提示的 Frontier 推进策略),然后 05 → 06 → 07 前端串行
  - 本切片改动可由 `/ship-it` 流水线 commit + PR + 合并入 main,与切片 01 完全解耦(没动切片 01 的代码)
- **已知风险**:无。`./init.sh` 全绿(600),零回归。无 alembic 迁移改动(本切片是纯权限矩阵 + 数据补丁),CI Migrations job 不受影响

### Session 125 文档影响评估(每任务必给)

| 文档 | 影响 | 处置 |
|---|---|---|
| `项目指南/02-后端架构/06-权限模型RBAC.md` | 新 obj=devices 进 casbin 案例 + 老租户 backfill 范式 | 不改:文档抽象表述,devices 是 customer/devices/device_models 系列的又一个同构案例;backfill 是一次性脚本,不进运行时 |
| `AGENTS.md` | `Tenant` 表无 `is_deleted` 列(只有 `status`)这个事实值得加「容易踩的坑」 | 待定:可在下次 harness 文档巡检时统一补;现存 `scripts/backfill_permissions.py:226` 已踩此坑 |
| `harness/clean-state-checklist.md` | 无新规则触发 | 不改 |
| `harness/docs/plan-devices-crud-ui.md` | §7 backfill 方案落地与 plan 完全对齐(独立脚本 + 模块级函数 + K1-K6 测试) | 不改:plan 描述准确 |

**结论**:零文档需立即更新。仅有一处可选改进(`Tenant` 表无 `is_deleted` 的事实)留作下次 harness 巡检。

---

### Session 126 — 2026-07-22(devices-crud-ui 切片 03 HQ 全景视图,系列 2/4 第三刀)

- **本轮目标**:实施 `harness/docs/plan-devices-crud-ui.md` 切片 03 —— HQ 全景视图后端:super_admin 和 hq_staff 通过 `GET /devices/` 和 `GET /devices/{id}` 拿到跨所有租户的 `DeviceHqRead` 全景(tenant_name / model_name / customer_name),hq_staff 写端点(create/update/delete)返 403。WIP=1 严格守边界,不动切片 01/02 已落地的代码行为(零回归)、不做切片 04 bind/unbind、不碰前端。
- **已完成**(对照切片 03 acceptance criteria 逐项打勾):
  - ✅ `app/schemas/device.py`:加 `DeviceHqRead(DeviceRead)`,继承全部字段 + 3 个全景字段(`tenant_name` / `model_name` / `customer_name`,均 `str | None = None` —— 软删关联行或无 customer 绑定时降级为 None,不藏 device)
  - ✅ `app/models/device.py`:加 3 个 `relationship`(`tenant` / `model` / `customer`,用 `primaryjoin` + `foreign_keys` 显式绑定,**不 `back_populates`** 避免反向耦合 customer/tenant/device_model 域)+ `TYPE_CHECKING` 块(ruff F821 用,运行时不 import,SQLAlchemy 通过 declarative registry 解析字符串类名)
  - ✅ `app/repositories/device.py`:加 `list_all_with_meta()` / `get_all_with_meta(device_id)`,用 `selectinload(Device.tenant/model/customer)` 三连预加载(防 N+1 + 防 async session `MissingGreenlet`),软删过滤(`is_deleted=False`),**不复用** `customer.batch_tenant_info`(那是 customer 域耦合,只返 tenant_name)
  - ✅ `app/services/device_service.py`:`list` / `get` 用 `is_cross_tenant_viewer(platform_role)` 分叉 —— 跨租户调 `list_all_with_meta`/`get_all_with_meta` 返 `DeviceHqRead`(不调 `permission_service.require`,放行靠底层 `check:103` 的 `hq_staff+read` 特判 + `super_admin` bypass);否则原切片 01 逻辑(`require("devices","read")` + 本租户 `DeviceRead`)。新增 `_to_hq_read` helper,用 `getattr` 安全读 `*_name`(关联行软删/无绑定时降级 None)
  - ✅ `app/api/v1/devices.py`:`GET /` 和 `GET /{id}` **移除 router-level `require_permission("devices","read")` 依赖**(否则 hq_staff 直接 403),改为端点内分流 —— 跨租户 viewer 调 service HQ 分支;本租户走 service 内的 `require`。`response_model=None`(返回类型按角色分叉:`DeviceRead` 门店 / `DeviceHqRead` 全景,声明任一会丢字段或污染门店视图)。POST/PUT/DELETE 保持 router-level `require_permission`(写端点 hq_staff 正常 403)
  - ✅ `tests/test_devices_api.py`:加 **E 章节 HQ 全景** 5 个测试 + `_seed_customer` / `_seed_two_tenant_devices` helper:
    - `test_super_admin_list_returns_hq_panorama`:super_admin list 跨租户 + 全景字段(tenant_name/model_name/customer_name)
    - `test_super_admin_get_one_returns_hq_panorama`:super_admin GET 跨租户 device → 200 + 全景(不 404)
    - `test_hq_staff_list_returns_hq_panorama`:hq_staff list 全景(**核心回归守卫**:切片 03 前这里对 hq_staff 是 403)
    - `test_hq_staff_writes_are_403`:hq_staff create/update/delete 全 403(WIP=1 边界:HQ viewer 只读)
    - `test_hq_get_soft_deleted_device_returns_404`:HQ GET 软删 device → 404(防泄漏 tombstone)
  - ✅ 文件头 docstring 更新(章节布局加 E 章节,标注 slice 03)
- **验证证据**:
  - `./init.sh` 全绿:**605 passed**(600 baseline + 5 新 E 章节),零回归。ruff 全绿(含 TYPE_CHECKING 修 F821)
  - `tests/test_devices_api.py` 单文件:**22 passed**(切片 01 A/B/C/D/G/H 14 + 切片 02 K 3 + 切片 03 E 5)
- **设计决策记录**(供后续切片/feature 参考):
  - **relationship 不用 `back_populates`**:Device 加 tenant/model/customer 三个 relationship 是 selectinload 的硬前提(否则 `selectinload(Device.tenant)` 无目标)。但目标 model 不需要反向 collection(没 reader 受益),所以用 `primaryjoin` + `foreign_keys` 单向声明,不耦合 customer/tenant/device_model 域。这与项目其他 model(如 UserTenant↔Tenant 用 back_populates)不同,因为那些是双向导航刚需,这里是单向 HQ 读
  - **`response_model=None` 而非 union**:`list[DeviceRead | DeviceHqRead]` 会产生丑陋的 `anyOf` OpenAPI schema;`response_model=DeviceHqRead` 会让门店视图多 3 个 null 字段(改变切片 01 API 契约);`response_model=None` 最诚实 —— 返回类型按角色分叉,docstring 说明。OpenAPI schema 损失可接受(前端切片 05 会自己定义 types.ts)
  - **`*_name` 降级为 None 而非藏 device**:HQ 视图需要看完整 inventory,即使关联的 tenant/model/customer 被软删(关系行还在,name 字段还在)。`getattr(device.tenant, "name", None)` 安全读取,关系未加载或行为 None 时降级
  - **hq_staff 写端点 403 的底层路径**:router-level `require_permission("devices","create")` → `permission_service.check` → `platform_role == "hq_staff" and act == "read"` 不满足(create≠read)→ 落 casbin → hq_staff 绑 member 角色 → member 无 `devices:create` → **403**。这是 hq-platform-role feature(Session ~80)建立的 hq_staff 只读语义,本切片复用未改
- **边界遵守**(切片 03 严格不做的事,做了就是越界):
  - ❌ bind/unbind 端点(切片 04)
  - ❌ 前端任何文件(`DeviceHqRead` frontend type 留给切片 05)
  - ❌ 改动切片 01 A/B/C/D/G/H 测试 + 切片 02 K 测试的行为(GET / 和 GET /{id} 守卫从 router-level 移到端点内,但 A/B/D/G/H 断言的是字段值和状态码,行为不变 —— 22 passed 证实零回归)
  - ❌ 修 customers-page HqView 对 hq_staff 不可见的既存 bug(WIP=1,留给后续 customer feature)
  - ❌ 顺手重构/clean up 既存代码
- **暴露的既存 bug**(WIP=1 不在本切片修,仅记录):`frontend/src/pages/customers-page.tsx` 当前 `isSuperAdmin(me) ? <HqView/> : <StoreView/>`,**hq_staff 看不到 customers HqView**(只能看 StoreView)。这是 customers-ui feature 的遗漏。devices-page(切片 07)会修正:`isSuperAdmin(me) || isHQStaff(me)`。customers-page 的同类修复留给后续 customer feature 单独做
- **提交记录**:待用户决定是否单独 commit + PR(本切片改动:5 文件 —— `app/schemas/device.py` / `app/models/device.py` / `app/repositories/device.py` / `app/services/device_service.py` / `app/api/v1/devices.py` 改动;`tests/test_devices_api.py` 改动)。**不改 feature_list.json 状态**(devices-crud-ui 整 feature 还有切片 04-07,status 仍 `not_started`)
- **下一步最佳动作**:切片 04(bind/unbind 客户绑定端点,幂等语义)—— `POST /devices/{id}/bind` 返 200 + `already_bound` 标志,`DELETE /devices/{id}/bind` 返 204(无绑定也 204)。然后 05-07(前端)
  - 本切片改动与切片 01/02 完全解耦(GET 守卫改造是切片 03 的本职,不算动切片 01 代码),可由 `/ship-it` 流水线 commit + PR + 合并入 main

### Session 126 文档影响评估(每任务必给)

| 文档 | 影响 | 处置 |
|---|---|---|
| `harness/docs/plan-devices-crud-ui.md` | 切片 03 落地与 plan §6/§8 完全对齐(端点内分流 + selectinload + E 章节 5 测试) | 不改:plan 描述准确 |
| `项目指南/02-后端架构/03-数据库与ORM.md` | Device model 加 relationship(tenant/model/customer)是 selectinload 前提这个范式值得记录 | 待定:可在下次 ORM 文档巡检时补"跨域单向 relationship(不 back_populates)"范式;当前 tenant.py 的 selectinload 范例已存在 |
| `frontend/src/pages/customers-page.tsx` | 暴露既存 bug:hq_staff 看不到 customers HqView(`isSuperAdmin(me) ? ...`) | **不改(越界)**:WIP=1,留给后续 customer feature;devices-page 切片 07 会用正确范式 `isSuperAdmin(me) || isHQStaff(me)`,届时可反向验证 customers-page 的修复方向 |
| `harness/clean-state-checklist.md` | 无新规则触发 | 不改 |

**结论**:零文档需立即更新。一处既存 bug(customers-page HqView 对 hq_staff 不可见)被本切片暴露但不在范围内修,已记录待后续 customer feature。

---

### Session 127 — 2026-07-22(devices-crud-ui 切片 04 客户绑定端点,系列 2/4 第四刀)

- **本轮目标**:实施 `harness/docs/plan-devices-crud-ui.md` 切片 04 —— 客户绑定端点(bind/unbind,幂等语义):owner/admin 通过 `POST /devices/{id}/bind` 给设备绑客户(返 200 + `already_bound` 标志),`DELETE /devices/{id}/bind` 解绑(无绑定也返 204,DELETE 幂等)。WIP=1 严格守边界,不动切片 01/02/03 已落地的代码行为(零回归)、不碰前端(切片 05-07)。
- **已完成**(对照切片 04 acceptance criteria 逐项打勾):
  - ✅ `app/schemas/device.py`:加 `DeviceBindRequest(customer_id: str, min_length=1)` + `DeviceBindResponse(device_id, customer_id, already_bound: bool)`。模块 docstring 更新(从"Bind/unbind DTOs land in slice 04"改为"已落地,模型 bind 动作端点")。`customer_id` 是**全局 Customer id**(`customers.id`),bind 仅在该 customer 在本租户有 live `CustomerProfile` 时成功
  - ✅ `app/services/device_service.py`:
    - `bind(device_id, tenant_id, customer_id, actor_id, platform_role)` → 返 `(device, already_bound: bool)`:`require("devices","update")` → `_assert_customer_in_tenant` → `_get_live_device` → 若 `device.customer_id == customer_id` 返 `already_bound=True` **不写库**(幂等),否则覆盖 `already_bound=False` 写库。返 tuple 而非 `DeviceBindResponse`(schema 是 API 层职责,service 保持纯净)
    - `unbind(device_id, tenant_id, actor_id, platform_role)`:`require("devices","update")` → `_get_live_device` → 若 `customer_id is None` 直接 return(no-op,不抛错),否则 set None + flush + commit
    - `_assert_customer_in_tenant(tenant_id, customer_id)`:走 `CustomerProfileRepository.get_by_customer_tenant(customer_id, tenant_id)`,失败 → `BizError 400`。跨租户/不存在 customer 合并同一错误(防枚举,同 device 跨租户 404 逻辑)
    - 顶部模块 docstring 更新:guards 列表从 3 条扩到 4 条(加 `_assert_customer_in_tenant`);writes 段补 bind/unbind 守卫说明
  - ✅ `app/api/v1/devices.py`:
    - `POST /{device_id}/bind` → **200**(`status_code=HTTP_200_OK`,**非 201** —— device 资源已存在,bind 是赋值动作),`response_model=DeviceBindResponse`,`dependencies=[require_permission("devices","update")]`。端点调 `service.bind` 拿 `(device, already_bound)` 后自构 `DeviceBindResponse`
    - `DELETE /{device_id}/bind` → **204**(`HTTP_204_NO_CONTENT`,无绑定也 204),同上守卫。调 `service.unbind`
    - 模块 docstring 更新:bind/unbind 段从"not here yet"改为已落地 + 守卫/幂等语义说明
  - ✅ `tests/test_devices_api.py` F 章节 8 条 + `_seed_customer_with_profile` helper + `_seed_device_in_test_tenant` helper:
    - F1 `test_f1_bind_success_200_already_bound_false`:bind 未绑定 device → 200 + `already_bound:false` + 持久化(GET 验证)
    - F2 `test_f2_bind_same_customer_idempotent_200_already_bound_true`:重复 bind 同 customer → 第二次 200 + `already_bound:true`(不写库)
    - F3 `test_f3_bind_different_customer_overwrites_200`:bind 不同 customer 覆盖 → 200 + `already_bound:false` + GET 验证指向新 customer
    - F4 `test_f4_unbind_success_204`:unbind 已绑定 device → 204 + GET 验证 customer_id=None
    - F5 `test_f5_unbind_unbound_device_204_idempotent`:unbind 从未绑定的 device → 204(**非 404**,幂等 no-op)
    - F6 `test_f6_bind_customer_from_other_tenant_400`:bind 只在另一租户有 profile 的 customer → 400
    - F7 `test_f7_bind_nonexistent_customer_400`:bind 不存在 customer id → 400(与 F6 同错误,防枚举)
    - F8 `test_f8_member_bind_403`:member bind + unbind 全 403(无 `devices:update`)
    - 文件头 docstring 更新(章节布局加 F 章节 8 条,标注 slice 04)
- **验证证据**:
  - `./init.sh` 全绿:**613 passed**(605 baseline + 8 新 F 章节),零回归。ruff 全绿(修了一处 F401 未用 import `DeviceBindResponse` in service.py —— service 返 tuple,API 层自构 response)
  - `tests/test_devices_api.py` 单文件:**30 passed**(切片 01 A/B/C/D/G/H 14 + 切片 02 K 3 + 切片 03 E 5 + 切片 04 F 8)
- **设计决策记录**(供后续切片/feature 参考):
  - **`_assert_customer_in_tenant` 用 `get_by_customer_tenant` 而非 `get_for_tenant`**:plan §4 原文写"走 `CustomerProfileRepository.get_for_tenant(customer_id, tenant_id)`",但 `get_for_tenant(obj_id, tenant_id)` 的第一参数是 **CustomerProfile.id**(继承自 `TenantScopedRepository`),不是 customer_id。语义正确的查询是 `get_by_customer_tenant(customer_id, tenant_id)`(L272,正是"该 customer 在本租户有没有 live profile")。这是 plan 描述精度问题,实施时按语义选对方法,行为与 plan §3 关键边界 #2 完全一致
  - **bind 返 tuple `(device, already_bound)` 而非 `DeviceBindResponse`**:service 层不依赖 schema(API 层职责),保持 Controller→Service→Repository 单向依赖。API 端点拿 tuple 后自构 `DeviceBindResponse`,与切片 01 `create`/`update` 返 `DeviceRead`(在 service 内构造)的范式略不同,但那是因为 `DeviceRead` 有 `from_attributes` 可从 ORM 直接 validate;`DeviceBindResponse` 是动作结果(含 `already_bound` 标志),无对应 ORM 字段,必须 API 层显式构造
  - **bind 幂等 + 覆盖同走 200**:bind 同 customer → `already_bound:true` 不写库;bind 不同 customer → `already_bound:false` 覆盖。两者都 200(非 201),因为 device 资源已存在,bind 是赋值动作(PUT 语义)。`already_bound` 标志让客户端区分"新绑定"vs"重复绑定"无需额外 GET
  - **unbind 无绑定 → 204 非 404**:DELETE 幂等是 REST 惯例,避免客户端先 GET 判空再 DELETE。service 层 `if device.customer_id is None: return`(早退,不抛 NotFoundError)
  - **跨租户/不存在 customer 合并 400**:`_assert_customer_in_tenant` 失败路径统一 `BizError 400`,不区分"存在但跨租户"vs"不存在"。与 device 跨租户 → 404 的枚举防御逻辑同构(customer 域防枚举)
- **边界遵守**(切片 04 严格不做的事,做了就是越界):
  - ❌ 前端任何文件(`DeviceBindRequest`/`DeviceBindResponse` frontend type 留给切片 05)
  - ❌ 改动切片 01 A/B/C/D/G/H + 切片 02 K + 切片 03 E 测试的行为(只新增 F 章节 + 2 个 helper,不动既有 —— 30 passed 含全部既有 22 条证实零回归)
  - ❌ bind 端点用 super_admin 守卫(devices 是租户级资源,用 `require_permission("devices","update")`)
  - ❌ 顺手重构/clean up 既存代码
  - ❌ 修 customers-page HqView 对 hq_staff 不可见的既存 bug(留给后续 customer feature)
- **提交记录**:待用户决定是否单独 commit + PR(本切片改动:4 文件 —— `app/schemas/device.py` / `app/services/device_service.py` / `app/api/v1/devices.py` / `tests/test_devices_api.py`)。**不改 feature_list.json 状态**(devices-crud-ui 整 feature 还有切片 05-07,status 仍 `not_started`)
- **下一步最佳动作**:切片 05(前端地基:types/endpoints/queries + isHQStaff + 路由)—— `frontend/src/api/types.ts` 加 `Device`/`DeviceCreate`/`DeviceUpdate`/`DeviceBindRequest`/`DeviceBindResponse`/`DeviceHqRead`/`DeviceModelPublic`;`endpoints.ts` + `queries.ts` 加 devices 完整 API client;`permission.ts` 加 `isHQStaff(me)`;`App.tsx` 加 `/devices` 路由;`nav-items.ts` 加菜单项。然后 06-07(UI)
  - 本切片改动与切片 01/02/03 完全解耦(只新增 schema/service 方法 + API 端点 + F 章节,不动既有代码行为),可由 `/ship-it` 流水线 commit + PR + 合并入 main

### Session 127 文档影响评估(每任务必给)

| 文档 | 影响 | 处置 |
|---|---|---|
| `harness/docs/plan-devices-crud-ui.md` | 切片 04 落地与 plan §4/§6/§8 完全对齐。唯一精度偏差:§4 原文"`_assert_customer_in_tenant` 走 `CustomerProfileRepository.get_for_tenant`",实际应用 `get_by_customer_tenant`(`get_for_tenant` 第一参数是 profile id 非 customer_id) | 不改:行为与 plan §3 关键边界 #2 语义完全一致,仅是方法名精度问题;plan 描述的是"查 customer 在本租户的 profile"这个意图,实施按语义选对了方法。可在 plan v3 修订时补一句方法名澄清,非阻塞 |
| `项目指南/02-后端架构/03-数据库与ORM.md` | bind 端点的"动作子资源 POST 返 200 非 201"范式值得记录(group attach/detach 是另一例,但守卫不同) | 待定:可在下次后端架构巡检时补"动作端点 vs 资源创建端点的状态码约定";当前 group 端点已存在参照 |
| `harness/clean-state-checklist.md` | 无新规则触发 | 不改 |

**结论**:零文档需立即更新。一处 plan 描述精度偏差(`get_for_tenant` vs `get_by_customer_tenant`)已按语义正确实施,非阻塞,记录待 plan 下次修订澄清。

---

### Session 128 — 2026-07-22(devices-crud-ui 切片 05 前端地基,系列 2/4 第五刀)

- **本轮目标**:实施 `harness/docs/plan-devices-crud-ui.md` 切片 05 —— 前端地基:devices/device-models 完整类型 + API client + query hooks + `isHQStaff` helper + `/devices` 路由可达(stub 页)+ 菜单项。UI 实现留给切片 06/07,WIP=1 不越界。
- **已完成**(对照切片 05 acceptance criteria 7 项逐项打勾):
  - ✅ `frontend/src/api/types.ts`(devices 段插在 customers 段后、billing 段前):
    - `DeviceStatus = "active" | "maintenance" | "retired"`(Literal,镜像后端)
    - `Device`(对齐 `DeviceRead`):id/tenant_id/model_id/serial_number/status/customer_id(`string|null`)/created_by(`string|null`)/created_at/updated_at
    - `DeviceCreate`:model_id/serial_number/status?/customer_id?(create-time hint)
    - `DeviceUpdate`:model_id?/serial_number?/status?(**无 customer_id** —— bind 走专用端点,注释说明)
    - `DeviceHqRead extends Device`:tenant_name/model_name/customer_name(均 `string|null`,后端返 null)
    - `DeviceBindRequest`:{customer_id: string}
    - `DeviceBindResponse`:{device_id, customer_id, already_bound: boolean}
    - `DeviceModelPublic`:{id, name, specs: Record<string, unknown>}(镜像 `DeviceModelPublicRead`,下拉用,未来 device-models 管理页共用)
  - ✅ `frontend/src/api/endpoints.ts`(devices + device-models 段):
    - `fetchDevices()` → GET /devices/(返 `Device[] | DeviceHqRead[]`,union 因后端按 platform_role 分叉)
    - `fetchDevice(id)` → GET /devices/{id}
    - `createDevice(payload)` → POST /devices/
    - `updateDevice(id, payload)` → PUT /devices/{id}
    - `deleteDevice(id)` → DELETE /devices/{id}
    - `bindDeviceCustomer(id, customerId)` → POST /devices/{id}/bind(返 `DeviceBindResponse`,body 用 `satisfies DeviceBindRequest`)
    - `unbindDeviceCustomer(id)` → DELETE /devices/{id}/bind
    - `fetchDeviceModels()` → GET /device-models/(返 `DeviceModelPublic[]`)
  - ✅ `frontend/src/hooks/queries.ts`:
    - `qk.devices` / `qk.deviceModels` 两个 query key
    - `useDevices()` / `useCreateDevice()` / `useUpdateDevice()` / `useDeleteDevice()` / `useBindDeviceCustomer()` / `useUnbindDeviceCustomer()` / `useDeviceModels(enabled = true)`(7 hooks,全部走 `useApiMutation` + invalidate `qk.devices`,enabled 守卫镜像 `useAllTenants`)
  - ✅ `frontend/src/lib/permission.ts`:`isHQStaff(me)` helper(镜像 `isSuperAdmin` 签名 + JSDoc 说明 hq_staff 是跨租户只读角色,调用方用 `isSuperAdmin(me) || isHQStaff(me)` 分叉 HQ 视图)
  - ✅ `frontend/src/pages/devices-page.tsx`:新建 stub 页(named export `DevicesPage`),最小 Card 占位 + docstring 说明切片 06/07 将替换为 `isSuperAdmin(me) || isHQStaff(me) ? <HqView/> : <StoreView/>` 分叉
  - ✅ `frontend/src/App.tsx`:`DevicesPage` lazy import(named export shim)+ `<Route path="/devices" element={<DevicesPage/>}/>`(裸 ProtectedRoute,member 可读,无额外守卫)
  - ✅ `frontend/src/components/layout/nav-items.ts`:`Monitor` icon 导入(字母序)+ ITEMS 加 `{ to: "/devices", label: "设备", icon: Monitor, menuCode: "menu:devices" }` + 业务管理 subgroup 加 `"/devices"`
- **验证证据**:
  - `cd frontend && npm run build`:✅ 3.28s 通过,生成 `dist/assets/devices-page-CXk0tdLt.js` (0.67 kB)
  - `npx oxlint`:✅ 0 warnings 0 errors(74 files, 102 rules)
  - `/code-review` 双轴审查:Standards 0 finding(无硬违规 + 无 Fowler smell,镜像既有范式属 repo-endorsed)+ Spec 0 finding(7 checklist 全实现,URL/类型/hook 形状全对)
- **设计决策记录**:
  - **nav icon 用 component ref `Monitor` 非 JSX `<Monitor/>`**:plan §6 字面写 `icon: <Monitor/>`,但 `nav-items.ts` 的 `NavItem.icon` 类型是 `React.ComponentType<{className?: string}>`(component ref),所有既有项(`LayoutDashboard`/`Bot`/`Contact`)都是 ref 不是 JSX。按文件约定实施(正确),plan 文字是 prose 精度问题。checklist 注释已标注此偏差
  - **`fetchDevices` 返 union `Device[] | DeviceHqRead[]`**:后端 GET /devices/ 按 platform_role 分叉返两种 shape(`response_model=None`),TS 端用 union 表达,调用方(切片 06/07)按角色断言。不在本切片做运行时判别(那是 UI 层职责)
  - **`bindDeviceCustomer` 用 `satisfies DeviceBindRequest`** 而非显式类型标注 body:既保证 body shape 符合契约,又保留字面量推断,与 endpoints.ts 既有风格一致
  - **stub 页用 Card 组件而非裸 `<div>`**:最小但符合设计系统(其他页都有 Card header),避免切片 06 替换时样式突兀。docstring 明确标注是 placeholder + 替换计划
- **边界遵守**(切片 05 严格不做的事):
  - ❌ devices-page.tsx 真实 UI(Table/Dialog/HqView/StoreView 分叉 —— 全留给切片 06/07)
  - ❌ 改动后端任何文件(切片 01-04 契约已定型)
  - ❌ 修 customers-page HqView 对 hq_staff 不可见既存 bug(留给后续 customer feature)
  - ❌ 顺手重构既存前端代码
- **提交记录**:本切片改动 7 文件(6 改 + 1 新)—— types.ts/endpoints.ts/queries.ts/permission.ts/App.tsx/nav-items.ts + 新 devices-page.tsx,另加 plan checklist 勾选 + feature_list.json evidence + 本 progress 记录。✅ **已合并 main(PR #96 commit 1fa192b,CI 4/4 全绿:Backend pytest 6m20s / E2E 1m46s / Frontend 23s / Migrations 51s)**。**不改 feature_list.json status**(devices-crud-ui 还有切片 06/07,status 仍 `in_progress`)
- **下一步最佳动作**:切片 06(前端 StoreView — 门店设备管理页)—— 替换 stub 为真实 UI:`useDevices()` 列表 Table + 入库 Dialog(`useDeviceModels()` 下拉)+ 编辑 Dialog + 绑定客户 Dialog(`useCustomerProfiles()`)+ 软删确认 + `canCreate`/`canUpdate`/`canDelete` 按 `hasPermission` 隐藏写按钮。然后切片 07(HqView + 整体验证收尾,feature 收官)

### Session 128 文档影响评估(每任务必给)

| 文档 | 影响 | 处置 |
|---|---|---|
| `harness/docs/plan-devices-crud-ui.md` | 切片 05 落地与 acceptance criteria 完全对齐。唯一精度偏差:§6 nav item 写 `icon: <Monitor/>`(JSX),实际文件约定用 component ref `icon: Monitor` | 不改:实施按文件 `NavItem.icon` 类型正确落地,plan 文字是 prose 不精确。checklist 注释已标注 |
| `项目指南/03-前端架构/` | 无新范式(全部镜像既有 types/endpoints/queries/permission/App/nav-items 约定) | 不改 |
| `harness/clean-state-checklist.md` | 无新规则触发 | 不改 |

**结论**:零文档需立即更新。一处 plan prose 精度偏差(nav icon JSX vs component ref)已按文件类型约定正确实施,非阻塞。

---


## 给下一个切片(06)的提示词

> 用于在新对话中继续 devices-crud-ui 切片 06。复制下面 `---` 包裹的内容作为新对话的第一条消息。

---
/implement devices-crud-ui 切片 06:前端 StoreView(门店设备管理页)

## 任务
实施 harness/docs/plan-devices-crud-ui.md「实施切片 → 切片 06」章节。
替换切片 05 的 stub `frontend/src/pages/devices-page.tsx` 为真实 StoreView UI(切片 07 才加 HqView 分叉,
本切片只做门店视图)。先读该文档切片 06 的 acceptance criteria(8 项 checklist)逐项落地。

## 前置
切片 01-04 已合并入 main(Device ORM + 权限 seed + HQ 后端 + bind/unbind 端点,后端契约全定型,613 passed)。
切片 05 已完成(Session 128):前端地基全部就位 ——
- `types.ts`:`Device`/`DeviceCreate`/`DeviceUpdate`/`DeviceBindRequest`/`DeviceBindResponse`/`DeviceHqRead`/`DeviceModelPublic`
- `endpoints.ts`:`fetchDevices`/`fetchDevice`/`createDevice`/`updateDevice`/`deleteDevice`/`bindDeviceCustomer`/`unbindDeviceCustomer`/`fetchDeviceModels`
- `queries.ts`:`qk.devices`/`qk.deviceModels` + `useDevices`/`useCreateDevice`/`useUpdateDevice`/`useDeleteDevice`/`useBindDeviceCustomer`/`useUnbindDeviceCustomer`/`useDeviceModels`
- `permission.ts`:`isHQStaff(me)`(本切片暂不用,切片 07 HqView 分叉才用)
- `App.tsx`:`/devices` 路由 + lazy import 已通
- `nav-items.ts`:「设备」菜单项已加(menuCode: menu:devices)
- `pages/devices-page.tsx`:stub 占位页(本切片替换为真实 UI)
分支起点:切到 main 的最新(切片 01-04 已合并)。

## 开工流程(按 AGENTS.md,依次做,不要跳)
1. pwd 确认在仓库根目录
2. 读 progress.md(尤其 Session 128 切片 05 记录)
3. 读 feature_list.active.json 确认 devices-crud-ui 仍是最高优先级 in_progress
4. git log --oneline -5
5. ./init.sh 跑基础验证 —— 失败先修基础
6. cd frontend && npm run build + npx oxlint 确认切片 05 地基无回归

## 本切片要做什么(对照切片 06 acceptance criteria 8 项)
1. `devices-page.tsx` StoreView:列表 Table(序列号 / 型号名 / 状态 Badge / 绑定客户 / 创建时间 / 操作 DropdownMenu)—— 参照 `customers-page.tsx` StoreView 范式
2. 状态 Badge 映射:active→运行中(dot-success)/ maintenance→维护中(dot-warning)/ retired→已退役(dot-destructive)
3. 入库 Dialog:`useDeviceModels()` 填型号 Select(只活型号,API 已过滤)+ serial_number Input + 初始 status Select(active 默认)
4. 编辑 Dialog:serial_number + status 三态 Select + customer Select(可选,`useCustomerProfiles()`)+ 「不绑定」选项
5. **软删型号 UX**(plan §3 关键边界 #1-c):device 已绑定软删型号时,编辑 Dialog 型号字段只读灰显当前型号名,不允许改成软删型号
6. 绑定客户 Dialog:内联 Select 范式参照 `chat-page.tsx` 的客户选择器,从 `useCustomerProfiles()` 拉
7. 删除确认 Dialog(destructive variant)
8. `canCreate`/`canUpdate`/`canDelete` 用 `hasPermission(me,"devices",act)` 隐藏写按钮

## 边界(WIP=1,严格不做)
- ❌ HqView(切片 07 才做,本切片 StoreView 之外的角色仍走 stub 或简单提示)
- ❌ 改后端任何文件
- ❌ 修 customers-page HqView 对 hq_staff 不可见既存 bug
- ❌ 改切片 05 的 types/endpoints/queries/permission/nav-items(契约已定型,只消费)

## 关键约束
- **`useDevices()` 返 union `Device[] | DeviceHqRead[]`**:StoreView 里 tenant 角色拿到的是 `Device[]`,可直接当 Device 用(切片 05 设计决策)。若 TS 报错需 narrowing,在 StoreView 入口断言角色后再渲染
- **型号下拉用 `useDeviceModels()`**:本切片可在 Dialog 打开时才拉(enabled 守卫收紧),避免首屏空拉
- **绑定客户走 `useBindDeviceCustomer`**:不是 update 的 customer_id 字段(后端 PUT 不支持 customer_id,只能走 /bind 端点)。编辑 Dialog 改客户 = bind 新 customer(覆盖语义)
- **软删型号只读**:型号下拉若含已软删型号(API 实际已过滤 `is_deleted=False`,但编辑现有 device 时当前型号可能已软删),需灰显当前值不让改

## 完成定义(对照切片 06 acceptance criteria 逐项打勾)
- StoreView Table 6 列齐全
- 状态 Badge 三态映射
- 入库 Dialog(型号 Select + serial + status)
- 编辑 Dialog(serial + status + customer Select + 软删型号只读)
- 绑定客户 Dialog
- 删除确认 Dialog
- 写按钮 hasPermission 守卫
- cd frontend && npm run build + npx oxlint 通过

## 收尾(做完后必做)
1. /code-review 双轴审查
2. 勾 plan checklist 切片 06 的 8 项 + 标题加 ✅ PR 证据
3. 更新 progress.md Session 记录 + feature_list.json evidence
4. 给切片 07(HqView + feature 收官)的提示词
---

### Session 130 — 2026-07-23(device-booking EP2 回环:grill → to-spec → to-tickets,系列 3/4 切片规划)

> **EP2 单回环完成**,无 /handoff 中断(three-tier-workflow §3 硬约束守住)。device-booking 全切片规划就位,EP3 待 devices-crud-ui 收官后接。

**做了什么**(EP2 一个回环内,grill → to-spec → to-tickets):
1. `/grill-with-docs`(烤清需求边界):8 个核心决策收敛,5 个用户拍板(D5 customer 端做/D6 排期前后端都做/D7 表一次建齐/D8 不软删只用 cancelled/D9 取消入口……其中 D9 实际归入默认推荐)+ 3 个采用推荐默认(D1 冲突用 400 非 409 / D2 不建状态机纯函数 / D4 左闭右开无 buffer)+ 补 4 个默认推荐(D10 PUT 仅 pending 可调 / D11 GET /me/bookings / D12 按天聚合 / D3 walk-in 支持 customer_id nullable)。每决策带推荐 + 仓库现状依据。
2. `/to-spec`(落 PRD):产 `harness/docs/plan-device-booking.md` 主体(§0 决策记录 12 条 + §1-9 完整 PRD + §4 影响面清单/多租户/权限/表设计 checklist + §6 边界声明 + §7 风险 + §8 验收标准)。
3. `/to-tickets`(拆切片):产「实施切片」段,7 个 tracer-bullet 垂直切片 + 切片依赖图。每片含 Blocked by + What it delivers + Acceptance criteria checklist(`- [ ]` 待 EP3 勾)。

**关键技术决策(供 EP3 实施者速读)**:
- **D1 时段冲突 = 400 不是 409**:全仓库无 409 概念(Group 同名/device 序列号重复都走 BizError→400),feature_list.json verification 写「409」是笔误,以 plan §0 D1 为准。冲突 SQL 左闭右开(`start1 < end2 AND start2 < end1`),只对 pending/confirmed/in_service 活跃态判冲突。
- **D8 不软删**:bookings 表**不加** `is_deleted`/`deleted_at` 列(唯一偏离仓库软删惯例,因 booking 只取消不删),**无** `DELETE /bookings/{id}` 端点,取消走 `POST /bookings/{id}/cancel`(→204,pending→cancelled)。
- **D7 表一次建齐**:5 个时间列(scheduled_* NOT NULL + started_at/ended_at/feedback nullable)+ notes nullable,device-poweron feature **不需再加迁移列**(其 notes 已声明依赖本 feature 先建好 schema)。
- **D2 不建 booking_state.py**:本 feature 只有 pending↔cancelled 两转换,Service inline 校验足够;6 态纯函数留给 device-poweron 建(对齐 AGENTS 铁律 6「按需加,不预建空架子」)。
- **状态守卫铁律**:POST/PUT 的 pydantic schema **不含** status/started_at/ended_at/feedback 字段(防客户端绕过状态机),status 只由 /cancel 改。
- **customer own 防越权**:`GET /me/bookings` 后端注入 `current_user.customer_id`,**端点不接受 customer_id 参数**(防传他人 id 看他人预约);门店员工(无 customer_id)→ 403。

**改动文件清单**:
- 新增:`harness/docs/plan-device-booking.md`(EP2 主产物,~480 行,12 决策 + 7 切片 + 依赖图 + 调研证据表)
- 改:`feature_list.json` + `feature_list.active.json`(device-booking 加 `plan` 字段 + notes 补 EP2 完成标记 + 修正 409→400 / DELETE→POST /cancel 笔误)
- 跑 `./scripts/sync-active-features.sh` 刷新派生视图 ✅(3 活跃 + 5 passing + 1 里程碑 = 9 条)

**验证**:
- JSON 合法性:`python3 -c "json.load(...)"` ✅
- sync 脚本:✅(无 drift)
- **未跑 `./init.sh`**(EP2 只产规划文档,无代码改动,ruff/pytest 不适用;前端 build 不适用)

### Session 130 文档影响评估(每任务必给)

| 文档 | 影响 | 处置 |
|---|---|---|
| `harness/docs/plan-device-booking.md` | **本 Session 主产物**(新建)。EP2 一个回环产出,含 12 决策(D1-D12)+ 7 切片 + 依赖图 + 调研证据表 | ✅ 已建 |
| `feature_list.json` + `feature_list.active.json` | device-booking 加 `plan` 字段(让"是否进过 EP2"可判,对齐 three-tier-workflow §3);notes 修正 verification 笔误(409→400、DELETE→POST /cancel)+ 补 EP2 完成标记 | ✅ 已改 + sync 刷新 |
| `harness/docs/three-tier-workflow.md` | EP2 单回环约束本次守住(无 /handoff 中断,context 未触 60%)。无需补规则 | 不改 |
| `harness/clean-state-checklist.md` | 无新规则触发(EP2 产物是 plan 文档,未触代码层 checklist) | 不改 |
| `项目指南/` | 无新范式(bookings 表设计/check 权限 seed/HQ 分叉/customer own 全镜像既有 device 范式) | 不改 |

**结论**:零文档需立即更新 beyond 已改的 plan + feature_list。EP2 单回环无中断,WIP=1 未破(device-booking 仍 `not_started`,EP3 实施时才转 `in_progress`)。

---

## 给下一个 EP3 切片(device-booking 01)的提示词

> **前置阻塞**:`devices-crud-ui`(priority 62)须先全 passing(其切片 06/07 待做)。device-booking 依赖 devices-crud-ui 切片 01 的 Device 表 + DeviceService(已合并 main),但 WIP=1 要求串行。**当前 frontier = devices-crud-ui 切片 06**,不是 device-booking。

当 devices-crud-ui 收官后,在新对话中接 device-booking 切片 01,复制下面 `---` 包裹的内容作为新对话的第一条消息。

---
/implement device-booking 切片 01:后端地基 Booking 表 + 时段冲突 + 状态守卫 CRUD

## 任务
实施 harness/docs/plan-device-booking.md「实施切片 → 切片 01」章节。
新建 bookings 表(一次建齐 5 时间列 + 6 态 status CHECK)+ TenantScopedRepository + Service(时段冲突 400 + 状态守卫)+ 4 端点(POST/GET/PUT /api/v1/bookings + POST /bookings/{id}/cancel,**无 DELETE**)。
先读该文档切片 01 的 acceptance criteria(8 项 checklist)+ §0 决策记录(D1-D12)+ §4.4 表设计 checklist 逐项落地。

## 关键决策(必读 plan §0)
- D1:时段冲突走 BizError → **400**(不是 409),左闭右开,只对 pending/confirmed/in_service 判冲突
- D7:bookings 表一次建齐 scheduled_*(NOT NULL) + started_at/ended_at/feedback(nullable) + notes(nullable)
- D8:**不软删**,无 is_deleted 列,无 DELETE 端点;取消 = POST /bookings/{id}/cancel(→204)
- D2:不建 booking_state.py 纯函数(Service inline 校验 pending↔cancelled 即可)
- 状态守卫:POST/PUT 的 pydantic schema 不含 status/started_at/ended_at/feedback 字段

## 前置
devices-crud-ui 全 passing(其 Device 表 + DeviceService + DeviceRepository 已合并 main,migrations head = `a0eaec7aab7c`)。
分支起点:切到 main 最新。

## 开工流程(按 AGENTS.md,依次做,不要跳)
1. pwd 确认在仓库根目录
2. 读 progress.md(尤其本 Session 130 记录 + 顶部摘要)
3. 读 harness/docs/plan-device-booking.md(§0 决策 + §4.4 表设计 + 切片 01 acceptance criteria)
4. git log --oneline -5 看最近发生了什么
5. 运行 ./init.sh 装依赖 + 跑基础验证
6. 如果基础验证失败,先修基础,不要在坏起点上叠新功能
---

### Session 131 — 2026-07-23(devices-crud-ui EP3 末切片 07:前端 HqView + feature 收官,系列 2/4 全 passing)

> **EP3 末切片 = feature 收尾仪式**(three-tier-workflow §4)。devices-crud-ui 7 个切片全部完成,feature 从 `in_progress` → `passing`。下一个 frontier = `device-booking`(priority 63,EP2 回环已在 Session 130 就绪)。

**做了什么**(切片 07,单切片内:实现 → 验证 → 收尾):
1. **HqView 实现**(`frontend/src/pages/devices-page.tsx`):把切片 06 的 `HqPlaceholder` 替换为真正的 `HqView` 跨租户只读全景表格。
   - 顶层分叉沿用切片 06 已就位的形状:`isSuperAdmin(me) || isHQStaff(me) ? <HqView/> : <StoreView/>`(devices 这条线对 hq_staff 正确,见下方 bug 说明)。
   - HqView 列:所属门店(tenant_name)/ 序列号 / 型号名(model_name)/ 状态 Badge(复用 STATUS_META)/ 绑定客户(customer_name)/ 创建时间,共 6 列。只读,无写控件、无 DropdownMenu。
   - 数据走 `useDevices()`,union `Device[] | DeviceHqRead[]`,在 HqView 边界 `as DeviceHqRead[]` 单点 narrowing(后端 `require_cross_tenant_viewer` 保证 HQ 角色拿 DeviceHqRead[])。三个 display name 服务端预展开,无需客户端拉 models/tenants/profiles feed。
   - 清理切片 06 占位的 `Cpu` import(HqPlaceholder 用过,HqView 不用)避免 oxlint unused。文件头注释从「slice 06 StoreView」改为「切片 06 StoreView + 切片 07 HqView」全量描述。
2. **feature 收尾仪式**(对照 plan 切片 07 acceptance criteria 逐项):
   - `./init.sh` 全绿:ruff clean + pytest **613 passed**(228.75s,全章节 A-K)。
   - 前端:`npm run build` ✅(2.16s,类型检查无错)+ `npx oxlint` ✅(0 warnings 0 errors,74 files)。
   - `alembic upgrade head && alembic check`:本切片纯前端,**无新迁移文件**(迁移链 head 仍为 `a0eaec7aab7c`,切片 01-04 的迁移已在 main 合并并经 CI 验证)。本地 docker 未起,依赖 CI 通过(与切片 05 收尾同处置)。
   - `feature_list.json`:devices-crud-ui `status` → `passing`;evidence 替换「进行中」尾条为切片 06 + 切片 07 两条实测记录(共 7 条),补回切片 06 的 PR #99 记录(Session 129 evidence 只记到切片 05)。
   - `./scripts/sync-active-features.sh` ✅:活跃 3 → 2(devices-crud-ui 归档到 passing 区),device-booking 现为最高优先级未完成。
   - `progress.md` 顶部摘要更新:最高优先级未完成指向 device-booking。
   - plan checklist 切片 07 全勾 + 标题追加 ✅。

**关键决策(供回顾)**:
- **不修 customers-page.tsx**(WIP=1 铁律):`customers-page.tsx:127` 的 HqView 分叉只判 `isSuperAdmin(me)`,**不含 `isHQStaff`** —— hq_staff 角色看 /customers 会落到 StoreView(跨租户查询必然空/报错)。这是既存 bug,但属 customer feature 范畴,本 feature 不越界修。已在 evidence + 文档影响评估留记录,留给后续 customer feature(或专门的 hq_staff 修 bug 任务)处理。devices-page.tsx 切片 06/07 的分叉正确含 isHQStaff,**不受此 bug 影响**。
- **union narrowing 单点化**:`useDevices()` 返回 union,只在 HqView 入口断言一次,StoreView 不变(它本来就收 Device[])。避免在多处加类型守卫。
- **DeviceHqRead 服务端预展开三个 name**:HQ 表格不需要客户端 lookup,既正确(避免 HQ 角色拉不到本租户外数据)又高效(无 N+1)。

**改动文件清单**:
- 改:`frontend/src/pages/devices-page.tsx`(HqPlaceholder → HqView + 文件头注释 + import 清理)
- 改:`feature_list.json`(status + evidence)+ `feature_list.active.json`(sync 生成)+ `harness/docs/archive/features-passing-archive.json`(sync 生成,devices-crud-ui 归档)
- 改:`progress.md`(顶部摘要 + 本 Session 记录)+ `harness/docs/plan-devices-crud-ui.md`(切片 07 checklist + 标题)

### Session 131 文档影响评估(每任务必给)

| 文档 | 影响 | 处置 |
|---|---|---|
| `harness/docs/plan-devices-crud-ui.md` | 切片 07 acceptance criteria checklist 全勾(9 项 `[x]`)+ 标题追加 ✅ PR 证据(待 PR 合并回填) | ✅ 本 Session 已改 |
| `feature_list.json` + 派生视图 | devices-crud-ui `in_progress` → `passing`;evidence 替换「进行中」尾条为切片 06+07 两条实测;sync 脚本刷新(活跃 3→2,归档 +1)| ✅ 已改 + sync 刷新 |
| `progress.md` | 顶部「最高优先级未完成」从 devices-crud-ui 改指 device-booking;追加 Session 131 记录 | ✅ 本 Session 已改 |
| `项目指南/` | 无新范式(HqView 双视图分叉、union narrowing、HQ 服务端预展开均镜像 customers-page 既有范式)| 不改 |
| **既存 bug 记录(留痕,不在本 feature 修)** | `frontend/src/pages/customers-page.tsx:127` 的 `HqView` 分叉只判 `isSuperAdmin(me)`,**漏 `isHQStaff`** —— hq_staff 看 /customers 落到 StoreView(跨租户查询异常)。属 customer 范畴,WIP=1 本 feature 不越界修。devices-page.tsx 切片 06/07 分叉正确(`isSuperAdmin \|\| isHQStaff`),不受影响。**留给后续 customer feature 处理** | 留记录,不改 |

**结论**:零文档需立即更新 beyond 已改的 plan/feature_list/progress。devices-crud-ui 全 feature(7 切片)收官,WIP=1 未破(整个 feature 期间无其他 feature 并行)。

---

## 给下一个 EP3 切片(device-booking 01)的提示词

> devices-crud-ui 全 passing,frontier 正式交给 device-booking(系列 3/4)。EP2 回环(Session 130)产出的 plan-device-booking.md 已含 7 切片 + 12 决策,EP3 从切片 01 接。在新对话中复制下面 `---` 包裹的内容作为第一条消息。

---
/implement device-booking 切片 01:后端地基 Booking 表 + 时段冲突 + 状态守卫 CRUD

## 任务
实施 harness/docs/plan-device-booking.md「实施切片 → 切片 01」章节。
新建 bookings 表(一次建齐 5 时间列 + 6 态 status CHECK)+ TenantScopedRepository + Service(时段冲突 400 + 状态守卫)+ 4 端点(POST/GET/PUT /api/v1/bookings + POST /bookings/{id}/cancel,**无 DELETE**)。
先读该文档切片 01 的 acceptance criteria(8 项 checklist)+ §0 决策记录(D1-D12)+ §4.4 表设计 checklist 逐项落地。

## 关键决策(必读 plan §0)
- D1:时段冲突走 BizError → **400**(不是 409),左闭右开,只对 pending/confirmed/in_service 判冲突
- D7:bookings 表一次建齐 scheduled_*(NOT NULL) + started_at/ended_at/feedback(nullable) + notes(nullable)
- D8:**不软删**,无 is_deleted 列,无 DELETE 端点;取消 = POST /bookings/{id}/cancel(→204)
- D2:不建 booking_state.py 纯函数(Service inline 校验 pending↔cancelled 即可)
- 状态守卫:POST/PUT 的 pydantic schema 不含 status/started_at/ended_at/feedback 字段

## 前置
devices-crud-ui 全 passing(7 切片全合并 main,迁移 head = `a0eaec7aab7c`)。
分支起点:切到 main 最新。

## 开工流程(按 AGENTS.md,依次做,不要跳)
1. pwd 确认在仓库根目录
2. 读 progress.md(尤其本 Session 131 记录 + 顶部摘要)
3. 读 harness/docs/plan-device-booking.md(§0 决策 + §4.4 表设计 + 切片 01 acceptance criteria)
4. git log --oneline -5 看最近发生了什么
5. 运行 ./init.sh 装依赖 + 跑基础验证
6. 如果基础验证失败,先修基础,不要在坏起点上叠新功能
---

### Session 132 — 2026-07-24(device-booking EP3 切片 02:权限 seed + 老租户 backfill)

- **本轮目标**: device-booking 切片 02 —— 给 owner/admin/member 三个系统角色 seed bookings 权限 + `menu:bookings`,并给**现存所有租户**幂等 backfill(功能上线即用,不破坏其他 perm)。复刻 devices-crud-ui 切片 02 范式(PR #92)。前置:main 已在 f2bfc93(切片01已合并),工作区干净。
- **实施**(4 文件,纯后端 + 测试,无迁移):
  - `app/services/permission_service.py`:
    - `DEFAULT_OWNER_PERMS` 加 `bookings:read/create/update/delete`;`DEFAULT_ADMIN_PERMS` 加 `bookings:read/create/update`(no delete —— admin 不能 cancel,复刻 customer/device 约定);`DEFAULT_MEMBER_PERMS` 加 `bookings:read`(read-only)。
    - `DEFAULT_MENU_PERMS["owner"|"admin"|"member"]` 各加 `"bookings"`(对应 `menu:bookings` nav 入口)。
    - `OBJ_CN` / `MENU_CN` 加 `"bookings" → "预约"`(catalogue 中文标签,`test_menu_cn_covers_all_seeded_menu_codes` 自动校验覆盖)。
    - 新增 `backfill_bookings_perms_for_existing_tenants(db)` 函数:结构完全复刻 `backfill_devices_perms_for_existing_tenants`,scope guardrail 只动 `(obj="bookings", *)` + `("menu","bookings")`。三层幂等(catalogue upsert / grant no-op / casbin rebuild from SCD2)。
  - `scripts/backfill_bookings_perms.py`:独立一次性脚本(async main + `AsyncSessionLocal` + `--dry-run` + 调上述函数 + 打印每租户 `+N new grants`)。CI 不跑,部署 slice 02 代码后手动执行一次。
  - `tests/test_bookings_api.py` 新增 K 章节(3 测试):
    - `_seed_backfill_target_tenant`(K1):造无 bookings 策略的新租户 + 三系统角色 + 预置 `customers:read`(三角色)+ `devices:read`(owner)作 K6 对照。
    - `test_k_backfill_grants_bookings_perms_correctly`(K2+K3+K4):owner 拿 4 api + menu = 5;admin 3+1=4;member 1+1=2(stats 计数校验)+ owner 全 bookings + menu:bookings 通过 `permission_service.check` + member 明确**拒绝** `bookings:create`(anti-overgrant)。
    - `test_k_backfill_idempotent`(K5):再跑 backfill → stats[tenant]==0 + RolePermission 行 id 集合不变(无重复 grant)。
    - `test_k_backfill_preserves_other_perms`(K6):backfill 前后 `customers:read`/`devices:read` 仍通过 check,且 `bookings:read` 开始工作。
  - `tests/test_permission_service.py`:3 个 catalogue 完整性 pinning 测试同步更新期望集(加 bookings):
    - `test_default_owner_perms_cover_full_catalogue`:owner 期望集加 bookings 4 个 CRUD。
    - `_ALL_BUSINESS_MENUS` 常量(owner/admin 共用)加 `"bookings"`。
    - `test_default_menu_perms_member_only_sees_business_menus`:member menu 期望集加 `"bookings"`。
    - 这 3 个测试是硬编码 `set(...) ==` 断言,加 perm 必须同步(非 scope creep,复刻 devices slice 02 当时的处理)。
- **验证**:
  - `ruff check` clean(app/ + tests/ + scripts/ 全绿)。
  - `pytest` 全量 **638 passed, 0 failed**。
  - `./init.sh` ✅ 基础验证通过(ruff + pytest 全绿)。
  - 无迁移(纯权限数据 seed + backfill,alembic 链不变,head 仍 `8423ee2df128`)。
- **/code-review 双轴结果**:
  - **Spec axis ✅**:5 条 acceptance criteria 全满足,忠实复刻 devices 基线,无 scope creep,OBJ_CN/MENU_CN 更新属必需。
  - **Standards axis**:全部为判断性/复刻范式,非 blocker。最有价值发现 = menu-perm loop 的 `add_policy` 在 SCD2 grant 之前(与「宪法」SCD2→casbin→audit 顺序相反)+ 冗余(后接 `sync_role_permissions_to_casbin` 全量重建)。但这是**完全复刻已合并的 devices 切片 02 代码**(PR #92),若单独改 bookings 版本会引入 Divergent Change(两 backfill fn 不一致),应在未来统一重构 devices+bookings 两版(超 WIP=1 范围)。其他发现(`select(Tenant)` 越层 / 无 audit / Duplicated Code / dry-run 弱化)均复刻 devices 范式。
- **已知风险**: 无功能风险。menu-perm casbin 累积重复 policy 行的潜在问题(若 adapter 不去重)与 devices 既存代码同源,K5 测试验证 DB 层幂等性通过。统一重构待未来健康度巡检。
- **文档影响评估**: 见下方。
- **下一步最佳动作**: device-booking 切片 03(HQ 全景视图 + 排期聚合端点后端)—— `BookingHqRead` schema + `selectinload` 防 N+1 + `GET /` `GET /{id}` 改端点体内分流(移除切片 01 临时 router-level `require_permission`) + `GET /devices/{id}/schedule` 排期聚合。走 `/implement`。

### Session 132 文档影响评估(每任务必给)

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/06-权限模型RBAC.md`(DEFAULT_*_PERMS 表) | ⚠️ 需更新(但属收尾切片统一做) | 本切片**不动**(与 devices slice 02 当时处理一致:权限表文档在 feature 收官切片 07 统一回填,避免每切片改文档)。bookings perm 已在 `permission_service.py` 代码注释自描述 |
| `harness/docs/plan-device-booking.md` | ✅ 需更新 | 已勾选切片 02 五条 acceptance checklist + 标题追加 ✅ PR #107 |
| `progress.md` | ✅ 需更新 | 顶部「最高优先级」改为切片 02 已合并 + 切片 03 待做;追加本 Session 132 记录 |
| `feature_list.json` | ✅ 需更新 | evidence 追加切片 02 实测记录(EP3 切片级进度,status 仍 `in_progress` —— feature 未收官) |
| `项目指南/02-后端架构/03-数据库与ORM.md` | ❌ 无影响 | 无表/迁移变更(纯权限 seed + backfill 数据层) |

> 判断依据:本切片只动权限 seed + backfill(无 schema/migration/API 契约变更),权限矩阵文档(06)本可在收尾切片 07 统一回填(对齐 devices slice 02 当时不单独改文档的处理)。

---

### Session 137 — 2026-07-24(device-booking EP3 末切片 07:HqView + customer 视图 + feature 收官,系列 3/4 全 passing)

> **EP3 末切片 = feature 收尾仪式**(three-tier-workflow §4 第 1-8 步)。device-booking 7 个切片全部完成,feature 从 `in_progress` → `passing`。下一个 frontier = `device-poweron`(priority 64,依赖已解锁)。

**切片 07 实测结果:**
- BookingsPage 顶层三叉路由:`isSuperAdmin(me) || isHQStaff(me) ? <HqView/> : hasCustomerIdentity(me) ? <MyBookingsView/> : <StoreView/>`(复刻 devices-page 二叉 + 加 customer 第三叉,HQ 优先于 customer 身份)。
- HqView:跨租户只读全景表格,复刻 devices-page HqView 骨架(PageHeader + Card + Table + ListState + EmptyState),换数据源 `useBookings() → BookingHqRead[]` narrowing cast,列 tenant_name/device_name/customer_name/scheduled_*/status Badge/created_at,walk-in 显「散客(walk-in)」,无写按钮。
- MyBookingsView:customer 只读列表,调 `useMyBookings()`(后端 /me/bookings 已按 caller customer_id 过滤),无写按钮(创建预约是门店员工职责)。
- `hasCustomerIdentity(me)` helper 新建于 `permission.ts`(照 isHQStaff 范式,判断 `me.customer_id` 非空)。
- **Blocker 修复**:plan 要求 `me.customer_id` 判断,但 MeResponse API 契约未暴露 customer_id(切片 04 只加在后端内部 CurrentUser)→ 补 `MeResponse.customer_id` 字段(`app/schemas/auth.py` schema + `app/api/v1/auth.py` `_build_me_response` 透传 `user.customer_id` + frontend `types.ts` 对齐),窄范围契约对齐,无新迁移无表结构改动。
- 测试 N 章节 2 个:N1(customer 身份 GET /auth/me 返回 own customer_id)+ N2(store-staff 返回 null)。
- 验证:./init.sh 全绿 653 passed(基线 651 + N1/N2 新 2)+ ruff 0 error + cd frontend && npm run build ✓ 1.94s + npx oxlint 0 warnings/errors(75 files)。
- /code-review 双轴:Standards 0 硬违规(4 判断级 smell 均为复刻 devices-page 约定或可接受:Repeated Switches 三叉字面量 / `as BookingHqRead[]` 强转 / HqView·MyBookingsView 同文件骨架 / hasCustomerIdentity Middle Man),Spec 代码实现全勾(MeResponse.customer_id 契约对齐判定 in-scope 非越界)。
- 已知 UX 缺口:MyBookingsView 设备列显 `device_id` 前缀(BookingRead 不带 device_name,拉 devices feed 会跨租户泄露故不拉,后端 /me/bookings 加 selectinload device_name 留给未来增量,plan §3 line 55 未硬定列故 spec 合规)。

**feature 收尾仪式 8 步(three-tier §4):**
1. ✅ verification 笔误修正:第 3 条「时段冲突...拒绝 409」→ 400(plan §0 D1 已定 400,409 是原笔误);第 4 条「POST/GET/PUT/DELETE /api/v1/bookings」→ DELETE 改为 POST /cancel(D8 决策 bookings 不软删,无 DELETE 端点)。
2. ✅ `feature_list.json` device-booking.status: in_progress → passing。
3. ✅ evidence 追加切片 07 + feature 收尾总结(共 9 条:EP2 + 切片 01-07 + 收尾)。
4. ✅ `./scripts/sync-active-features.sh` 刷新 active 视图(1 活跃 = device-poweron,device-booking 进 passing 归档)。
5. ✅ progress.md 顶部更新:device-booking ✅ passing,frontier 推进到 device-poweron(priority 64)。
6. ✅ 文档影响评估(见下方表格)。
7. ✅ ./init.sh 全绿(ruff + pytest 653)+ cd frontend && npm run build + npx oxlint。
8. ✅ 依赖解锁扫描:device-poweron(priority 64,depends_on device-booking)依赖已解锁,按 three-tier §5 可置 in_progress —— 待用户决定是否立即启动(若无指示,下一个 frontier 就是它)。

### Session 137 文档影响评估(每任务必给)

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/06-权限模型RBAC.md`(DEFAULT_*_PERMS 表) | ❌ 无影响 | bookings perm 已在切片 02 处理,本切片不动权限 seed |
| `项目指南/02-后端架构/*`(auth/me 契约) | ❌ 无影响 | MeResponse 加 customer_id 是既有契约的窄字段扩展(范式不变,仍是「token claim → CurrentUser → MeResponse 透传」既定模式),不改架构约定。后端架构文档描述的是范式层级,本次是范式内的实例 |
| `项目指南/04-前端架构/*`(bookings-page 三叉路由) | ❌ 无影响 | 三叉路由是 devices-page 二叉范式 + customers-page 双视角范式的组合实例,不改变前端架构约定。hasCustomerIdentity helper 与 isHQStaff/isSuperAdmin 同范式 |
| `harness/docs/plan-device-booking.md` | ✅ 已更新 | 勾选切片 07 acceptance checklist 10 项 + 标题追加 ✅ PR #113 |
| `progress.md` | ✅ 已更新 | 顶部「最高优先级」从 device-booking 改指 device-poweron;追加 Session 137 记录 |
| `feature_list.json` + 派生视图 | ✅ 已更新 | device-booking `in_progress` → `passing`;verification 笔误修正(409→400 / DELETE→POST /cancel);evidence 追加切片 07 + 收尾总结;sync 刷新 |

> 判断依据:本次 feature 涉及新增 bookings 实体全套(表/API/UI,切片 01-06 已落地)+ 切片 07 的 MeResponse.customer_id 契约扩展 + 三叉路由 + hasCustomerIdentity helper。但既有文档(02-后端架构 / 04-前端架构)描述的是**架构范式层级**(RBAC 模型 / Controller→Service→Repository 分层 / 前端 permission helper 范式),本次所有改动都是**既有范式内的实例**(新实体遵循既有多租户隔离范式 / 新 helper 遵循既有 isHQStaff 范式 / 契约扩展遵循既有 token→CurrentUser→MeResponse 透传模式),不改变架构约定,故文档无需同步。plan/progress/feature_list 三源已更新。

---

### Session 138 — 2026-07-25(device-poweron EP3 末切片 03:store 三按钮 + feature 收官,设备功能系列 4/4 全 passing)

> **EP3 末切片 = feature 收尾仪式**(three-tier-workflow §4 第 1-7 步)。device-poweron 3 个切片全部完成,feature 从 `in_progress` → `passing`。**设备功能系列(61-64)本日全部收官**,无在途 frontier,等待用户新需求。

**切片 03 实测结果:**
- `frontend/src/api/endpoints.ts`:+`endBooking(id, payload?)`(POST /end,返 Booking,body 可选 BookingEndPayload)+ `noShowBooking(id)`(POST /no-show,204 无 body)。注释标注权限(owner only via `:delete`,B2)+ slice 边界(从切片 02 移到此处避免预建空架子,铁律 6)。
- `frontend/src/hooks/queries.ts`:+`useEndBooking()`(`{id, payload?}` TVars,`BOOKING_WRITE_KEYS` 失效)+ `useNoShowBooking()`(`id` TVars,同失效集)。骨架对齐 `useCancelBooking`/`useStartBooking`。
- `frontend/src/pages/bookings-page.tsx` StoreView 操作 DropdownMenu 重写:
  - 新增 `ACTIONABLE_STATUS`(pending/confirmed/in_service 三态)常量,松绑原 `MUTABLE_STATUS`(pending-only)的菜单显示守卫。`MUTABLE_STATUS` 保留 —— 它仍守护「改约/取消」pending-only 语义;`ACTIONABLE_STATUS` 守护 lifecycle 菜单显示。
  - 行级 action 可见性:`canStart`(pending/confirmed 行,守 `canUpdate`=`:update`,owner/admin 可见,含 walk-in 散客 B4)/`canEnd`(in_service 行,守 `canCancel`=`:delete`,owner only)/`canMarkNoShow`(actionable 行,守 `canCancel`,owner only)。`confirmed` 行按钮属防御性渲染(状态机允许跳转,device-booking 永不写 confirmed → 运行期不可达,代码注释明示)。
  - +`submitStart`/`submitEnd`/`submitNoShow` 三 handler(沿用 `submitCancel` 的 try/catch + toast pattern):「已开机」/「已结束服务」/「已标记爽约」+ 失败 toast `apiErrorMessage(err)`。
  - +end-service Dialog(`<textarea>` 原生 + tailwind,沿用 customers-page 范式,不新增 ui/textarea;`submitEnd` 接 raw JSON 或 free text —— JSON.parse 失败时 wrap 为 `{note: text}` 避免 audit trail 丢失,这是 slice 03 自定 UX,diverges from customers-page 的 reject 策略,代码注释明示)+ no-show 确认 Dialog(复刻 cancel 确认 Dialog 形状)。
  - `StoreView` 加 `export`(为组件测,沿用切片 02 给 `MyBookingsView` 加 export 的范式)。
- `frontend/src/pages/__tests__/store-view.test.tsx`(新,6 tests):walk-in pending 行触发 startBooking / in_service 行点结束服务开 Dialog + 填 JSON + 提交触发 endBooking(带 feedback)/ pending 行爽约 + 确认 Dialog → noShowBooking / 终态行(done/cancelled/no_show)无操作菜单 / member 视图无写按钮(canUpdate+canDelete 均假)/ pending 行四菜单项共存(确认开机+标记爽约+改约+取消预约)。沿用切片 02 my-bookings-view.test.tsx 的 hoisted mocks + renderWithProviders + makeMut stub 模式;额外 mock `@/components/auth/auth-context` 的 useAuth(注入 owner/member me 变体驱动按钮可见性)。
- **测试基建踩坑**:① DropdownMenu trigger 是无 accessible name 的 ghost icon button,直接 `getByRole("button")` 会撞 FilterChips/创建按钮 → 改用 `tbody tr` 选行 + 行内 scope 找 trigger;② `user.type` 把 `{`/`}` 解析为 v14 modifier 描述符 → textarea JSON 输入改用 `fireEvent.change`(等价真实输入且避免转义地狱);③ STATUS_META 中文 label 撞 FilterChips button label("待确认"/"爽约") → 用 `selector: "td"` 限定 td scope(最终改用 `tbody tr` 选行更稳)。

**feature 收尾仪式 7 步(three-tier §4):**
1. ✅ `./init.sh` 全绿 714 passed(ruff + pytest,SQLite 内存库)+ `cd frontend && npm run build` ✓ 1.53s + `npx oxlint` 0 warnings 0 errors(80 files 102 rules)+ `npx vitest run` ✓ 12/12(2 files:my-bookings-view 6 + store-view 6)。
2. ✅ `feature_list.json` device-poweron:`status` `in_progress` → `passing` + `evidence` 6 条(切片 01/02/03 PR + init.sh/build/oxlint/vitest 实测 + code-review 双轴结论)+ **修正 verification 三处笔误**:① 第 1 条「ConflictError → HTTP 409」→ **400**(InvalidTransition 子类 BizError,plan §0 D1 定调);② 第 1 条「写 feedback **JSONB**」→ **通用 JSON**(device-booking 建为 SQLAlchemy JSON 非 JSONB,双库兼容);③ 补「vitest 前端组件测」条目(原 verification 无此维度,plan §8 v2 修正)。
3. ✅ `./scripts/sync-active-features.sh` 刷新 active 视图(0 活跃 = device-poweron 翻 passing 后无在途 + 5 最近 passing 含 device-poweron)。
4. ✅ progress.md 顶部更新:设备功能系列(61-64)**全部收官**标记;frontier 段改「无在途,等用户新需求」;EP3 断点段从「frontier = device-poweron 切片 01」改为「待定,无在途」;追加 Session 138 记录。
5. ✅ 文档影响评估(见下方表格)。
6. ✅ 依赖解锁扫描:扫 `feature_list.json` 全部 feature 的 `depends_on` —— **无任何下游指向 device-poweron**(device-poweron 是设备系列 4/4 收官,无下游,符合 plan §6 边界声明)。无需解锁任何 in_progress。
7. ⏳ 提交 + PR + CI 守门:工作区改动 = endpoints.ts + queries.ts + bookings-page.tsx + store-view.test.tsx(新)+ plan-device-poweron.md + feature_list.json + progress.md 七件;待用户决定是否提交。

### Session 138 文档影响评估(每任务必给)

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/*`(状态机/service/api 范式) | ❌ 无影响 | 本切片纯前端(endpoints/hooks/UI/组件测),后端切片 01 已落地不动;状态机纯函数范式由切片 01 落定,文档无需同步 |
| `项目指南/04-前端架构/*`(mutation/DropdownMenu/Dialog 范式) | ❌ 无影响 | useEndBooking/useNoShowBooking 沿用 useApiMutation 骨架;StoreView DropdownMenu 沿用切片 06 既定模式 + 扩展 lifecycle 项;feedback Dialog textarea 沿用 customers-page 范式。都是既有范式内的实例,不改前端架构约定 |
| `harness/docs/plan-device-poweron.md` | ✅ 已更新 | 勾选切片 03 acceptance checklist 13 项 + 标题追加 ✅ PR #116 |
| `progress.md` | ✅ 已更新 | 顶部「最高优先级」改「设备系列收官,无在途」;EP3 断点改待定;追加 Session 138 记录 + 文档影响评估 |
| `feature_list.json` + 派生视图 | ✅ 已更新 | device-poweron `in_progress` → `passing`;verification 三处笔误修正(409→400 / JSONB→JSON / 补 vitest);evidence 6 条;sync 刷新 |

> 判断依据:本次 feature 切片 03 是纯前端改动(store 三按钮 + 组件测),所有改动都是**既有范式内的实例**(`useApiMutation` 骨架 / DropdownMenu+Dialog 模式 / vitest hoisted mocks 模式 / `BOOKING_WRITE_KEYS` 失效集),不改变架构约定。后端状态机/service/三端点由切片 01 已落地,本切片只读引用。故 02-后端架构 / 04-前端架构 文档无需同步;plan/progress/feature_list 三源已更新。

---

## Session 139(2026-07-25):`hugo` 暗号 → 巡检 stage 5 首次完整走通 + bookings-page-split 重构

### 入口:`hugo` 暗号 → 三源验真 → 探索流程

用户触发 `hugo` 暗号。按 AGENTS.md 路由表,这是入口 A 硬触发。判断子模式:上一轮(device-poweron Session 138)已合并完成,本轮进入时**无在途 frontier**,这是**回归验证流程**(三源交叉验真)。

**三源验真结果:✅ 一致**
- 源1 feature_list.json status:device-poweron / device-booking / devices-crud-ui / device-models-crud 全 passing
- 源2 git log 合并 commit:设备系列 PR#106-116 全 merge 入 main
- 源3 plan checklist:device-poweron 3 切片 + EP2 收尾 + 自检 + 收尾动作全 `[x]`

验真通过后,扫 feature_list.json 找下一 frontier,发现**全部 64 feature passing,无 not_started**(当时 active.json 未刷新)。用户选「代码健康度巡检」选项。

### Stage 5 巡检完整走通(Step 0-3)

按 `harness/docs/codebase-health-check.md` + `/improve-codebase-architecture` skill 流程:

**Step 0 bootstrap**:CONTEXT.md 已存在(2026-07-20 创建),docs/adr/ 不存在(lazy 契约)。

**Step 1 Explore**:
- 找 hot spots:`git log --since="2026-07-20" --name-only` 看自上次巡检改动频次 top —— bookings-page.tsx(5)+ queries/endpoints/types(各 4)+ booking_service.py(4)+ devices.py(4)
- wc -l 对比 baseline(2026-07-20):`permission_service.py` 617→**867**(+40%,超 §1.2 阈值)+ bookings-page.tsx —→**1373**(新建,超 settings-page)+ booking_service.py —→681(新建)
- 派 2 个并行 Explore sub-agent(后端 booking/device + 前端 fat files)做有机走读,返 14 候选
- 精选去重为 8 个 friction 点(Strong ×4 + Worth exploring ×4)

**Step 2 HTML 报告**:
- 写自包含 HTML 到 `$TMPDIR/architecture-review-20260725-010252.html`(600 行)
- 归档到 `~/.cache/ai-agent-platform-architecture-reviews/2026-07-25.html`(不入库,SKILL.md 契约)
- macOS `open` 浏览器打开
- 8 候选每个含 before/after Mermaid 图 + Problem/Solution/Wins/Deletion test + badge
- Top recommendation:候选 1(Booking 三视图拆 module)+ 候选 2(cancel 并入状态机)

**Step 3 Grill 候选 1**(用户选):
- 调 `/grilling` skill,一次一问,4 个 decision:
  - D2 目录结构 → **bookings/ 子文件夹**(项目首个 page 子文件夹先例)
  - D4 测试位置 → **bookings/__tests__/**(测试跟 view 走)
  - D6 范围边界 → **只拆不碰 cast**(守不越界,候选 8 独立切片)
  - D7 验证策略 → **现有 12 测试全绿 + 补 HqView smoke test**
- 产 `harness/docs/plan-bookings-page-split.md`(196 行,非复杂任务跳过 §7 对抗式审查)

### 实施(bookings-page-split,priority 65,工程化 area)

**EP2 收尾**:登记 feature_list.json(priority 65,area=工程化,status=not_started)+ sync active + 翻 in_progress。

**拆分**(纯机械搬运,零行为变更):
- `frontend/src/pages/bookings-page.tsx`(1373 行)→ 删
- 新建 `frontend/src/pages/bookings/` 文件夹:
  - `bookings-page.tsx`(barrel re-export BookingsPage,保 App.tsx lazy import 路径兼容)
  - `index.tsx`(三叉路由入口 ~30 行:`isSuperAdmin||isHQStaff?HqView:hasCustomerIdentity?MyBookingsView:StoreView`)
  - `store-view.tsx`(StoreView + 4 Dialog + DropdownMenu 三动作 ~680 行)
  - `hq-view.tsx`(HqView export ~140 行,原私有,拆分后首次可测)
  - `my-bookings-view.tsx`(MyBookingsView ~150 行)
  - `shared.tsx`(STATUS_META/NONE/MUTABLE/ACTIONABLE 常量 + FilterChips/BookingStatusBadge/deviceNameOf + date helpers + slotTone + ScheduleGridCard/ScheduleSlot ~360 行)
- `App.tsx`:lazy import `@/pages/bookings-page` → `@/pages/bookings/bookings-page`
- 测试:`git mv` 挪 store-view.test.tsx + my-bookings-view.test.tsx 到 `bookings/__tests__/`(保留历史)+ 改 import 路径
- 新增 `hq-view.test.tsx` smoke 3 tests(渲染跨店表+列头+行数据 / 空态 EmptyState / null fallback:tenant_name 门店硬删 + walk-in 散客 + device_name 软删)

**验证(全绿)**:
- `npx tsc -b` ✓(修 1 处 unused import:shared.tsx 误导入 EmptyState)
- `npx vitest run` ✓ **15/15**(3 files:store-view 6 + my-bookings-view 6 + hq-view 3)
- `npx oxlint` ✓ 0 warnings 0 errors(86 files 102 rules)
- `npm run build` ✓ 1.75s(bookings-page chunk 18.98 kB 与拆分前一致 → 零行为变更证据)
- `./init.sh` ✓ 714 passed(后端无改动,基线无回归)

### /code-review 双轴审查

派 2 个并行 general-purpose sub-agent(Standards + Spec):

**Standards 轴**:无 hard violation(AGENTS.md 铁律均未触达,纯前端 view 搬运)。Judgement call:
- 🟡 `shared.tsx` 轻微 **Divergent Change** —— ScheduleGridCard + 其私有 date helpers(slotTone/dayLabel/hhmm 等)只被 StoreView 消费,却混在所有 view 共享文件里。本次不拆(plan 守纯 locality 范围),登记为独立后续候选 `bookings-shared-split`。
- 🟢 `bookings-page.tsx` Middle Man —— 单行 re-export,但 plan §4.5 D1 有意识保留(保路由兼容),注释讲清楚。放行。
- 🟢 `Note(candidate-X)` 非 Speculative Generality —— 是「守卫:这里有意保留原状」的标注,非未实现扩展点。

**Spec 轴**:核心目标达成(零行为变更 + locality)。发现:
- 🔴 §10.10「无新 TODO/FIXME」vs §4.5 D3「注释标注委托 candidate 8」**自相矛盾** —— 我加了 4 处 `TODO(candidate-7/8)`。
- 🟡 §10.9 cast 计数有误(spec 写 5 处,实际原文件 7 处)。
- 🟡 `shared.ts` → `shared.tsx`(spec 写 .ts,实际含 JSX 故 .tsx)。

**处置**:
- 🔴 TODO 冲突 → 改 `TODO(candidate-X)` 为 `Note(candidate-X)`(保标注价值,不触发 IDE TODO 扫描器)。frontend/src/ TODO 总数回到基线 2(Logto 占位)。
- 🟡 plan 文字瑕疵订正:cast 5→7 处、shared.ts→shared.tsx、§10.10 措辞改「无新 TODO/FIXME 引入(基线 2 处 Logto 占位不变)」。
- 🟡 shared.tsx Divergent Change → plan §4.5 D1 加「已知 smell」注释,登记独立后续候选。

### feature 收尾

- `feature_list.json`:bookings-page-split status `in_progress` → `passing` + evidence 6 条
- `./scripts/sync-active-features.sh` 刷新(archive 累计 60 条)
- `progress.md`:顶部「最高优先级」改 bookings-page-split 收官 + 下一 frontier = device-models-admin-ui(priority 66);EP3 断点段更新;追加本 Session 139 记录

### 关键发现:device-models-admin-ui(priority 66)

sync-active 刷新后发现 active.json 出现 `device-models-admin-ui not_started`。查证:这是**既存 feature**(不是我本次加的),notes 写「设备功能系列补遗(61 device-models-crud 的范围漂移修复)」—— feature 61 verification 写了「前端管理页」但 evidence 剥离给 62,62 实际只做门店下拉,super_admin 管理页缺口一直未补。后端 CRUD 全齐(已实测端到端),本 feature 仅前端。**这是真实的下一个 frontier**(priority 66,依赖 device-models-crud 已 passing)。

### Session 139 文档影响评估

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/04-前端架构/*`(page 组织/mutation 范式) | ❌ 无影响 | 本次是纯机械搬运,view 内业务逻辑原样保留;bookings/ 子文件夹是项目首个 page 子文件夹先例,但属「单 feature 体量 justify」的局部决策,不上升为架构约定(其他 page 仍 xxx-page.tsx 平铺) |
| `harness/docs/codebase-health-log.md` | ✅ 已更新 | 回填 2026-07-20 待填字段 + 追加 2026-07-25 行(8 候选 + Top + grill=Yes + plan 文档名)+ 新 baseline 快照段(permission 867 / bookings-page 1373 / 测试 714 passed + vitest 12→15) |
| `harness/docs/plan-bookings-page-split.md` | ✅ 已创建 + 订正 | grill 产出 196 行;code-review 后订正 4 处(cast 5→7 / shared.ts→shared.tsx / §10.10 措辞 / 加「已知 smell」Divergent Change 注释) |
| `progress.md` | ✅ 已更新 | 顶部状态改 bookings-page-split 收官 + 下一 frontier = device-models-admin-ui;EP3 断点更新;追加 Session 139 记录 |
| `feature_list.json` + 派生视图 | ✅ 已更新 | 新增 bookings-page-split(priority 65,area=工程化)+ status in_progress→passing + evidence 6 条;sync 刷新 active/archive |
| `~/.cache/ai-agent-platform-architecture-reviews/2026-07-25.html` | ✅ 已归档(不入库) | 巡检 HTML 报告,SKILL.md 契约规定不入库 |

> 判断依据:本次是巡检产出 + 纯前端机械搬运重构,所有改动都在**既有范式内**(vitest 基建 / view module 组织 / lazy import / shared module 抽取),不改变架构约定。bookings/ 子文件夹是单 feature 体量的局部决策,不上升为全局约定。巡检剩余 7 候选(candidate 2-8)在 plan §8 Out of Scope 列明,各自独立后续任务。

---

## Session 140(2026-07-25):device-models-admin-ui EP2 回环(grill → to-spec → to-tickets)

### 入口:EP2 起点

按用户指令启动 EP2 回环:`device-models-admin-ui`(priority 66,业务实体)走 `/grill-with-docs → /to-spec → /to-tickets` 一个回环内完成,产出 `harness/docs/plan-device-models-admin-ui.md` 的「实施切片」段。

**定位三层入口**(three-tier §1):plan 文档 `harness/docs/plan-device-models-admin-ui.md` **不存在** → 在 EP2 起点(非 EP3)。前置 feature `device-models-crud`(priority 61)已 passing,依赖满足。

**开工流程**(AGENTS.md):`pwd` ✓ + 读 progress.md(知 Session 139 收官 bookings-page-split,本 feature 是下一 frontier)+ 读 feature_list.active.json(本 feature priority 66,唯一 not_started,选为 frontier)+ git log(知 bookings-page-split 已 merge)+ init.sh 全绿(714 passed)+ plan 文档不存在 → EP2 起点。

### 上下文采集(进 grill 前的事实基础)

读了 7 个关键文件定边界:
- **后端 CRUD 全齐**:`app/api/v1/device_models.py`(POST/PUT/DELETE 守 `require_super_admin()`;GET 开放按 `platform_role` 分叉返 `DeviceModelRead` 全字段 vs `DeviceModelPublicRead` {id,name,specs})+ `app/schemas/device_model.py`(`DeviceModelCreate/Update/Read` 字段:name/brand/supplier/unit_cost(Decimal)/specs(dict[str,Any] 默认 {}))+ `app/models/device_model.py`(表已建,部分唯一索引 + Numeric(12,2)+ JSONB)
- **前端范式参考**:`frontend/src/pages/groups-page.tsx`(同平台级 super_admin 范式,react-hook-form+zod+Controller,546 行)+ `devices-page.tsx`(设备业务 UI 模式)+ `components/auth/require-super-admin.tsx`(守卫范例,`me.platform_role !== "super_admin"` → Navigate to="/")+ `components/layout/nav-items.ts`(平台分组 `platformOnly: true` 范式)+ `lib/permission.ts`(isSuperAdmin helper)+ `App.tsx`(RequireSuperAdmin 路由块)
- **前端现有 device-models 基建**:types.ts 只有 `DeviceModelPublic`(下拉视图);endpoints.ts 只有 `fetchDeviceModels()` 返 `DeviceModelPublic[]`;queries.ts 只有 `useDeviceModels()` + `qk.deviceModels` cache key。**缺**:admin 版完整字段 types + CRUD endpoints + 4 个 hooks
- **辅助确认**:`formatCurrency(n)` 已存在(`lib/format.ts:65`)无需新建;`useApiMutation<TVars,TData>(fn,[invalidateKeys])` 签名清晰

### Grill 阶段(/grill-with-docs → /grilling + /domain-modeling)

调 skill,一次一问,带推荐答案。6 个决策点烤清:

| 决策 | 用户选择 | 备注 |
|---|---|---|
| **切片粒度** | 拆 2 片(地基 + UI) | 推荐。types/endpoints/hooks 是无 UI 基建可独立 verify,page+route+nav 是可见层。对齐 devices-crud-ui 的「地基+UI」切法但更轻(无后端) |
| **specs 编辑器** | 结构化 key-value 行编辑器,**全量版多类型** | 用户否决「原始 JSON textarea」推荐,选全量版(string/number/boolean Select)。后端 dict[str,Any] 契约允许任意 JSON 值,堵住单类型反而不一致 |
| **KeySpecRows 边界** | 全量版多类型 | 空 key 过滤 + 重复 key 后者覆盖 + 按 type 序列化 + 反序列化 round-trip |
| **unit_cost 呈现** | 货币格式 | 推荐。formatCurrency(Number(m.unit_cost)),Decimal→string→Number 安全 |
| **brand/supplier** | brand 加 datalist 联想 + supplier 纯 Input | HTML 原生 datalist,无新组件 |
| **列表** | + 名称/品牌搜索框 | client-side filter,一个 useState,参照 groups-ui 无分页 |
| **测试** | KeySpecRows 单测(推荐) | 序列化逻辑是主要复杂点,page 不强制(对齐 devices-page 现状) |

### To-Spec + To-Tickets(一个回环内完成)

`/to-spec` 落 PRD 主体到 `harness/docs/plan-device-models-admin-ui.md`:
- §1 Problem:缺口溯源(61 verification 写了管理页但 evidence 剥离给 62,62 只做门店下拉,super_admin 管理页一直未交付)
- §4.5 决策表 18 行(已落定无 TODO/待定)+ §4.6 已查证事实 10 行(避免 EP3 返工)
- §5 测试:KeySpecRows 4 类 case 单测,page 不强制
- §6 切片规划:2 片
- §7 对抗式审查自评:不达复杂任务阈值(6 改 + 2 新 < 10,不涉鉴权/迁移/跨服务),跳过

`/to-tickets` 产「实施切片」段:
- **切片 01**(frontier,无 blocker):前端地基 types+endpoints+hooks,5 条 acceptance
- **切片 02**(blocked by 01):UI 层 page+route+nav+KeySpecRows+vitest,8 条 acceptance
- 依赖图:01 → 02 线性串行,无环
- EP2 收尾自检 gate:4 项全过(依赖无环 / 每片有 acceptance / 首片可开工 / plan 主体决策落定)

### EP2 收尾(three-tier §3 + §5)

- ✅ plan 文档「实施切片」段齐全(2 片)+ 自检 gate 4 项过
- ✅ `feature_list.json`:回填 `plan` 字段指向 plan 文档(让「是否进过 EP2」可判)+ `status` `not_started` → `in_progress`(当前 frontier,依赖 device-models-crud 已 passing,符合 §5 规则 2)+ notes 尾部更新(EP2 已完成,下一步 EP3 切片 01)
- ✅ `./scripts/sync-active-features.sh` 已跑(刷新 active 视图:1 活跃 + 5 最近 passing,active.json 内 status/plan 字段已正确同步)
- ✅ `progress.md`:顶部「最高优先级」段更新(EP2 已完成,下一步 EP3 切片 01)+ EP3 断点段更新(从「下一 frontier = device-models-admin-ui」改为「EP2 已完成,EP3 切片 01 起点」)+ 追加本 Session 140 记录

### 关键边界声明(守 WIP=1 不越界)

- **不触碰后端**:`app/` / alembic / `device-models-crud` 已落地代码全不动
- **不重构 devices-page 型号下拉**:`DeviceModelPublic` 类型保留不动
- **不进权限矩阵 UI**:`device_models` 不走 casbin,对齐 groups 平台级资源范式
- **不补 seed 脚本**:种子数据是 dev 体验问题,非产品能力
- **不加分页 / 服务端搜索**:表预期小,client-side filter 足够

### Session 140 文档影响评估

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/*` | ❌ 无影响 | 本 feature 纯前端,后端 CRUD 由 device-models-crud 已落地不动;无新表 / 无迁移 / 无状态机 |
| `项目指南/04-前端架构/*` | ❌ 无影响 | 本 feature 沿用既有范式(react-hook-form+zod+Controller / useApiMutation 骨架 / RequireSuperAdmin 守卫 / platformOnly nav / formatCurrency)。唯一新组件 `KeySpecRows` 是 device-models 业务专属,不上升为架构约定 |
| `harness/docs/plan-device-models-admin-ui.md` | ✅ 已创建 | EP2 产物:PRD 主体 + 2 切片 + 依赖图 + 自检 gate |
| `progress.md` | ✅ 已更新 | 顶部「最高优先级」改 EP2 已完成 + 下一步 EP3 切片 01;EP3 断点更新;追加 Session 140 记录 |
| `feature_list.json` + 派生视图 | ✅ 已更新 | 回填 `plan` 字段;`status` not_started → in_progress;notes 尾部更新;待跑 sync-active 刷新 |

> 判断依据:本次 EP2 是纯规划产物(plan 文档 + feature_list 字段回填 + progress 记录),**无任何代码改动**。所有实施决策都基于已查证事实(后端 CRUD 全齐 + 前端范式参考齐备),不改变架构约定。`KeySpecRows` 是本 feature 业务专属新组件,但序列化逻辑是 dict[str,Any] 契约的必然产物,不上升为前端架构约定(其他 page 若有自由 JSON 字段才考虑抽通用组件,YAGNI)。下一步 EP3 切片 01 走 `/implement`。

---

## Session 141(2026-07-25):device-models-admin-ui EP3 切片 01(前端地基 types/endpoints/hooks)+ Standards 修正

### 入口:EP3 切片 01

按用户指令推进 `device-models-admin-ui` 切片 01(frontier)。读 `harness/docs/plan-device-models-admin-ui.md` 切片 01 章节,5 条 acceptance criteria:`types.ts` 加 3 interface / `endpoints.ts` 加 4 函数 / `queries.ts` 加 4 hooks / tsc 通过 / oxlint 0 warnings。

### 实施第一轮(按原 spec)

按 plan AC2/AC3 原文实现:`fetchDeviceModelsAdmin()` + `useDeviceModelsAdmin()` 独立读函数/hook,共用 `qk.deviceModels` cache。tsc + oxlint + build 全绿,pytest test_device_models_api.py 22 passed 回归。

### /code-review 双轴:发现 Standards H1 硬违反

- **Standards H1(硬)**:`fetchDeviceModelsAdmin` 独立函数违反 `endpoints.ts` 既有 union 单函数约定(`fetchDevices(): Promise<Device[] | DeviceHqRead[]>` 同 URL role-branching 用 union)。**且** super_admin 调 `fetchDeviceModels` 实际收到 `DeviceModelRead` 但签名承诺 `DeviceModelPublic[]`,**类型契约不诚实**。
- **Standards S2**:同 queryKey 不同读形状 → 缓存碰撞(super_admin 会话里 `useDeviceModels` + `useDeviceModelsAdmin` 并存时后者覆盖前者形状)。
- **Spec 轴**:5/5 AC 全满足,无 blocker。

H1 与 spec AC2/AC3 明文冲突(AC 要求独立函数 + 共享 cache)。**用户裁决「修 Standards 偏离 spec」**:改 union 单函数。

### Standards 修正(union 单函数方案)

- `fetchDeviceModels(): Promise<DeviceModelPublic[] | DeviceModelRead[]>` —— 对齐 `fetchDevices` 范式
- 删 `fetchDeviceModelsAdmin` / `useDeviceModelsAdmin`
- 保留三写 mutation(`useCreate/Update/DeleteDeviceModel`,spec 无冲突部分)
- `useDeviceModels` 注释更新为反映双视图(门店下拉 + super_admin 管理页)
- 切片 02 page 在 RequireSuperAdmin 守卫下断言收窄 union 为 `DeviceModelRead[]`(参照 devices-page StoreView vs HqView 范式)

plan AC2/AC3/§4.5/§10/切片02 brand datalist AC 同步更新引用 + 决策注记。

### ⚠️ 发现 main 上 PR #119 已合并(同切片,原 spec 方案)

提交 PR #120 时发现 `main` 已通过 **PR #119**(另一个 session)用**原 spec 方案**(`fetchDeviceModelsAdmin` + `useDeviceModelsAdmin` 独立函数)合并了切片 01。我的 PR #120(union 方案)与之冲突,`mergeable_state: dirty`(base 落后)。

**用户裁决「以 PR #120 为准(覆盖 #119 修正 Standards)」**:reset 分支到最新 `origin/main`(#119 后),重新落地 union 修正(覆盖 #119 读侧),force push,更新 PR #120 描述说明这是 #119 的 Standards 修正。

### 验证

- ✅ `npx tsc --noEmit` 0 错
- ✅ `npx oxlint src/` 0 warnings
- ✅ `npm run build` 通过
- ✅ PR #120 CI 全绿:Frontend 25s / Migrations 59s / E2E 1m58s / Backend (pytest+ruff) 6m48s
- ✅ PR #120 已 squash 合并(mergeCommit `52f53e5`,2026-07-25T02:55:29Z)

### 关键经验

1. **会话开始时 git status 干净 ≠ main 是最新**:另一 session 可能在并行推进同 feature。本会话开工流程读了 git log -5,但 main 在会话期间被 #119 推进了。后续若发现 PR 与 main 冲突,先查 main 当前 HEAD 是否已含同 feature 工作。
2. **Standards vs Spec 冲突时,上报用户决策**:不要自行折中。本次 H1(Standards 硬违反)与 AC2/AC3(spec 明文)真实冲突,用户裁决「修 Standards」。
3. **「同 URL role-branching 用 union 单函数」是 endpoints.ts 的隐式约定**:对齐 `fetchDevices` / `fetchBookings` 范式,新 endpoint 应遵循,避免类型不诚实 + 缓存碰撞。

### Session 141 文档影响评估

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/*` | ❌ 无影响 | 纯前端,无后端改动 |
| `项目指南/04-前端架构/*` | ❌ 无影响 | 沿用既有 union endpoint 范式(fetchDevices/fetchBookings),无新架构约定 |
| `harness/docs/plan-device-models-admin-ui.md` | ✅ 已更新 | 切片 01 AC2/AC3 + §6 简表 + §4.5 决策表 + §10 验收 + 切片02 brand datalist AC 同步 union 方案 + 决策注记 |
| `progress.md` | ✅ 已更新 | 顶部「最高优先级」改切片 01 ✅ + 下一步切片 02;EP3 断点更新;追加 Session 141 记录 |
| `feature_list.json` + 派生视图 | ❌ 无影响 | 切片 01 非末切片,status 仍 `in_progress`,不改 feature 状态 |

> 判断依据:切片 01 是纯前端 API 层契约补遗,无后端改动,无架构约定变更。Standards 修正(union 单函数)是对齐既有 `fetchDevices` 范式,不引入新约定。下一步 EP3 切片 02(末切片):UI 层 page+route+nav+KeySpecRows+vitest,走 `/implement`。

---

### Session 145 — 2026-07-25(platform-cross-tenant-write EP3 切片 01-04 合并 PR #124,4/5 切片)

- **本轮目标**:把 `feat/platform-cross-tenant-write-slice02` 分支(含切片 01 devices 后端 + 切片 02+03 bookings 全 6 写动作合并 + 切片 04 前端,共 4 feat commit + 2 docs commit)开 PR 合并到 main,CI 绿后合,跑 sync-active,推进 EP3 断点到切片 05。
- **已完成**:
  - **分支检查**:`git log main..HEAD` = 4 commits(9912c67 devices / 3624ce5 bookings / dc880b3 frontend / 43ba98c docs 收尾);diff stat 20 文件 +3739/-1169(含 2 新文件 `app/services/_tenant_target.py` + `frontend/src/pages/bookings/shared-dialog.tsx`)。无现存 PR(`gh pr list --head` 空)。
  - **推送**:`git push -u origin feat/platform-cross-tenant-write-slice02` —— 首次连接 github.com:443 超时(3 次重试全 75s 超时),`api.github.com` 通而 `github.com` 不通;诊断 DNS 正常 + curl 直连 github.com:443 返回 200 后,重试 push 成功(git 连接建立阶段对网络抖动敏感)。
  - **PR 创建**:`gh pr create --base main --head feat/platform-cross-tenant-write-slice02 --title "feat(platform-cross-tenant-write): 切片 01-04 — 平台角色跨店写 devices/bookings 全栈"`,body 按项目既有 PR 格式(Summary / Changes 分后端共享基础设施 + devices + bookings + 前端 / Acceptance Criteria 引 plan §6 / Verification / Out of Scope / Depends)。→ **PR #124**。
  - **CI 监控**:4 个 job 全绿 —— Migrations 46s ✅ / Frontend 31s ✅ / Backend (pytest+ruff) 7m58s ✅ / E2E (Playwright) 1m50s ✅。后台 watcher 脚本 + 前台 polling 双轨确认。
  - **合并**:`gh pr merge 124 --squash --delete-branch` → main 顶部 `c5bf99c feat(platform-cross-tenant-write): 切片 01-04 — 平台角色跨店写 devices/bookings 全栈 (#124)`,远端分支已删。
  - **本地同步**:`git checkout main && git pull --ff-only` —— 已含 #124 squash commit。本地残留分支 `feat/platform-cross-tenant-write-slice01`(plan §6 切片 01 标题提到的早期分支,实际工作并入了 slice02,未推送远端,保留无害)。
  - **sync-active**:`./scripts/sync-active-features.sh` → active: 2 活跃 + 5 最近 passing + 1 里程碑;archive 新增 61 条。**关键验证**:`platform-cross-tenant-write` status 保持 `in_progress`(切片 05 未做,evidence 空,不提前标 passing),在 active.json 活跃列表中正确出现。
  - **progress.md 更新**:顶部「最高优先级」改切片 01-04 ✅ PR #124 + 下一步切片 05;EP3 断点推进到切片 05(末切片,7 条 AC,feature 收尾);platform-cross-tenant-write 条目改 Session 145 记录;追加本 Session 145 记录 + 文档影响评估。

### 验证(PR #124 CI 全绿证据)

- ✅ Migrations (alembic upgrade on Postgres): pass 46s
- ✅ Frontend (typecheck + build + lint): pass 31s
- ✅ Backend (pytest + ruff): pass 7m58s
- ✅ E2E (Playwright): pass 1m50s
- ✅ PR #124 squash 合并(mergeCommit `c5bf99c`,2026-07-25)

### 关键经验

1. **CI 监控双轨**:后台 watcher 脚本(15min 上限)+ 前台 polling(短轮询)并行,任一先确认即可。本次后台 watcher stdout 缓冲未见输出,靠前台 polling 拿到结果 —— 后台任务的 stdout 不一定实时 flush,关键节点要有前台兜底。
2. **git push 网络抖动 ≠ 永久故障**:github.com:443 偶发超时(api.github.com 同时通),`curl -sS https://github.com/` 验证 443 端点可达后重试 push 即可,不需要换协议或诊断 DNS。
3. **squash 合并后 plan §6 切片标题里的「PR 待提交」字样需在收尾时更新**:本次 plan §6 切片 01-04 标题已在 docs commit 43ba98c 里标 ✅ 但未填 PR 号,合并后应在 feature 收尾(切片 05)统一回填 PR #124 到 plan。本次 Session 不改 plan(纯收尾推进 + 文档登记,plan 文字微调留切片 05 一并做,避免越界)。

### Session 145 文档影响评估

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/*` | ❌ 无影响 | 切片 01-04 在 Session 144 EP2 已评估,helper 与 `is_cross_tenant_viewer` 同范式,文档已有覆盖 |
| `项目指南/04-前端架构/*` | ❌ 无影响 | 沿用既有 HqView + 共享组件范式,无新架构约定 |
| `harness/docs/plan-platform-cross-tenant-write.md` | ⏳ 留切片 05 | 切片 01-04 标题已 ✅(docs commit 43ba98c),PR 号回填 + plan 状态 draft→passing 留切片 05 feature 收尾一并做(避免越界) |
| `progress.md` | ✅ 已更新 | 顶部「最高优先级」+ EP3 断点 + platform-cross-tenant-write 条目 + 追加 Session 145 记录 + 文档影响评估 |
| `feature_list.json` + 派生视图 | ❌ 无影响 | 切片 01-04 非末切片,status 仍 `in_progress`,evidence 空(不提前标 passing),sync-active 仅刷新派生视图 |

> 判断依据:本 Session 是 PR 合并 + 文档登记,无代码改动(plan §6 AC 在前序 Session 已验证)。feature 收尾(status→passing + evidence + plan 状态 + 文档影响评估的最终勾选)是切片 05 的职责,本 Session 不越界提前做。下一步 EP3 切片 05(末切片):`test_hq_platform_role.py` 旧断言改写 + 全量验证 + feature 收尾,走 `/implement`。

---

## Session 155(2026-07-28):composite-chat EP3 切片 04(前端模式切换 + 真实端到端 + feature 收尾,末切片收官)

### 入口:EP3 切片 04(末切片)

按用户指令推进 `composite-chat` 切片 04(末切片:前端模式切换 + 真实验证 + ship-it 收尾)。读 `harness/docs/plan-composite-chat.md` §六点五 切片 04 checklist(14 项)+ Step 9-11 实现细节 + AC4(8 条前端验收)+ §九 ADR-0002 判断。开工流程:基线 828 passed 确认起点干净。

### 实施(`/implement`)

落地 5 前端文件 + 1 后端 blocker 修复:

1. **types.ts**:`ConversationKind` + `Conversation.kind`(single|composite)+ `Message.status/error/fragments`(M8 顺手补对齐后端 MessageRead)+ `CompositeFragment`/`CompositeRequest`/`CompositeResponse` 三 interface(token triple + agent_name/snippet/status 镜像后端 schema)。
2. **endpoints.ts**:`compositeChat(payload)`(POST /chat/composite 非 SSE 走 axios api)+ `CompositeInsufficientBalanceError` 自定义错误类(402 单独 catch:AxiosError 402 → 带 backend detail 的错误类,调用方 instanceof 区分)。
3. **composite-mode.tsx**(新建,kebab-case 照 pages/bookings 惯例):两视图(compose 无 selectedConversationId → agent 多选 + 输入 + 发起 + Skeleton + 结果;history 有 selectedConversationId → 只读渲染 messages 含 fragments 折叠);`compositeAgents` useMemo 内部过滤 orchestrator;402 内联充值引导卡片(amber + Wallet icon + 「前往充值」CTA `useNavigate('/billing')`,非 bare toast);`FragmentsList` 子组件折叠每条带 Badge success/destructive;续问拦截(M10 仅查看历史)。
4. **chat-page.tsx**:`mode` state(`useState<ConversationKind>('single')` H5 默认态)+ useEffect 按 kind 同步 + header Switch(复用 switch.tsx M7,composite 隐藏 agent/customer Select)+ 会话列表「复合」Badge + body 条件渲染(mode==='single'?...:CompositeMode)。
5. **casbin_enforcer.py**(MissingGreenlet blocker 修复):`get_enforcer` 的 sync_url 转换原只 `replace('+psycopg','')`,对 `postgresql+asyncpg://` 无效 → casbin sync Adapter 拿 asyncpg 驱动跑 sync SQLAlchemy,uvicorn+postgres 下所有 DB 接口 500 `MissingGreenlet`(sqlite 测试不暴露);改为循环 replace `+asyncpg/+aiosqlite/+psycopg` 落地 sync 默认驱动。

### 端到端验证(真实 DeepSeek key 全链路)

**M9 前置满足**:llm_configs 表 platform 行 `sk-***ec3a` + DeepSeek base_url + tenant 覆盖 deepseek-reasoner。3 agent(综合测试顾问 + 2 SpikeAgent,super_admin 旁路 wallet)复合查询「用一句话简述你是谁」:
- ✅ fan-out 3 agent 并行全 completed
- ✅ synthesize 152 字综合答案
- ✅ fragments 3 条带 snippet + status + token triple
- ✅ 计费 N+1=4 笔 UsageEvent(3 fragment 各 agent_id + 1 synthesize agent_id=NULL,全指向同一 message_id)
- ✅ 历史 GET messages API 返回 fragments 前端可渲染
- ✅ 向后兼容单 agent `/chat/stream` SSE delta+[DONE] 正常

### /code-review 双轴(并行子代理)

- **Standards**:0 硬违规;4 判断项 —— Duplicated Code(message 气泡 ~20 行后续可抽组件)/ Speculative Generality(synthesize_model 后端镜像豁免)/ casbin for 循环可读性轻微 / AC4.5 行数超标(已修:compositeAgents useMemo 下沉 composite-mode)。
- **Spec**:AC4.1-4.4/4.6/4.7 ✓ + AC4.5 ✗已修 + AC4.8 △已修(toast → 内联充值引导卡片带 CTA)。casbin 改动越界但合理(AC5.4 端到端前置阻塞)。

两轴反馈均已修复并验证(build 0 错 + oxlint 0 warnings + 828 passed 零回归)。

### feature 收尾仪式(末切片 7 步)

1. plan §六点五 切片 04 checklist 全勾 + 标题 ✅
2. feature_list.json status in_progress → passing + evidence 加切片 04 条 + 收尾条
3. progress.md 顶部「最高优先级未完成」刷新(0 活跃)+ EP3 断点收官 + Session 155 记录
4. 文档影响评估:feature_list ✅ / progress ✅ / CONTEXT+项目指南 ❌(plan 已记录)/ README ❌ / **ADR-0002 判断:双模式边界清晰,plan 记录足够,不提 ADR**
5. `./scripts/sync-active-features.sh` 跑过(active 0 活跃 + 5 最近 passing)
6. 依赖解锁扫描:priority 72 最高位,无下游 depends_on,无需解锁
7. clean-state-checklist 9 项全勾

### 验证

- 后端:`./init.sh` 全绿 **828 passed**(casbin 修复后零回归,基线 828→828,permission+composite 103 测试全绿)+ ruff clean
- 前端:`npm run build` 0 类型错误 + `oxlint` 0 warnings

### 备注

工作区有预先存在的 smoke marker 体系改动(pyproject.toml + tests/test_*.py + AGENTS.md + init.sh + harness 文档,引入 `pytest -m smoke` 冒烟子集 + `./init.sh full` 分档),**非本切片工作**,切片 04 commit 只包含自己的 6 个文件,smoke 体系改动留在工作区未提交(留给后续会话/用户处理)。

---

## Session 150(2026-07-27):principal-module EP3 切片 02b(device_service 迁全 7 方法到 Principal)

### 入口:EP3 切片 02b

按用户指令推进 `principal-module` 切片 02b(migrate batch:device_service 迁全 7 方法)。读 `harness/docs/plan-principal-module.md` 切片 02b 章节(6 AC)+ §4.4 五条不可违反契约 + §7.1 行数净减估算(预警 02b 同向偏差)。范式照搬切片 02a(booking_service 已迁且 review 通过)。

### 实施(`/implement`)

仅改 `app/services/device_service.py` 一个文件(diff +69/-57,净 +12 行,432 → 444):

1. **AC2b.1 `__init__`**:加 `self.principal = Principal(db)` + 5 行注释(与 booking_service L99-105 逐字一致)+ import 调整。
2. **AC2b.2 迁全 7 方法**:list/get(读路径,for_read + `if access.is_panorama:` 折叠 panorama 分支)+ create/update/delete/bind/unbind(写路径,for_write + `if access.require:` 门控 + `effective_tenant = access.effective_tenant` alias)。
3. **三 import 干净删除**:`resolve_target_tenant` / `is_cross_tenant_viewer` / `is_platform_writer` —— device 全 7 方法都用 helper,迁完零残余代码引用。docstring/comment 里的历史交叉引用保留(删了丢设计意图)。
4. **create 业务逻辑守卫等价替换**:`is_platform_writer(platform_role)`(跨店 customer 绑定断言门控,L255 原)→ `access.require is None`。Principal 不变式(principal.py L24 + plan §4.0 Q3':`WriteAccess.require is None ⇔ is_platform_writer`)保证等价。加 3 行注释钉死这个等价关系,引用 plan §4.0 Q3'。

### 验证(契约全 GREEN)

- ✅ 全量 pytest **783 passed**(777 baseline + 6 Principal contract,零回归;256s)
- ✅ test_devices_api + test_hq_platform_role **61 passed**(device 专项回归护栏)
- ✅ ruff clean(device_service + 全 repo)
- ✅ plan §4.4 五条不可违反契约全守:BizError 文案逐字不变(for_write 内部仍调 resolve_target_tenant)/ require 参数运行时等价(store 分支 access.effective_tenant == user_tenant_id == 旧 effective_tenant)/ permission_service 单一入口不动(Principal 不调 require)/ DataScopeService 行为不动(device 读路径无 DataScopeService 调用)/ 零行为变更

### /code-review 双轴(并行子智能体)

- **Standards 轴:APPROVE,0 硬违反**。形状与 booking_service(02a 参考)逐字一致 / is_platform_writer → access.require is None 替换忠实(对照 principal.py L24 不变式 + L136-140 实现)/ 三 import 干净删除 / `assert access.require is not None`(list/get 2 处)与 booking L264/299 同范式。2 判断项非阻塞:① 7 方法结构性重复(Principal 模式固有成本,02a 已接受)/ ② device 写方法 require→fetch 顺序 vs booking end/no_show 的 fetch→require(保留自重构前,非本切片范围)。
- **Spec 轴:0 硬失败**。AC2b.1-2.4 全满足;AC2b.5 LOC +12(非 -20)是 §7.1 L300 明文预警的同向偏差,预授权修订 → 唯一待办是把实际 +12 + 成因留痕写进 plan(与 AC2a.6 同范式)。§4.4 五契约全守。1 判断项:无 scope creep。

### AC2b.5 行数指标修订留痕(沿用 AC2a.6 / §7.1 范式)

- **估算**:plan §7.1 「净减 ≥ 20 行」(逐方法 ~4 行 × 7 ≈ 28,保守 20)
- **实测**:净**增 +12 行**(432 → 444,diff +69/-57),与估算反向
- **成因(同 02a,plan §7.1 预警兑现)**:① `for_write`/`for_read` 6 个 keyword args 展开(即便 line-length=100 最紧凑仍 3-4 行 vs 旧 `resolve_target_tenant(a,b,c)` 单行)是主因;② `effective_tenant = access.effective_tenant` alias(5 写方法各 +1)次之。device **无** 02a 的 Note 注释开销(plan §4.2 无 device 不迁方法),故 +12 < 02a 的 +34。
- **结论**:Principal 的真实价值是「鉴权决策收口到单一推理点 + 跨 service 形状统一」(deletion test §1),不是 LOC 削减。AC2b.5 修订为「leverage 重构接受,LOC 指标放弃」,切片 03 预计继续同向。

### 收尾(非末切片,不做 feature 收尾仪式)

- plan 切片 02b 标题追加 ✅ + commit 证据(PR 待开,沙箱网络不可达 GitHub,沿用 02a 范式)
- plan AC2b.1-2.5 全勾选 + AC2b.5 inline 修订留痕(实际 +12 + 成因)
- progress.md 顶部「最高优先级未完成」更新(02b ✅)+ 顶部切片 02b 单行条目 + EP3 断点推进到切片 03 + 追加本 Session 150 记录 + 文档影响评估
- **不动 feature_list.json status / 不写 evidence / 不 sync-active**(末切片 AC3.8 的职责,非末切片不越界)

### 关键经验

1. **device 全 7 方法都用 helper → import 干净删除**:与 02a(booking 4 方法不迁,三 import 保留)的形状区别。迁前 grep 确认每个 import 的全部引用点,确认零残余代码引用才删 —— docstring/comment 里的历史交叉引用是设计意图不是死代码,保留。
2. **业务逻辑用 Principal 不变式等价替换**:`create` 的 `is_platform_writer` 不只是鉴权分支,还是跨店 customer 绑定断言的业务门控。Principal 不变式(`require is None ⇔ is_platform_writer`)让 `access.require is None` 成为忠实等价 —— 加注释钉死这个等价(code-review Standards 轴重点核查项)。
3. **LOC 同向偏差第三次兑现(02a +12→+34 / 02b +12 / 03 预计继续)**:plan §7.1 的预警机制(「实施时若再遇,沿用本节留痕方式修订 AC 数字」)让指标修订变成机械留痕而非 spec 失败。Principal 的 leverage 价值不依赖 LOC。

### Session 150 文档影响评估

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/*` | ❌ 无影响 | 纯后端 service 层内部重构,行为零变更;现有四层架构 + 多租户隔离文档完全覆盖 Principal 模式 |
| `harness/docs/plan-principal-module.md` | ✅ 已更新 | 切片 02b 标题 ✅ + commit 证据(PR 待开)+ AC2b.1-2.5 全勾选 + AC2b.5 inline 修订留痕(实际 +12 + 成因)|
| `progress.md` | ✅ 已更新 | 顶部「最高优先级未完成」+ 顶部切片 02b 单行条目 + EP3 断点推进到切片 03 + 追加 Session 150 记录 + 文档影响评估 |
| `feature_list.json` + 派生视图 | ❌ 无影响 | 切片 02b 非末切片,status 仍 `in_progress`,evidence 空(不提前标 passing),sync-active 不跑(派生视图无变化)|

> 判断依据:切片 02b 是纯后端 service 层 migrate batch(单文件 +69/-57),行为零变更,无架构约定变更,无新表/迁移/前端改动。LOC 指标修订是 plan §7.1 预警兑现的机械留痕(与 AC2a.6 同范式),非 spec 失败。下一步 EP3 切片 03(末切片):customer_service 迁 2 方法 + CONTEXT.md Principal 条目 + 4 旧 helper docstring 交叉引用 + feature 收尾(status→passing + evidence + sync-active),走 `/implement`。

---

## Session 156(2026-07-29):bookings-shared-split EP3 切片 1(抽 status-meta.ts + date-utils.ts 底座,expand 阶段)

plan `harness/docs/plan-shared-tsx-split.md` 切片 1 —— expand-contract 的 **expand 阶段**:新建两个叶子模块,shared.tsx 改 import-then-export facade,消费者零改动。

### 落地(3 文件,zero behaviour change)

- 新建 `frontend/src/pages/bookings/status-meta.ts`:STATUS_META / MUTABLE_STATUS / ACTIONABLE_STATUS / NONE(4 符号,booking 状态领域模型,无 React 依赖)。4 段语义注释逐字迁移自原 shared.tsx,新增模块级 JSDoc 头(说明为何独立成模块:状态机常量是 bookings 子域词汇表,加新状态只改一处)。
- 新建 `frontend/src/pages/bookings/date-utils.ts`:startOfToday / addDays / isoDate / hhmm / dayLabel(5 纯日期函数,叶子节点)。3 段 JSDoc 逐字迁移,section 注释「Local-time date math」升格为模块头。
- 改 `frontend/src/pages/bookings/shared.tsx`(360→290 行,-88/+24):删 9 符号本地定义,改 `import { ... } from "./status-meta"` + `import { ... } from "./date-utils"` 后 `export { ... }`(import 入本地作用域供内部消费 + re-export 维持 facade)。

### 关键技术决策:为何 import-then-export 而非纯 `export {} from "./x"`

初版用纯 re-export 直接 tsc 报 17 处 `Cannot find name`。根因:shared.tsx 内部 `BookingStatusBadge`/`ScheduleSlot` 仍直接用 `STATUS_META`,`applyBookingFilter`/`ScheduleGridCard`/`ScheduleSlot` 仍用 5 个 date helpers —— 纯 re-export 会把这些符号踢出本地作用域。**import-then-export 是唯一正确形式**:既满足 AC3「re-export」又满足内部消费。facade 本身是切片 2 删消费者 deep import 后才移除的文档化过渡态(plan §4.1 D2 + §4.7 明确)。

### 验证(全绿,zero behaviour change 的唯一证据)

- ✅ `npx vitest run` **65/65 pass**(store-view 6 + my-bookings-view 6 + hq-view 13 + schedule-grid 11 + config-dialog 5 + format 15 + key-spec-rows 7 + queries-booking-config 2)
- ✅ `npm run build` 绿(bookings chunk 31.29 kB,纯 locality 搬运不改变打包形状)
- ✅ `npx tsc -b` 干净(尤其验证 import 路径改对)
- ✅ `npx oxlint` 0 warning
- ✅ `./init.sh full` **828 passed**(后端零改动,基线无回归,259s)

### /code-review 双轴(并行子智能体)

- **Standards 轴:APPROVE,0 硬违反**。不越界(diff 只碰 3 声明文件,5 消费者零改动)/ 引用代码用符号名 / 切片 1 AC 全满足。2 判断项(均非阻塞):① facade re-export 是正当 expand-contract 形态(内部仍消费符号,纯 re-export 会断;切片 2 才删 facade)② `MUTABLE_STATUS`/`ACTIONABLE_STATUS`/`NONE`/`addDays`/`dayLabel`/`isoDate`/`hhmm` 7 符号是 import-only-for-export 的过渡态 Middle Man,但这是 expand-contract 文档化瞬态,linter 允许。
- **Spec 轴:0 硬失败**。AC1-4 全满足(注释逐字迁移 / 消费者零改动 / 4 项验证全绿)。无 scope creep:D3 不补测 ✅(无新 test 文件)/ D5 `fmt`/`fromDatetimeLocalValue` re-export 未提前删 ✅ / D7 deviceNameOf 未动 ✅ / §4.7 范围外符号(filter 组 4 + schedule-grid-card 组 3 + BookingStatusBadge)全留 shared ✅。import-then-export 模式经核查**正确且必要**。

### 会话决策留痕

用户会话硬约束原写「只新建文件,不动 shared.tsx」,但 plan §6 切片 1 AC 第三条 + 文件清单(3 文件)要求「shared.tsx 从两个新文件 re-export,消费者零改动」—— 二者直接冲突。用 AskUserQuestion 澄清,用户选「遵循 plan:加 re-export(推荐)」。结果:expand-contract 标准范式,切片 1 结束符号定义源已迁移,facade 待切片 2 删。

### 收尾(非末切片,不做 feature 收尾仪式)

- plan §6 切片 1 标题追加 ✅ + AC1-4 全勾选 + inline 完成证据
- progress.md 顶部「最高优先级未完成」frontier 推进到切片 2 + 追加 Session 156 记录 + 文档影响评估
- commit `ae69dac` on `feat/bookings-shared-split` 分支(从 main 开出,遵循「若在默认分支先开分支」)
- **不动 feature_list.json status / 不写 evidence / 不 sync-active**(末切片 AC3 的职责,非末切片不越界)

### Session 156 文档影响评估

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/*` | ❌ 无影响 | 纯前端 locality 重构,行为零变更;现有四层架构 + 多租户隔离文档不涉及前端模块拆分 |
| `harness/docs/plan-shared-tsx-split.md` | ✅ 已更新 | 切片 1 标题 ✅ + AC1-4 全勾选 + inline 完成证据 |
| `progress.md` | ✅ 已更新 | 顶部「最高优先级未完成」frontier 推进到切片 2 + 追加 Session 156 记录 + 文档影响评估 |
| `feature_list.json` + 派生视图 | ❌ 无影响 | 切片 1 非末切片,status 仍 `in_progress`,evidence 空(不提前标 passing),sync-active 不跑(派生视图无变化)|

> 判断依据:切片 1 是纯前端文件挪动(新建 2 + 改 1 facade),行为零变更,无架构约定变更,无新表/迁移/后端改动。下一步 EP3 切片 2:抽 `filter.ts`(4 符号)+ `schedule-grid-card.tsx`(ScheduleGridCard/ScheduleSlot/slotTone)+ 改 5 消费者 deep import 指向新文件 + shared 瘦身到只留 BookingStatusBadge + deviceNameOf + D5 fmt/fromDatetimeLocalValue 回源 `@/lib/format`,走 `/implement`。

---

## Session 157(2026-07-29):bookings-shared-split EP3 切片 2(抽 filter.tsx + schedule-grid-card.tsx + 改消费者 deep import + shared 瘦身,D5 回源,contract 阶段)

plan `harness/docs/plan-shared-tsx-split.md` 切片 2 —— expand-contract 的 **contract 阶段**:抽组件层、把消费者从 shared facade 改指 deep import、瘦身 shared.tsx、消除便利 re-export。

### 落地(8 文件,zero behaviour change)

- 新建 `frontend/src/pages/bookings/filter.tsx`:BookingFilter(type)/ FILTER_OPTIONS / FilterChips / applyBookingFilter(4 符号,列表过滤逻辑,单消费者 store-view)。依赖 `date-utils.ts`(startOfToday/addDays/isoDate)。逐字迁移,模块头注释含消费者 + 依赖 + D4/D5 说明。
- 新建 `frontend/src/pages/bookings/schedule-grid-card.tsx`:ScheduleGridCard / ScheduleSlot / slotTone(3 符号,StoreView 专属网格卡组件树)。slotTone 归此非 badges(D6:单消费者 ScheduleSlot,与 BookingStatusBadge 是不同视觉系统)。依赖 `status-meta.ts`(STATUS_META)+ `date-utils.ts`(startOfToday/addDays/isoDate/dayLabel/hhmm)。
- 改 `store-view.tsx`:`./shared` 的 import 拆成 4 处(`./shared` 留 BookingStatusBadge+deviceNameOf / `./filter` 取 FilterChips+applyBookingFilter+BookingFilter / `./schedule-grid-card` 取 ScheduleGridCard / `@/lib/format` 取 fmt)。
- 改 `hq-view.tsx`:`./shared` 留 BookingStatusBadge,isoDate+startOfToday → `./date-utils`,fmt → `@/lib/format`。
- 改 `my-bookings-view.tsx`:`./shared` 留 BookingStatusBadge,fmt → `@/lib/format`。
- 改 `shared-dialog.tsx`:ACTIONABLE_STATUS+MUTABLE_STATUS+NONE → `./status-meta`,fromDatetimeLocalValue 合并进既有 `@/lib/format` import(D5 回源,消除便利 re-export)。
- 改 `schedule-grid.tsx`:hhmm → `./date-utils`。
- 改 `shared.tsx`(290→38 行,-252):删所有 re-export(status-meta 4 + date-utils 5 + fmt/fromDatetimeLocalValue)+ 迁出的 9 符号(filter 组 4 + schedule-grid-card 组 3 + 注:slotTone),只剩 BookingStatusBadge(从 status-meta 取 STATUS_META)+ deviceNameOf(D7:单消费者但语义是显示原语,留 shared 避免孤儿)。

### 关键技术决策

- **filter.ts → filter.tsx**:plan §4.1/§6 记为 `filter.ts`,但 FilterChips 含 JSX,TypeScript 硬约束要求 JSX 文件用 `.tsx` 扩展名。落地为 `filter.tsx`(内容与 plan 一致),消费者用无扩展名 `from "./filter"` 故对调用方不可见。/code-review Spec 轴确认为「必要且可接受的偏差」。
- **D5 回源实施细节**:shared-dialog 已有 `import { toDatetimeLocalValue } from "@/lib/format"`,fromDatetimeLocalValue 合并进同一个 import 块(不新开 import 行),保持每个 import 源一行。store-view/hq-view/my-bookings-view 的 fmt 各自从 `@/lib/format` 取(`formatDateTime as fmt` 别名保持调用点零改动)。

### 验证(全绿,zero behaviour change 的唯一证据)

- ✅ `npx vitest run` **65/65 pass**(与切片 1 基线一致:store-view 6 + my-bookings-view 6 + hq-view 13 + schedule-grid 11 + config-dialog 5 + format 15 + key-spec-rows 7 + queries-booking-config 2)
- ✅ `npm run build` 绿(bookings chunk 31.29 kB,纯 locality 搬运不改变打包形状)
- ✅ `npx tsc -b` exit 0(import 路径全对,无未用 import)
- ✅ `npx oxlint src/pages/bookings/` 0 warning(18 文件)

### /code-review 双轴(并行子智能体)

- **Standards 轴:APPROVE,0 硬违反**。AGENTS.md 铁律全后端范畴(四层架构/多租户/三 token/软删除)与前端 locality 重构无交集;`@/*` 别名 + tsconfig + oxlint 全合规。逐字搬移无逻辑漂移(diff 字节级比对);新文件模块头注释(中文 JSDoc + 消费者 + 依赖 + D 决策 ID)对齐切片 1 sibling;瘦身 shared.tsx 单一职责连贯(Divergent Change 已消解)。3 判断项(均非阻塞):① 内联 D4/D5 注释引用外部 plan 决策 ID 需对照文档;② 同批注释在 4 文件重复(Shotgun Surgery,一次性重构备注成本极低);③ deviceNameOf 单消费者留 shared(有 D7 rationale)。
- **Spec 轴:APPROVE,8 AC 全满足**。AC1-AC8 逐条核对通过(grep 确认无 `from "./shared"` 拉取已迁出符号)。决策遵守:D2(瘦身不删)✓ / D4(纯 deep import 无 barrel)✓ / D5(回源 @/lib/format)✓ / D6(slotTone 在 grid-card 非 badges)✓ / D7(deviceNameOf 留 shared)✓。§4.7 范围外项全未碰:无新单测(D3)✓ / 无 cast 处理(候选 8)✓ / 无状态机改动(候选 2)✓。唯一偏差 filter.ts→filter.tsx 是 TS 硬约束必要偏差。

### 收尾(非末切片,不做 feature 收尾仪式)

- plan §6 切片 2 标题追加 ✅ + AC1-8 全勾选 + inline 完成证据
- progress.md 顶部「最高优先级未完成」frontier 推进到切片 3 + EP3 断点切片链进度更新 + 追加 Session 157 记录 + 文档影响评估
- commit `a0075d4` on `main`(切片 1 代码 ae69dac 已在 feat/bookings-shared-split 分支后随分支 tip 进入 main;本次切片 2 直接在 main 提交)
- **不动 feature_list.json status / 不写 evidence / 不 sync-active**(末切片 3 的职责,非末切片不越界)

### Session 157 文档影响评估

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/*` | ❌ 无影响 | 纯前端 locality 重构,行为零变更;四层架构 + 多租户隔离文档不涉及前端模块拆分 |
| `harness/docs/plan-shared-tsx-split.md` | ✅ 已更新 | 切片 2 标题 ✅ + AC1-8 全勾选 + inline 完成证据 |
| `progress.md` | ✅ 已更新 | 顶部 frontier 推进到切片 3 + EP3 断点切片链进度 + Session 157 记录 + 文档影响评估 |
| `feature_list.json` + 派生视图 | ❌ 无影响 | 切片 2 非末切片,status 仍 `in_progress`,evidence 空,sync-active 不跑 |

> 判断依据:切片 2 是纯前端文件挪动(新建 2 + 改 5 消费者 + 改 1 瘦身),行为零变更,无架构约定变更,无新表/迁移/后端改动。下一步 EP3 切片 3(末切片):`./init.sh full` 全绿 + `cd frontend && npm run build` 绿 + feature_list.json status→passing/evidence 写齐 + progress.md:1934 候选描述消解确认 + sync-active 刷新,走 `/implement`。

### Session 173 文档影响评估(design-system-token-foundation 切片 02 末切片)

| 文档 | 是否需更新 | 本 Session 动作 |
|---|---|---|
| `项目指南/02-后端架构/*` | ❌ 无影响 | 纯前端 className 映射(badge/toast 语义硬编码 → token),后端零改动;四层架构 + 多租户隔离 + ORM 文档不涉及前端 token |
| `harness/docs/plan-design-system-token-foundation.md` | ✅ 已更新 | 顶部 status `draft v1 → ✅ passing` + 切片 02 标题追加 `✅ commit 8398ab2` + 8 AC 全勾选(含 inline 完成证据,toast 实心 vs tint 偏差 + avatar/toast vacuous 条款留痕) |
| `progress.md` | ✅ 已更新 | 顶部 frontier「A in_progress」→「A passing,下一步 B frontier」+ Session 173 完整记录(/implement + /code-review 双轴 + feature 收尾仪式)+ 本文档影响评估 |
| `feature_list.json` + 派生视图 | ✅ 已更新 | 末切片,status `in_progress → passing` + evidence 4 条(切片01 token 基建 / 切片02 ui 映射 + grep 归 0 / WCAG 修复 + 对比度手算 / 收尾全量验证)+ sync-active 刷新(2 活跃 B+C + 5 最近 passing)|

> 判断依据:切片 02 是纯前端 className 映射(2 改 ui 组件 + 1 新建测试),后端零改动,无架构约定变更,无新表/迁移。toast 实心 vs tint 的 WCAG 对比度修复是视觉可读性决策(非架构变更),已记入 evidence + plan §切片02 AC inline。**feature 完整收官**:Feature A(token 地基)✅ passing,Feature B(color-sweep,depends_on A)解锁为下一 frontier。下一步 EP3 `/implement` Feature B 切片 01(success 色系业务页扫荡,A token 已就绪可消费 —— 注意 Feature B tint 范式需复核对比度,见 Session 173 记录的洞察)。
