# 计划:UserService super_admin lookup seam 抽取(UserLocator)

> **id**: user-service-lookup-seam
> **状态**: draft v1
> **优先级**: 84(待登记 feature_list.json)
> **创建日期**: 2026-07-31
> **来源**: 第 9 次架构巡检 Top recommendation(候选 1,Strong)

---

## 0. v1 → vN 变更摘要

(首版,无修订。若实施阶段发现 D1-D6 决策需调整,在此登记。)

---

## 1. Problem Statement

`user_service.py` 的 5 个方法(`get` / `update` / `delete` / `change_status` / `reset_password`)逐字节重复同一段 lookup glue:

```python
is_super_admin = platform_role == "super_admin"
if not is_super_admin:
    await permission_service.require(actor_id, tenant_id, self.OBJECT, "<action>")
if is_super_admin:
    user = await self.users.get(user_id)
    if user is None or user.is_deleted:
        raise NotFoundError(f"用户 {user_id} 不存在")
else:
    user = await self.list_repo.get(tenant_id, user_id)
    if user is None:
        raise NotFoundError(f"用户 {user_id} 不在该租户中")
```

这是教科书式的 shallow seam:删掉它,复杂度只是平移到 5 处复制粘贴,不会集中。

**为什么现在做**:第 9 次架构巡检 Top recommendation。设计系统系列刚收官,后端 service 是真正的架构热点(user_service.py 476 行)。customer_service / device_service **没有**这个 seam(它们走 Principal panorama),只有 user_service 因「super_admin 跨租户 vs store 租户内」二分未进 Principal(ADR-0001 把 user_service 列为 Principal 适用域之外),seam 散落未收口。

---

## 2. Solution

在 `UserService` 内部抽一个私有方法 `_resolve_user(self, user_id, tenant_id, is_super_admin: bool) -> User`,把 5 处重复的 lookup + is_deleted 守卫 + NotFoundError 文案分流收敛到一处。**纯内部重构,零行为变更,零 interface 变化,零 ADR 张力**(ADR-0001 钉的是 Principal 不扩到 user_service,不是禁止 user_service 内部深化)。

seam docstring 钉死「文案分流 = 多租户存在性模糊 security property」,防未来误把两条文案 DRY 成一条(store 用户的「不在该租户中」是有意的存在性模糊,不告诉 store 用户「这人在别店」)。

---

## 3. User Stories

- 作为**后端开发者**,我想让 super_admin/store 的 lookup 决策收口到一处,以便未来改 lookup 逻辑(如加缓存/改软删策略)只改一处而非 5 处。
- 作为**后端开发者**,我想让 `_resolve_user` 的两条分支可单测,以便定位「super_admin 路径」与「store 路径」的 bug 时不用通过 HTTP 端到端复现。
- 作为**多租户隔离的守卫者**,我想让 NotFoundError 文案分流的 security property 被 docstring 钉死,以便未来的重构者不会误把两条文案统一(破坏存在性模糊)。
- 作为**agent(代码导航者)**,我想让 lookup 的 single source of truth 存在,以便 grep「super_admin lookup」只命中一处而非散落 5 处(locality 修复)。

---

## 4. Implementation Decisions

### 4.0 Grill 决策表(D1-D6,实施必须遵守)

| # | 决策 | 内容 | 理由 |
|---|---|---|---|
| **D1** | seam 边界 | **lookup-only**(含 is_deleted 守卫 + NotFoundError),**不吃 require** | require 的 action 因方法而异(read/update/delete),无法参数化收敛;Principal 范式也把 require 留给 service |
| **D2** | 签名 | `_resolve_user(self, user_id, tenant_id, is_super_admin: bool) -> User` | 各方法**本来就**先算 `is_super_admin`(require 分支要用),bool 已在手,传它不重复判断;跟 `list_repo.list(super_admin=is_super_admin)` 风格一致 |
| **D3** | 文案 | seam 内部 `if is_super_admin` 分流,**两条文案逐字保留**(super_admin→"不存在" / store→"不在该租户中") | 文案的 scope 区分是有意的 security property(存在性模糊);零行为变更;无测试断言文案但 security property 值得保留 |
| **D4** | 深度 | seam 只返回 `User`,**不碰读法分流**(`_read`/`_read_all` + batch_tenant_info 留各方法) | 读法分流需要 tenant_info(super_admin 要 batch_tenant_info),跟 lookup 是两件事;不同方法对 user 后续处理不同;seam 吃 leverage 不碰 locality |
| **D5** | 覆盖范围 | **5 方法**(get/update/delete/change_status/reset_password),`list`/`statistics` 不进 seam | list/statistics 无「lookup + is_deleted 守卫 + NotFoundError」三元组(list 返回列表无 NotFoundError,statistics 返回聚合无 lookup);强行套 seam 扭曲签名 |
| **D6** | 注释 | seam docstring 钉死文案分流理由;delete 的跨店软删注释**保留上移**(它讲后续软删逻辑不是 lookup) | single source of truth;delete L345 注释是 method-local 业务(跨店 membership 拆除),跟 seam 无关 |

