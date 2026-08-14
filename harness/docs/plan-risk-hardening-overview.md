# 计划:业务功能风险 Top5 消化 · 生产加固系列总纲

> 这是**生产加固系列的总纲文档**(登记性质,进行中)。
> 来源:第 10 次巡检(2026-08-14)「业务功能质量:风险 Top 5」新板块,完整报告
> `~/.cache/ai-agent-platform-architecture-reviews/2026-08-14.html`,巡检日志见
> [codebase-health-log.md](./codebase-health-log.md) 第 10 次行。
> EP1 于 2026-08-14 完成:**8 项决策全部经用户逐项拍板**(AskUserQuestion 2 轮),无「未获回复按推荐采纳」项。
> 进行中不写进度段(three-tier §5 规则 ④);进度看 `progress.md` 顶部摘要;收官时在文末写「系列状态」段。

---

## 背景

第 10 次巡检首次增设「业务功能质量」轴。结论:功能完成度本身很高(89 feature 全 passing,链路真实现为主),但**正确性与安全侧存在 5 个生产级风险**——3🔴(无任何限流+7 天 TTL / 预约 TOCTOU 竞态 / 计费 best-effort 无对账+SSE 无钱包放行)+ 2🟡(super_admin 跨租户写零审计 / dev 后门押注 APP_ENV)。

本系列把这 5 条风险**全部**消化,作为「生产加固」一步到位。系列内的修复保持窄修复形态,不顺带做架构重构(见「系列边界」)。

## EP1 决策记录(2026-08-14,用户逐项拍板)

| # | 决策点 | 拍板结果 |
|---|---|---|
| D1 | 系列范围 | **5 条风险全进**(🟡 两条不留口子——安全加固做一半说不清收官) |
| D2 | feature 粒度 | 一风险一 feature,**R3 拆 2 条**(钱包门 / 对账)→ 共 **6 条** |
| D3 | 执行顺序 | R1 → R2 → R3a → R3b → R4 → R5(priority 96→91,🔴 优先) |
| D4 | R1 防爆破形态 | **slowapi 全局 API 限流 + 登录失败锁定**(用户选了比最小方案更广的防护面,接受新依赖与全局配置面)+ token TTL 从 7 天降小时级 |
| D5 | R3 拆分界线 | **先钱包门(止血)后对账(兜底)**;两 feature 都**不动 TurnAccountant**(架构候选 ② 独立立项时消化) |
| D6 | R4 审计面 | 补**三处最高危**:充值 / 定价覆盖 / 知识下发与撤回(不做 super_admin 全量埋点) |
| D7 | R5 处置力度 | **三件套全修**:dev 后门独立开关默认关 + key 启动期 fail-fast + 低额预警 scheduler 显式化 |
| D8 | 系列收官标准 | 6 条全 passing **+ 第 11 次巡检复验 Top5 清零**(独立复验,用户指定) |

> 各 feature 的**阈值类取舍**(锁定次数/时长、TTL 具体值、限流配额、对账周期等)在 EP2 各自 grill 时**必须问用户拍板**,不得按推荐默认采纳——本系列 EP1 的既定纪律。

## 交付清单(按 priority 96→91)

> 号段说明:series 占 **96-91**(高于 knowledge 系列 90)。原因:78-85 已被归档区 passing feature 占用(member-service-direct-tests 85 / user-service-lookup-seam 84 / design-system 三件 83-81 / queries-endpoints 80 / customers 79 / devices 78),「priority 大 = 新」单调递增约定下唯一干净的连续号段是 91+。

### 1. 全局限流 + 登录防爆破 `rate-limit-login-lockout`(priority 96,认证-安全)— 风险 R1 🔴

- **现状**:`POST /auth/login` 可无限尝试,无失败锁定;全库无任何限流(slowapi/limiter 在 requirements 与 app 内 grep 零命中);`access_token_ttl_minutes = 10080`(7 天)。弱密码租户一旦被爆破,横向可用期很长。
- **目标(D4 已拍板)**:引入 slowapi 全局 API 限流框架(按用户/IP 可配,登录锁定是其中一例)+ 登录失败计数锁定 + TTL 降小时级。
- **EP2 待拍板(用户)**:登录失败几次触发锁定、锁多久;TTL 降到几小时;slowapi 默认配额(普通端点 vs 认证端点分级);限流存储后端(本项目无 Redis,内存 vs 引入 Redis 需定);429 响应体格式与前端处理。
- **证据锚点**:`app/services/auth_service.py` 登录路径 / `app/core/config.py:48`。

