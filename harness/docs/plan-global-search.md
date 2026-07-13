# 计划:全局搜索(跨 Agent/客户/对话/用户)

> 对应 feature_list.json 的 `id`: `global-search`
> 状态: not_started
> 优先级: 51
> 前置: 无(对话搜索依赖 conversation-management 50,可先做其他实体)
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:只有 users 有 search,无跨实体全局搜索

### 现状

- **唯一有 search 的**:`app/api/v1/users.py` L61 支持 `search` 参数(同 list 端点还有 status/role/sort 等过滤)
- **无 search 的**:agents / conversations / groups / customers 都无搜索参数
- **无全局搜索**:无跨实体聚合搜索端点,无顶部搜索框

### 目标

1. 单实体搜索:agents/customers/conversations 各加 search 参数
2. 全局搜索:顶部搜索框,跨实体聚合结果,分类展示,点击跳转
3. 权限:按当前用户可访问范围(门店用户本租户,super_admin 全局)

---

## 前置条件

- 无。对话内容搜索依赖 conversation-management(50)的 search;可先做 agents/customers/users 的全局搜索。

---

## 实施步骤

### 第一阶段:后端

#### Step 1:各实体加 search 参数

- **agents**(`app/api/v1/agents.py` GET / 列表):加 `search` 参数(name ILIKE)
- **customers**(`app/api/v1/customers.py`):加 `search`(name/identity_key ILIKE)
- **conversations**:依赖 50(title ILIKE),或本任务加
- **检查**:各 list 端点支持 search 过滤

#### Step 2:全局搜索端点

- **新建**(`app/api/v1/search.py`):
  ```python
  @router.get("/")
  async def global_search(q: str, user, db, limit_per_type: int = 5):
      if len(q.strip()) < 2: return {}
      results = {}
      results["agents"] = await agent_repo.search(q, user.tenant_id, limit)
      results["customers"] = await customer_repo.search(q, user.tenant_id, limit)
      results["conversations"] = await conv_repo.search(q, user.tenant_id, user.user_id, limit)
      if is_cross_tenant_viewer(user.platform_role):  # super_admin/hq_staff
          results["users"] = await user_repo.search(q, limit)
          results["tenants"] = await tenant_repo.search(q, limit)
      return results
  ```
- **权限**:门店用户搜本租户;super_admin 全局(加 users/tenants)
- **路由注册**
- **检查**:输入 q 返回各实体分类结果;权限过滤

### 第二阶段:前端

#### Step 3:types + endpoints + hooks

- **改** types:`GlobalSearchResult`(各实体分类)
- **改** endpoints:`globalSearch(q)`
- **改** hooks:`useGlobalSearch(q)`(debounce 300ms)
- **检查**:tsc 无错

#### Step 4:顶部全局搜索框

- **改什么**(`frontend/src/components/layout/dashboard-layout.tsx`):
  - 顶栏加搜索框(放大镜图标)
  - 输入(防抖)→ 调 useGlobalSearch → 下拉显示结果分类(Agent/客户/对话/用户)
  - 每类显示 top 5,点击跳转对应详情页
  - 「查看全部」跳转带 search 参数的列表页
- **检查**:搜索框输入 → 实时下拉结果 → 点击跳转

### 第三阶段:验证

#### Step 5:测试 + 总验证

- **后端**(`tests/test_global_search.py`):
  - 各实体搜索(q 命中 name/title)
  - 全局聚合返回分类
  - 权限:门店用户搜本租户;super_admin 加 users/tenants
  - q < 2 字符 → 空结果
- **命令**:`./init.sh` + `npm run build`
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准

1. agents/customers/conversations 各加 search 参数
2. `GET /search?q=` 全局聚合(各实体分类,limit_per_type)
3. 权限:门店本租户;super_admin 加 users/tenants
4. 前端顶部搜索框(防抖)+ 下拉分类结果 + 点击跳转
5. `./init.sh` + `npm run build` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 全局搜索查多表慢 | limit_per_type=5;并发查询(asyncio.gather);q < 2 字符不查 |
| 防抖体验 | 前端 debounce 300ms + loading 态 |
| ILIKE 性能 | 量级内可接受;超大量加 trigram 索引(pg_trgm) |

### 不做的事(边界)

- 不做全文检索/Elasticsearch(ILIKE 够用)
- 不做搜索历史/热搜
- 不做搜索结果高亮(后续)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| 已有 search(users) | `app/api/v1/users.py` L61-65 |
| 布局(加搜索框) | `frontend/src/components/layout/dashboard-layout.tsx` |
| 跨租户判断 | `app/services/permission_service.py` `is_cross_tenant_viewer` |
