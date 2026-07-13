# plan:demo-seed —— 大健康连锁演示案例 + 项目地图

| 字段 | 值 |
|------|-----|
| **id** | `demo-seed` |
| **priority** | 37 |
| **area** | 演示案例 |
| **status** | passing |
| **depends_on** | — (依赖 MVP 业务模块 17-22 已全部 passing,数据模型已就位) |
| **verification** | `./init.sh` 全绿(纯脚本+文档,无 app/ 改动);脚本幂等可重跑 |

---

## 1. 背景与目标

用户补充了大健康/中医/理疗连锁店的业务背景,需要:

1. **一套演示案例数据** —— 能导入系统,让用户直观看到「总部看全局、门店看自己、客户跨店复用」的核心价值。
2. **一份项目地图** —— 一眼看懂数据模型全貌(平台级 vs 租户级实体、跨店身份复用、三层权限模型)。

本任务把两者合并为一个 harness 任务:**一个 Python 种子脚本 + 更新两份过时文档**。

### 为什么需要

- 现有无任何业务场景演示数据(只有 `init_admin.py` 建的 1 租户 + 1 超管),用户无法直观感受多租户业务价值。
- `项目指南/附录/关系图.md` 第三章 ER 简图**已过时**(断言「所有业务表都带 tenant_id」,但 Group/Customer 是平台级无 tenant_id)。
- `docs/db-schema.mmd` 也**已过时**(停在 2026-07-09,缺 Group/CustomerProfile/GroupTenant/Customer/ApiToken/LlmConfig 等 6 张表)。

---

## 2. 演示场景设计(大健康连锁「颐和堂」)

```
颐和堂大健康连锁
├─ 组织A「颐和堂中医馆」(Group, 连锁企业)
│   ├─ 朝阳理疗中心 (tenant=朝阳)
│   │   ├─ 陈馆长(owner) / 李师傅(member) / 王师傅(member)
│   │   ├─ 客户: 张先生(138xxx) / 刘女士(139xxx)
│   │   └─ Agent: 朝阳店健康顾问
│   └─ 海淀中医门诊 (tenant=海淀)
│       ├─ 赵馆长(owner) / 孙师傅(member)
│       ├─ 客户: 张先生(跨店复用同手机号!) / 周先生
│       └─ Agent: 海淀店健康顾问
├─ 组织B「独立养生馆」(Group, 单店)
│   └─ 王府井理疗馆 (tenant=王府井)
│       ├─ 吴馆长(owner)
│       ├─ 客户: 刘女士(跨店!)
│       └─ Agent: 王府井店健康顾问
└─ 总部(super_admin 已由 init_admin 建好)
    ├─ Agent: 颐和堂总部督导
    └─ hq_staff: 总部督导员(只读看板)
```

**核心验证点**:
- **跨店身份复用**:张先生跨朝阳+海淀(同 `identity_key` 复用 Customer 全局身份)、刘女士跨朝阳+王府井。
- **总部聚合视图**:super_admin/hq_staff 能看到「张先生去过 2 家、刘女士去过 2 家」。
- **门店隔离**:朝阳店 owner 只看到本店 2 个档案,看不到海淀/王府井的。

---

## 3. 交付物

### 3.1 种子脚本 `scripts/seed_demo.py`

照搬 `scripts/init_admin.py` 范式(async + AsyncSessionLocal + 幂等 select-then-add + 调 Service/Repository)。

**脚本结构**:
- 常量区:`STORES`(3 门店 × 员工)/ `HQ_STAFF` / `GROUPS`(2 组织)/ `CUSTOMERS`(5 档案)/ `AGENTS`(4 智能体)
- `_get_or_create_tenant(db, name)` —— 幂等建门店
- `_get_or_create_user(db, username, display, platform_role)` —— 幂等建用户
- `_ensure_membership(db, user_id, tenant_id, role)` —— 幂等 SCD2 角色绑定
- `_seed_tenant_rbac(db, tenant, owner)` —— 每个门店初始化 RBAC(casbin + 权限 SCD2)
- `main()` —— 按 5 步建数据 + 汇总打印账号清单

**权限约束处理**:
- `GroupService.create(payload)` 无 `require` 守卫(平台级实体),脚本直接调 ✓
- `CustomerService.create_profile(actor_id, tenant_id, payload, platform_role=None)` 有 `require(customers, create)`,传 `actor_id=该门店 owner.user_id` + `platform_role=None`(owner 在该 tenant 有 casbin 策略)✓
- `AgentService.create(user_id, tenant_id, payload, platform_role)` 有 `require(agents, create)`,门店 Agent 传 owner,平台 Agent 传 super_admin ✓
- 每个门店在创建任何业务数据前,先 `RbacService.seed_defaults` + `permission_service.seed_tenant_defaults` 完整初始化 RBAC ✓

**幂等设计**(可重跑):
- 门店/用户按 name/username select-then-add
- 角色绑定用 `UserTenantRepository.assign_role`(内部 SCD2 幂等:role 相同则复用 current 行)
- Group 按 code 查重
- CustomerProfile 在创建前查 `(customer_id, tenant_id, is_deleted=False)` 已存在则跳过
- Agent 按 `(name, tenant_id)` 查重

### 3.2 更新 `docs/db-schema.mmd`(ER 图补全)

