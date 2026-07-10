"""把 Pydantic v2 校验错误翻译成中文消息。

锚点是错误的 ``type``(Pydantic 稳定契约),不是英文 ``msg``——
英文文案随 pydantic-core 版本/参数变化,匹配文本脆弱。
未命中映射表时透传原始 ``msg``,保证不崩。

设计见 harness/docs/validation-error-i18n-plan.md §3.2。
本模块是纯逻辑,不依赖 FastAPI,便于单测。
"""

# 错误 type → 中文模板。
# {field} 取自 loc 末段(经 _FIELD_LABELS 翻译);
# 其余占位(如 {min_length})取自 err["ctx"]。
_TYPE_TEMPLATES: dict[str, str] = {
    "missing": "{field} 为必填项",
    "string_too_short": "{field} 至少需要 {min_length} 个字符",
    "string_too_long": "{field} 不能超过 {max_length} 个字符",
    "int_parsing": "{field} 必须是整数",
    "bool_parsing": "{field} 格式不正确",
    "float_parsing": "{field} 格式不正确",
    # 自定义 validator 抛的 value_error 透传原始 msg(见兜底逻辑)。
}

# loc 末段字段名 → 中文。对齐 app/schemas/user.py 的字段。
_FIELD_LABELS: dict[str, str] = {
    "username": "用户名",
    "email": "邮箱",
    "password": "密码",
    "display_name": "显示名",
    "real_name": "真实姓名",
    "phone": "手机号",
    "avatar": "头像",
    "role": "角色",
    "status": "状态",
    "organization_ids": "所属组织",
}


class _SafeDict(dict):
    """Mapping that returns "" for any missing key, so .format never raises.

    Used instead of plain kwargs so that a template placeholder absent from
    ``ctx`` (e.g. string_too_short without min_length) degrades to an empty
    slot instead of raising KeyError.
    """

    def __missing__(self, key: str) -> str:
        return ""


def localize_message(err: dict) -> str:
    """翻译单条 Pydantic 校验错误为中文。

    未命中 type 映射表、或 ctx 缺占位时,均透传/退化,绝不抛异常。
    """
    type_ = err.get("type", "")
    ctx = err.get("ctx") or {}
    field = _field_label(err.get("loc") or ())
    tmpl = _TYPE_TEMPLATES.get(type_)
    if tmpl is None:
        return err.get("msg") or "参数校验失败"  # 兜底透传
    # 合并 field 与 ctx;_SafeDict 让缺失占位渲染为空串,永不抛 KeyError。
    fmt_map = _SafeDict(ctx)
    fmt_map["field"] = field
    return tmpl.format_map(fmt_map)


def _field_label(loc: tuple) -> str:
    key = loc[-1] if loc else ""
    return _FIELD_LABELS.get(str(key), str(key) or "该项")
