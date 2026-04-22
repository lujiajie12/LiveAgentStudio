from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.repositories.base import LiveBarrageEventRepository, MessageRepository, SessionRepository, ToolCallLogRepository
from app.schemas.domain import LiveBarrageEventRecord, MessageRecord, MessageRole, ToolCallLogRecord
from app.services.memory_service import MemoryService


class OpsService:
    """聚合 Studio v2 页面所需的高优意图、动作卡片和追踪数据。"""

    def __init__(
        self,
        *,
        tool_log_repository: ToolCallLogRepository,
        memory_service: MemoryService,
        message_repository: MessageRepository,
        session_repository: SessionRepository,
        barrage_repository: LiveBarrageEventRepository,
    ):
        self.tool_log_repository = tool_log_repository
        self.memory_service = memory_service
        self.message_repository = message_repository
        self.session_repository = session_repository
        self.barrage_repository = barrage_repository

    async def list_recent_traces(self, limit: int = 20) -> list[dict[str, Any]]:
        logs = await self.tool_log_repository.list_recent(limit=limit * 20)
        grouped: dict[str, list[ToolCallLogRecord]] = defaultdict(list)
        for log in logs:
            if log.trace_id:
                grouped[log.trace_id].append(log)

        traces: list[dict[str, Any]] = []
        for trace_id, items in grouped.items():
            items.sort(key=lambda item: item.created_at)
            latest = items[-1]
            traces.append(
                {
                    "trace_id": trace_id,
                    "session_id": latest.session_id,
                    "created_at": items[0].created_at.isoformat(),
                    "updated_at": latest.created_at.isoformat(),
                    "statuses": sorted({item.status for item in items}),
                    "nodes": [item.node_name for item in items if item.node_name],
                    "error_count": sum(1 for item in items if item.status in {"error", "failed"}),
                    "degraded_count": sum(1 for item in items if item.status == "degraded"),
                }
            )

        traces.sort(key=lambda item: item["updated_at"], reverse=True)
        return traces[:limit]

    async def get_trace_detail(self, trace_id: str) -> dict[str, Any]:
        logs = await self.tool_log_repository.list_by_trace(trace_id)
        logs.sort(key=lambda item: item.created_at)
        if not logs:
            return {"trace_id": trace_id, "logs": [], "memory": None}

        session_id = next((item.session_id for item in logs if item.session_id), None)
        memory = await self.memory_service.get_memory_snapshot(session_id) if session_id else None
        return {
            "trace_id": trace_id,
            "session_id": session_id,
            "logs": [
                {
                    "id": item.id,
                    "tool_name": item.tool_name,
                    "node_name": item.node_name,
                    "category": item.category,
                    "status": item.status,
                    "latency_ms": item.latency_ms,
                    "input_payload": item.input_payload,
                    "output_summary": item.output_summary,
                    "created_at": item.created_at.isoformat(),
                }
                for item in logs
            ],
            "memory": memory,
        }

    async def get_priority_queue(self, session_id: str, limit: int = 3) -> list[dict[str, Any]]:
        barrages = await self.barrage_repository.list_recent_by_session(session_id, limit=120)
        cards = self._build_priority_cards(list(reversed(barrages)))
        if not cards:
            cards = self._build_fallback_priority_cards()
        return cards[:limit]

    async def get_action_center(self, session_id: str) -> dict[str, Any]:
        messages = await self.message_repository.list_by_session(session_id)
        assistant_messages = [item for item in messages if item.role == MessageRole.assistant]
        latest_assistant = assistant_messages[-1] if assistant_messages else None
        latest_script = self._find_latest_agent_message(assistant_messages, "script")
        session_record = await self.session_repository.get(session_id)

        cards = [
            self._build_qa_card(latest_assistant),
            self._build_guardrail_card(latest_assistant),
            self._build_ops_card(session_record, latest_script, messages),
        ]
        return {"session_id": session_id, "cards": cards}

    async def broadcast_tts(
        self,
        *,
        session_id: str,
        text: str,
        voice: str,
        requested_by: str,
    ) -> dict[str, Any]:
        cleaned = text.strip()
        job_id = str(uuid4())
        now = datetime.utcnow()
        await self.tool_log_repository.create(
            ToolCallLogRecord(
                session_id=session_id,
                tool_name="tts_broadcast",
                node_name="tts",
                category="tts",
                input_payload={
                    "voice": voice,
                    "requested_by": requested_by,
                    "text_length": len(cleaned),
                },
                output_summary=cleaned[:120],
                status="accepted",
                created_at=now,
            )
        )
        return {
            "job_id": job_id,
            "session_id": session_id,
            "voice": voice,
            "provider": "browser-local",
            "status": "accepted",
            "preview_text": cleaned,
            "created_at": now.isoformat(),
            "message": "已接收 TTS 插播请求，前端可直接使用浏览器语音播报。",
        }

    def _build_priority_cards(self, barrages: list[LiveBarrageEventRecord]) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        latest_by_key: dict[str, LiveBarrageEventRecord] = {}

        for barrage in barrages:
            key = self._normalize_priority_key(barrage.text)
            if not key:
                continue
            counts[key] += 1
            latest_by_key[key] = barrage

        ordered: list[dict[str, Any]] = []
        for barrage in sorted(latest_by_key.values(), key=lambda item: item.created_at, reverse=True):
            key = self._normalize_priority_key(barrage.text)
            if not key:
                continue
            label, tone, recommended_intent = self._classify_priority(barrage.text)
            summary = f"请帮我处理这个直播间问题：{barrage.text.strip()}"
            ordered.append(
                {
                    "id": f"priority-{barrage.id}",
                    "label": label,
                    "tone": tone,
                    "frequency": f"{max(counts[key], 1)}次/分钟",
                    "summary": summary,
                    "prompt": summary,
                    "source_message_id": barrage.id,
                    "recommended_intent": recommended_intent,
                    "created_at": barrage.created_at.isoformat(),
                }
            )

        return ordered

    def _build_fallback_priority_cards(self) -> list[dict[str, Any]]:
        now = datetime.utcnow().isoformat()
        return [
            {
                "id": "priority-fallback-qa",
                "label": "聚类: 用户咨询",
                "tone": "neutral",
                "frequency": "4次/分钟",
                "summary": "请帮我处理这个直播间问题：今天这场直播主推什么？",
                "prompt": "请帮我处理这个直播间问题：今天这场直播主推什么？",
                "recommended_intent": "qa",
                "created_at": now,
            },
            {
                "id": "priority-fallback-product",
                "label": "实体: 产品参数",
                "tone": "info",
                "frequency": "2次/分钟",
                "summary": "请帮我处理这个直播间问题：这款产品适合什么家庭使用？",
                "prompt": "请帮我处理这个直播间问题：这款产品适合什么家庭使用？",
                "recommended_intent": "qa",
                "created_at": now,
            },
        ]

    def _build_qa_card(self, message: MessageRecord | None) -> dict[str, Any]:
        if not message:
            return {
                "key": "qa",
                "title": "AI 当前输出",
                "subtitle": "等待请求",
                "tone": "indigo",
                "status": "idle",
                "editable": True,
                "content": "左侧高优问题或下方指令交给 AI 生成后，这里会展示 QA、直答、脚本和复盘的最新结果。",
                "detail": "等待新的 AI 请求",
                "references": [],
                "metadata": {},
            }

        metadata = message.metadata or {}
        agent_name = message.agent_name or metadata.get("agent_name") or message.intent or "qa"
        references = metadata.get("references", [])
        presentation = self._resolve_output_presentation(str(agent_name), metadata)

        if metadata.get("unresolved") and presentation["response_kind"] == "qa":
            detail = "知识库命中不足，建议人工复核"
        else:
            detail = presentation["detail"]

        return {
            "key": "qa",
            "title": presentation["title"],
            "subtitle": presentation["subtitle"],
            "tone": presentation["tone"],
            "status": "ready",
            "editable": True,
            "content": message.content,
            "detail": detail,
            "references": references,
            "metadata": {
                **metadata,
                "message_id": message.id,
                "message_created_at": message.created_at.isoformat(),
                "response_kind": presentation["response_kind"],
                "display_type": presentation["display_type"],
                "tag_tone": presentation["tag_tone"],
                "display_detail": detail,
            },
        }

    def _build_guardrail_card(self, message: MessageRecord | None) -> dict[str, Any]:
        if not message:
            return {
                "key": "guardrail",
                "title": "实时风控与拦截",
                "subtitle": "输出治理",
                "tone": "neutral",
                "status": "idle",
                "editable": False,
                "content": "当前暂无风控记录。发送一条请求后，这里会展示最近一次合规校验结果和拦截说明。",
                "detail": "等待新的输出结果",
                "references": [],
                "metadata": {
                    "severity": "safe",
                    "rule": "暂无触发规则",
                    "original_text": "",
                    "triggered_at": None,
                },
            }

        metadata = message.metadata or {}
        action = str(metadata.get("guardrail_action") or "pass").lower()
        violations = metadata.get("guardrail_violations") or []
        guardrail_pass = bool(metadata.get("guardrail_pass", True))
        reason = metadata.get("guardrail_reason")
        base_metadata = {
            "severity": "safe",
            "rule": reason or ("、".join(violations) if violations else "当前无违规风险"),
            "original_text": message.content,
            "triggered_at": message.created_at.isoformat(),
        }

        if not guardrail_pass or action in {"block", "hard_block"}:
            tone = "danger"
            status = "blocked"
            detail = "命中高风险规则，已拦截输出"
            content = reason or "本次输出因高风险内容被拦截，建议改写后再发送。"
            base_metadata["severity"] = "high"
        elif action in {"modified", "soft_block"} or violations:
            tone = "warning"
            status = "modified"
            detail = "发现风险词，已执行软处理"
            content = reason or f"检测到 {', '.join(violations)} 等风险点，系统已做软处理后放行。"
            base_metadata["severity"] = "medium"
        else:
            tone = "success"
            status = "pass"
            detail = "最近一次输出已通过合规校验"
            content = "当前无拦截事件。系统已完成敏感词、绝对化表达和引用合规校验。"

        return {
            "key": "guardrail",
            "title": "实时风控与拦截",
            "subtitle": "输出治理",
            "tone": tone,
            "status": status,
            "editable": False,
            "content": content,
            "detail": detail,
            "references": [],
            "metadata": {
                **base_metadata,
                "guardrail_action": action,
                "guardrail_reason": reason,
                "guardrail_violations": violations,
            },
        }

    def _build_ops_card(
        self,
        session_record: Any,
        script_message: MessageRecord | None,
        messages: list[MessageRecord],
    ) -> dict[str, Any]:
        current_product_id = getattr(session_record, "current_product_id", None) or ""
        product_label = current_product_id or "未设置商品"
        prompt_product = current_product_id or "当前直播商品"
        stage = getattr(session_record, "live_stage", None) or "intro"
        user_count = sum(1 for item in messages if item.role == MessageRole.user)

        plans = [
            {
                "id": "A",
                "title": "方案 A：紧急逼单",
                "summary": "强调库存、优惠和限时信息，快速推动最后一轮转化。",
                "prompt": f"帮我生成一段{prompt_product}的逼单话术，当前直播阶段是{stage}，强调库存紧张和优惠节奏。",
            },
            {
                "id": "B",
                "title": "方案 B：福利互动",
                "summary": "发起评论区互动或截屏福利，先拉停留和参与，再承接下一个卖点。",
                "prompt": f"帮我生成一段{prompt_product}的互动留存话术，当前直播阶段是{stage}，用福利互动把观众留在直播间。",
            },
        ]

        insight = f"当前会话已累计 {user_count} 条用户消息，直播阶段为 {stage}，当前讲解商品为 {product_label}。"

        if script_message:
            metadata = script_message.metadata or {}
            detail = metadata.get("script_reason") or "最近一条控场话术已生成，可继续推送提词器或进行 TTS 插播。"
            content = (
                f"{insight} 最近已生成一条口播脚本，建议根据当前互动节奏选择推送提词器、TTS 插播，"
                "或继续生成承接话术。"
            )
            return {
                "key": "ops",
                "title": "运营控场编排",
                "subtitle": "流量策略提醒",
                "tone": "warning",
                "status": "ready",
                "editable": True,
                "content": content,
                "detail": detail,
                "references": [],
                "metadata": {
                    **metadata,
                    "trigger": "互动率波动",
                    "insight": insight,
                    "plans": [
                        {
                            "id": "A",
                            "title": "方案 A：执行当前脚本",
                            "summary": "使用最近一次生成的话术，直接承接当前直播节奏。",
                            "prompt": script_message.content,
                        },
                        plans[1],
                    ],
                },
            }

        content = (
            f"{insight} 如需控场话术，可从左侧高优问题区或主输出输入框触发 Script Agent。"
        )
        return {
            "key": "ops",
            "title": "运营控场编排",
            "subtitle": "流量策略提醒",
            "tone": "yellow",
            "status": "idle",
            "editable": True,
            "content": content,
            "detail": "当前暂无新的控场脚本输出",
            "references": [],
            "metadata": {
                "trigger": "策略建议",
                "insight": insight,
                "plans": plans,
            },
        }

    def _resolve_tool_presentation(self, metadata: dict[str, Any]) -> dict[str, str] | None:
        tool_intent = str(metadata.get("tool_intent") or "").lower()
        planner_action = str(metadata.get("planner_action") or "").lower()
        tools_used = {str(item).lower() for item in metadata.get("tools_used", []) or []}

        if tool_intent == "datetime" or planner_action == "call_datetime":
            return {
                "title": "Tool Agent",
                "subtitle": "日期时间",
                "tone": "blue",
                "response_kind": "tool_datetime",
                "display_type": "日期时间",
                "tag_tone": "tool",
                "detail": "已调用日期时间工具",
            }
        if tool_intent == "web_search" or planner_action == "call_web_search" or "google_search" in tools_used:
            return {
                "title": "Tool Agent",
                "subtitle": "联网搜索",
                "tone": "blue",
                "response_kind": "tool_web_search",
                "display_type": "联网搜索",
                "tag_tone": "tool",
                "detail": "已调用联网搜索工具",
            }
        if tool_intent == "memory_recall" or planner_action == "recall_memory":
            return {
                "title": "Tool Agent",
                "subtitle": "记忆召回",
                "tone": "blue",
                "response_kind": "tool_memory",
                "display_type": "记忆召回",
                "tag_tone": "tool",
                "detail": "已调用记忆召回工具",
            }
        return None

    def _resolve_output_presentation(self, agent_name: str, metadata: dict[str, Any]) -> dict[str, str]:
        tool_presentation = self._resolve_tool_presentation(metadata)
        if tool_presentation:
            return tool_presentation

        normalized = agent_name.lower()
        if normalized in {"direct", "direct_reply", "skill"}:
            return {
                "title": "Direct Agent",
                "subtitle": "快速直答",
                "tone": "indigo",
                "response_kind": "direct",
                "display_type": "Direct",
                "tag_tone": "stream",
                "detail": "Skill 预设回答" if normalized == "skill" else "直接回复，无需知识库检索",
            }
        if normalized == "script":
            return {
                "title": "Script Agent",
                "subtitle": "口播脚本",
                "tone": "yellow",
                "response_kind": "script",
                "display_type": "脚本",
                "tag_tone": "script",
                "detail": str(metadata.get("script_reason") or metadata.get("route_reason") or "已生成直播口播脚本"),
            }
        if normalized == "analyst":
            return {
                "title": "Analyst Agent",
                "subtitle": "复盘分析",
                "tone": "blue",
                "response_kind": "analyst",
                "display_type": "复盘",
                "tag_tone": "analyst",
                "detail": str(metadata.get("route_reason") or "已生成复盘分析"),
            }
        return {
            "title": "RAG 知识 Agent",
            "subtitle": "实时解答",
            "tone": "indigo",
            "response_kind": "qa",
            "display_type": "RAG",
            "tag_tone": "rag",
            "detail": f"引用 {len(metadata.get('references', []) or [])} 条知识片段",
        }

    def _find_latest_agent_message(self, messages: list[MessageRecord], agent_name: str) -> MessageRecord | None:
        for message in reversed(messages):
            metadata = message.metadata or {}
            if message.agent_name == agent_name or metadata.get("agent_name") == agent_name or message.intent == agent_name:
                return message
        return None

    def _find_latest_qa_message(self, messages: list[MessageRecord]) -> MessageRecord | None:
        for message in reversed(messages):
            metadata = message.metadata or {}
            agent_name = message.agent_name or metadata.get("agent_name") or message.intent or ""
            if agent_name in {"qa", "direct", "direct_reply"}:
                return message
        return None

    def _normalize_priority_key(self, text: str) -> str:
        return re.sub(r"[\s\W_]+", "", text or "", flags=re.UNICODE).lower()

    def _classify_priority(self, text: str) -> tuple[str, str, str]:
        content = text or ""
        if any(keyword in content for keyword in ("退", "换", "运费", "售后", "保修", "退款")):
            return "聚类: 退换货策略", "warning", "qa"
        if any(keyword in content for keyword in ("适合", "区别", "参数", "规格", "材质", "成分", "功率", "型号")):
            return "实体: 产品参数", "info", "qa"
        if any(keyword in content for keyword in ("促单", "话术", "库存", "优惠", "脚本", "倒计时")):
            return "聚类: 运营场控", "accent", "script"
        return "聚类: 用户咨询", "neutral", "qa"
