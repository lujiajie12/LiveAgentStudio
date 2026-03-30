from typing import Any, NotRequired, TypedDict


class LiveAgentState(TypedDict):
    # API layer base context.
    trace_id: str
    session_id: str
    user_id: str
    user_role: NotRequired[str]
    user_input: str
    live_stage: str
    current_product_id: str | None
    short_term_memory: list[dict[str, str]]
    hot_keywords: NotRequired[list[str]]
    script_style: NotRequired[str | None]
    live_offer_snapshot: NotRequired[dict[str, Any]]
    memory_status: NotRequired[str]
    custom_sensitive_terms: NotRequired[list[str]]
    high_frequency_questions: NotRequired[list[dict[str, Any]]]

    # Router output.
    intent: NotRequired[str]
    intent_confidence: NotRequired[float]
    route_reason: NotRequired[str]
    knowledge_scope: NotRequired[str]
    route_fallback_reason: NotRequired[str | None]
    route_low_confidence: NotRequired[bool]

    # Business-agent output.
    agent_output: NotRequired[str]
    references: NotRequired[list[str]]
    retrieved_docs: NotRequired[list[dict[str, Any]]]
    rewritten_query: NotRequired[str]
    qa_confidence: NotRequired[float]
    unresolved: NotRequired[bool]
    script_type: NotRequired[str]
    script_tone: NotRequired[str]
    script_reason: NotRequired[str]
    script_candidates: NotRequired[list[str]]
    analyst_report: NotRequired[dict[str, Any]]
    report_id: NotRequired[str]

    # Guardrail output.
    guardrail_pass: NotRequired[bool]
    guardrail_reason: NotRequired[str | None]
    guardrail_action: NotRequired[str]
    guardrail_violations: NotRequired[list[str]]
    final_output: NotRequired[str]
    agent_name: NotRequired[str]


StatePatch = dict[str, Any]
