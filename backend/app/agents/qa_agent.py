import json
import logging
import re
from time import perf_counter
from typing import Any, Protocol

from app.agents.base import BaseAgent
from app.core.config import settings
from app.core.observability import record_timed_tool_call
from app.graph.state import LiveAgentState, StatePatch

try:
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:  # pragma: no cover
    HumanMessage = None
    SystemMessage = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:  # pragma: no cover
    ChatOpenAI = None


logger = logging.getLogger(__name__)

QA_NO_ANSWER_TEXT = "抱歉，我暂时没有在知识库中找到足够信息，建议联系人工客服进一步确认。"
QA_LOW_CONFIDENCE_TEXT = "抱歉，这个问题目前缺少足够依据，建议联系人工客服进一步确认。"
CJK_CHARS = r"\u3400-\u4dbf\u4e00-\u9fff"
CJK_CLOSE_PUNCT = r"，。！？；：、）》」』】"
CJK_OPEN_PUNCT = r"（《「『【"


class QAAgentLLM(Protocol):
    # 调用支持结构化输出的 LLM 能力。
    async def ainvoke_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        ...

    # 调用纯文本输出的 LLM 能力。
    async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        ...


class ChatOpenAIJsonClient:
    # 初始化通用 LLM 客户端，供 QA、Script、Analyst 复用。
    def __init__(self, label: str = "agent"):
        self._client = None
        self.label = label
        api_key = settings.LLM_API_KEY or settings.OPENAI_API_KEY
        base_url = settings.LLM_BASE_URL or settings.OPENAI_BASE_URL
        model = settings.LLM_MODEL or settings.ROUTER_MODEL
        if api_key and ChatOpenAI is not None:
            self._client = ChatOpenAI(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=0,
            )

    # 从模型回复中尽量提取出 JSON 载荷，兼容 fenced code block 和前后缀噪声。
    def _extract_json_payload(self, content: str) -> dict[str, Any]:
        candidate = content.strip()
        if not candidate:
            raise json.JSONDecodeError("empty response", candidate, 0)

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

        fenced = candidate.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        if fenced != candidate:
            try:
                return json.loads(fenced)
            except json.JSONDecodeError:
                pass

        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(candidate[start : end + 1])

        raise json.JSONDecodeError("no json object found", candidate, 0)

    # 直接向底层 LLM 请求纯文本结果。
    async def ainvoke_text(self, system_prompt: str, user_prompt: str) -> str:
        if self._client is None or SystemMessage is None or HumanMessage is None:
            raise RuntimeError("qa llm client unavailable")

        started = perf_counter()
        try:
            response = await self._client.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )
        except Exception:
            await record_timed_tool_call(
                f"{self.label}_llm_text",
                started_at=started,
                node_name=self.label,
                category="llm",
                status="degraded",
            )
            raise
        content = str(response.content).strip()
        await record_timed_tool_call(
            f"{self.label}_llm_text",
            started_at=started,
            node_name=self.label,
            category="llm",
            output_summary=content[:200],
            status="ok",
        )
        return content

    # 基于纯文本调用结果再做一次 JSON 提取。
    async def ainvoke_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        return self._extract_json_payload(await self.ainvoke_text(system_prompt, user_prompt))


