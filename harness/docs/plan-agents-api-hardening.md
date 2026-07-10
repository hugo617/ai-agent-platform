# 计划:Agent 配置 API 加固(测试补全 + 异常对齐)

> 对应 feature_list.json 的 `id`: `agents-api-hardening`
> 状态: not_started
> 优先级: 11(下一个该做的)
> 参照模板: roles-crud 的后端对齐模式 + users.py 的 `_http_exc`

---

## 背景:为什么不是"从零搭建"

Agent CRUD 的**后端已完整实现**(5 个端点,Service/Repository 齐,main.py 已注册路由),前端 `agents-page.tsx` 也已接通后端。本任务的真实工作是**把后端加固到与 users/roles 同等稳健度**:

1. **测试覆盖**:当前 5 个测试全是 happy-path(用 `app_client` owner 身份),**零权限边界/零多租户/零软删除覆盖**
2. **异常对齐**:Service 抛裸 `ValueError`,API 层全映射成 404(对删除/更新可能掩盖真实错误)

### 当前状态速查

| 层 | 状态 | 文件 / 位置 |
|----|------|------------|
| Model | ✅ 已完成 | `app/models/agent.py` Agent 表 |
| Repository | ✅ 已完成 | `app/repositories/agent.py` AgentRepository(`get_for_tenant`/`list_for_tenant` 带 tenant 过滤) |
| Service | ⚠️ 抛裸 ValueError | `app/services/agent_service.py` `_owned` L21 抛 `ValueError` |
| Schema | ✅ 已完成 | `app/schemas/agent.py` AgentRead/Create/Update |
| API | ⚠️ 错误映射粗糙 | `app/api/v1/agents.py` 4 处 `except ValueError → 404`(L55/73/90) |
| 测试 | ❌ 仅 5 个 happy-path | `tests/test_agents_api.py`(全用 `app_client`,无 member/admin fixture) |

---

## 目标

让 Agent API 达到与 users/roles 同等完成度:
- Service 改用 `NotFoundError`(类型化异常),API 错误映射改 `isinstance`
- 测试覆盖:权限边界(member 403)、跨租户隔离、软删除、更新/404
- `./init.sh` 全绿(现有 96 passed + 新增,无回归)

---

## 前置条件

- 无外部依赖。所有 fixture(`app_client`/`member_client`/`super_admin_client`)在 `tests/conftest.py` 已就绪。

---

## 实施步骤

### 第一阶段:后端异常对齐(改 Service + API)

#### Step 1:AgentService 改用类型化异常

当前 `app/services/agent_service.py` 的 `_owned` 抛裸 `ValueError`,改成 `NotFoundError`(对齐 rbac_service.py 的模式)。

- **改什么**(`app/services/agent_service.py`):
  - 顶部 import:`from app.services.errors import NotFoundError`
  - L21 `raise ValueError(f"agent {agent_id} not found in tenant {tenant_id}")` → `raise NotFoundError(f"agent {agent_id} not found in tenant {tenant_id}")`
- **检查**:无需改其他方法——`_owned` 是唯一抛异常处。`NotFoundError` 是 `ValueError` 子类,API 层现有 `except ValueError` 仍捕获(过渡期不会破)。

#### Step 2:agents.py 错误映射改 isinstance

当前 `app/api/v1/agents.py` 的 `get_agent`/`update_agent`/`delete_agent` 三处用 `except ValueError → 一律 404`,粗糙。对齐 `users.py:29` 的 `_http_exc` 模式(按异常类型分流 404/400)。

- **改什么**(`app/api/v1/agents.py`):
  - 顶部 import:`from app.services.errors import NotFoundError`(或直接照搬 `_http_exc`)
  - 加 `_http_exc` 辅助函数(照抄 `users.py:29-37`):
    ```python
    def _http_exc(e: ValueError) -> HTTPException:
        if isinstance(e, NotFoundError):
            return HTTPException(status_code=404, detail=str(e))
        return HTTPException(status_code=400, detail=str(e))
    ```
  - `get_agent`(L53-56)、`update_agent`(L71-74)、`delete_agent`(L88-91):
    `except ValueError as e: raise HTTPException(404, ...)` → `except ValueError as e: raise _http_exc(e) from e`