### 2. 预约时段 TOCTOU 竞态 DB 兜底 `booking-toctou-guard`(priority 95,预约-后端)— 风险 R2 🔴

- **现状**:冲突检测是纯应用层 check-then-insert(`find_overlap` 左闭右开),模型层刻意无唯一约束、无事务内锁——并发双订同一设备同时段可双双落库。模型注释自认 "deliberately no partial unique index"。
- **目标**:加 DB 级兜底,让并发双订在数据库层被结构性拒绝(部分唯一索引或事务内锁,**形态 EP2 烤定**)。
- **EP2 待拍板(用户)**:兜底形态(部分唯一索引 vs advisory lock);唯一约束的排除态语义——「什么状态算占坑」(cancelled 之外,no_show/completed 是否也排除,直接影响业务规则);存量脏数据(历史双订)预检与处置。
- **证据锚点**:`app/models/booking.py`(:42 附近注释)/ `app/repositories/booking.py` find_overlap / `app/services/booking_service.py` 创建路径。

### 3. SSE 钱包门口径统一 `chat-stream-wallet-gate`(priority 94,计费-后端)— 风险 R3 前半 🔴

- **现状**:`/chat/stream` 对无钱包租户直接放行,composite 路径则严格 402——**同一钱包契约两套口径**,SSE 路径是持续性资损口。
- **目标(D5 已拍板)**:SSE 路径补与 composite 同口径的钱包预检(402),止血资损。不动 TurnAccountant、不改计费编排结构。
- **EP2 待拍板(用户)**:预检时点(建立连接前 vs 首 token 前);余额判断口径是否与 composite 逐字对齐(含零钱包 vs 负余额的边界);402 错误体是否复用 composite 现有格式。
- **证据锚点**:`app/api/v1/chat.py` SSE 路径钱包判断缺失处 vs composite 路径 402 门。

### 4. 计费对账闭环 `billing-reconciliation-job`(priority 93,计费-后端)— 风险 R3 后半 🔴

- **现状**:UsageEvent 写入与扣费是两个独立事务,charge 失败仅 `logger.exception` + rollback(余额可少扣),代码注释宣称的 "reconciled from usage_events" 对账 job **并不存在**。
- **目标(D5 已拍板)**:对账 job 挂现有 APScheduler 框架(`app/core/scheduler.py`,notification-scheduler pri 54 已建):usage_events 聚合 vs wallet_transactions 差额核对,产出日报 + 告警,让「少扣费」从静默变可见。
- **EP2 待拍板(用户)**:对账周期(小时级 vs 日报);差额容忍度(精确为 0 vs 容忍 rounding);告警通道(现有 in-app 通知系统?);**是否自动补扣**(建议只报不补,补扣需人工决策——资损金额与租户关系需人判断);对账结果落表(新表 vs 复用 SystemLog,按「按需加表」铁律评估)。
- **证据锚点**:`app/api/v1/chat.py` charge 失败处理 / `app/services/billing_service.py` 事务边界。

### 5. super_admin 三处最高危写操作补审计 `super-admin-write-audit`(priority 92,审计-后端)— 风险 R4 🟡

- **现状**:充值、定价覆盖、知识下发/撤回这些**最高权操作**只留业务列(operator_id/distributed_by),不写 SystemLog;审计基础设施(LoggingService.record + audit-log-ui pri 48)只覆盖 login/user CRUD/RBAC/booking_config。事后追责链断裂。
- **目标(D6 已拍板)**:三处补 `LoggingService.record` 调用写 SystemLog(充值 / 定价覆盖 / 知识下发与撤回),复用现有审计基础设施与前端审计页。
- **EP2 待拍板(用户)**:审计事件命名与分级(action 值域);detail 字段粒度(金额/定价快照/目标租户 id 记到什么程度);知识下发与撤回是两个 action 还是一个 action 两种 outcome。
- **证据锚点**:`app/api/v1/billing.py` 充值路径 / LoggingService.record 调用面 grep。

### 6. dev 后门与配置静默降级三件套 `config-startup-guard`(priority 91,配置-治理)— 风险 R5 🟡

