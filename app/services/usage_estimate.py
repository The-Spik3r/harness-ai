"""Token estimate for a provider that reports no usage (PRD-020 6.7, D8, O7).

Pure: `math` and `json` only, no settings, no `app` import. A characters-per-token
heuristic, no tokenizer (PRD-020 non-goal): the count is ceil(chars / cpt) per
side, so it is an estimate and the audit row says so (`usage_estimated`).
"""

import json
import math
from typing import TYPE_CHECKING, Any, Mapping, Optional, Sequence

if TYPE_CHECKING:  # annotations only: the module imports nothing from `app` at runtime
    from app.models.messages import Message, ToolCallSpec


def _message_chars(message: "Message") -> int:
    """Characters of one message: its content (None counts 0) plus its calls' arguments."""
    total = len(message.content or "")
    for call in message.tool_calls or ():
        total += len(call.arguments)
    return total


def estimate_tokens(
    sent: "Sequence[Message]",
    received: "tuple[str, Sequence[ToolCallSpec]]",
    chars_per_token: float,
    *,
    tools: Optional[Sequence[Mapping[str, Any]]] = None,
) -> int:
    """ceil(sent chars / cpt) + ceil(received chars / cpt).

    `sent` is the messages actually sent upstream; `tools`, when the request
    carried a tools list (an empty list included), counts as its sorted-key JSON
    length. `received` is `(response text, tool calls)`; a call counts by its
    `arguments`. Characters, not bytes, like `len(content)` elsewhere.
    """
    if chars_per_token <= 0:
        raise ValueError(f"chars_per_token must be positive, got {chars_per_token!r}")
    sent_chars = sum(_message_chars(m) for m in sent)
    if tools is not None:
        sent_chars += len(json.dumps(tools, sort_keys=True, ensure_ascii=False))
    content, calls = received
    received_chars = len(content or "") + sum(len(c.arguments) for c in calls)
    return math.ceil(sent_chars / chars_per_token) + math.ceil(received_chars / chars_per_token)
