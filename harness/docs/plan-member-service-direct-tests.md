# 计划:MemberService 直接测试(SCD2 + casbin 双写契约)

> **id**: member-service-direct-tests
> **状态**: draft v1
> **优先级**: 85(待登记 feature_list.json)
> **创建日期**: 2026-08-01
> **来源**: 第 9 次架构巡检候选 ④(Worth exploring)

---

## 0. v1 → vN 变更摘要

(首版,无修订。若实施阶段发现测试范式问题,在此登记。)

---

## 1. Problem Statement

`member_service.py`(149 行,4 方法 list/add/update_role/remove)是 **SCD2 写路径 + casbin sync 双写契约**的执行者之一:

- `add`:SCD2 `assign_role` + casbin `add_role_for_user_in_domain`
- `update_role`:SCD2 `assign_role`(关旧行开新行)+ casbin `set_role_for_user_in_domain` + notification(best-effort)
- `remove`:SCD2 `remove_member`(关行不物理删)+ casbin `remove_user_from_tenant`

这套双写是 `permission_service` docstring 钉的「宪法」(DB membership 与 casbin grouping 必须一致,否则越权或漏权)。**但 member_service 目前零直接测试** —— 只通过 `test_rbac_api.py` / `test_users_api.py` 经 HTTP 间接打到。一个 casbin sync 漂移 bug 会同时坏 user_service 和 member_service,但没有隔离测试能定位到 member_service。

**为什么现在做**:第 9 次巡检候选 ④。刚做完 `user-service-lookup-seam`(候选 ①),建立了 `test_user_service.py` service 层直接测试范式,member_service 测试可复用。纯加测,零行为变更,零 ADR 风险。

---

## 2. Solution

新增 `tests/test_member_service.py`,用 service 层 contract test 范式(参考 `test_principal.py` / `test_two_scope_repo.py`)直接测 `MemberService` 的 4 方法,钉死 **SCD2 DB 写 + casbin grouping 双写一致契约** + 边界(NotFoundError / self-guard / SCD2 历史保留)。**不改 member_service 源码**(纯加测;若测试发现真 bug,另起 bug-fix feature,不在本 feature 越界改)。

---

## 3. User Stories

- 作为**后端开发者**,我想让 member_service 的 SCD2+casbin 双写契约有直接测试,以便定位 casbin sync 漂移 bug 时能隔离到 member_service 而非混在 user_service 里。
- 作为**多租户权限的守卫者**,我想让「DB membership 与 casbin grouping 一致」被测试钉死,以便未来重构 member_service(如抽 seam、改 notification 触发)时不会意外破坏双写一致性。
- 作为**后端开发者**,我想让 SCD2 历史保留语义(remove 后旧行 valid_to 关闭但物理保留)被测试覆盖,以便未来改 remove 实现时不会误把软删改成硬删丢历史。
- 作为**agent(代码导航者)**,我想让 member_service 的契约有测试文档化,以便理解「add/update/remove 各自的 casbin sync 调用」时不只靠读 docstring。

---

## 4. Implementation Decisions

### 4.0 Grill 决策表(D1-D4,实施必须遵守)

| # | 决策 | 内容 | 理由 |
|---|---|---|---|
| **D1** | 测试哲学 | **只测外部可观察契约**(DB membership 状态 + casbin grouping 状态 + 异常类型/文案),**不测内部调用次数/顺序**(非 mock 调用断言) | 契约是 security property(casbin 漂移=越权),测它有意义;实现细节会随重构变,测了反成枷锁;对齐 to-spec skill「only test external behavior, not implementation details」 |
| **D2** | 测试 seam | **service 层直接测**(`test_env` fixture + `factory()` 开 session 构造 `MemberService`),范式参考 `test_principal.py`;**不写 HTTP 测试**(已有 `test_rbac_api.py` 间接覆盖) | 巡检候选 ④ 核心价值 = 隔离 member_service 双写契约;HTTP 测不到 casbin enforcer 内部状态;service 层能直接断言 grouping policy |
| **D3** | 覆盖范围 | 4 方法契约 + 边界:① 双写一致(add/update/remove 后 DB membership 与 casbin grouping 同步);② NotFoundError(非成员 update/remove);③ self-guard(remove 自删→BizError);④ SCD2 历史保留(remove 后旧 membership 行 valid_to 关闭但物理保留);⑤ add 的 get_or_create 路径(payload.email 新用户) | 覆盖双写契约的全部正常 + 异常路径 |
| **D4** | 是否改 member_service | **不改**(纯加测,零行为变更)。若测试发现真 bug 另起 bug-fix feature | 纯加测 feature 的边界;越界改会混淆「加测」与「修 bug」 |

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 0 | 不改 member_service(D4) |
| 数据库迁移 | 0 | 无 |
| 前端文件改动 | 0 | 无 |
| 新增测试类 | 1 | `tests/test_member_service.py`(service 层 contract test) |
| Skill / Hook / 配置 | 0 | 无 |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**
- 是否修改现有租户隔离逻辑? **NO**(纯加测,零行为变更)
- 是否引入跨租户访问点? **NO**
- 验证:测试用 `test_env` 的隔离 enforcer + 隔离 tenant_id,断言双写在隔离环境内一致

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 require_permission caller? **NO**(纯加测)
- 是否影响 graph.py 工具内 check? **NO**

