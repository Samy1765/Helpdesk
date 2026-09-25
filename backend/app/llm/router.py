"""
Precision AI - LLM Router
Implements the upper levels of the cost-optimisation pipeline:

  LEVEL 4  small / local model (Ollama by default)  -> extraction, simple troubleshooting
  LEVEL 5  capable cloud model                       -> complex or ambiguous cases only

Features: tier fallback, response cache, strict JSON-schema validation of outputs,
retries with timeouts, and a usage row (tokens, cost, latency, cache hit) for every call.
If no provider is reachable the router returns None and callers fall back to deterministic logic.
"""

import hashlib
import json
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.providers import LLMResponse, LLMUnavailableError, get_provider
from app.models.agent import LLMUsageLog

logger = get_logger(__name__)
settings = get_settings()

T = TypeVar("T", bound=BaseModel)
SMALL, LARGE = "small", "large"


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    tier: str
    tokens: int
    cost: float
    cache_hit: bool
    parsed: Optional[BaseModel] = None


class _LRUCache:
    def __init__(self, size: int):
        self.size = size
        self._data: OrderedDict[str, LLMResponse] = OrderedDict()

    def get(self, key: str) -> Optional[LLMResponse]:
        if key in self._data:
            self._data.move_to_end(key)
            return self._data[key]
        return None

    def put(self, key: str, value: LLMResponse):
        self._data[key] = value
        self._data.move_to_end(key)
        while len(self._data) > self.size:
            self._data.popitem(last=False)

    def clear(self):
        self._data.clear()


_cache = _LRUCache(settings.LLM_CACHE_SIZE)


def _tier_chain(tier: str) -> list[tuple[str, str, str]]:
    """(tier, provider, model) in the order they should be tried."""
    small = (SMALL, settings.LLM_SMALL_PROVIDER, settings.LLM_SMALL_MODEL)
    large = (LARGE, settings.LLM_LARGE_PROVIDER, settings.LLM_LARGE_MODEL)
    # A small-tier task may fall forward to the large model (still works, costs more);
    # a large-tier task may degrade to the small model rather than failing.
    return [small, large] if tier == SMALL else [large, small]


def extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model response (handles ```json fences)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fence.group(1) if fence else text
    if not candidate.startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start == -1 or end <= start:
            return None
        candidate = candidate[start:end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def available_tiers() -> dict[str, Optional[str]]:
    out: dict[str, Optional[str]] = {}
    for tier, prov_name, model in (_tier_chain(SMALL)[0], _tier_chain(LARGE)[0]):
        prov = get_provider(prov_name)
        out[tier] = f"{prov_name}:{model}" if prov and await prov.is_available() else None
    return out


async def complete(
    *,
    db: Optional[AsyncSession],
    purpose: str,
    prompt: str,
    system_prompt: str,
    tier: str = SMALL,
    schema: Optional[type[T]] = None,
    temperature: float = 0.2,
    max_tokens: int = 700,
    ticket_id: Optional[int] = None,
    agent_run_id: Optional[int] = None,
) -> Optional[LLMResult]:
    """Run an LLM completion through the tier chain. Returns None if no model could serve it
    or if every model's output failed schema validation."""
    for tier_name, prov_name, model in _tier_chain(tier):
        provider = get_provider(prov_name)
        if provider is None or not await provider.is_available():
            continue

        cache_key = hashlib.sha256(
            json.dumps([prov_name, model, system_prompt, prompt, temperature, bool(schema)]).encode()
        ).hexdigest()
        cached = _cache.get(cache_key)
        response: Optional[LLMResponse] = cached
        error: Optional[str] = None

        if response is None:
            for _attempt in range(settings.LLM_MAX_RETRIES + 1):
                try:
                    response = await provider.generate(
                        prompt, model=model, system_prompt=system_prompt,
                        temperature=temperature, max_tokens=max_tokens, json_mode=schema is not None,
                    )
                    error = None
                    break
                except LLMUnavailableError as exc:
                    error = str(exc)[:300]

        parsed = None
        if response is not None and schema is not None:
            data = extract_json(response.content)
            try:
                parsed = schema.model_validate(data) if data is not None else None
            except ValidationError:
                parsed = None
            if parsed is None:
                error = "output failed schema validation"

        ok = response is not None and error is None
        if ok and cached is None:
            _cache.put(cache_key, response)

        _log_usage(db, response, prov_name, model, tier_name, purpose, cached is not None,
                   ok, error, ticket_id, agent_run_id)
        logger.info("llm_call", purpose=purpose, provider=prov_name, model=model, tier=tier_name,
                    ok=ok, cache_hit=cached is not None,
                    tokens=response.total_tokens if response else 0,
                    latency_ms=round(response.latency_ms, 1) if response else None,
                    ticket_id=ticket_id, agent_run_id=agent_run_id, error=error)
        if ok:
            return LLMResult(
                text=response.content.strip(), provider=prov_name, model=model, tier=tier_name,
                tokens=0 if cached else response.total_tokens,
                cost=0.0 if cached else response.estimated_cost,
                cache_hit=cached is not None, parsed=parsed,
            )
    return None


def _log_usage(db, response, provider, model, tier, purpose, cache_hit, ok, error, ticket_id, run_id):
    if db is None:
        return
    db.add(LLMUsageLog(
        ticket_id=ticket_id, agent_run_id=run_id, provider=provider, model=model, tier=tier,
        purpose=purpose,
        prompt_tokens=0 if (cache_hit or response is None) else response.prompt_tokens,
        completion_tokens=0 if (cache_hit or response is None) else response.completion_tokens,
        estimated_cost=0.0 if (cache_hit or response is None) else response.estimated_cost,
        cache_hit=cache_hit, success=ok, error=error,
        latency_ms=0.0 if (cache_hit or response is None) else response.latency_ms,
    ))


def clear_cache():
    _cache.clear()
