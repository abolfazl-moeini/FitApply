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
