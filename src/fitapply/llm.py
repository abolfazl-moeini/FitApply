"""LLM Provider abstraction supporting both Antigravity SDK and LiteLLM."""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def clean_json_text(text: str) -> str:
    """Strip markdown code fences, surrounding prose, and whitespace from JSON response."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()
    return text.strip()


class BaseLLM(ABC):
    """Abstract interface for LLM completions."""

    @abstractmethod
    async def complete(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text completion from LLM."""
        pass

    async def complete_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system: Optional[str] = None,
    ) -> T:
        """Generate a completion and validate against a Pydantic model."""
        schema_json = json.dumps(response_model.model_json_schema(), ensure_ascii=False, indent=2)
        full_system = (
            (system + "\n\n" if system else "")
            + f"You MUST respond ONLY with a valid JSON object matching this schema:\n{schema_json}\nDo not include any explanation or extra text outside the JSON."
        )
        raw = await self.complete(prompt=prompt, system=full_system)
        cleaned = clean_json_text(raw)
        data = json.loads(cleaned)
        return response_model.model_validate(data)


class AntigravityLLM(BaseLLM):
    """Native Antigravity Python SDK provider."""

    def __init__(self, system_instructions: Optional[str] = None):
        self.default_system = system_instructions or "You are a helpful and precise career automation AI."

    async def complete(self, prompt: str, system: Optional[str] = None) -> str:
        try:
            from google.antigravity import Agent, LocalAgentConfig
        except ImportError as e:
            raise ImportError(
                "google-antigravity is not installed. Install with `uv pip install google-antigravity`"
            ) from e

        sys_inst = system or self.default_system
        config = LocalAgentConfig(system_instructions=sys_inst)
        tokens = []
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            async for token in response:
                tokens.append(token)
        return "".join(tokens)


class LiteLLM(BaseLLM):
    """Universal LiteLLM provider supporting Gemini, OpenAI, Claude, Ollama, etc."""

    def __init__(
        self,
        model: str = "gemini/gemini-2.5-flash",
        temperature: float = 0.2,
        api_base: Optional[str] = None,
    ):
        self.model = model
        self.temperature = temperature
        self.api_base = api_base

    async def complete(self, prompt: str, system: Optional[str] = None) -> str:
        try:
            import litellm
        except ImportError as e:
            raise ImportError("litellm is not installed. Install with `uv pip install litellm`") from e

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self.api_base:
            kwargs["api_base"] = self.api_base

        resp = await litellm.acompletion(**kwargs)
        return resp.choices[0].message.content or ""


def get_llm_provider(config: Dict[str, Any]) -> BaseLLM:
    """Factory to instantiate the configured LLM provider."""
    llm_cfg = config.get("llm", {})
    provider = llm_cfg.get("provider", "antigravity").lower()

    if provider == "antigravity":
        return AntigravityLLM()
    elif provider == "litellm":
        return LiteLLM(
            model=llm_cfg.get("model", "gemini/gemini-2.5-flash"),
            temperature=llm_cfg.get("temperature", 0.2),
            api_base=llm_cfg.get("api_base"),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}. Expected 'antigravity' or 'litellm'.")
