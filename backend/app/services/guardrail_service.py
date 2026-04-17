from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field


NO_PERMISSION_TEXT = "当前账号暂无复盘分析权限，如需查看数据复盘请联系运营或管理员处理。"


class GuardrailResult(BaseModel):
    passed: bool
    reason: str | None = None
    final_output: str
    violations: list[str] = Field(default_factory=list)
    references: list[str] | None = None
    action: str = "pass"


class GuardrailService:
    # GuardrailService 是主链的统一治理出口：
    # 不管前面是 planner、qa、script 还是 analyst 产出的内容，最终都会在这里做权限、
    # 敏感词、夸大宣传、长度、引用合法性等检查。
    def __init__(self, sensitive_terms: list[str]):
        self.sensitive_terms = sensitive_terms
        self.soft_replace_rules: list[tuple[str, str]] = [
            (r"最强", "更强"),
            (r"全网最佳", "很有竞争力"),
            (r"第一", "表现突出"),
            (r"唯一", "较少见"),
            (r"国家级", "权威级"),
            (r"100%", "尽量"),
            (r"永久", "长期"),
            (r"绝对", "更"),
        ]

    # 统一治理入口。
    # 为了兼容旧调用方，这里既支持只传一段纯文本，也支持传完整 state。
    async def evaluate(self, payload: str | dict[str, Any]) -> GuardrailResult:
        if isinstance(payload, str):
            return self._evaluate_text(payload)
        return self._evaluate_state(payload)

    # 纯文本模式是兼容分支，只做最基础的敏感词硬拦截。
    def _evaluate_text(self, text: str) -> GuardrailResult:
        violations = [term for term in self.sensitive_terms if term and term in text]
        if violations:
            return GuardrailResult(
                passed=False,
                reason="sensitive_terms",
                final_output="这条内容存在合规风险，建议改成更准确、更克制的表达后再发送。",
                violations=violations,
                action="hard_block",
            )
        return GuardrailResult(passed=True, final_output=text)

    # 完整 state 模式才是主链正式使用的治理逻辑。
    # 这里会同时处理权限、夸大宣传、敏感词、长度限制和引用校验。
    def _evaluate_state(self, state: dict[str, Any]) -> GuardrailResult:
        text = str(state.get("agent_output", "") or "")
        intent = str(state.get("intent", "") or "")
        user_role = str(state.get("user_role", "") or "")
        active_sensitive_terms = self.sensitive_terms + [
            str(term).strip() for term in state.get("custom_sensitive_terms", []) if str(term).strip()
        ]
        violations: list[str] = []
        reasons: list[str] = []
        action = "pass"

        # analyst 输出涉及权限控制，非运营/管理员不允许直接查看复盘分析。
        if intent == "analyst" and user_role not in {"operator", "admin"}:
            return GuardrailResult(
                passed=False,
                reason="permission_denied",
                final_output=NO_PERMISSION_TEXT,
                violations=["permission_denied"],
                action="hard_block",
                references=[],
            )

        modified_text = text
        # 对夸张宣传做软改写，而不是直接报错。
        # 这样既能保住回答连续性，又能把风险表达压下去。
        for pattern, replacement in self.soft_replace_rules:
            if re.search(pattern, modified_text):
                violations.append(pattern)
                modified_text = re.sub(pattern, replacement, modified_text)
        if modified_text != text:
            reasons.append("exaggerated_claims")
            action = "soft_block"

        # 敏感词属于硬风险，发现后直接拦截。
        hard_violations = [term for term in active_sensitive_terms if term and term in modified_text]
        if hard_violations:
            return GuardrailResult(
                passed=False,
                reason="sensitive_terms",
                final_output="这条内容存在合规风险，建议切换为更准确、更克制的表达后再发送。",
                violations=violations + hard_violations,
                action="hard_block",
                references=[],
            )

        # 不同类型内容允许的最大长度不同：
        # QA 更短，脚本中等，分析报告可以更长一些。
        max_length = 500 if intent == "qa" else 300 if intent == "script" else 1200
        if len(modified_text) > max_length:
            modified_text = modified_text[: max_length - 3].rstrip() + "..."
            reasons.append("length_truncated")
            action = "soft_block" if action == "pass" else action

        # 引用必须来自真实召回文档，不能把不存在的 doc_id 带到前端。
        normalized_references = self._validate_references(
            references=state.get("references", []),
            retrieved_docs=state.get("retrieved_docs", []),
        )
        if normalized_references != list(state.get("references", []) or []):
            reasons.append("invalid_references")
            action = "warn_pass" if action == "pass" else action

        return GuardrailResult(
            passed=True,
            reason=",".join(reasons) if reasons else None,
            final_output=modified_text,
            violations=violations,
            references=normalized_references,
            action=action,
        )

    # 只保留真实召回文档里的 doc_id，避免前端看到伪造引用。
    def _validate_references(
        self,
        references: list[Any],
        retrieved_docs: list[dict[str, Any]],
    ) -> list[str]:
        valid_doc_ids = {
            str(doc.get("doc_id", "")).strip()
            for doc in retrieved_docs
            if str(doc.get("doc_id", "")).strip()
        }
        if not valid_doc_ids:
            return []

        normalized: list[str] = []
        for item in references or []:
            ref_id = str(item).strip()
            if ref_id and ref_id in valid_doc_ids and ref_id not in normalized:
                normalized.append(ref_id)
        return normalized
