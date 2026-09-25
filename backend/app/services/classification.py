"""
Precision AI - Classification Engine
LEVEL 0/1 of the routing pipeline: deterministic keyword + intent-pattern classification.
Only when rule confidence is low is a (small) LLM consulted, and its JSON output is
validated against the set of active categories before it is used.

Categories are loaded from the database (ticket_categories.keywords), so new categories
can be added without code changes; the built-in intent patterns are an enhancement on top.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm import router as llm
from app.models.ticket import TicketCategory

logger = get_logger(__name__)

LLM_CLASSIFY_BELOW = 0.60

# (intent, category, human label, regex patterns)
INTENTS: list[tuple[str, str, str, list[str]]] = [
    ("vpn_mfa_failure", "VPN", "VPN authentication / MFA failure",
     [r"vpn.*(mfa|2fa|two.factor|authenticat|sec_auth|token|okta|duo)", r"(mfa|2fa).*vpn"]),
    ("vpn_disconnection", "VPN", "VPN keeps disconnecting",
     [r"vpn.*(disconnect|drops?|dropping|cuts? out|keeps? (losing|dropping))", r"(connects?|connected) (and |then )+.*(drop|disconnect)"]),
    ("vpn_connection_failure", "VPN", "VPN connection failure",
     [r"vpn", r"anyconnect|globalprotect|forticlient"]),
    ("account_locked", "Password", "Account locked out",
     [r"(account|user).*(locked|disabled|blocked)", r"locked out"]),
    ("mfa_issue", "Password", "MFA / authenticator problem",
     [r"(mfa|2fa|authenticator|otp|one.time code).*(not|lost|new phone|fail|reset)", r"new phone.*(authenticator|mfa)"]),
    ("password_reset", "Password", "Password reset request",
     [r"(reset|change|forgot|forgotten|expired?).*password", r"password.*(reset|expired?|forgot|not working|incorrect)"]),
    ("phishing_report", "Security", "Suspicious email / phishing report",
     [r"phish", r"suspicious (email|link|message|attachment)", r"(fake|spoofed) (email|login page)",
      r"clicked (a|the) link|entered my (password|credentials)|was (fake|a scam)|scam"]),
    ("malware_suspected", "Security", "Suspected malware infection",
     [r"virus|malware|ransomware|trojan|pop.?ups? .*(everywhere|keep)|files? (encrypted|renamed)"]),
    ("unauthorized_access", "Security", "Unauthorized access / compromised account",
     [r"(unauthori[sz]ed|unknown|strange) (login|access|sign.?in)", r"(hacked|compromised)"]),
    ("calendar_sync", "Email", "Calendar / Teams sync issue",
     [r"calendar.*(sync|not (show|updat))", r"(meeting|invite).*(not|missing)"]),
    ("outlook_crash", "Email", "Outlook crashing",
     [r"outlook.*(crash|freez|hang|not respond|closes)"]),
    ("email_send_receive", "Email", "Cannot send or receive email",
     [r"(email|mail|outlook).*(not|can.?t|cannot|unable).*(send|receiv|deliver)", r"(bounce|undeliverable|stuck in outbox)"]),
    ("email_access_failure", "Email", "Cannot access email",
     [r"(email|mail|outlook|mailbox|inbox|exchange)"]),
    ("paper_jam", "Printer", "Printer paper jam",
     [r"paper jam|jammed"]),
    ("printer_driver", "Printer", "Printer driver / setup issue",
     [r"(printer|print).*(driver|install|add|setup|set up|offline)"]),
    ("printer_not_printing", "Printer", "Printer not printing",
     [r"print|scanner|toner|spooler"]),
    ("database_outage", "Database", "Database outage",
     [r"(database|db|sql).*(down|outage|unavailable|offline|crash)"]),
    ("database_performance", "Database", "Database performance degradation",
     [r"(database|db|query|sql).*(slow|timeout|timing out|deadlock|lock)"]),
    ("database_access", "Database", "Database access problem",
     [r"database|sql|oracle|postgres|mysql|mongodb|db access|schema|table"]),
    ("server_outage", "Server", "Server / service outage",
     [r"(server|service|site|portal|intranet|sharepoint|website|web app|application server|host).*(down|outage|unreachable|not responding|50[0234])",
      r"\b50[234]\b|service unavailable|bad gateway|gateway timeout"]),
    ("disk_space", "Server", "Server disk space exhaustion",
     [r"(disk|drive|volume|storage).*(full|space|capacity)"]),
    ("server_performance", "Server", "Server performance degradation",
     [r"server|cpu|memory usage|load average|iis|nginx|apache|tomcat"]),
    ("bsod", "Hardware", "Blue screen / system crash",
     [r"blue screen|bsod|stop code|kernel panic"]),
    ("battery_issue", "Hardware", "Battery / charging issue",
     [r"battery|charg(er|ing)|power adapter|won.?t turn on|not turning on"]),
    ("display_issue", "Hardware", "Display / monitor issue",
     [r"(screen|monitor|display).*(flicker|black|blank|crack|no signal|dim|lines)"]),
    ("peripheral_issue", "Hardware", "Peripheral device issue",
     [r"keyboard|mouse|headset|webcam|docking|dock|usb"]),
    ("laptop_hardware_failure", "Hardware", "Laptop / desktop hardware failure",
     [r"laptop|desktop|computer|overheat|fan|hard drive|ssd|ram"]),
    ("license_activation", "Software", "Software license / activation issue",
     [r"licen[cs]e|activation|activate|subscription expired|seat"]),
    ("software_install_request", "Software", "Software installation request",
     [r"(install|installation|need|request|download).*(software|app|application|program|tool)", r"install"]),
    ("software_crash", "Software", "Application crash / error",
     [r"(crash|freez|not respond|hangs|error|won.?t (open|start|launch))"]),
    ("wifi_connectivity", "Network", "Wi-Fi connectivity issue",
     [r"wi.?fi|wireless|ssid|hotspot"]),
    ("dns_resolution", "Network", "DNS / name resolution issue",
     [r"dns|name resolution|cannot resolve|nxdomain"]),
    ("network_outage", "Network", "Network outage",
     [r"(network|internet|lan|ethernet).*(down|outage|no connection|not working)"]),
    ("network_slow", "Network", "Slow network",
     [r"(network|internet|connection|bandwidth).*(slow|lag|latency|packet loss)"]),
]

INTENT_LABELS = {i[0]: i[2] for i in INTENTS}

# Default keywords, used when the DB rows have none (e.g. a category added without keywords).
DEFAULT_KEYWORDS: dict[str, list[str]] = {
    "VPN": ["vpn", "anyconnect", "globalprotect", "forticlient", "remote access", "tunnel"],
    "Network": ["network", "wifi", "wi-fi", "wireless", "ethernet", "internet", "dns", "dhcp",
                "ip address", "bandwidth", "latency", "router", "switch", "lan", "connectivity"],
    "Password": ["password", "locked out", "account locked", "forgot", "reset my", "credentials",
                 "mfa", "2fa", "authenticator", "sign in", "login", "log in", "sso"],
    "Email": ["email", "e-mail", "outlook", "exchange", "mailbox", "inbox", "calendar", "teams",
              "smtp", "distribution list", "shared mailbox"],
    "Database": ["database", "sql", "query", "oracle", "mysql", "postgres", "mongodb", "deadlock",
                 "stored procedure", "db"],
    "Hardware": ["laptop", "desktop", "computer", "monitor", "keyboard", "mouse", "screen", "docking",
                 "headset", "webcam", "charger", "battery", "hard drive", "ssd", "blue screen", "bsod", "overheating"],
    "Software": ["software", "install", "application", "app", "license", "licence", "crash", "update",
                 "patch", "excel", "word", "powerpoint", "adobe", "figma", "zoom", "slack", "chrome"],
    "Printer": ["printer", "print", "printing", "scanner", "toner", "paper jam", "spooler", "print queue"],
    "Security": ["phishing", "phish", "virus", "malware", "ransomware", "suspicious", "hacked", "breach",
                 "compromised", "unauthorized", "antivirus", "spam", "scam", "spoofed", "impersonating",
                 "fake email", "clicked the link", "clicked a link", "entered my password",
                 "entered my credentials", "opened the attachment"],
    "Server": ["server", "outage", "service down", "iis", "nginx", "apache", "tomcat", "cpu", "disk space",
               "memory usage", "production", "host", "503", "502", "504", "service unavailable", "bad gateway",
               "intranet", "portal", "website", "site is down"],
}


@dataclass
class CategorySpec:
    id: int
    name: str
    keywords: list[str]


@dataclass
class Classification:
    category: Optional[str]
    category_id: Optional[int]
    sub_category: Optional[str]
    intent: Optional[str]
    entities: dict
    confidence: float
    method: str
    matched_keywords: list[str] = field(default_factory=list)
    title: Optional[str] = None
    llm_used: bool = False

    def as_dict(self) -> dict:
        return {
            "category": self.category, "sub_category": self.sub_category, "intent": self.intent,
            "entities": self.entities, "confidence": round(self.confidence, 3), "method": self.method,
            "matched_keywords": self.matched_keywords,
        }


class LLMClassification(BaseModel):
    """Strict schema for LLM classification output. Anything else is rejected."""
    category: str
    sub_category: Optional[str] = Field(default=None, max_length=100)
    intent: Optional[str] = Field(default=None, max_length=80)
    entities: dict[str, str] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    title: Optional[str] = Field(default=None, max_length=120)

    @field_validator("intent")
    @classmethod
    def snake_intent(cls, v):
        if v is None:
            return v
        v = re.sub(r"[^a-z0-9_]+", "_", v.strip().lower()).strip("_")
        return v or None

    @field_validator("entities", mode="before")
    @classmethod
    def stringify(cls, v):
        if not isinstance(v, dict):
            return {}
        return {str(k)[:40]: str(val)[:200] for k, val in list(v.items())[:12] if val not in (None, "")}


async def load_categories(db: AsyncSession) -> list[CategorySpec]:
    rows = (await db.execute(select(TicketCategory).where(TicketCategory.is_active.is_(True)))).unique().scalars()
    return [CategorySpec(c.id, c.name, list(c.keywords or []) or DEFAULT_KEYWORDS.get(c.name, [c.name.lower()]))
            for c in rows]


def _kw_hit(keyword: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(keyword.lower())}(?![a-z0-9])", text) is not None


def classify_by_rules(text: str, categories: list[CategorySpec]) -> tuple[Optional[CategorySpec], float, list[str]]:
    text_l = text.lower()
    scored: list[tuple[float, CategorySpec, list[str]]] = []
    for cat in categories:
        hits = [kw for kw in cat.keywords if _kw_hit(kw, text_l)]
        if not hits:
            continue
        score = sum(2.0 if " " in kw else 1.0 for kw in hits)
        if _kw_hit(cat.name, text_l):
            score += 1.5  # the category name itself is a strong signal ("VPN", "printer")
        scored.append((score, cat, hits))
    if not scored:
        return None, 0.0, []
    scored.sort(key=lambda s: s[0], reverse=True)
    top_score, top_cat, hits = scored[0]
    second = scored[1][0] if len(scored) > 1 else 0.0
    confidence = 0.5 + 0.12 * top_score - 0.1 * second
    return top_cat, max(0.3, min(0.97, confidence)), hits


def detect_intent(text: str, category: Optional[str]) -> Optional[str]:
    """First matching intent pattern, restricted to the chosen category when known."""
    text_l = text.lower()
    for intent, cat, _label, patterns in INTENTS:
        if category and cat != category:
            continue
        if any(re.search(p, text_l) for p in patterns):
            return intent
    return None


def intent_category(intent: Optional[str]) -> Optional[str]:
    for name, cat, _label, _p in INTENTS:
        if name == intent:
            return cat
    return None


def extract_entities(text: str) -> dict:
    """Deterministic entity extraction (no personal data is extracted)."""
    t = text.lower()
    ent: dict[str, str] = {}
    for os_name, pat in (("Windows 11", r"windows 11|win ?11"), ("Windows 10", r"windows 10|win ?10"),
                         ("Windows", r"windows"), ("macOS", r"mac ?os|macbook|\bmac\b"),
                         ("Linux", r"linux|ubuntu|fedora|debian"), ("iOS", r"iphone|ipad|\bios\b"),
                         ("Android", r"android")):
        if re.search(pat, t):
            ent["os"] = os_name
            break
    for dev, pat in (("Laptop", r"laptop|notebook|macbook"), ("Desktop", r"desktop|workstation|\bpc\b"),
                     ("Mobile phone", r"phone|mobile"), ("Printer", r"printer"), ("Monitor", r"monitor")):
        if re.search(pat, t):
            ent["device"] = dev
            break
    apps = ["outlook", "teams", "excel", "word", "powerpoint", "chrome", "edge", "firefox", "zoom", "slack",
            "figma", "adobe acrobat", "photoshop", "visual studio", "vs code", "sap", "salesforce",
            "cisco anyconnect", "anyconnect", "globalprotect", "okta", "jira", "sharepoint", "onedrive"]
    for app in apps:
        if re.search(rf"\b{re.escape(app)}\b", t):
            ent["application"] = app.title() if app not in ("sap", "vs code") else app.upper()
            break
    m = re.search(r"\b(?:error|code)[\s:#]*([a-z]{0,6}[_-]?\d{2,6}[a-z0-9_-]*|0x[0-9a-f]{4,8}|[a-z]+_[a-z_]+\d*)\b", t)
    if m:
        ent["error_code"] = m.group(1).upper()
    m = re.search(r"\b((?:\d{1,3}\.){3}\d{1,3})\b", t)
    if m:
        ent["ip_address"] = m.group(1)
    m = re.search(r"\b(\d{1,4})\s+(?:users|people|employees|colleagues|staff)\b", t)
    if m:
        ent["affected_users"] = m.group(1)
    m = re.search(r"\b(?:floor|level)\s*(\d{1,2})\b|\b(\d{1,2})(?:st|nd|rd|th) floor\b", t)
    if m:
        ent["floor"] = m.group(1) or m.group(2)
    if re.search(r"\b(mfa|2fa|two.factor|authenticator)\b", t):
        ent["mfa_involved"] = "yes"
    if re.search(r"(home|remote|hotel|airport|travel)", t):
        ent["location_type"] = "remote"
    elif re.search(r"\b(office|on.?site|floor)\b", t):
        ent["location_type"] = "office"
    return ent


def make_title(text: str, intent: Optional[str], category: Optional[str], entities: dict) -> str:
    if intent and intent in INTENT_LABELS:
        title = INTENT_LABELS[intent]
        detail = entities.get("application") or entities.get("os") or entities.get("device")
        if detail and detail.lower() not in title.lower():
            title = f"{title} ({detail})"
        return title
    first = re.split(r"(?<=[.!?])\s|\n", text.strip())[0][:90].strip()
    first = first[0].upper() + first[1:] if first else "IT support request"
    return f"{category} issue: {first}" if category and category.lower() not in first.lower() else first


async def classify(
    text: str,
    db: AsyncSession,
    *,
    ticket_id: Optional[int] = None,
    allow_llm: bool = True,
) -> Classification:
    categories = await load_categories(db)
    by_name = {c.name: c for c in categories}
    cat, conf, hits = classify_by_rules(text, categories)
    # Level-0 safety rule: a security signal (phishing, malware, compromise) always routes to
    # Security, even when generic words like "email" or "password" score higher.
    security_intent = detect_intent(text, "Security")
    if security_intent and "Security" in by_name and (cat is None or cat.name != "Security"):
        cat, conf = by_name["Security"], 0.9
    intent = detect_intent(text, cat.name if cat else None)
    # An intent pattern hit on a category with no keyword match is still useful evidence
    if cat is None:
        intent = detect_intent(text, None)
        ic = intent_category(intent)
        if ic in by_name:
            cat, conf = by_name[ic], 0.5
    elif intent:
        conf = min(0.97, conf + 0.08)

    entities = extract_entities(text)
    result = Classification(
        category=cat.name if cat else None, category_id=cat.id if cat else None,
        sub_category=INTENT_LABELS.get(intent) if intent else None, intent=intent,
        entities=entities, confidence=conf, method="rules", matched_keywords=hits,
    )

    if allow_llm and conf < LLM_CLASSIFY_BELOW:
        llm_result = await _classify_with_llm(text, categories, db, ticket_id)
        if llm_result is not None:
            result = _merge(result, llm_result, by_name)

    if result.category is None:
        # Nothing matched and no LLM: route to the general software queue with low confidence
        fallback = by_name.get("Software") or (categories[0] if categories else None)
        if fallback:
            result.category, result.category_id, result.confidence = fallback.name, fallback.id, 0.3
            result.method = "default"

    result.title = result.title or make_title(text, result.intent, result.category, result.entities)
    logger.info("ticket_classified", category=result.category, intent=result.intent,
                confidence=round(result.confidence, 3), method=result.method, ticket_id=ticket_id)
    return result


async def _classify_with_llm(text, categories, db, ticket_id) -> Optional[LLMClassification]:
    names = ", ".join(c.name for c in categories)
    system = (
        "You classify IT helpdesk issues. Respond with ONLY a JSON object with keys: "
        '"category" (exactly one of: ' + names + '), "sub_category", "intent" (snake_case), '
        '"entities" (object of short strings: os, device, application, error_code), '
        '"confidence" (0-1), "title" (max 10 words). Do not invent details not in the text.'
    )
    res = await llm.complete(db=db, purpose="classification", tier=llm.SMALL, prompt=f"Issue:\n{text[:2500]}",
                             system_prompt=system, schema=LLMClassification, max_tokens=300,
                             ticket_id=ticket_id)
    if res is None or res.parsed is None:
        return None
    parsed: LLMClassification = res.parsed  # type: ignore[assignment]
    if parsed.category not in {c.name for c in categories}:
        logger.warning("llm_classification_rejected", category=parsed.category)
        return None
    return parsed


def _merge(rules: Classification, llm_out: LLMClassification, by_name: dict[str, CategorySpec]) -> Classification:
    cat = by_name[llm_out.category]
    agree = rules.category == cat.name
    confidence = min(0.95, max(llm_out.confidence, rules.confidence) + (0.1 if agree else 0.0))
    if not agree and rules.category is not None:
        confidence = min(confidence, 0.7)  # disagreement between rules and model lowers trust
    entities = {**llm_out.entities, **rules.entities}  # deterministic extraction wins on conflict
    intent = rules.intent if agree and rules.intent else (llm_out.intent or rules.intent)
    return Classification(
        category=cat.name, category_id=cat.id,
        sub_category=llm_out.sub_category or rules.sub_category, intent=intent, entities=entities,
        confidence=confidence, method="rules+llm" if rules.category else "llm",
        matched_keywords=rules.matched_keywords, title=llm_out.title, llm_used=True,
    )
