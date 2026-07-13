# 计划:MVP 补全总纲(SaaS 产品体面 + 配套能力 + V2 差异化)

> 这是 **MVP 补全系列的总纲文档**(登记性质)。
> 2026-07-12 全面扫描后,识别出 12 个能力缺口。本总纲汇总全貌 + 登记占位任务。
> 各任务详细 plan 在执行到时再写(用户选择「先总纲登记,按需细化」粒度)。

---

## 背景:全面扫描后的 MVP 全景

2026-07-12(Session 062)对平台做了 15 维度全面扫描。结论:**地基扎实、能力扎实但表面层薄**——RBAC/多租户/认证是生产级,但大量用户可见的 SaaS 能力是真空。

### 已完成的地基(37 passing)

| 域 | 覆盖 |
|---|---|
| 组织域 | Group(总部)+Tenant(门店)+Customer(双层身份)完整 |
| 权限域 | RBAC + 权限矩阵(菜单/操作/数据权限重构系列已规划 39-42) |
| AI 内核 | 流式对话 + 上下文工程 + Markdown + 推理参数 |
| AtoA | CLI + Skill + API Token 开放生态 |
| 计费 | Token 费用管理系列已规划(43-46) |

### 扫描发现的 12 个能力缺口(本次登记)

---

## 缺口清单(按梯队)

### 第一梯队:SaaS 产品基本体面(成本低、体感大,优先做)

#### 1. Dashboard 数据看板 `dashboard-analytics`(priority 47)
- **现状**:占位页,4 个硬编码卡片(角色/Agent 数/租户ID/在线状态),无图表无趋势。**后端已有 `/users/statistics` 但前端没用它**。
- **目标**:真实数据看板——用户/Agent/对话/客户统计卡片 + 近期趋势图 + (token 计费上线后)消耗趋势。门店级 + 总部级双视角。
- **成本**:低(后端 stats 端点已有,前端接数据 + 加轻量图表)
- **依赖**:token 计费(43-46)完成后可加消耗维度;可先做基础统计

#### 2. 审计日志 UI `audit-log-ui`(priority 48)
- **现状**:SystemLog 模型在写(`logging_service.record`),但**无查询 API、无前端页面**。数据在黑暗里。
- **目标**:审计日志查询端点(按操作人/时间/类型/资源过滤)+ 前端审计页(表格 + 过滤)。super_admin 看全平台,owner 看本租户。
- **成本**:低(数据已在,补查询 + UI)
- **依赖**:无

#### 3. 用户个人中心 `user-profile-account`(priority 49)
- **现状**:无个人中心页。用户改不了自己密码/资料,只能找管理员。`GET /auth/me` 只读。
- **目标**:个人中心页——改密码、改资料(姓名/头像)、查看我的会话/我的用量。`PUT /auth/me` 端点。
- **成本**:低-中(标准 CRUD + 前端页)
- **依赖**:无(头像上传依赖文件上传 55)

#### 4. 对话管理增强 `conversation-management`(priority 50)
- **现状**:对话只能列表/读/删。无搜索、导出、重命名、标签/收藏。
- **目标**:对话搜索(按标题/内容全文)、重命名、标签/收藏分类、置顶、批量删除。聊天体验基本完整。
- **成本**:中(后端加搜索 + 标签字段 + 前端交互)
- **依赖**:无

#### 5. 全局搜索 `global-search`(priority 51)
- **现状**:只有 users 有 search 参数,其他实体无搜索。无跨实体全局搜索。
- **目标**:全局搜索(顶部搜索框,跨 Agent/客户/对话/用户)→ 结果分类展示。单实体搜索(agents/customers/conversations 各加 search 参数)。
- **成本**:中(后端跨实体查询聚合 + 前端搜索 UI)
- **依赖**:无(对话搜索依赖 50)

#### 6. 租户配置(品牌) `tenant-branding-config`(priority 52)
- **现状**:settings 只有 LLM 配置 + API Token。无品牌(logo/名称/主题色)。
- **目标**:租户级品牌配置——logo、显示名称、主题色、登录页文案。多租户白标 SaaS 基本能力。
- **成本**:中(加配置表/字段 + 前端配置页 + 主题应用)
- **依赖**:文件上传(55,logo 需要)

#### 7. 健康检查/监控 `health-monitoring`(priority 53)
- **现状**:只有 `/health` 返回 ok,不检查 DB。无 `/ready`、无 metrics。
- **目标**:`/ready`(检查 DB 连接)、`/metrics`(Prometheus 格式)、基础监控(请求量/延迟/错误率)。生产部署必需。
- **成本**:低(标准运维能力)
- **依赖**:无

---

### 第二梯队:配套能力 + 经营分析

#### 8. 通知系统 + 定时任务 `notification-scheduler`(priority 54)
- **现状**:无通知系统、无定时任务框架。一切同步处理。
- **目标**:① in-app 通知(站内消息中心,模型 + API + 铃铛组件);② APScheduler 定时任务框架(余额预警扫描、用量日报、过期清理)。
- **商业价值**:**Token 计费的配套**——余额预警、充值到账、月度用量报告都靠它。不做的话 token 计费体验不完整。
- **成本**:中(APScheduler 集成 + 通知模型 + 前端铃铛)
- **依赖**:token 计费(44)用于余额预警触发