### 4.4 数据库表设计 checklist

不适用(无新表,纯测试)。

---

## 5. 不变式契约(实施必须守住)

1. **零行为变更**:member_service 源码零改动(D4)。`./init.sh full` 全量 passed(基线 + 新测试数)零回归。
2. **真 DB + 真 casbin**:测试用 `test_env` 的真 SQLite schema + 真 casbin enforcer(经 `patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer)` 注入),**不用 mock**(D1)。这是 contract test 的本质 —— 验真双写,非验 mock 调用。
3. **不测实现细节**:不断言 `assign_role` / `set_role_for_user_in_domain` 的调用次数或顺序(D1)。只断言最终可观察状态:DB `memberships.current_role` 返回值 + casbin enforcer 的 `has_role_for_user_in_domain`。
4. **隔离 member_service**:测试直接调 `MemberService(db)`,不经 HTTP(D2)。与 user_service 测试解耦,定位 casbin 漂移时能隔离。
5. **若发现真 bug 不越界修**:测试若暴露 member_service 真实 bug(如 casbin sync 缺失),不在本 feature 改源码(D4)—— 标记为 `pytest.xfail` 或留 TODO,另起 bug-fix feature。

---

## 6. 切片(to-tickets 产出,EP2 单回环)

本 feature 规模小(1 测试文件新增,源码零改),单切片即可:

### 切片 01 — `test_member_service.py` SCD2+casbin 双写契约测试(单切片 = 末切片)

**What it delivers**:新增 `tests/test_member_service.py`,service 层 contract test 覆盖 4 方法的双写契约 + 边界,隔离 member_service 的 SCD2+casbin 双写。

**Blocked by**: 无(frontier)

**Acceptance criteria**:

- [ ] 新增 `tests/test_member_service.py`,用 `test_env` fixture + `factory()` 构造 `MemberService`,`patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer)` 注入隔离 enforcer(范式参考 conftest.py L273 等多处 + test_principal.py)
- [ ] **list 契约**:owner 调 list → 返回 seed 的 owner membership(MemberRead:user_id/role/joined_at);空 tenant → 返回 []
- [ ] **add 契约(双写一致)**:add 新成员(role=admin)→ DB `memberships.current_role(user, tenant)` 返回 admin AND casbin `enforcer.has_role_for_user_in_domain(user, "role:admin", tenant)` 为 True
- [ ] **add 的 get_or_create 路径**:add 一个 payload.email 对应的不存在 user → User 被创建(get_or_create)+ membership 建立
- [ ] **update_role 契约(双写一致)**:owner 把成员 role 从 member 改 admin → DB current_role 返回 admin AND casbin 旧 role 消失(`has_role_for_user_in_domain(user, "role:member", tenant)` 为 False)AND 新 role 出现(admin True)
- [ ] **update_role 边界**:update 一个非成员 → NotFoundError("user {id} is not a member of this tenant")
- [ ] **remove 契约(双写一致)**:remove 成员 → DB current_role 返回 None(成员已移除)AND casbin grouping 删除(`has_role_for_user_in_domain` 对所有 role 为 False)
- [ ] **remove 的 SCD2 历史保留**:remove 后,查 UserTenant 历史(valid_to 已关闭的旧行)仍物理存在(软删非硬删)—— 可通过 repo 层查原始行或断言 `is_deleted`/`valid_to` 语义
- [ ] **remove 的 self-guard**:owner remove 自己 → BizError("cannot remove yourself")
- [ ] **remove 边界**:remove 一个非成员 → NotFoundError
- [ ] **不测实现细节**(D1):不断言 assign_role / set_role_for_user_in_domain 的调用次数或顺序;只断言最终 DB + casbin 可观察状态
- [ ] **member_service 源码零改动**(D4):grep `git diff app/services/member_service.py` 为空
- [ ] `./init.sh full` 全量 passed(基线 + 新测试数,零回归)
- [ ] ruff clean
- [ ] **feature 收尾**:feature_list.json `status` → `passing` + evidence 写实测 + `./scripts/sync-active-features.sh` 刷新 + 依赖解锁扫描(纯加测无下游)+ 分支清理 + **plan 顶部状态行同步 passing**(避免重蹈 spacing-card-hierarchy 的 CI 债)

