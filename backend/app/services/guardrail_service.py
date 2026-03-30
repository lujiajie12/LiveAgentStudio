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
    # 初始化治理服务，注入敏感词和软改写规则。
    def __init__(self, sensitive_terms: list[str]):
        self.sensitive_terms = sensitive_terms
        self.soft_replace_rules: list[tuple[str, str]] = [
            (r"最强", "更强"),
            (r"全网最低", "很有竞争力"),
            (r"第一", "表现突出"),
            (r"唯一", "较少见"),
            (r"国家级", "权威级"),
            (r"100%", "尽量"),
            (r"永久", "长期"),
            (r"绝对", "更"),
        ]

    # 统一治理入口，同时兼容纯文本模式和完整状态模式。
    async def evaluate(self, payload: str | dict[str, Any]) -> GuardrailResult:
        if isinstance(payload, str):
            return self._evaluate_text(payload)
        return self._evaluate_state(payload)

    # 纯文本模式下只做敏感词硬拦截，兼容旧调用方。
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

    # 完整状态模式下执行权限、夸大宣传、长度和引用合法性治理。
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
        for pattern, replacement in self.soft_replace_rules:
            if re.search(pattern, modified_text):
                violations.append(pattern)
                modified_text = re.sub(pattern, replacement, modified_text)
        if modified_text != text:
            reasons.append("exaggerated_claims")
            action = "soft_block"

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

        max_length = 500 if intent == "qa" else 300 if intent == "script" else 1200
        if len(modified_text) > max_length:
            modified_text = modified_text[: max_length - 3].rstrip() + "..."
            reasons.append("length_truncated")
            action = "soft_block" if action == "pass" else action

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

    # 只保留真实召回文档里的引用，避免前端看到伪造 doc_id。
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
