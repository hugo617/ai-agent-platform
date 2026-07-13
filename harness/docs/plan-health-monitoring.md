# 计划:健康检查/监控(/ready + Prometheus metrics)

> 对应 feature_list.json 的 `id`: `health-monitoring`
> 状态: not_started
> 优先级: 53
> 前置: 无
> 总纲: [`plan-mvp-completion-overview.md`](plan-mvp-completion-overview.md)

---

## 背景:/health 不碰 DB,无 /ready 无 metrics

### 现状

- `app/main.py` L78-80:`GET /health` 返回 `{"status": "ok", "app", "env"}`——只存活探针,不检查 DB
- 无 `/ready`(就绪探针)
- 无 `/metrics`(Prometheus 指标)
- 生产部署缺运维监控能力

### 目标

1. `/ready`:检查 DB 连通性 + 关键依赖,失败 503
2. `/metrics`:Prometheus 格式指标
3. 增强 `/health`:加 DB 检查

---

## 前置条件

- 无。

---

## 实施步骤

### 第一阶段:/ready 就绪探针

#### Step 1:GET /ready 端点

- **改什么**(`app/main.py` 加端点):
  ```python
  @app.get("/ready")
  async def readiness():
      checks = {}
      # DB 连通性
      try:
          async with db_session() as s:
              await s.execute(text("SELECT 1"))
          checks["db"] = "ok"
      except Exception:
          checks["db"] = "fail"
      http_status = 200 if all(v == "ok" for v in checks.values()) else 503
      return JSONResponse({"status": "ready" if http_status == 200 else "not_ready", "checks": checks}, status_code=http_status)
  ```
- **检查**:DB 正常 → 200;DB 断开 → 503

#### Step 2:增强 /health

- **改什么**(`app/main.py` /health 加轻量 DB 检查):
  - 现状只返回 ok;加可选 DB ping(超时 1s,失败不阻断只标 db: fail)
  - 保持快速(liveness 要轻)
- **检查**:health 仍快速返回;附 db 状态

### 第二阶段:/metrics Prometheus

#### Step 3:集成 prometheus_client

- **加依赖**(`requirements.txt`):`prometheus-client`
- **新建**(`app/core/metrics.py`):
  ```python
  from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

  REQUESTS = Counter("http_requests_total", "Total requests", ["method", "endpoint", "status"])
  LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["endpoint"])
  DB_POOL = Gauge("db_pool_size", "DB pool size")  # 可选
  ```
- **中间件**(`app/main.py` 加 Middleware):记录每个请求的 method/endpoint/status/latency
  ```python
  @app.middleware("http")
  async def metrics_middleware(request, call_next):
      start = time.time()
      response = await call_next(request)
      REQUESTS.labels(request.method, request.url.path, response.status_code).inc()
      LATENCY.labels(request.url.path).observe(time.time() - start)
      return response
  ```
- **端点**:
  ```python
  @app.get("/metrics")
  async def metrics():
      return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
  ```
- **排除**:`/metrics`、`/health`、`/ready` 不计入(避免自循环)
- **检查**:GET /metrics 返回 Prometheus 格式文本

### 第三阶段:验证

#### Step 4:测试 + 总验证

- **后端**(`tests/test_health.py`):
  - /ready:DB 正常 → 200;模拟断开 → 503(可 mock)
  - /metrics:返回 Prometheus 格式 + 含 http_requests_total
  - /health:返回 db 状态
- **命令**:`./init.sh`
- **全过 → 填 evidence + status 改 passing**

---

## 验收标准

1. `GET /ready`:检查 DB 连通(SELECT 1),失败 503
2. `GET /metrics`:Prometheus 格式(http_requests_total / request_duration_seconds,按 endpoint 标签)
3. `/health` 增强:附 DB 状态
4. 中间件记录请求指标;排除 /metrics/health/ready 自循环
5. `./init.sh` 全绿

---

## 风险 / 注意事项

| 风险 | 缓解 |
|------|------|
| metrics 中间件性能开销 | observe 是 O(1);高 QPS 可采样 |
| /ready 检查超时阻塞 | DB ping 加超时(1s);失败快速返回 503 |
| metrics 端点暴露敏感信息 | 只暴露计数/延迟,不暴露业务数据;生产可加 IP 白名单 |

### 不做的事(边界)

- 不做分布式追踪(OpenTelemetry/Jaeger,后续)
- 不做日志聚合(ELK/Loki,运维层)
- 不做自定义业务 metrics(只基础 HTTP 指标)

---

## 参考文件

| 参照 | 路径 |
|------|------|
| /health(待增强) | `app/main.py` L78-80 |
| 中间件注册 | `app/main.py` |
| DB session | `app/core/database.py` |
