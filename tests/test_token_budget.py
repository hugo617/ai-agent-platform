"""Unit tests for the token-budget pure functions.

These mirror the ``test_validation_errors.py`` style: no DB, no async, no
fixtures — just the heuristic math and the truncation policy.
"""

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.token_budget import (
    CONTEXT_TOKEN_BUDGET,
    MIN_HISTORY_MESSAGES,
    RESERVE_FOR_REPLY,
    estimate_messages_tokens,
    estimate_tokens,
    truncate_history,
)

# --------------------------------------------------------------- estimate_tokens


def test_estimate_tokens_empty_string_is_zero():
    assert estimate_tokens("") == 0


def test_estimate_tokens_pure_chinese():
    # 4 CJK chars → 4 tokens + 1 (conservative bias) = 5.
    assert estimate_tokens("你好世界") == 5


def test_estimate_tokens_pure_english():
    # "hello world" = 11 ASCII chars → 11 // 4 = 2 tokens + 1 bias = 3.
    assert estimate_tokens("hello world") == 3


def test_estimate_tokens_mixed_is_conservative_high():
    # Mixed content should count both CJK and ASCII portions. The exact number
    # matters less than the guarantee that it's ≥ the CJK-only count.
    text = "你好 hello"  # 2 CJK + 6 ascii (incl. space) → 2 + 1 = 3 + 1 = 4
    assert estimate_tokens(text) == 4
    # Conservative: never under-counts the CJK portion.
    assert estimate_tokens(text) >= 2


# ------------------------------------------------------ estimate_messages_tokens


def test_estimate_messages_tokens_sums_with_overhead():
    msgs = [
        HumanMessage(content="你好"),    # 2 CJK → 3 + 4 overhead = 7
        AIMessage(content="你好世界"),  # 4 CJK → 5 + 4 overhead = 9
    ]
    # 7 + 9 = 16
    assert estimate_messages_tokens(msgs) == 16


def test_estimate_messages_tokens_empty_list():
    assert estimate_messages_tokens([]) == 0


# ----------------------------------------------------------- truncate_history


def _make_history(n: int, content: str = "hello") -> list:
    """Build ``n`` alternating user/assistant messages."""
    msgs = []
    for i in range(n):
        if i % 2 == 0:
            msgs.append(HumanMessage(content=f"{content} {i}"))
        else:
            msgs.append(AIMessage(content=f"{content} {i}"))
    return msgs


def test_truncate_history_no_truncation_when_within_budget():
    # A short history well within the default budget is returned as-is.
    history = _make_history(4)
    result = truncate_history(history)
    assert result == history
    assert len(result) == 4


def test_truncate_history_drops_oldest_first():
    # Construct a history whose total tokens far exceed a tiny budget, with
    # enough messages to be above the minimum floor. The oldest messages must
    # be the ones dropped.
    history = _make_history(20, content="你好世界测试" * 10)  # very heavy
    # Use a tiny budget so truncation is forced, but keep min_messages default.
    result = truncate_history(history, budget=50, reserve_for_reply=0, min_messages=6)
    assert len(result) <= len(history)
    assert len(result) >= MIN_HISTORY_MESSAGES
    # The most recent message (index 19) must survive.
    assert result[-1].content == "你好世界测试" * 10 + " 19"
    # An early message (index 0) should have been dropped.
    assert all(m.content != "你好世界测试" * 10 + " 0" for m in result)


def test_truncate_history_respects_minimum_floor():
    # Even with an absurdly small budget, we never drop below MIN_HISTORY_MESSAGES.
    history = _make_history(30, content="x" * 1000)
    result = truncate_history(history, budget=1, reserve_for_reply=0, min_messages=6)
    assert len(result) == MIN_HISTORY_MESSAGES
    # And the surviving messages are the most recent ones.
    assert result[-1].content == "x" * 1000 + " 29"


def test_truncate_history_empty_list():
    assert truncate_history([]) == []


def test_truncate_history_preserves_recent_context():
    # With a moderate budget that forces some truncation, the tail (recent
    # turns) is kept so the agent has continuity.
    history = _make_history(15, content="你好世界" * 20)
    result = truncate_history(history, budget=100, reserve_for_reply=0, min_messages=6)
    # The last few messages survive.
    last_contents = [m.content for m in result[-3:]]
    expected_tail = [
        "你好世界" * 20 + f" {i}" for i in (12, 13, 14)
    ]
    assert last_contents == expected_tail


def test_constants_are_sane():
    # Budget must leave room for the reply reserve; minimum floor must be even
    # (user/assistant pairs) and small relative to budget.
    assert CONTEXT_TOKEN_BUDGET > RESERVE_FOR_REPLY
    assert MIN_HISTORY_MESSAGES >= 4
    assert MIN_HISTORY_MESSAGES % 2 == 0