- **现状**:① `APP_ENV=development` 下 `/dev/token` 可为任意用户铸 super_admin token(押注部署把环境变量设对);② LLM/embedding key 默认 "sk-replace-me" 落 env 兜底,要到运行时调 LLM 才失败;③ 低额预警 `scheduler_enabled` 默认 False,忘开则静默不跑。
- **目标(D7 已拍板,三件套全修)**:① `/dev/token` 改显式独立开关,**默认关**,与 APP_ENV 解耦;② key 启动期 fail-fast 校验(不再等到运行时);③ 低额预警 scheduler 显式化(部署清单 + 启动日志可见,忘开有声音)。
- **EP2 待拍板(用户)**:开关命名与默认值语义;fail-fast 的环境范围(仅非 development?还是显式白名单);scheduler 显式化的具体形态(启动 WARN 日志行 vs 配置模板注释 vs 两者)。
- **证据锚点**:`app/main.py` /dev/token 路由(:239 附近)/ `app/core/config.py`(:48 TTL、:62/:85/:118 三处默认值)。

## 优先级与依赖全景

```
96 R1 rate-limit-login-lockout(认证-安全)─┐
95 R2 booking-toctou-guard(预约)        ─┤
94 R3a chat-stream-wallet-gate(计费)    ─┼─ 六条不同域,相互独立(depends_on 全空),
93 R3b billing-reconciliation-job(计费) ─┤   WIP=1 下按 priority 串行执行。
92 R4 super-admin-write-audit(审计)     ─┤   R3a→R3b 有「先止血后兜底」的做事顺序,
91 R5 config-startup-guard(配置治理)    ─┘   但无硬依赖,可按需要调序。
                                        收官 = 全 passing + 第 11 次巡检复验 Top5 清零
```

## 系列边界(不做的事)

- **TurnAccountant 计费编排下沉**(第 10 次巡检架构候选 ②,第 6/9/10 次三度复现):不入本系列。R3a/R3b 只做窄修复;重构独立立项时消化,届时统一口径的收益归重构。
- **Quick wins #1(CI frontend job 加 `npm run test`)**:一行改动收益大,但超出 Top5 范围——归第 10 次巡检候选 ⑤(前端类型契约防线)或独立小改动处理,不挤进本系列。
- **网关层限流 / WAF / CDN 防护**:部署侧能力,不作为本系列交付(R1 在应用层自足,用户已拍板)。
- **super_admin 跨租户写全量审计**:本轮只做三处最高危(D6);若第 11 次巡检复验认为不够再扩。
- **支付网关 / OSS 存储 / 邮件短信等外围桩**:巡检已认定非本风险板块范围。

## 收官标准(D8 已拍板)

1. 6 条 feature 全部 `passing`,且**每条风险的修复点都有回归测试常驻 CI**(如:并发双订被 DB 兜底拦住的测试、对账 job 能检出差额的测试、登录锁定触发的测试);
2. **第 11 次巡检业务功能轴复验:Top5 清零**(不复发、无新引入);
3. 满足 1+2 后,在本文末尾写「系列状态:✅ 全部完成」段(three-tier §5 规则 ④)。

## 规划粒度说明

镜像 [plan-mvp-completion-overview.md](./plan-mvp-completion-overview.md) 范式:本总纲登记全部 6 条(现状/目标/EP2 待拍板);feature_list.json 的 `plan` 字段暂指本总纲,**各 feature 详细 plan 在 EP2 拆切片时再写**(届时 `plan` 字段改为指向 `plan-<id>.md`)。

## 参考文件

| 风险 | 证据锚点(第 10 次巡检报告口径) |
|---|---|
| R1 无限流+7 天 TTL | `app/services/auth_service.py` 登录路径 / `app/core/config.py:48` |
| R2 booking TOCTOU | `app/models/booking.py:42` / `app/repositories/booking.py:81-113` / `app/services/booking_service.py:521` |
| R3 计费无对账+SSE 放行 | `app/api/v1/chat.py:104,130-139,258-269 vs 467-476` / `app/services/billing_service.py:26-33` |
| R4 super_admin 零审计 | `app/api/v1/billing.py:171-193` / LoggingService.record 调用面 |
| R5 dev 后门押注配置 | `app/main.py:239-263` / `app/core/config.py:62,85,118` |
| 完整报告 | `~/.cache/ai-agent-platform-architecture-reviews/2026-08-14.html`(业务功能风险 Top5 板块 + Quick wins) |
