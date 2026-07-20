# 代码健康度巡检日志

> 每次跑 [`/improve-codebase-architecture`](codebase-health-check.md) 后追加一行。
> baseline 快照段记录 `wc -l` top 10,作为下次巡检的对比基准。

---

## 巡检记录

| 日期 | 候选数 | Top recommendation | 进 grill? | 产出 plan | HTML 归档 |
|---|---|---|---|---|---|
| 2026-07-20 | _待 Step 2 填_ | _待 Step 2 填_ | _待 Step 3 填_ | _待 Step 3 填_ | `~/.cache/ai-agent-platform-architecture-reviews/2026-07-20.html` |

---

## Baseline 快照(2026-07-20,首次巡检)

### 后端 service top 10(按行数)

```
     197 app/services/auth_service.py
     228 app/services/knowledge_service.py
     268 app/services/api_token_service.py
     268 app/services/billing_service.py
     271 app/services/agent_service.py
     327 app/services/rbac_service.py
     351 app/services/conversation_service.py
     353 app/services/customer_service.py
     476 app/services/user_service.py
     617 app/services/permission_service.py     <-- 最大,横切关注点
```

### 后端 api top 10(按行数)

```
     246 app/api/v1/customers.py
     258 app/api/v1/conversations.py
     260 app/api/v1/auth.py
     311 app/api/v1/chat.py
     313 app/api/v1/billing.py
     495 app/api/v1/exports.py     <-- 最大,1 endpoint 内含 6 实体生成
```

### 前端 fat files top 5

```
    1188 frontend/src/pages/settings-page.tsx
    1079 frontend/src/hooks/queries.ts
    1048 frontend/src/api/endpoints.ts
     954 frontend/src/pages/chat-page.tsx
     862 frontend/src/api/types.ts
```

### 质量基线(本次巡检时点)

- 后端测试:**561 passed**
- 覆盖率:**93%**(门槛 ≥80%)
- oxlint:**0 warning 0 error**
- ruff:**All checks passed**
- `app/` 内 TODO/FIXME/HACK/XXX:**0 处**(已过 3 轮 cleanup)
- 前端单测:**0**(仅 1 个 Playwright e2e)
- CONTEXT.md:**首次创建**(本次 Step 0)
- docs/adr/:**尚不存在**(等 Step 3 grill 触发 lazy 创建)

### 下次巡检 trigger

- 第 **70** 个 feature 完成时(当前 60,距下次 10 个)
- 或 §1.2 触发条件任一满足
