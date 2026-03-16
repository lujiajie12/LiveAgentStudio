from pydantic import BaseModel, Field


class GuardrailResult(BaseModel):
    passed: bool
    reason: str | None = None
    final_output: str
    violations: list[str] = Field(default_factory=list)


class GuardrailService:
    def __init__(self, sensitive_terms: list[str]):
        self.sensitive_terms = sensitive_terms

    async def evaluate(self, text: str) -> GuardrailResult:
        violations = [term for term in self.sensitive_terms if term in text]
        if violations:
            return GuardrailResult(
                passed=False,
                reason="sensitive_terms",
                final_output="这条内容存在合规风险，建议切换为更准确、克制的表达后再发送。",
                violations=violations,
            )
        return GuardrailResult(passed=True, final_output=text)
