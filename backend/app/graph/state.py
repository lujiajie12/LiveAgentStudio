from typing import Any, NotRequired, TypedDict


class LiveAgentState(TypedDict):
    # API layer base context.
    trace_id: str
    session_id: str
    user_id: str
    user_role: NotRequired[str]
    app_id: NotRequired[str]
    run_id: NotRequired[str]
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
    route_target: NotRequired[str]
    requires_retrieval: NotRequired[bool]
    knowledge_scope: NotRequired[str]
    tool_intent: NotRequired[str]
    memory_recall_request: NotRequired[dict[str, Any]]
    planner_mode: NotRequired[str]
    planner_action: NotRequired[str]
    planner_action_args: NotRequired[dict[str, Any]]
    planner_step_count: NotRequired[int]
    planner_trace: NotRequired[list[dict[str, Any]]]
    executor_observations: NotRequired[list[dict[str, Any]]]
    planning_completed: NotRequired[bool]
    route_fallback_reason: NotRequired[str | None]
    route_low_confidence: NotRequired[bool]

    # Business-agent output.
    agent_output: NotRequired[str]
    references: NotRequired[list[str]]
    retrieved_docs: NotRequired[list[dict[str, Any]]]
    long_term_memories: NotRequired[list[dict[str, Any]]]
    long_term_memory_hits: NotRequired[int]
    rewritten_query: NotRequired[str]
    query_budget: NotRequired[dict[str, Any] | None]
    qa_confidence: NotRequired[float]
    unresolved: NotRequired[bool]
    tools_used: NotRequired[list[str]]
    tool_outputs: NotRequired[dict[str, Any]]
    script_type: NotRequired[str]
    script_tone: NotRequired[str]
    script_reason: NotRequired[str]
    script_candidates: NotRequired[list[str]]
    should_persist_report: NotRequired[bool]
    output_render_mode: NotRequired[str]
    needs_contextual_rewrite: NotRequired[bool]
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
