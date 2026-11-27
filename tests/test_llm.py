"""Tests for LLM cleaner and JSON parsing."""

import pytest
from pydantic import BaseModel
from fitapply.llm import clean_json_text, BaseLLM


class SampleModel(BaseModel):
    name: str
    score: int


def test_clean_json_text_pure():
    raw = '{"name": "test", "score": 90}'
    assert clean_json_text(raw) == raw


def test_clean_json_text_with_fences():
    raw = '```json\n{"name": "test", "score": 90}\n```'
    assert clean_json_text(raw) == '{"name": "test", "score": 90}'


def test_clean_json_text_with_prose():
    raw = 'Here is the evaluation:\n```json\n{"name": "test", "score": 90}\n```\nHope it helps!'
    assert clean_json_text(raw) == '{"name": "test", "score": 90}'


def test_clean_json_text_unfenced_with_prose():
    raw = 'Sure, the result is {"name": "test", "score": 90} as requested.'
    assert clean_json_text(raw) == '{"name": "test", "score": 90}'


class DummyLLM(BaseLLM):
    def __init__(self, output: str):
        self.output = output

    async def complete(self, prompt: str, system: str | None = None) -> str:
        return self.output


@pytest.mark.asyncio
async def test_complete_structured():
    llm = DummyLLM('```json\n{"name": "Alice", "score": 95}\n```')
    res = await llm.complete_structured("prompt", SampleModel)
    assert res.name == "Alice"
    assert res.score == 95


class RetryingLLM(BaseLLM):
    def __init__(self):
        self.call_count = 0

    async def complete(self, prompt: str, system: str | None = None) -> str:
        self.call_count += 1
        if self.call_count == 1:
            return "This is not valid JSON at all"
        return '{"name": "Bob", "score": 99}'


@pytest.mark.asyncio
async def test_complete_structured_with_retry():
    llm = RetryingLLM()
    res = await llm.complete_structured("give me json", SampleModel)
    assert llm.call_count == 2
    assert res.name == "Bob"
    assert res.score == 99


@pytest.mark.asyncio
async def test_provider_failure_is_not_retried_or_leaked_into_prompt():
    class BrokenLLM(BaseLLM):
        calls = 0
        async def complete(self, prompt: str, system: str | None = None) -> str:
            self.calls += 1
            raise RuntimeError("sensitive-provider-detail")

    llm = BrokenLLM()
    with pytest.raises(RuntimeError, match="sensitive-provider-detail"):
        await llm.complete_structured("prompt", SampleModel)
    assert llm.calls == 1