### 4.1 影响面清单

| 类别 | 数量 | 明细 |
|---|---|---|
| 后端文件改动 | 1 | `app/services/user_service.py`(抽 `_resolve_user` + 5 方法改调) |
| 数据库迁移 | 0 | 无 |
| 前端文件改动 | 0 | 无(纯后端内部重构) |
| 新增测试类 | 1 | `tests/test_user_service.py`(service 层直接测,范式参考 `test_principal.py` / `test_two_scope_repo.py`) |
| Skill / Hook / 配置 | 0 | 无 |

### 4.2 多租户影响评估

- 是否新增租户 scoped 表? **NO**
- 是否修改现有租户隔离逻辑? **NO**(零行为变更,lookup 路径逐字保留)
- 是否引入跨租户访问点? **NO**(super_admin 跨租户访问点已存在,seam 只是收敛不是新增)
- 验证:多租户测试用例 —— `_resolve_user` 两分支直接测(super_admin global + is_deleted 守卫 / store tenant-scoped),文案分流断言(防 DRY 误改)

### 4.3 权限影响评估

- 是否新增 permission code? **NO**
- 是否修改 DEFAULT_*_PERMS? **NO**
- 是否影响 60+ 处 `require_permission` caller? **NO**(seam 不碰 require,require 调用逐字保留在各方法)
- 是否影响 graph.py 工具内 check? **NO**

### 4.4 数据库表设计 checklist

不适用(无新表,纯 service 层重构)。

---

## 5. 不变式契约(实施必须守住)

1. **零行为变更**:5 方法的 lookup 行为逐字等价(seam 内部逻辑 = 原 5 处逻辑的提取)。`./init.sh full` 842 passed 零回归。
2. **文案逐字保留**:两条 NotFoundError 文案 `f"用户 {user_id} 不存在"`(super_admin)/ `f"用户 {user_id} 不在该租户中"`(store)逐字不动。**这是多租户存在性模糊的 security property,不得为 DRY 统一**。
3. **is_deleted 守卫保留**:super_admin 分支的 `user is None or user.is_deleted` 守卫逐字保留(super_admin 看全局须过滤软删;store 分支 list_repo.get 已在 tenant-scoped query 内带 is_deleted 过滤,无显式守卫)。
4. **require 不进 seam**:各方法的 `if not is_super_admin: await permission_service.require(...)` 逐字保留(D1)。seam 只吃 lookup。
5. **interface 不变**:`UserService` 的 public 方法签名零变化(`_resolve_user` 是私有)。
6. **ADR-0001 边界不动**:user_service 仍不进 Principal 覆盖域;seam 是 user_service **内部**深化,不扩 Principal。

---

## 6. 切片(to-tickets 产出,EP2 单回环)

本 feature 规模小(1 文件源码改 + 1 测试新增),按 expand-contract 单切片即可:

### 切片 01 — `_resolve_user` 抽取 + 5 方法改调 + service 层直接测试(单切片 = 末切片)

**What it delivers**:5 处 lookup glue 收敛到 `_resolve_user`,附 service 层直接测试钉死两分支行为 + 文案分流 security property。

**Blocked by**: 无(frontier)

**Acceptance criteria**:

- [ ] `app/services/user_service.py` 新增私有方法 `_resolve_user(self, user_id, tenant_id, is_super_admin: bool) -> User`,docstring 钉死文案分流理由(D3 security property + D6)
- [ ] `_resolve_user` 内部逻辑:`if is_super_admin: self.users.get(user_id) + is_deleted 守卫 + raise "不存在" else: self.list_repo.get(tenant_id, user_id) + raise "不在该租户中"`(逐字等价原 5 处)
- [ ] `get` / `update` / `delete` / `change_status` / `reset_password` 5 方法改调 `_resolve_user(user_id, tenant_id, is_super_admin)`,删除各自的 lookup + is_deleted 守卫 + NotFoundError 内联块(D5)
- [ ] 5 方法的 `if not is_super_admin: require(...)` 逐字保留(D1,require 不进 seam)
- [ ] `list` / `statistics` 不改(D5,无 lookup 三元组)
- [ ] delete 的跨店软删注释保留(上移到 delete 方法内适当位置,D6)
- [ ] 新增 `tests/test_user_service.py`:直接测 `_resolve_user` 两分支
  - super_admin 分支:`self.users.get` 命中 + is_deleted=True → NotFoundError "不存在";命中 + is_deleted=False → 返回 User
  - store 分支:`self.list_repo.get` 命中 → 返回 User;None → NotFoundError "不在该租户中"
  - 文案断言:两条文案逐字断言(防未来 DRY 误改,钉死 D3 security property)