class QAAgent(BaseAgent):
    name = "qa"

    # 初始化 QA 智能体，注入检索管线和可替换的 LLM 客户端。
    def __init__(self, retrieval_pipeline=None, llm_client: QAAgentLLM | None = None):
        self.pipeline = retrieval_pipeline
        self.llm_client = llm_client or ChatOpenAIJsonClient()
        self.high_frequency_repository = None

    # 允许在容器装配阶段延迟注入长期高频问题仓库。
    def bind_high_frequency_repository(self, repository) -> None:
        self.high_frequency_repository = repository

    # 读取最近若干轮对话，给查询改写和回答生成提供上下文。
    def _recent_memory(self, state: LiveAgentState, turns: int) -> list[dict[str, str]]:
        history = list(state.get("short_term_memory", []))
        if not history:
            return []
        return history[-(turns * 2) :]

    # 规范化查询改写结果里的中文空格，避免把检索 query 搞脏。
    def _normalize_rewritten_query(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text).strip()
        normalized = re.sub(fr"(?<=[{CJK_CHARS}])\s+(?=[{CJK_CHARS}])", "", normalized)
        normalized = re.sub(fr"(?<=[{CJK_CHARS}])\s+(?=[{CJK_CLOSE_PUNCT}])", "", normalized)
        normalized = re.sub(fr"(?<=[{CJK_CLOSE_PUNCT}])\s+(?=[{CJK_CHARS}])", "", normalized)
        normalized = re.sub(fr"(?<=[{CJK_OPEN_PUNCT}])\s+(?=[{CJK_CHARS}])", "", normalized)
        normalized = re.sub(fr"(?<=[{CJK_CHARS}])\s+(?=[0-9])", "", normalized)
        normalized = re.sub(fr"(?<=[0-9])\s+(?=[{CJK_CHARS}])", "", normalized)
        return normalized

    # 判断当前问题是否强依赖上下文，从而决定是否优先做查询改写。
    def _needs_contextual_rewrite(self, query: str) -> bool:
        lowered = query.lower()
        pronouns = (
            "这",
            "这个",
            "这款",
            "它",
            "那个",
            "哪款",
            "上面",
            "刚才",
            "再说",
            "那",
            "这些",
            "那些",
        )
        if len(query.strip()) <= 12:
            return True
        return any(token in lowered for token in pronouns)

    # 当模型改写失败时，用最近一轮用户表达做保守拼接兜底。
    def _fallback_rewrite(self, state: LiveAgentState) -> str:
        query = state["user_input"].strip()
        memory = self._recent_memory(state, turns=2)
        if not memory or not self._needs_contextual_rewrite(query):
            return self._normalize_rewritten_query(query)

        latest_user_turn = next(
            (
                str(item.get("content", "")).strip()
                for item in reversed(memory)
                if str(item.get("role", "")).strip() == "user" and str(item.get("content", "")).strip()
            ),
            "",
        )
        if not latest_user_turn or latest_user_turn == query:
            return self._normalize_rewritten_query(query)
        return self._normalize_rewritten_query(f"{latest_user_turn}；补充问题：{query}")

    # 调用 LLM 做查询改写，并在失败时回退到规则兜底方案。
    async def _rewrite_query(self, state: LiveAgentState) -> str:
        started = perf_counter()
        query = state["user_input"].strip()
        memory = self._recent_memory(state, turns=2)
        if not memory:
            return self._normalize_rewritten_query(query)

        system_prompt = (
            "You rewrite live-commerce QA queries for retrieval. "
            "Resolve pronouns and omissions with recent conversation context. "
            "Do not change the user's intent. "
            'Return strict JSON only: {"rewritten_query":"..."}'
        )
        user_prompt = json.dumps(
            {
                "user_input": query,
                "recent_memory": memory,
                "current_product_id": state.get("current_product_id"),
                "live_stage": state.get("live_stage"),
            },
            ensure_ascii=False,
        )
        try:
            payload = await self.llm_client.ainvoke_json(system_prompt, user_prompt)
        except Exception:
            await record_timed_tool_call(
                "qa_query_rewrite",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": query},
                status="degraded",
            )
            return self._fallback_rewrite(state)

        rewritten_query = str(payload.get("rewritten_query", "")).strip()
        if not rewritten_query:
            await record_timed_tool_call(
                "qa_query_rewrite",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": query},
                status="degraded",
            )
            return self._fallback_rewrite(state)
        await record_timed_tool_call(
            "qa_query_rewrite",
            started_at=started,
            node_name="qa",
            category="llm",
            input_payload={"query": query},
            output_summary=rewritten_query,
            status="ok",
        )
        return self._normalize_rewritten_query(rewritten_query)

    # 把检索结果裁成 Top-3，并统一整理成后续 Prompt 使用的结构。
    def _top_retrieved_docs(self, rerank_results: list[Any], top_k: int = 3) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        for rank, result in enumerate(rerank_results[:top_k], start=1):
            metadata = dict(getattr(result, "metadata", {}) or {})
            docs.append(
                {
                    "rank": rank,
                    "doc_id": getattr(result, "doc_id", ""),
                    "content": getattr(result, "content", ""),
                    "score": getattr(result, "final_score", 0.0),
                    "source_type": getattr(result, "source_type", ""),
                    "source_file": metadata.get("source_file", ""),
                    "metadata": metadata,
                }
            )
        return docs

    # 返回统一的无答案结构，便于零召回和模型失败场景复用。
    def _no_answer_result(self) -> dict[str, Any]:
        return {
            "answer": QA_NO_ANSWER_TEXT,
            "references": [],
            "confidence": 0.0,
            "unresolved": True,
        }

    # 按当前商品加载长期高频问题，帮助 QA 在常见问法场景下更快进入正确语义。
    async def _load_high_frequency_questions(self, state: LiveAgentState) -> list[dict[str, Any]]:
        if self.high_frequency_repository is None:
            return []
        product_id = str(state.get("current_product_id") or "").strip()
        if not product_id:
            return []
        try:
            records = await self.high_frequency_repository.list_by_product(
                product_id,
                limit=settings.HIGH_FREQUENCY_QUESTION_LIMIT,
            )
        except Exception:
            return []
        return [{"question": record.question, "frequency": record.frequency} for record in records]

    # 当结构化回答失败时，退到纯文本回答模式尽量保住可读结果。
    async def _generate_text_answer(
        self,
        state: LiveAgentState,
        rewritten_query: str,
        retrieved_docs: list[dict[str, Any]],
        high_frequency_questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        started = perf_counter()
        system_prompt = (
            "你是直播电商 QA 助手。"
            "必须只基于给定知识片段回答，不能编造事实。"
            "请直接输出自然中文回答，不要输出 JSON。"
        )
        user_prompt = json.dumps(
            {
                "current_product_id": state.get("current_product_id"),
                "live_stage": state.get("live_stage"),
                "short_term_memory": self._recent_memory(state, turns=3),
                "knowledge_context": retrieved_docs,
                "high_frequency_questions": high_frequency_questions,
                "rewritten_query": rewritten_query,
                "original_user_input": state["user_input"],
            },
            ensure_ascii=False,
        )

        try:
            answer = (await self.llm_client.ainvoke_text(system_prompt, user_prompt)).strip()
        except Exception as exc:
            logger.warning("qa_text_generation_failed trace_id=%s error=%s", state.get("trace_id"), exc)
            await record_timed_tool_call(
                "qa_answer_generation_text",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": rewritten_query},
                output_summary=str(exc),
                status="degraded",
            )
            return self._no_answer_result()

        if not answer:
            await record_timed_tool_call(
                "qa_answer_generation_text",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": rewritten_query},
                status="degraded",
            )
            return self._no_answer_result()
        await record_timed_tool_call(
            "qa_answer_generation_text",
            started_at=started,
            node_name="qa",
            category="llm",
            input_payload={"query": rewritten_query},
            output_summary=answer[:200],
            status="ok",
        )

        references = [str(doc["doc_id"]) for doc in retrieved_docs if str(doc.get("doc_id", "")).strip()]
        return {
            "answer": answer,
            "references": references,
            "confidence": 0.68,
            "unresolved": False,
        }

    # 优先要求模型返回 JSON；若失败，再退回纯文本生成。
    async def _generate_answer(
        self,
        state: LiveAgentState,
        rewritten_query: str,
        retrieved_docs: list[dict[str, Any]],
        high_frequency_questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        started = perf_counter()
        system_prompt = (
            "You are a live-commerce QA agent. "
            "Answer in Chinese and only use the provided knowledge context. "
            "Do not invent facts. Keep the answer concise and practical. "
            'Return strict JSON only: {"answer":"...","references":["doc_id"],"confidence":0.0}'
        )
        user_prompt = json.dumps(
            {
                "current_product_id": state.get("current_product_id"),
                "live_stage": state.get("live_stage"),
                "short_term_memory": self._recent_memory(state, turns=3),
                "knowledge_context": retrieved_docs,
                "high_frequency_questions": high_frequency_questions,
                "rewritten_query": rewritten_query,
                "original_user_input": state["user_input"],
            },
            ensure_ascii=False,
        )

        try:
            payload = await self.llm_client.ainvoke_json(system_prompt, user_prompt)
        except Exception as exc:
            logger.warning("qa_json_generation_failed trace_id=%s error=%s", state.get("trace_id"), exc)
            await record_timed_tool_call(
                "qa_answer_generation_json",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": rewritten_query},
                output_summary=str(exc),
                status="degraded",
            )
            return await self._generate_text_answer(state, rewritten_query, retrieved_docs, high_frequency_questions)

        answer = str(payload.get("answer", "")).strip()
        references = payload.get("references", [])
        confidence = payload.get("confidence", 0.0)

        if not isinstance(references, list):
            references = []

        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0

        if not answer:
            await record_timed_tool_call(
                "qa_answer_generation_json",
                started_at=started,
                node_name="qa",
                category="llm",
                input_payload={"query": rewritten_query},
                status="degraded",
            )
            return await self._generate_text_answer(state, rewritten_query, retrieved_docs, high_frequency_questions)

        await record_timed_tool_call(
            "qa_answer_generation_json",
            started_at=started,
            node_name="qa",
            category="llm",
            input_payload={"query": rewritten_query},
            output_summary=answer[:200],
            status="ok",
        )

        return {
            "answer": answer,
            "references": references,
            "confidence": confidence,
            "unresolved": confidence < 0.5,
        }

    # 对模型给出的引用做白名单校验，只保留本轮真实召回到的文档。
    def _normalize_references(self, generated_refs: list[Any], retrieved_docs: list[dict[str, Any]]) -> list[str]:
        valid_ids = [str(doc["doc_id"]) for doc in retrieved_docs if str(doc.get("doc_id", "")).strip()]
        if not valid_ids:
            return []

        normalized: list[str] = []
        for ref in generated_refs:
            ref_id = str(ref).strip()
            if ref_id and ref_id in valid_ids and ref_id not in normalized:
                normalized.append(ref_id)
        return normalized or valid_ids

    # 执行完整 QA 主链：改写、检索、生成、引用清洗和低置信度降级。
    async def run(self, state: LiveAgentState) -> StatePatch:
        rewritten_query = await self._rewrite_query(state)
        retrieved_docs: list[dict[str, Any]] = []
        high_frequency_questions = await self._load_high_frequency_questions(state)

        if self.pipeline is not None:
            retrieval_started = perf_counter()
            try:
                _, rerank_results = await self.pipeline.retrieve(
                    rewritten_query,
                    source_hint=state.get("knowledge_scope"),
                )
                retrieved_docs = self._top_retrieved_docs(rerank_results, top_k=3)
                await record_timed_tool_call(
                    "qa_retrieval",
                    started_at=retrieval_started,
                    node_name="qa",
                    category="retrieval",
                    input_payload={"query": rewritten_query},
                    output_summary=f"docs={len(retrieved_docs)}",
                    status="ok" if retrieved_docs else "degraded",
                )
            except Exception as exc:
                logger.warning("qa_retrieval_failed trace_id=%s error=%s", state.get("trace_id"), exc)
                await record_timed_tool_call(
                    "qa_retrieval",
                    started_at=retrieval_started,
                    node_name="qa",
                    category="retrieval",
                    input_payload={"query": rewritten_query},
                    output_summary=str(exc),
                    status="degraded",
                )
                retrieved_docs = []

        if not retrieved_docs:
            return {
                "rewritten_query": rewritten_query,
                "agent_output": QA_NO_ANSWER_TEXT,
                "references": [],
                "retrieved_docs": [],
                "high_frequency_questions": high_frequency_questions,
                "qa_confidence": 0.0,
                "unresolved": True,
                "agent_name": self.name,
            }

        qa_result = await self._generate_answer(
            state,
            rewritten_query,
            retrieved_docs,
            high_frequency_questions,
        )
        references = self._normalize_references(qa_result.get("references", []), retrieved_docs)
        confidence = float(qa_result.get("confidence", 0.0))
        unresolved = bool(qa_result.get("unresolved", False)) or confidence < 0.5
        answer = str(qa_result.get("answer", "")).strip() or QA_NO_ANSWER_TEXT

        if unresolved and answer not in {QA_NO_ANSWER_TEXT, QA_LOW_CONFIDENCE_TEXT}:
            answer = QA_LOW_CONFIDENCE_TEXT

        return {
            "rewritten_query": rewritten_query,
            "agent_output": answer,
            "references": references if not unresolved or answer != QA_NO_ANSWER_TEXT else [],
            "retrieved_docs": retrieved_docs,
            "high_frequency_questions": high_frequency_questions,
            "qa_confidence": confidence,
            "unresolved": unresolved,
            "agent_name": self.name,
        }