当前停在 2026-07-09(16 表,缺 6 张新表)。补全到 2026-07-12 的全部表(22 表),FK 关系准确。

重点标注三类实体:
- **平台级实体(无 tenant_id)**:Group / Customer / GroupTenant(关联表)
- **租户级实体(有 tenant_id)**:Agent / Conversation / Message / CustomerProfile / LlmConfig / ApiToken
- **关联表**:UserTenant(SCD2,用户↔租户)/ GroupTenant(M2M,组织↔租户)

### 3.3 更新 `项目指南/附录/关系图.md`

- **第三章 ER 简图**:修正「所有业务表都带 tenant_id」的错误断言;补 Group/Customer/CustomerProfile/GroupTenant;区分平台级 vs 租户级
- **新增第十章:业务实体全景图** —— 一张 mermaid 图展示 Tenant/User/UserTenant/Group/GroupTenant/Customer/CustomerProfile/Agent 的关系 + 文字说明三个核心概念(成员 vs 客户 / 跨店复用 / 平台级 vs 租户级)+ 权限模型 3 层流程图
- **新增第十一章:演示案例说明** —— 指向 `scripts/seed_demo.py` + 账号清单表 + 数据全景表 + 4 个验证点

### 3.4 harness 文档登记

- `feature_list.json` 追加 1 条(priority 37,area 演示案例,status passing)
- `progress.md` 任务规划表加 1 行 + Session 记录

---

## 4. 实施步骤

1. **写 `scripts/seed_demo.py`** —— 照搬 init_admin 结构,建门店/员工/组织/客户/Agent
2. **起后端(docker postgres)→ 跑脚本 → 验证数据** —— 登录各角色看数据隔离/聚合
3. **更新 `docs/db-schema.mmd`** —— 补全 ER 图到 22 表
4. **更新 `项目指南/附录/关系图.md`** —— 第三章修正 + 新增第十/十一章
5. **写本任务的 plan 文档 + 登记 feature_list.json + progress.md**
6. **验证** —— 脚本幂等可重跑 + `./init.sh` 全绿(纯文档+脚本,无功能代码改动)

---

## 5. 验收标准

1. `python scripts/seed_demo.py` 幂等可重跑(第二次跑打印「exists」不报错)
2. 脚本跑完后:3 门店 + 6 员工 + 1 hq_staff + 2 组织 + 5 客户档案(含 2 个跨店身份)+ 4 Agent 全部入库
3. 登录验证:朝阳店 owner 只看本店客户档案;super_admin 看到张先生跨 2 店 / 刘女士跨 2 店
4. `docs/db-schema.mmd` 含全部当前表(含 Group/Customer/CustomerProfile 等),mermaid 语法合法
5. `项目指南/附录/关系图.md` 第三章节断言修正 + 新增业务实体全景图 + 演示案例说明
6. `./init.sh` 全绿(纯文档+脚本,无 app/ 代码改动,基线不回归)

---

## 6. 风险 / 不做的事

- **脚本权限**:CustomerService/AgentService 内部 `require` 查 casbin,需传门店 owner 作 actor;若 casbin 未正确 seed 会 403 → 缓解:脚本内先 `seed_tenant_defaults` 再调 create
- **不做**:不改任何 `app/` 功能代码、不加批量导入端点、不做前端改动、不删现有 `init_admin.py`
- **密码安全**:演示账号统一弱密码 `Demo@123456`,脚本注释标明「仅演示用,生产勿用」
- **SQLite vs Postgres**:脚本用 `AsyncSessionLocal` 连真实库(生产 Postgres);`init.sh` 的 SQLite 测试不跑脚本(脚本不在 testpaths)

---

## 7. 实现记录(evidence)

- `scripts/seed_demo.py`(260+ 行):照搬 init_admin 范式,5 步建数据 + 汇总打印;幂等设计覆盖门店/用户/角色绑定/组织/客户档案/Agent 全部
- 真实 Postgres 验证(docker aap-postgres):脚本首跑成功创建全部数据;二跑打印「exists」全部跳过(幂等确认)
- 跨店聚合验证:super_admin 查客户 → 张先生 profile_count=2(朝阳+海淀)、刘女士 profile_count=2(朝阳+王府井)
- 门店隔离验证:朝阳店 owner 查客户档案 → 只见 2 个(张先生+刘女士本店档案),不见海淀/王府井
- `docs/db-schema.mmd`:从 16 表补全到 22 表,删除废弃的 organizations/user_organizations,新增 groups/group_tenants/customers/customer_profiles/api_tokens/llm_configs
- `项目指南/附录/关系图.md`:第三章断言修正(平台级 vs 租户级三类实体)+ 新增第十章(业务实体全景图 mermaid + 三核心概念 + 权限模型)+ 第十一章(演示案例说明)
- `./init.sh` 全绿:纯文档+脚本任务,`app/` 零改动,基线不回归

---

> **续篇**:本任务种下了组织/客户/门店三域基础数据。后续 `demo-seed-full`(priority 38)
> 在此基础上扩 `seed_demo.py` 加 `--reset` 清理重建 + 补全全部缺口业务表
> (对话/消息/LLM配置/API Token/自定义角色权限/审计日志/多登录方式/Agent推理参数差异化)。
> 全量补全详见 [`plan-demo-seed-full.md`](plan-demo-seed-full.md)。
