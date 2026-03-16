from typing import Any, NotRequired, TypedDict


class LiveAgentState(TypedDict):
    trace_id: str
    session_id: str
    user_id: str
    user_input: str
    live_stage: str
    current_product_id: str | None
    short_term_memory: list[dict[str, str]]
    intent: NotRequired[str]
    intent_confidence: NotRequired[float]
    route_reason: NotRequired[str]
    route_fallback_reason: NotRequired[str | None]
    route_low_confidence: NotRequired[bool]
    agent_output: NotRequired[str]
    references: NotRequired[list[str]]
    retrieved_docs: NotRequired[list[dict[str, Any]]]
    guardrail_pass: NotRequired[bool]
    guardrail_reason: NotRequired[str | None]
    final_output: NotRequired[str]
    agent_name: NotRequired[str]


StatePatch = dict[str, Any]