#### 9. 数据导出 `data-export`(priority 55,原规划移此)
- **现状**:无任何导出能力。
- **目标**:客户清单/对话记录/用量明细/审计日志导出 CSV(门店级 + 总部级)。复用现有 TanStack Table 数据。门店月度经营分析必备。
- **成本**:低-中(后端 CSV 生成端点 + 前端下载按钮)
- **依赖**:无(用量导出依赖 token 计费 43)

#### 10. 文件上传 + 对象存储 `file-upload-storage`(priority 56)
- **现状**:无上传能力。`Customer.avatar` 是死字段。无对象存储配置。
- **目标**:文件/图片上传——头像、客户照片、(V2)知识库文档。对象存储抽象(本地 dev / S3/OSS 生产可切换)。
- **成本**:中(存储抽象层 + 上传端点 + 前端上传组件)
- **依赖**:无;**被依赖**:租户品牌 logo(52)、用户头像(49)、RAG 文档(58)

---

### 第三梯队:AI 差异化卖点(大投入,V2 候选)

#### 11. 知识库/RAG `knowledge-base-rag`(priority 57)
- **现状**:`pgvector` 声明了但**从没用过**。Agent 只能空聊,不能查企业知识库。无 embedding、无分块、无检索。
- **目标**:激活 pgvector——文档上传→分块→embedding(接 embedding 模型)→向量存储→检索→注入 Agent prompt。知识库管理 UI(文档 CRUD + 检索调试)。
- **商业价值**:这是让 AI 真正「有用」的核心能力(从「能聊」到「懂业务」)。
- **成本**:**高**(embedding 管线 + 向量存储 + 检索调优 + 知识库 UI)。V2 级别。
- **依赖**:文件上传(56)

#### 12. 多 Agent 编排 `multi-agent-orchestration`(priority 58)
- **现状**:单 ReAct agent(`create_react_agent`)。一个 agent 调不了另一个,无工作流。
- **目标**:LangGraph 多节点图——一个 Agent 可调用/转交给另一个(如:客服 Agent 遇专业问题转专家 Agent;编排 Agent 分派子任务)。
- **商业价值**:差异化卖点(复杂业务场景的智能体协作)。
- **成本**:**高**(重写编排层 + 多 agent 状态管理 + 调试工具)。V2 级别。
- **依赖**:无(独立模块)

---

## 优先级与依赖全景

```
第一梯队(SaaS 体面,独立或弱依赖,可穿插做):
  47 dashboard ──(弱)──▶ token计费(消耗维度)
  48 audit-log-ui(独立)
  49 user-profile ──(弱)──▶ 56 file-upload(头像)
  50 conversation-mgmt(独立)
  51 global-search ──(弱)──▶ 50(对话搜索)
  52 tenant-branding ──(弱)──▶ 56 file-upload(logo)
  53 health-monitoring(独立)

第二梯队(配套):
  54 notification-scheduler ──▶ token计费(余额预警)
  55 data-export(独立)
  56 file-upload(地基,被 49/52/57 依赖)

第三梯队(V2,大投入):
  57 knowledge-base-rag ──▶ 56 file-upload
  58 multi-agent-orchestration(独立)
```

> 与已规划系列的关系:本系列 12 个缺口 + 权限重构(39-42)+ Token 计费(43-46)+ demo-seed-full(38) = 当前全部 not_started。WIP=1 仍顺序执行,优先级由用户按业务需要排定。

---

## 规划粒度说明

用户选择「**先总纲登记,按需细化**」:
- 本总纲文档登记全部 12 个缺口(背景/目标/成本/依赖)
- feature_list.json 占位登记(priority 47-58,plan 字段暂指本总纲)
- **各任务详细 plan 在执行到时再写**(避免一次规划 11 份 plan 做不过来)
- 执行时把对应 feature 的 `plan` 字段改为指向新建的 `plan-<id>.md`

---

## 不做的事(本总纲边界)

- **i18n 国际化**:当前全中文硬编码。只做国内市场可暂缓;要出海再规划(未登记)
- **Webhook 外发集成**:平台无法通知外部系统。场景不明确,暂不登记
- **对接真实支付**:Token 计费已决策纯额度划拨,支付留远期(未登记)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| Dashboard 占位页 | `frontend/src/pages/dashboard-page.tsx` |
| 未用的 stats 端点 | `app/api/v1/users.py` `/users/statistics` |
| SystemLog 模型(待暴露) | `app/models/log.py` + `app/services/logging_service.py` |
| settings 页(待加品牌) | `frontend/src/pages/settings-page.tsx` |
| pgvector(待激活) | `requirements.txt:19` + `docker-compose.yml` |
| stream_agent(多 agent 改造点) | `app/agents/graph.py` |
| /health(待增强) | `app/main.py:78-80` |
| 扫描依据 | 2026-07-12 Session 062 全面 15 维度扫描 |
