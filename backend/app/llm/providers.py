"""
Precision AI - LLM Provider Abstraction
Every provider implements the same `LLMProvider` interface over plain HTTP, so models are
swappable via environment variables. Supported: Ollama (local, free), Groq, OpenAI, Gemini.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import get_settings

settings = get_settings()

# USD per 1M tokens (input, output). Estimates only; used for cost tracking dashboards.
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "ollama": (0.0, 0.0),
    "groq": (0.59, 0.79),
    "openai": (0.15, 0.60),
    "gemini": (0.10, 0.40),
}


class LLMUnavailableError(RuntimeError):
    """Raised when a provider cannot serve a request (no key, unreachable, HTTP error)."""


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def estimated_cost(self) -> float:
        cin, cout = PRICING_PER_MTOK.get(self.provider, (0.0, 0.0))
        return (self.prompt_tokens * cin + self.completion_tokens * cout) / 1_000_000


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def is_available(self) -> bool: ...

    @abstractmethod
    async def generate(self, prompt: str, *, model: str, system_prompt: Optional[str] = None,
                       temperature: float = 0.2, max_tokens: int = 800,
                       json_mode: bool = False) -> LLMResponse: ...


class OpenAICompatibleProvider(LLMProvider):
    """Shared implementation for OpenAI-style chat completion APIs (OpenAI, Groq)."""

    base_url: str = ""

    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key

    async def is_available(self) -> bool:
        return bool(self.api_key)

    async def generate(self, prompt, *, model, system_prompt=None, temperature=0.2,
                       max_tokens=800, json_mode=False) -> LLMResponse:
        if not self.api_key:
            raise LLMUnavailableError(f"{self.name}: no API key configured")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                resp = await client.post(f"{self.base_url}/chat/completions", json=body,
                                         headers={"Authorization": f"Bearer {self.api_key}"})
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"{self.name}: {type(exc).__name__}") from exc
        data = resp.json()
        usage = data.get("usage", {})
        return LLMResponse(
            content=data["choices"][0]["message"]["content"] or "",
            model=model, provider=self.name,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_ms=(time.perf_counter() - start) * 1000,
        )


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    base_url = "https://api.groq.com/openai/v1"

    def __init__(self):
        super().__init__(settings.GROQ_API_KEY)


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"
    base_url = "https://api.openai.com/v1"

    def __init__(self):
        super().__init__(settings.OPENAI_API_KEY)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY

    async def is_available(self) -> bool:
        return bool(self.api_key)

    async def generate(self, prompt, *, model, system_prompt=None, temperature=0.2,
                       max_tokens=800, json_mode=False) -> LLMResponse:
        if not self.api_key:
            raise LLMUnavailableError("gemini: no API key configured")
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, json=body, headers={"x-goog-api-key": self.api_key})
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMUnavailableError(f"gemini: {type(exc).__name__}") from exc
        data = resp.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise LLMUnavailableError("gemini: empty response") from exc
        meta = data.get("usageMetadata", {})
        return LLMResponse(content=text, model=model, provider="gemini",
                           prompt_tokens=meta.get("promptTokenCount", 0),
                           completion_tokens=meta.get("candidatesTokenCount", 0),
                           latency_ms=(time.perf_counter() - start) * 1000)


class OllamaProvider(LLMProvider):
    """Local models via Ollama - no API key, no per-token cost."""
    name = "ollama"
    _AVAILABILITY_TTL = 30.0

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self._available: Optional[bool] = None
        self._checked_at = 0.0

    async def is_available(self) -> bool:
        # Cache the probe so a missing Ollama does not add latency to every request
        if self._available is not None and time.monotonic() - self._checked_at < self._AVAILABILITY_TTL:
            return self._available
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                self._available = (await client.get(f"{self.base_url}/api/tags")).status_code == 200
        except httpx.HTTPError:
            self._available = False
        self._checked_at = time.monotonic()
        return self._available

    async def generate(self, prompt, *, model, system_prompt=None, temperature=0.2,
                       max_tokens=800, json_mode=False) -> LLMResponse:
        body: dict = {"model": model, "prompt": prompt, "stream": False,
                      "options": {"temperature": temperature, "num_predict": max_tokens}}
        if system_prompt:
            body["system"] = system_prompt
        if json_mode:
            body["format"] = "json"
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=max(settings.LLM_TIMEOUT_SECONDS, 90.0)) as client:
                resp = await client.post(f"{self.base_url}/api/generate", json=body)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            self._available = None  # force re-probe next time
            raise LLMUnavailableError(f"ollama: {type(exc).__name__}") from exc
        data = resp.json()
        return LLMResponse(content=data.get("response", ""), model=model, provider="ollama",
                           prompt_tokens=data.get("prompt_eval_count", 0),
                           completion_tokens=data.get("eval_count", 0),
                           latency_ms=(time.perf_counter() - start) * 1000)


_PROVIDERS: dict[str, LLMProvider] = {}


def get_provider(name: str) -> Optional[LLMProvider]:
    name = (name or "").lower()
    if name in ("", "none", "disabled"):
        return None
    if name not in _PROVIDERS:
        factory = {"groq": GroqProvider, "openai": OpenAIProvider,
                   "gemini": GeminiProvider, "ollama": OllamaProvider}.get(name)
        if factory is None:
            return None
        _PROVIDERS[name] = factory()
    return _PROVIDERS[name]
