import json
from collections import Counter
from time import perf_counter
from typing import Any

from app.agents.base import BaseAgent
from app.agents.qa_agent import ChatOpenAIJsonClient
from app.core.observability import record_timed_tool_call
from app.graph.state import LiveAgentState, StatePatch
from app.repositories.base import HighFrequencyQuestionRepository, MessageRepository, ReportRepository, SessionRepository
from app.schemas.domain import MessageRole, ReportRecord, SessionStatus


NO_ANALYST_DATA_TEXT = "当前会话还缺少足够的历史消息，暂时无法生成有效复盘。"
NO_ANALYST_PERMISSION_TEXT = "当前账号暂无复盘分析权限，如需查看数据复盘请联系运营或管理员处理。"


class AnalystAgent(BaseAgent):
    name = "analyst"

    # 初始化复盘智能体，注入消息仓库、会话仓库、报告仓库和 LLM 客户端。
    def __init__(
        self,
        message_repository: MessageRepository,
        session_repository: SessionRepository,
        report_repository: ReportRepository,
        high_frequency_repository: HighFrequencyQuestionRepository | None = None,
        llm_client: ChatOpenAIJsonClient | None = None,
    ):
        self.message_repository = message_repository
        self.session_repository = session_repository
        self.report_repository = report_repository
        self.high_frequency_repository = high_frequency_repository
        self.llm_client = llm_client or ChatOpenAIJsonClient()

    # 执行完整复盘链路：鉴权、读取消息、统计指标、生成报告并按需落库。
    async def run(self, state: LiveAgentState) -> StatePatch:
        if str(state.get("user_role", "") or "") not in {"operator", "admin"}:
            return {
                "agent_output": NO_ANALYST_PERMISSION_TEXT,
                "references": [],
                "retrieved_docs": [],
                "analyst_report": {},
                "agent_name": self.name,
            }

        session = await self.session_repository.get(state["session_id"])
        messages = await self.message_repository.list_by_session(state["session_id"])
        history_messages = self._history_messages(messages, state["user_input"])
        if not history_messages:
            return {
                "agent_output": NO_ANALYST_DATA_TEXT,
                "references": [],
                "retrieved_docs": [],
                "analyst_report": {},
                "agent_name": self.name,
            }

        report = await self._build_report(state, history_messages, session)
        report_id = None
        if self._should_persist_report(state, session):
            saved = await self.report_repository.create(
                ReportRecord(
                    session_id=state["session_id"],
                    summary=report["summary"],
                    total_messages=report["total_messages"],
                    intent_distribution=report["intent_distribution"],
                    top_questions=report["top_questions"],
                    unresolved_questions=report["unresolved_questions"],
                    hot_products=report["hot_products"],
                    script_usage=report["script_usage"],
                    suggestions=report["suggestions"],
                )
            )
            report_id = saved.id
        await self._persist_high_frequency_questions(state, report["top_questions"])

        return {
            "agent_output": self._render_output(state["user_input"], report),
            "references": [],
            "retrieved_docs": [],
            "analyst_report": report,
            "report_id": report_id,
            "agent_name": self.name,
        }

    # 去掉当前这条触发分析的用户消息，避免把它统计进历史复盘数据。
    def _history_messages(self, messages: list[Any], current_input: str) -> list[Any]:
        trimmed = list(messages)
        if trimmed and getattr(trimmed[-1], "role", None) == MessageRole.user and getattr(trimmed[-1], "content", None) == current_input:
            trimmed = trimmed[:-1]
        return trimmed

    # 汇总历史消息并产出结构化复盘报告。
    async def _build_report(self, state: LiveAgentState, messages: list[Any], session: Any) -> dict[str, Any]:
        user_messages = [message for message in messages if message.role == MessageRole.user]
        assistant_messages = [message for message in messages if message.role == MessageRole.assistant]

        top_questions = self._top_questions(user_messages)
        unresolved_questions = self._unresolved_questions(messages)
        intent_distribution = self._intent_distribution(assistant_messages)
        script_usage = self._script_usage(assistant_messages)
        hot_products = self._hot_products(state, session)

        summary_bundle = await self._summarize_with_llm(
            state=state,
            total_messages=len(messages),
            intent_distribution=intent_distribution,
            top_questions=top_questions,
            unresolved_questions=unresolved_questions,
            hot_products=hot_products,
            script_usage=script_usage,
        )

        return {
            "summary": summary_bundle["summary"],
            "total_messages": len(messages),
            "intent_distribution": intent_distribution,
            "top_questions": top_questions,
            "unresolved_questions": unresolved_questions,
            "hot_products": hot_products,
            "script_usage": script_usage,
            "suggestions": summary_bundle["suggestions"],
        }

    # 统计高频用户问题，按归一化文本频次排序。
    def _top_questions(self, messages: list[Any]) -> list[str]:
        normalized_to_original: dict[str, str] = {}
        counter: Counter[str] = Counter()
        for message in messages:
            text = " ".join(str(message.content).split()).strip()
            if not text:
                continue
            normalized = text.lower()
            normalized_to_original.setdefault(normalized, text)
            counter[normalized] += 1
        return [normalized_to_original[key] for key, _ in counter.most_common(10)]

    # 根据 assistant 消息里的 unresolved 标记反推出未解决问题列表。
    def _unresolved_questions(self, messages: list[Any]) -> list[str]:
        unresolved: list[str] = []
        previous_user: str | None = None
        for message in messages:
            if message.role == MessageRole.user:
                previous_user = str(message.content).strip()
                continue
            if (
                message.role == MessageRole.assistant
                and bool(message.metadata.get("unresolved"))
                and previous_user
                and previous_user not in unresolved
            ):
                unresolved.append(previous_user)
        return unresolved

    # 统计 assistant 输出里的意图分布，便于复盘看业务结构占比。
    def _intent_distribution(self, messages: list[Any]) -> dict[str, float]:
        intents = [str(message.intent.value) for message in messages if message.intent is not None]
        if not intents:
            return {}
        counter = Counter(intents)
        total = sum(counter.values())
        return {intent: round(count / total, 2) for intent, count in counter.items()}

    # 统计本场使用过的各类话术次数。
    def _script_usage(self, messages: list[Any]) -> list[dict[str, Any]]:
        counter: Counter[str] = Counter()
        for message in messages:
            script_type = str(message.metadata.get("script_type", "")).strip()
            if script_type:
                counter[script_type] += 1
        return [{"script_type": script_type, "count": count} for script_type, count in counter.most_common()]

    # 汇总当前会话的热点商品，当前先基于会话商品 ID 做简版实现。
    def _hot_products(self, state: LiveAgentState, session: Any) -> list[str]:
        product_id = str(state.get("current_product_id") or getattr(session, "current_product_id", "") or "").strip()
        return [product_id] if product_id else []

    # 将本场直播提炼出的高频问题写回长期记忆库，供后续 QA 直接消费。
    async def _persist_high_frequency_questions(self, state: LiveAgentState, top_questions: list[str]) -> None:
        if self.high_frequency_repository is None:
            return
        product_id = str(state.get("current_product_id") or "").strip()
        if not product_id or not top_questions:
            return
        try:
            await self.high_frequency_repository.upsert_many(
                product_id,
                top_questions[:10],
                source_session_id=state.get("session_id"),
            )
        except Exception:
            return

    # 调用 LLM 生成摘要和建议，失败时退回规则版总结。
    async def _summarize_with_llm(
        self,
        state: LiveAgentState,
        total_messages: int,
        intent_distribution: dict[str, float],
        top_questions: list[str],
        unresolved_questions: list[str],
        hot_products: list[str],
        script_usage: list[dict[str, Any]],
    ) -> dict[str, Any]:
        started = perf_counter()
        system_prompt = (
            "You are a live-commerce analyst agent. "
            "Generate a concise Chinese review summary and 3 practical suggestions. "
            'Return strict JSON only: {"summary":"...","suggestions":["..."]}'
        )
        user_prompt = json.dumps(
            {
                "user_input": state.get("user_input"),
                "live_stage": state.get("live_stage"),
                "total_messages": total_messages,
                "intent_distribution": intent_distribution,
                "top_questions": top_questions[:5],
                "unresolved_questions": unresolved_questions[:5],
                "hot_products": hot_products,
                "script_usage": script_usage[:5],
            },
            ensure_ascii=False,
        )
        try:
            payload = await self.llm_client.ainvoke_json(system_prompt, user_prompt)
        except Exception:
            await record_timed_tool_call(
                "analyst_summary_generation",
                started_at=started,
                node_name="analyst",
                category="llm",
                input_payload={"total_messages": total_messages},
                status="degraded",
            )
            return self._fallback_summary(total_messages, top_questions, unresolved_questions, hot_products)

        summary = str(payload.get("summary", "")).strip()
        suggestions = [
            str(item).strip()
            for item in payload.get("suggestions", [])
            if str(item).strip()
        ]
        if not summary:
            await record_timed_tool_call(
                "analyst_summary_generation",
                started_at=started,
                node_name="analyst",
                category="llm",
                input_payload={"total_messages": total_messages},
                status="degraded",
            )
            return self._fallback_summary(total_messages, top_questions, unresolved_questions, hot_products)
        await record_timed_tool_call(
            "analyst_summary_generation",
            started_at=started,
            node_name="analyst",
            category="llm",
            input_payload={"total_messages": total_messages},
            output_summary=summary[:200],
            status="ok",
        )
        return {
            "summary": summary,
            "suggestions": suggestions[:5] or self._fallback_summary(
                total_messages,
                top_questions,
                unresolved_questions,
                hot_products,
            )["suggestions"],
        }

    # 当 LLM 不可用时，基于统计结果拼出保守可用的兜底复盘结论。
    def _fallback_summary(
        self,
        total_messages: int,
        top_questions: list[str],
        unresolved_questions: list[str],
        hot_products: list[str],
    ) -> dict[str, Any]:
        product_text = f"，主要关注商品为{hot_products[0]}" if hot_products else ""
        summary = f"本场已累计处理 {total_messages} 条消息{product_text}，用户问题主要集中在高频商品信息与成交相关诉求。"
        suggestions = [
            "把高频问题提前整理成主播提示卡，减少重复解释成本。",
            "针对未解决问题补齐资料库或标准答复，避免再次掉到人工兜底。",
            "把表现好的促单话术沉淀成模板，下一场直接复用。",
        ]
        if top_questions:
            suggestions[0] = f"优先优化这些高频问题的预设表达：{'; '.join(top_questions[:2])}。"
        if unresolved_questions:
            suggestions[1] = f"尽快补齐这些 unresolved 问题的处理方案：{'; '.join(unresolved_questions[:2])}。"
        return {"summary": summary, "suggestions": suggestions}

    # 判断本次分析结果是否需要正式落成报告记录。
    def _should_persist_report(self, state: LiveAgentState, session: Any) -> bool:
        query = str(state.get("user_input", "")).lower()
        if any(token in query for token in ("复盘", "报告", "总结", "分析")):
            return True
        return getattr(session, "status", None) == SessionStatus.ended if session is not None else False

    # 把结构化复盘结果渲染成更适合前端展示的文本输出。
    def _render_output(self, user_input: str, report: dict[str, Any]) -> str:
        lowered = user_input.lower()
        if any(token in lowered for token in ("高频", "问最多", "top问题")) and report["top_questions"]:
            return "本场高频问题主要有：" + "；".join(report["top_questions"][:3])
        if any(token in lowered for token in ("未解决", "unresolved")) and report["unresolved_questions"]:
            return "当前 unresolved 问题有：" + "；".join(report["unresolved_questions"][:3])
        return (
            f"{report['summary']}\n"
            f"消息总量：{report['total_messages']}\n"
            f"高频问题：{'；'.join(report['top_questions'][:3]) or '暂无'}\n"
            f"优化建议：{'；'.join(report['suggestions'][:3]) or '暂无'}"
        )