- **检查**:`get /agents/nonexistent` → 404(行为不变);未来若 Service 抛 BizError 会正确映射 400(而非错误地 404)。

### 第二阶段:测试覆盖补全

#### Step 3:补 test_agents_api.py 的覆盖

当前只有 5 个 happy-path 测试。参照 `test_rbac_api.py`(roles-crud 补的 13 个)和 `test_users_api.py` 的覆盖维度补全。

- **保留**:现有 5 个测试不删(happy-path 仍有价值)
- **新增测试用例**(用 `app_client`[owner] / `member_client` / `super_admin_client` fixture):
  - **权限边界**:
    - `member_client` POST /agents/ → 403(member 无 `agents:create`)
    - `member_client` DELETE /agents/{id} → 403(member 无 `agents:delete`)
    - `member_client` GET /agents/ → 200(member 有 `agents:read`,能看不能改)
  - **跨租户隔离**:
    - owner 在租户 A 建 agent → 用租户 B 的 client GET /agents/{id} → 404(读不到别租户的)
    - (需 conftest 有跨租户 fixture;若无则参照 test_users_crud.py 的多租户 setup)
  - **软删除**:
    - 删除 agent 后 GET /agents/ 列表不再出现(当前测试只测了 get 404,没测列表不出现)
  - **更新**:
    - PATCH 改 name/model 后 GET 确认字段已更新(当前 test_update_agent 已有,可增强断言)
  - **超管**(可选):
    - `super_admin_client` 能跨租户操作(验证平台级超管权限)
- **检查**:`pytest tests/test_agents_api.py -v` 全过,测试数从 5 增至约 12-14。

### 第三阶段:总验证

#### Step 4:全栈验证

- **命令**:
  ```bash
  ./init.sh   # ruff + pytest 全绿(含新增 agent 测试)
  ```
- **通过标准**:
  - `ruff check` All checks passed!
  - pytest 全绿(96 基线 + 新增 ≈ 8,无回归)
- **全过 → 填 evidence + status 改 passing + 更新 progress.md**

---

## 验收标准

(feature_list.json 的 verification 字段与这里同步)

1. `./init.sh` 全绿(ruff + pytest,含新增的 agent 权限/隔离/软删除测试)
2. 后端 AgentService 用 `NotFoundError`(类型化),API 错误映射用 `isinstance(_http_exc)`,不再裸 `except ValueError → 404`
3. test_agents_api.py 覆盖:权限边界(member 403)、跨租户隔离(404)、软删除(列表不出现)、更新、404

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 改异常类型破坏现有 5 个测试 | `NotFoundError` 是 `ValueError` 子类,现有 `except ValueError` 仍捕获;现有测试全过即证明不破 |
| 跨租户测试需要特殊 fixture | 参照 `test_users_crud.py` 的多租户 setup;若 conftest 缺失,用 `db_session` fixture 手动建第二租户的 user+token |
| `require_permission` 在 dependencies 层拦截 vs Service 层 `require` 重复 | agents.py 用 `dependencies=[Depends(require_permission(...))]`(声明式,在路由层),Service 内也调 `permission_service.require`(双层防御)。测试 403 时依赖的是路由层拦截——member 无权限策略 → 403,无需进入 Service |

### 不做的事(边界)

- 不改 Agent 表 schema(不加字段、不加唯一约束)
- 不改前端(`agents-page.tsx` 已接通,本任务纯后端)
- 不改 LLM 配置(那是 `chat-conversation-api` 任务的 DeepSeek 切换)

---

## 参考文件(实施时对照)

| 参照 | 路径 |
|------|------|
| users.py `_http_exc` 模板 | `app/api/v1/users.py:29-37` |
| roles-crud 的异常对齐(同款任务) | `app/api/v1/roles.py` + `app/services/rbac_service.py` |
| 异常定义 | `app/services/errors.py`(NotFoundError/BizError) |
| 测试 fixtures | `tests/conftest.py`(`app_client`/`member_client`/`super_admin_client`) |
| 权限测试范例 | `tests/test_rbac_api.py`(13 个,roles-crud 补的) |
| Agent Service(待改) | `app/services/agent_service.py` |
| Agent API(待改) | `app/api/v1/agents.py` |
