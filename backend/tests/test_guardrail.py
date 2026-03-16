import pytest

from app.services.guardrail_service import GuardrailService


@pytest.mark.asyncio
async def test_guardrail_blocks_sensitive_terms():
    service = GuardrailService(["最强"])
    result = await service.evaluate("这是最强的产品")
    assert result.passed is False
    assert result.reason == "sensitive_terms"


@pytest.mark.asyncio
async def test_guardrail_allows_normal_text():
    service = GuardrailService(["最强"])
    result = await service.evaluate("这款产品主打保湿和舒缓")
    assert result.passed is True
