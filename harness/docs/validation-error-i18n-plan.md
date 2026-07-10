# 计划:Pydantic 422 校验错误中文化

> 对应 feature_list.json 的 `id`: `validation-error-i18n`
> 状态: not_started
> 参考: 本计划前身是 docs/auth-history-scd2-plan.md 同级的实施草案,已纳入 harness 工程管理

## 起因

在 `app/schemas/user.py` 把 `UserCreate.username` 的 `min_length` 改为 3 后,
前端输入 2 个字符返回 `String should have at least 3 characters`。该英文文案由
Pydantic v2(`pydantic-core`)内置生成,不在项目代码中。本计划将其统一中文化。

- 技术栈基线:`fastapi==0.115.6` / `pydantic==2.10.4`

## 1. 目标与范围

**目标**：把 Pydantic v2 校验失败时的英文消息（如 `String should have at least 3 characters`）
统一转成中文友好提示（如 `用户名 至少需要 3 个字符`），全局生效、不随 schema 增长而膨胀。

**范围（in scope）**

- 后端注册 `RequestValidationError` 处理器，翻译 422 响应中的 `msg`。
- 维护一张「错误 `type` → 中文模板」映射表 + 一张「字段名 → 中文」映射表。
- 新增纯函数 + 单元测试 + 一条端到端集成测试。

**非目标（out of scope，保持现状）**

- 不改前端 `apiErrorMessage()` —— 见 §2 决策。
- 不做多错误聚合（前端目前只取 `detail[0]`，本次不改）。
- 不做完整 i18n 框架（无 `Accept-Language` 切换，当前只需中文）。

## 2. 关键决策（及理由）

| 决策 | 选择 | 理由 |
|---|---|---|
| 422 响应形状 | 保持 FastAPI 原生 `{detail:[{loc,msg,type,...}]}`，只替换 `msg` | 前端 `client.ts` 已按此形状解析，**零改动**；不破坏 OpenAPI / Apifox 契约 |
| 翻译锚点 | 错误 `type`（如 `string_too_short`），不匹配英文文本 | Pydantic v2 的 `type` 是稳定契约；英文 `msg` 随版本/参数变化，匹配文本脆弱 |
| 未命中处理 | 兜底透传原始 `msg`，不崩 | 避免漏翻译某条 `type` 导致前端报错 |
| 代码组织 | 纯函数 + 映射表抽到独立模块，handler 保持薄 | 高内聚/小文件，纯函数易单测 |

**依赖确认**：`requirements.txt` 已锁定 `fastapi==0.115.6` / `pydantic==2.10.4` —— 422 结构稳定，
`ctx` 带参数（`min_length`/`max_length` 等）可填模板。

## 3. 技术设计

### 3.1 数据流

```
Pydantic 校验失败 → FastAPI 抛 RequestValidationError
   │
   ▼
新 handler(app/main.py) → 对每个 err 调用 localize_message(err)
   │  localize_message(app/core/validation_errors.py)：
   │    field = 字段中文(loc)        ← 字段映射表
   │    tmpl  = type 模板(err.type)  ← type 映射表
   │    msg   = tmpl.format(field=..., **ctx)
   ▼
JSONResponse(422, {"detail": [{...原err, "msg": 中文msg}]})
   │  形状不变，仅 msg 被替换
   ▼
前端 client.ts → data.detail[0].msg  ← 现在是中文，无需改
```

### 3.2 核心代码骨架（计划，非最终实现）

**新增 `app/core/validation_errors.py`**（纯逻辑，无 FastAPI 依赖）：

```python
"""把 Pydantic v2 校验错误翻译成中文消息。

锚点是错误的 ``type``（Pydantic 稳定契约），不是英文 ``msg``。
未命中映射表时透传原始 msg，保证不崩。
"""

# 错误 type → 中文模板。{field} 取自 loc；其余占位取自 err["ctx"]。
_TYPE_TEMPLATES: dict[str, str] = {
    "missing":          "{field} 为必填项",
    "string_too_short": "{field} 至少需要 {min_length} 个字符",
    "string_too_long":  "{field} 不能超过 {max_length} 个字符",
    "int_parsing":      "{field} 必须是整数",
    # ……（实施时补全，见 §6）
}

# loc 末段字段名 → 中文。
_FIELD_LABELS: dict[str, str] = {
    "username":     "用户名",
    "email":        "邮箱",
    "password":     "密码",
    "display_name": "显示名",
    "real_name":    "真实姓名",
    "phone":        "手机号",
    "role":         "角色",
    # ……（实施时对齐 app/schemas/user.py 的字段）
}


def localize_message(err: dict) -> str:
    """翻译单条 Pydantic 校验错误为中文。"""
    type_ = err.get("type", "")
    ctx = err.get("ctx") or {}
    field = _field_label(err.get("loc") or ())
    tmpl = _TYPE_TEMPLATES.get(type_)
    if tmpl is None:
        return err.get("msg") or "参数校验失败"   # 兜底透传
    try:
        return tmpl.format(field=field, **ctx)
    except (KeyError, IndexError):
        return tmpl.format(field=field)            # ctx 占位缺失时退化


def _field_label(loc: tuple) -> str:
    key = loc[-1] if loc else ""
    return _FIELD_LABELS.get(str(key), str(key) or "该项")
```

