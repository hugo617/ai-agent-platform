# 计划:数据导出 CSV(客户/对话/用量/审计,门店+总部级)

> 对应 feature_list.json 的 `id`: `data-export`
> 状态: not_started
> 优先级: 55
> 前置: 无(用量导出依赖 token-usage-tracking 43)
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:无任何导出能力

### 现状

- 全项目搜 `export|csv|excel|xlsx|download` **零真实命中**(只有 TS export 关键字、函数名、域名词)
- 无 CSV 生成端点、无下载、无相关库(无 openpyxl/pandas/papaparse)
- 门店无法做月度经营分析(客户清单/对话记录/用量明细导不出来)

### 目标

1. 后端 CSV 生成端点(StreamingResponse + csv.writer,避免 OOM)
2. 覆盖:客户 / 对话 / 用量 / 审计日志
3. 门店级导本租户,总部级(super_admin)导全平台
4. 前端各列表页加「导出 CSV」按钮

---

## 前置条件

- 无。用量导出依赖 token-usage-tracking(43)的 UsageEvent 数据。

---

## 实施步骤

### 第一阶段:后端 CSV 导出端点

#### Step 1:导出工具 + 端点

- **新建**(`app/api/v1/exports.py`):
  ```python
  from fastapi.responses import StreamingResponse
  import csv, io

  def csv_stream(rows: list[dict], headers: list[str]):
      buffer = io.StringIO()
      writer = csv.writer(buffer)
      writer.writerow(headers)
      for row in rows:
          writer.writerow([row.get(h, "") for h in headers])
      buffer.seek(0)
      return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
                               headers={"Content-Disposition": "attachment; filename=export.csv"})

  @router.get("/{entity}")
  async def export_entity(entity: str, user, db, *, format="csv",
                          date_from=None, date_to=None):
      # entity: customers / conversations / usage / logs
      # 分流到各 service 的 export 方法
  ```
- **大数据量**:用 `yield` 分批(stream),避免一次 load 全部到内存
- **检查**:返回 CSV 文件下载

#### Step 2:各实体导出逻辑

- **customers 导出**:name/identity_key/gender/created_at/tags/status(门店级 tenant_id 过滤)
- **conversations 导出**:title/agent/user/created_at/message_count
- **usage 导出**(依赖 43):date/conversation/model/tokens/cost/customer(门店级;super_admin 全平台)
- **logs 导出**(依赖 48 的 SystemLog 查询):time/operator/action/resource
- **权限**:
  - customers/conversations/usage:`require_permission("<obj>", "read")`(门店级)或 super_admin
  - logs:`require_permission("logs", "read")` 或 super_admin
- **路由注册**

#### Step 3:时间范围 + 过滤

- **改什么**:export 端点接受 `date_from`/`date_to`/其他过滤参数,透传给各 service 查询
- **检查**:按时间范围导出;默认近 30 天

### 第二阶段:前端

#### Step 4:导出按钮 + 调用

- **改**(`frontend/src/api/endpoints.ts`):`exportEntity(entity, params)` → 触发下载(blob)
- **改**(各列表页):
  - customers-page:加「导出 CSV」按钮(带时间范围选择)
  - conversations(在 chat-page 或单独):导出对话列表
  - billing-page(依赖 46):导出用量明细
  - logs-page(依赖 48):导出审计日志
- **下载处理**:axios `responseType: blob` → 创建 `<a>` 下载
- **检查**:点击导出 → 浏览器下载 CSV

### 第三阶段:验证

#### Step 5:测试 + 总验证

- **后端**(`tests/test_export.py`):
  - 各实体导出内容正确(headers + rows)
  - 权限:门店级导本租户;super_admin 全平台
  - 大数据量 streaming 不 OOM(模拟 1 万行)
  - 时间范围过滤
- **命令**:`./init.sh` + `npm run build`
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准

1. `GET /exports/{entity}` 端点(customers/conversations/usage/logs),StreamingResponse CSV
2. 权限:门店级(wallet:read/billing:read/logs:read);super_admin 全平台
3. 时间范围 + 过滤参数
4. 大数据量 streaming 不 OOM
5. 前端各列表页「导出 CSV」按钮 + 下载生效
6. `./init.sh` + `npm run build` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| 大数据量 OOM | StreamingResponse + 分批 yield;或限制最大行数(10 万) |
| CSV 中文乱码 | 写入 BOM(`\ufeff`)或用 UTF-8 with BOM |
| 敏感数据导出(用量 cost) | 权限校验;日志记录谁导出了什么 |

### 不做的事(边界)

- 不做 Excel 格式(只 CSV;Excel 用 Excel 打开 CSV)
- 不做导出模板/导入(只导出)
- 不做异步导出任务(同步 streaming;超大数据量后续可接定时任务)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| 各实体 service | `app/services/customer_service.py` 等 |
| SystemLog 查询(依赖48) | `app/repositories/log.py`(任务48建) |
| UsageEvent(依赖43) | `app/models/usage_event.py`(任务43建) |
| 列表页(加导出按钮) | `frontend/src/pages/customers-page.tsx` 等 |
