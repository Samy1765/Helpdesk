"""
Precision AI - LLM Provider Abstraction
Every provider implements the same `LLMProvider` interface over plain HTTP, so models are
swappable via environment variables. Supported: Ollama (local, free), Groq, OpenAI, Gemini.
"""

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import get_settings

settings = get_settings()

# USD per 1M tokens (input, output). Estimates only; used for cost tracking dashboards.
# A model listed here overrides its provider's figure.
MODEL_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "gpt-4o-mini": (0.15, 0.60),
}
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "ollama": (0.0, 0.0),
    "groq": (0.15, 0.60),
    "openai": (0.15, 0.60),
    "gemini": (0.10, 0.40),
}

_SECRET_PATTERN = re.compile(r"\b(sk-|gsk_|AIza)[\w\-*.]+")


class LLMUnavailableError(RuntimeError):
    """Raised when a provider cannot serve a request (no key, unreachable, HTTP error).
    `retryable` is True only for transient failures (timeouts, rate limits, 5xx)."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def describe_http_error(provider: str, exc: httpx.HTTPError) -> LLMUnavailableError:
    """Turn an httpx error into a short, key-free message that says what went wrong
    (e.g. "groq: HTTP 404 - model decommissioned") and whether a retry can help."""
    if isinstance(exc, httpx.HTTPStatusError):
        resp = exc.response
        detail = ""
        try:
            err = resp.json().get("error")
            detail = (err.get("message") or "") if isinstance(err, dict) else str(err or "")
        except ValueError:
            detail = resp.text
        detail = _SECRET_PATTERN.sub("[redacted]", " ".join(detail.split()))[:180]
        retryable = resp.status_code == 429 or resp.status_code >= 500
        return LLMUnavailableError(f"{provider}: HTTP {resp.status_code}" + (f" - {detail}" if detail else ""),
                                   retryable=retryable)
    # Timeouts and connection failures are transient
    return LLMUnavailableError(f"{provider}: {type(exc).__name__}", retryable=isinstance(exc, httpx.TransportError))


def is_reasoning_model(provider: str, model: str) -> bool:
    """Models that spend completion tokens thinking before they answer."""
    m = (model or "").lower()
    if provider == "groq":
        return m.startswith("openai/gpt-oss")
    if provider == "openai":
        return m.startswith(("gpt-5", "o1", "o3", "o4"))
    if provider == "gemini":
        return m.startswith(("gemini-2.5", "gemini-3"))
    return False


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
        cin, cout = MODEL_PRICING_PER_MTOK.get(self.model) or PRICING_PER_MTOK.get(self.provider, (0.0, 0.0))
        return (self.prompt_tokens * cin + self.completion_tokens * cout) / 1_000_000


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def is_available(self) -> bool: ...

    @abstractmethod
    async def generate(self, prompt: str, *, model: str, system_prompt: Optional[str] = None,
                       temperature: float = 0.2, max_tokens: int = 800, json_mode: bool = False,
                       json_schema: Optional[dict] = None) -> LLMResponse: ...


class OpenAICompatibleProvider(LLMProvider):
    """Shared implementation for OpenAI-style chat completion APIs (OpenAI, Groq)."""

    base_url: str = ""

    def __init__(self, api_key: Optional[str]):
        self.api_key = api_key

    async def is_available(self) -> bool:
        return bool(self.api_key)

    def build_body(self, prompt: str, *, model: str, system_prompt: Optional[str], temperature: float,
                   max_tokens: int, json_mode: bool) -> dict:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        # max_completion_tokens is accepted by every current OpenAI and Groq model (max_tokens is not)
        body: dict = {"model": model, "messages": messages, "max_completion_tokens": max_tokens,
                      "temperature": temperature}
        if is_reasoning_model(self.name, model):
            body["max_completion_tokens"] = max_tokens + settings.LLM_REASONING_EXTRA_TOKENS
            body["reasoning_effort"] = settings.LLM_REASONING_EFFORT
            if self.name == "openai":
                del body["temperature"]  # OpenAI reasoning models reject a non-default temperature
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    async def generate(self, prompt, *, model, system_prompt=None, temperature=0.2,
                       max_tokens=800, json_mode=False, json_schema=None) -> LLMResponse:
        if not self.api_key:
            raise LLMUnavailableError(f"{self.name}: no API key configured")
        body = self.build_body(prompt, model=model, system_prompt=system_prompt, temperature=temperature,
                               max_tokens=max_tokens, json_mode=json_mode)
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                resp = await client.post(f"{self.base_url}/chat/completions", json=body,
                                         headers={"Authorization": f"Bearer {self.api_key}"})
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise describe_http_error(self.name, exc) from exc
        data = resp.json()
        usage = data.get("usage", {})
        return LLMResponse(
            content=data["choices"][0]["message"].get("content") or "",
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

    def build_body(self, prompt: str, *, model: str, system_prompt: Optional[str], temperature: float,
                   max_tokens: int, json_mode: bool) -> dict:
        # Thinking tokens count toward maxOutputTokens on Gemini 2.5+/3
        if is_reasoning_model(self.name, model):
            max_tokens += settings.LLM_REASONING_EXTRA_TOKENS
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        return body

    async def generate(self, prompt, *, model, system_prompt=None, temperature=0.2,
                       max_tokens=800, json_mode=False, json_schema=None) -> LLMResponse:
        if not self.api_key:
            raise LLMUnavailableError("gemini: no API key configured")
        body = self.build_body(prompt, model=model, system_prompt=system_prompt, temperature=temperature,
                               max_tokens=max_tokens, json_mode=json_mode)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, json=body, headers={"x-goog-api-key": self.api_key})
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise describe_http_error("gemini", exc) from exc
        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError) as exc:
            reason = (data.get("candidates") or [{}])[0].get("finishReason", "no candidates")
            raise LLMUnavailableError(f"gemini: empty response ({reason})") from exc
        # Skip thought summaries; the answer is the concatenation of the remaining text parts
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        meta = data.get("usageMetadata", {})
        return LLMResponse(content=text, model=model, provider="gemini",
                           prompt_tokens=meta.get("promptTokenCount", 0),
                           completion_tokens=meta.get("candidatesTokenCount", 0) + meta.get("thoughtsTokenCount", 0),
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

    def build_body(self, prompt: str, *, model: str, system_prompt: Optional[str], temperature: float,
                   max_tokens: int, json_mode: bool, json_schema: Optional[dict]) -> dict:
        body: dict = {"model": model, "prompt": prompt, "stream": False,
                      "options": {"temperature": temperature, "num_predict": max_tokens}}
        if system_prompt:
            body["system"] = system_prompt
        if json_schema:
            # Structured outputs: decoding is constrained to the schema, which small local models need
            body["format"] = json_schema
        elif json_mode:
            body["format"] = "json"
        return body

    async def generate(self, prompt, *, model, system_prompt=None, temperature=0.2,
                       max_tokens=800, json_mode=False, json_schema=None) -> LLMResponse:
        body = self.build_body(prompt, model=model, system_prompt=system_prompt, temperature=temperature,
                               max_tokens=max_tokens, json_mode=json_mode, json_schema=json_schema)
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=max(settings.LLM_TIMEOUT_SECONDS, 90.0)) as client:
                resp = await client.post(f"{self.base_url}/api/generate", json=body)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            self._available = None  # force re-probe next time
            raise describe_http_error("ollama", exc) from exc
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