**修改 `app/main.py`**（在现有 `PermissionError` handler 旁，约 137 行处）：

```python
from fastapi.exceptions import RequestValidationError  # 加到 import 区
from app.core.validation_errors import localize_message

@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    localized = [{**e, "msg": localize_message(e)} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": localized})
```

## 4. 文件改动清单

| 操作 | 文件 | 说明 |
|---|---|---|
| 新增 | `app/core/validation_errors.py` | 映射表 + `localize_message()` 纯函数（约 40 行）|
| 修改 | `app/main.py` | +2 行 import、+5 行 handler，紧邻 `PermissionError` handler |
| 新增 | `tests/test_validation_errors.py` | 纯函数单测 + 端到端集成测试 |

**零改动**：`frontend/src/api/client.ts`、所有 `app/schemas/*.py`、`app/api/v1/users.py`。

## 5. 分步实施计划（TDD，每步带验证）

> 顺序遵循 RED → GREEN → REFACTOR；每步有可独立运行的验证命令。

**步骤 0 — 基线确认**

- 跑现有用户相关测试，确认起点是绿的。
- 验证：`pytest tests/test_users_crud.py tests/test_users_api.py -q` → 全绿。

**步骤 1 — 写单测（RED）**

- 新建 `tests/test_validation_errors.py`，对 `localize_message` 写用例（见 §7）。
- 验证：`pytest tests/test_validation_errors.py -q` → **失败**（模块还不存在）。

**步骤 2 — 实现纯函数（GREEN）**

- 新建 `app/core/validation_errors.py`（§3.2），填充映射表。
- 验证：`pytest tests/test_validation_errors.py -q` → **全绿**。

**步骤 3 — 注册 handler + 集成测试**

- 改 `app/main.py` 加 handler；在 `tests/test_validation_errors.py` 加端到端用例：
  `POST /users` 带 `username="ab"`，断言 `status==422` 且 `detail[0].msg` 含「用户名」与「3」。
- 验证：`pytest tests/test_validation_errors.py -q` → 全绿（含集成用例）。

**步骤 4 — 回归**

- 全量测试，确认没破坏现有 422 相关用例（若现有用例断言过英文 `msg`，需相应更新为中文 —— 实施时检查）。
- 验证：`pytest -q` → 全绿。

**步骤 5 — 手测端到端**

- 启动后端，`curl` 创建短用户名，确认返回中文。
- 验证：`curl -s -XPOST localhost:8000/api/v1/users -H 'Authorization: ...' -d '{"username":"ab",...}'`
  → `detail[0].msg` 为中文。

## 6. 映射表初稿（实施时按实际触发的 type 补全）

| `type` | 中文模板 | `ctx` 占位 |
|---|---|---|
| `missing` | `{field} 为必填项` | — |
| `string_too_short` | `{field} 至少需要 {min_length} 个字符` | `min_length` |
| `string_too_long` | `{field} 不能超过 {max_length} 个字符` | `max_length` |
| `int_parsing` | `{field} 必须是整数` | — |
| `bool_parsing` / `float_parsing` | `{field} 格式不正确` | — |
| `value_error` | 透传原始 msg | （自定义 validator 抛的）|
| 其余未命中 | 透传 | — |

> 邮箱格式校验（`EmailStr`）在 Pydantic v2 里通常落到 `value_error`，会透传英文 ——
> 如需中文化，单独给 `email` 字段加 `@field_validator` 抛「邮箱格式不正确」（方案 3 作为这里的补丁）。
> 本计划不强制，留作可选增强。

## 7. 测试用例清单

**纯函数单测**（`localize_message`）：

1. `string_too_short` + `ctx={min_length:3}` + `loc=("body","username")` → `"用户名 至少需要 3 个字符"`
2. `missing` + `loc=("body","password")` → `"密码 为必填项"`
3. 未知 `type="some_new_type"` → 返回原始 `msg`（兜底）
4. `type` 命中但 `ctx` 缺占位 → 不抛异常，退化输出
5. `loc` 末段不在字段表 → 用原始字段名

**集成测试**（复用 `conftest.py` 的 `client` fixture，参照 `tests/test_users_crud.py` 写法）：

6. `POST /users` body `username="ab"` → 422，`detail[0].msg` 含「用户名」「3」

## 8. 风险与回滚

| 风险 | 缓解 |
|---|---|
| Pydantic 升级改 `type` 名称 | 兜底透传不崩；`type` 是官方稳定契约 |
| 漏翻译某 `type` 显示英文 | 兜底 = 透传英文（不是报错）；后续按需补表 |
| 破坏前端解析 | 422 形状不变，前端零改 |
| 现有测试断言过英文 msg | 步骤 4 检查并更新（属预期变更）|

**回滚**：删除 `main.py` 里的 handler + import，删 `validation_errors.py` 与测试文件 ——
零副作用，立即恢复英文。