---

## 7. 测试策略

### 测试 seam(最高位)

**service 层直接测**(D2),参考范式:
- `tests/test_principal.py`(Principal contract test,真 DB + 真 casbin,无 mock)
- `tests/test_two_scope_repo.py`(repo 层 contract test)
- conftest.py 的 `test_env` fixture(engine + factory + owner_user + tenant_id + enforcer)

### enforcer 注入

`permission_service` 通过 `_casbin_mod.get_enforcer()` 拿 enforcer(permission_service.py L46 注释明示 tests can monkeypatch)。测试用 `patch.object(casbin_mod, "get_enforcer", return_value=test_env.enforcer)` 注入隔离 enforcer,范式参考 conftest.py L273/323/406/525/582 多处。

### 什么算好测试

- **只测外部行为**(D1):DB membership 状态 + casbin grouping 状态 + 异常类型/文案,不测内部调用
- **真 DB + 真 casbin**:不用 mock repo / mock permission_service(contract test 本质)
- **钉死 security property**:双写一致是 security property(casbin 漂移=越权),测试核心价值
- **不重复 HTTP 测试**:happy path 交给 `test_rbac_api.py`,service 层只测双写契约 + 边界

---

## 8. Out of Scope

- **不改 member_service 源码**(D4,纯加测)。若发现真 bug 另起 bug-fix feature。
- **不写 HTTP 端到端测试**(D2,已有 `test_rbac_api.py` 间接覆盖)。
- **不用 mock 测内部调用**(D1,测实现细节会锁死重构)。
- **不测 notification 触发**(update_role 的 best-effort notification 是独立 concern,且是 best-effort 不影响契约;若需覆盖另起 feature)。
- **不碰 user_service**(那是候选 ①,已独立完成)。
- **不测 list 的权限分支**(permission_service.require 的 platform_role 分支由 permission_service 自己的测试覆盖,member_service 测试只验 list 返回契约)。

---

## 9. Further Notes

- **与候选 ①(已完成)的关系**:`user-service-lookup-seam` 建立了 `test_user_service.py` service 层直接测试范式,本 feature 复用。两者共享 membership repo,测试互为兜底。
- **SCD2 历史保留断言**:UserTenant 的 SCD2 语义(valid_from/valid_to)是 member_service remove 的核心契约(软删保历史)。断言方式:remove 后通过 repo 层查原始行(绕过 current_role 的 valid_to 过滤),验证旧行物理存在且 valid_to 已设。
- **LOC 预警**:纯加测 feature,LOC 必增(测试代码)。价值是 security property 钉死 + bug 定位隔离,非 LOC 削减。
- **巡检报告归档**:`~/.cache/ai-agent-platform-architecture-reviews/2026-07-31.html`(第 9 次巡检,候选 ④)。
- **CI 债教训**:本 feature 收尾时**必须同步 plan 顶部状态行**(参考 spacing-card-hierarchy 的 CI 债教训),避免重蹈 `check_plan_status_sync.py` 失败。

---

## 10. 验收标准(AC 汇总)

1. `./init.sh full` 全量 passed(零回归)
2. ruff clean
3. `test_member_service.py` 覆盖 4 方法双写契约 + 边界(D1-D3 全遵守)
4. member_service 源码零改动(D4,`git diff app/services/member_service.py` 空)
5. 不测实现细节(D1,无 mock 调用断言)
6. feature 收尾仪式(three-tier §4 第1-8步)+ **plan 状态行同步 passing**(CI 债教训)
