"""Category classification, entity extraction, LLM-output validation and priority intelligence."""

import pytest

from app.services import classification as cls
from app.services.classification import LLMClassification, extract_entities
from app.services.priority import assess_by_rules, priority_alert

SAMPLES = [
    ("My VPN isn't connecting, AnyConnect times out after the 2FA code", "VPN", "vpn_mfa_failure"),
    ("VPN connects and then keeps dropping every few minutes", "VPN", "vpn_disconnection"),
    ("I cannot access my company email, Outlook says disconnected", "Email", "email_access_failure"),
    ("Outlook crashes every time I open it", "Email", "outlook_crash"),
    ("I forgot my password and cannot log in", "Password", "password_reset"),
    ("My account is locked out after too many attempts", "Password", "account_locked"),
    ("The printer on floor 3 has a paper jam", "Printer", "paper_jam"),
    ("Documents are stuck in the print queue", "Printer", "printer_not_printing"),
    ("Wi-Fi is connected but there is no internet", "Network", "wifi_connectivity"),
    ("Need Figma installed on my laptop, please install the software", "Software", "software_install_request"),
    ("My laptop battery won't charge", "Hardware", "battery_issue"),
    ("I received a phishing email asking for my bank details", "Security", "phishing_report"),
    ("I clicked the link in a fake email and entered my password", "Security", "phishing_report"),
    ("The HR portal server is down with 503 errors", "Server", "server_outage"),
    ("Queries on the sales database are timing out", "Database", "database_performance"),
]


@pytest.mark.parametrize("text,category,intent", SAMPLES)
async def test_rule_classification(db, text, category, intent):
    result = await cls.classify(text, db, allow_llm=False)
    assert result.category == category
    assert result.intent == intent
    assert 0 < result.confidence <= 1
    assert result.title


async def test_unknown_text_gets_low_confidence_default(db):
    result = await cls.classify("hmm something odd", db, allow_llm=False)
    assert result.method == "default" and result.confidence <= 0.3


def test_entity_extraction():
    ent = extract_entities("Windows 11 laptop, Outlook error code 0x800CCC0E, 12 users on floor 3 affected")
    assert ent["os"] == "Windows 11"
    assert ent["device"] == "Laptop"
    assert ent["application"] == "Outlook"
    assert ent["error_code"] == "0X800CCC0E"
    assert ent["affected_users"] == "12"
    assert ent["floor"] == "3"


def test_llm_classification_schema_rejects_garbage():
    with pytest.raises(Exception):
        LLMClassification.model_validate({"category": "VPN", "confidence": 3.2})
    ok = LLMClassification.model_validate({"category": "VPN", "confidence": 0.8, "intent": "VPN Login-Failure!",
                                           "entities": {"os": "Windows", "n": 5, "empty": ""}})
    assert ok.intent == "vpn_login_failure"
    assert ok.entities == {"os": "Windows", "n": "5"}


async def test_llm_category_outside_active_set_is_rejected(db, monkeypatch):
    from app.llm import router

    async def fake_complete(**kwargs):
        schema = kwargs["schema"]
        return router.LLMResult(text="", provider="fake", model="m", tier="small", tokens=10, cost=0, cache_hit=False,
                                parsed=schema.model_validate({"category": "Coffee Machine", "confidence": 0.99}))

    monkeypatch.setattr(router, "complete", fake_complete)
    result = await cls.classify("blorp flarp", db, allow_llm=True)
    assert result.category != "Coffee Machine"


@pytest.mark.parametrize("text,category,expected", [
    ("I forgot my wallpaper settings, want a new desktop background", "Hardware", "low"),
    ("I can't change my wallpaper", "Software", "low"),
    ("I cannot access my company email", "Email", "medium"),
    ("Entire department cannot access production database", "Database", "high"),
    ("Production server is completely down", "Server", "critical"),
    ("Everyone in the company cannot access email", "Email", "critical"),
    ("I clicked the link and entered my password on a fake page", "Security", "high"),
    ("Internet is a bit slow but working", "Network", "low"),
])
def test_priority_rules(text, category, expected):
    assert assess_by_rules(text, category, {}, None).system_priority == expected


def test_priority_alert_does_not_silently_override():
    assessment = assess_by_rules("I would like a new wallpaper, not urgent", "Software", {}, "critical")
    assert assessment.system_priority == "low"
    alert = priority_alert("critical", assessment.system_priority)
    assert alert and "appears higher than the assessed impact" in alert
    assert priority_alert("medium", "medium") is None
    assert "higher than your selection" in priority_alert("low", "critical")
