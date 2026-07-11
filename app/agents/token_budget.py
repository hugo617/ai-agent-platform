"""Token budget estimation + sliding-window history truncation.

The chat pipeline used to feed *all* prior messages into the LLM context, which
guarantees a context-window overflow on long conversations. This module
provides a dependency-free approximate token counter and a ``truncate_history``
helper that keeps the conversation within a fixed budget while always
preserving the most recent turns.

Why approximate (not ``tiktoken``)?
  - DeepSeek has no official tokenizer, so ``tiktoken`` would only be precise
    for OpenAI models.
  - The goal here is *preventing crashes*, not exact accounting — a
    deliberately conservative estimate (over-count) truncates early, which is
    the safe direction.
"""

from langchain_core.messages import BaseMessage

# DeepSeek-chat has a 32K context window. We reserve room for the system
# prompt, the new user message, and the assistant reply, so the budget for
# *history* is well below the raw window.
CONTEXT_TOKEN_BUDGET = 24000
# Tokens set aside for the upcoming assistant reply. Keeps the model from
# running out of output space after we've packed history to the limit.
RESERVE_FOR_REPLY = 4096
# Even when history far exceeds the budget, never drop below this many
# messages (≈ 3 user/assistant turns) so the agent keeps conversational
# continuity. This is a hard floor; truncation stops here regardless of budget.
MIN_HISTORY_MESSAGES = 6


def estimate_tokens(text: str) -> int:
    """Approximate token count for a piece of text.

    Heuristic:
      - CJK characters (Chinese/Japanese/Korean) ≈ 1 token each.
      - Other (mostly ASCII/English) ≈ 1 token per 4 characters.

    The sum is rounded up (+1) to bias toward over-counting, which truncates
    earlier — safer than truncating too late. An empty string returns 0.
    """
    if not text:
        return 0
    cjk = 0
    other = 0
    for ch in text:
        # CJK Unified Ideographs + common CJK extension ranges.
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF          # CJK Unified Ideographs
            or 0x3400 <= code <= 0x4DBF        # CJK Extension A
            or 0x3040 <= code <= 0x30FF        # Hiragana + Katakana (Japanese)
            or 0xAC00 <= code <= 0xD7AF        # Hangul Syllables (Korean)
            or 0xF900 <= code <= 0xFAFF        # CJK Compatibility Ideographs
        ):
            cjk += 1
        else:
            other += 1
    # 4 ASCII chars ≈ 1 token (OpenAI's rule of thumb for English).
    approx = cjk + (other // 4)
    return approx + 1  # +1 to bias high (conservative truncation).


def estimate_messages_tokens(messages: list[BaseMessage]) -> int:
    """Approximate token count for a list of LangChain messages.

    Each message carries a small fixed overhead (role + formatting) — OpenAI
    documents ~4 tokens per message, which we add here.
    """
    total = 0
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        total += estimate_tokens(content) + 4  # +4 per-message overhead
    return total


def truncate_history(
    messages: list[BaseMessage],
    budget: int = CONTEXT_TOKEN_BUDGET,
    reserve_for_reply: int = RESERVE_FOR_REPLY,
    min_messages: int = MIN_HISTORY_MESSAGES,
) -> list[BaseMessage]:
    """Drop the oldest messages until the history fits the token budget.

    The budget covers the history alone (the system prompt is injected
    separately by the agent, and the new user message is appended by the
    caller). ``reserve_for_reply`` is subtracted from ``budget`` so the model
    has room to answer.

    Truncation removes the *oldest* entries first (sliding window). It stops
    once the remaining messages fit, or once ``min_messages`` is reached —
    never dropping below the floor, even if still over budget. This guarantees
    the agent always has recent context to continue the conversation.
    """
    if not messages:
        return []

    effective_budget = max(budget - reserve_for_reply, 0)

    # Fast path: already within budget.
    if estimate_messages_tokens(messages) <= effective_budget:
        return list(messages)

    # Drop oldest messages until we fit or hit the minimum floor.
    # We keep the tail (most recent); ``messages`` is ordered oldest→newest.
    kept = list(messages)
    while len(kept) > min_messages and estimate_messages_tokens(kept) > effective_budget:
        kept.pop(0)

    return kept
