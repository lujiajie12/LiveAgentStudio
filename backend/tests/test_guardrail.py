import pytest

from app.services.guardrail_service import GuardrailService, NO_PERMISSION_TEXT


@pytest.mark.asyncio
async def test_guardrail_softens_exaggerated_claims_and_truncates_script():
    service = GuardrailService(["包治百病"])
    result = await service.evaluate(
        {
            "intent": "script",
            "agent_output": "这就是最强产品。" + ("很长的话术" * 80),
            "references": [],
            "retrieved_docs": [],
        }
    )

    assert result.passed is True
    assert result.action == "soft_block"
    assert "最强" not in result.final_output
    assert len(result.final_output) <= 300


@pytest.mark.asyncio
async def test_guardrail_filters_invalid_references():
    service = GuardrailService(["包治百病"])
    result = await service.evaluate(
        {
            "intent": "qa",
            "agent_output": "这是正常问答。",
            "references": ["doc-1", "doc-x"],
            "retrieved_docs": [{"doc_id": "doc-1", "content": "stub"}],
        }
    )

    assert result.passed is True
    assert result.references == ["doc-1"]
    assert result.reason == "invalid_references"


@pytest.mark.asyncio
async def test_guardrail_blocks_analyst_for_non_operator():
    service = GuardrailService(["包治百病"])
    result = await service.evaluate(
        {
            "intent": "analyst",
            "user_role": "broadcaster",
            "agent_output": "这里本来是复盘结果。",
            "references": [],
            "retrieved_docs": [],
        }
    )

    assert result.passed is False
    assert result.reason == "permission_denied"
    assert result.final_output == NO_PERMISSION_TEXT


@pytest.mark.asyncio
async def test_guardrail_blocks_hard_sensitive_terms_for_plain_text():
    service = GuardrailService(["包治百病"])
    result = await service.evaluate("这个产品包治百病")

    assert result.passed is False
    assert result.reason == "sensitive_terms"
