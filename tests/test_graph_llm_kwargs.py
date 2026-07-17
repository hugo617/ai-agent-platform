"""Unit tests for ``app.agents.graph._build_llm_kwargs``.

This pure function translates resolved inference params (model, temperature,
...) into the kwargs dict passed to ``ChatOpenAI``. We test it in isolation
(no DB / no HTTP) because the thinking-mode toggle is a provider-protocol
concern that lives entirely inside this function — it should not require a
full SSE round-trip to verify.
"""

from app.agents.graph import _build_llm_kwargs


def _base() -> dict:
    return dict(
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        temperature=0.7,
    )


def test_kwargs_always_include_core_fields():
    """Model/credentials/streaming/temperature are always present."""
    kw = _build_llm_kwargs(**_base())
    assert kw["model"] == "deepseek-v4-flash"
    assert kw["api_key"] == "sk-test"
    assert kw["base_url"] == "https://api.deepseek.com"
    assert kw["streaming"] is True
    assert kw["stream_usage"] is True
    assert kw["temperature"] == 0.7


def test_optional_params_only_when_set():
    """max_tokens/top_p are omitted when None (let provider default apply)."""
    kw = _build_llm_kwargs(**_base())
    assert "max_tokens" not in kw
    assert "top_p" not in kw

    kw = _build_llm_kwargs(**_base(), max_tokens=512, top_p=0.9)
    assert kw["max_tokens"] == 512
    assert kw["top_p"] == 0.9


def test_thinking_disabled_injects_extra_body(monkeypatch):
    """When LLM_THINKING_ENABLED=false, DeepSeek's non-thinking param is sent."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "llm_thinking_enabled", False)
    kw = _build_llm_kwargs(**_base())
    assert kw["extra_body"] == {"thinking": {"type": "disabled"}}


def test_thinking_enabled_omits_extra_body(monkeypatch):
    """Default (thinking on) must NOT send extra_body — let provider decide."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "llm_thinking_enabled", True)
    kw = _build_llm_kwargs(**_base())
    assert "extra_body" not in kw
