"""Regression tests for the Gemini-first provider failover chain."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.ai.gateway import AIGateway, LLMProvider, LLMResponse
from app.core.exceptions import AIProviderError


class FakeProvider:
    def __init__(self, provider: LLMProvider, fail: bool = False) -> None:
        self.name = provider
        self.model = f'{provider.value}-model'
        self.config = SimpleNamespace(model=self.model)
        self.fail = fail
        self.calls = 0
        self.failures = 0

    async def execute(self, **_: object) -> LLMResponse:
        self.calls += 1
        if self.fail:
            raise AIProviderError(provider=self.name.value, message='provider unavailable')
        return LLMResponse(
            text='{"ok": true}',
            provider=self.name,
            model=self.model,
        )

    def record_failure(self) -> None:
        self.failures += 1


@pytest.mark.asyncio
async def test_gemini_provider_error_falls_back_to_groq(monkeypatch: pytest.MonkeyPatch) -> None:
    gemini = FakeProvider(LLMProvider.GEMINI, fail=True)
    groq = FakeProvider(LLMProvider.GROQ)
    gateway = object.__new__(AIGateway)
    gateway._providers = [gemini, groq]
    gateway._named_providers = {LLMProvider.GEMINI: gemini, LLMProvider.GROQ: groq}
    gateway._cache = {}
    gateway._bus = SimpleNamespace(publish_sync=AsyncMock())

    monkeypatch.setattr('app.ai.gateway.asyncio.sleep', AsyncMock())

    response = await gateway.execute(
        messages=[{'role': 'user', 'content': 'Return JSON'}],
        expect_json=False,
        use_cache=False,
    )

    assert response.provider == LLMProvider.GROQ
    assert gemini.calls == 3
    assert gemini.failures == 3
    assert groq.calls == 1
    gateway._bus.publish_sync.assert_awaited_once()