- [ ] `./init.sh full` 842 passed(零回归,零行为变更)
- [ ] ruff clean
- [ ] grep `is_super_admin = platform_role == "super_admin"` 在 user_service.py 仍命中 7 处(list/statistics/update 的 role 分支等仍需算 is_super_admin,D5 不动它们)—— 但 lookup + is_deleted 守卫 + NotFoundError 的三元组 grep 命中 = 1 处(只在 `_resolve_user` 内)
- [ ] **feature 收尾**:feature_list.json `status` → `passing` + evidence 写实测 + `./scripts/sync-active-features.sh` 刷新 + 依赖解锁扫描(纯重构无下游)+ 分支清理

---

## 7. 测试策略

### 测试 seam(最高位)

**现有 seam 优先**:`test_users_api.py` + `test_users_crud.py`(HTTP 端到端)已覆盖 5 方法的 happy path + 错误路径,本 feature 零行为变更,这些测试**不应坏**(若坏 = 行为变更 = 违契约)。

**新增 seam**:`test_user_service.py`(service 层直接测 `_resolve_user`),参考范式:
- `tests/test_principal.py`(Principal contract test,直接测 for_write/for_read 两分支)
- `tests/test_two_scope_repo.py`(repo 层 contract test,直接测四态)

### 什么算好测试

- **只测外部行为**(lookup 返回值 + 异常类型 + 异常文案),不测内部实现细节(不 mock `self.users`/`self.list_repo` 的调用次数)
- **钉死 security property**:两条 NotFoundError 文案逐字断言(这是测试的核心价值 —— 防未来 DRY 误改破坏存在性模糊)
- **不重复 HTTP 测试已覆盖的**:happy path 交给 `test_users_crud.py`,service 层只测 seam 的两分支边界

---

## 8. Out of Scope

- **不扩 Principal 覆盖域**(ADR-0001 钉死,user_service 不进 Principal)。本 feature 是 user_service 内部深化,不是 Principal 扩展。
- **不动 `list` / `statistics` 方法**(D5,它们无 lookup 三元组)。
- **不统一 NotFoundError 文案**(D3,文案分流是 security property)。
- **不吃 require 进 seam**(D1,require 的 action 因方法而异)。
- **不碰读法分流**(`_read` / `_read_all` / batch_tenant_info,D4)。
- **不碰 member_service**(那是候选 4,独立 feature)。
- **不碰 Principal.authorize_write**(那是候选 3,有 ADR 张力,独立 feature)。

---

## 9. Further Notes

- **与候选 4(member_service 直接测试)的关系**:两者共享 membership repo。本 feature 的 `test_user_service.py` 建立了 service 层直接测试范式,候选 4 可复用。但两者独立,无依赖。
- **与候选 3(Principal.authorize_write)的关系**:若候选 3 未来落地(Principal 吃 require),本 feature 的 seam 仍不变(seam 只吃 lookup,与 require 正交)。
- **LOC 预警**:本 feature 是 leverage 重构,LOC 可能**不降反升**(seam docstring + 测试新增)。Principal feature 已建立先例(AC 指标修订为「leverage 重构接受,LOC 指标放弃」)。本 feature 的价值是 locality + leverage + security property 钉死,不是 LOC 削减。
- **巡检报告归档**:`~/.cache/ai-agent-platform-architecture-reviews/2026-07-31.html`(第 9 次巡检,候选 1)。

---

## 10. 验收标准(AC 汇总)

1. `./init.sh full` 842 passed(零回归)
2. ruff clean
3. `_resolve_user` 抽取 + 5 方法改调(D1-D6 全遵守)
4. `test_user_service.py` 两分支 + 文案断言(钉死 D3 security property)
5. grep lookup 三元组在 user_service.py 命中 = 1 处(只在 `_resolve_user` 内)
6. feature 收尾仪式(three-tier §4 第1-8步)
