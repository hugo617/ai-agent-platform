"""Tests for Pydantic 422 validation-error localization.

Covers two layers:
  - pure-function unit tests for ``localize_message`` (no FastAPI)
  - one end-to-end integration test through the registered handler

Cases mirror §7 of harness/docs/validation-error-i18n-plan.md.
"""

import pytest

from app.core.validation_errors import localize_message

# ---------------------------------------------------------------------------
# Pure-function unit tests (§7 cases 1-5)
# ---------------------------------------------------------------------------


def test_string_too_short_uses_field_and_min_length():
    err = {
        "type": "string_too_short",
        "loc": ("body", "username"),
        "msg": "String should have at least 3 characters",
        "ctx": {"min_length": 3},
    }
    assert localize_message(err) == "用户名 至少需要 3 个字符"


def test_missing_field():
    err = {
        "type": "missing",
        "loc": ("body", "password"),
        "msg": "Field required",
    }
    assert localize_message(err) == "密码 为必填项"


def test_unknown_type_falls_back_to_original_msg():
    """An unmapped type must NOT crash — it returns the original English msg."""
    err = {
        "type": "some_new_type",
        "loc": ("body", "whatever"),
        "msg": "something pydantic said",
    }
    assert localize_message(err) == "something pydantic said"


def test_template_hit_but_ctx_missing_placeholder_degrades_gracefully():
    """string_too_short matched but ctx lacks min_length → must not raise."""
    err = {
        "type": "string_too_short",
        "loc": ("body", "username"),
        "msg": "String should have at least 3 characters",
        # NOTE: ctx deliberately absent
    }
    # Should not raise; degrades to a template without the number.
    result = localize_message(err)
    assert "用户名" in result
    assert "至少需要" in result


def test_loc_tail_not_in_field_table_uses_raw_name():
    err = {
        "type": "missing",
        "loc": ("body", "custom_field"),
        "msg": "Field required",
    }
    # Falls back to the raw loc tail when no Chinese label exists.
    assert localize_message(err) == "custom_field 为必填项"


# ---------------------------------------------------------------------------
# End-to-end integration test (§7 case 6) — handler registered in main.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user_short_username_returns_chinese_msg(app_client):
    """POST /users with a too-short username → 422 with a Chinese detail msg.

    Uses username of length 1 against UserCreate.username (min_length=2).
    Asserts the handler replaced msg and the response shape is unchanged.
    """
    resp = await app_client.post(
        "/api/v1/users/",  # trailing slash matches the router path
        json={
            "username": "a",  # 1 char < min_length=2
            "email": "valid@example.com",
            "password": "longenough",
        },
        headers={"Authorization": "Bearer fake"},  # token is mocked in conftest
    )
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body and isinstance(body["detail"], list)
    assert len(body["detail"]) >= 1
    msg = body["detail"][0]["msg"]
    assert "用户名" in msg
    assert "2" in msg  # min_length is 2 in the current schema
