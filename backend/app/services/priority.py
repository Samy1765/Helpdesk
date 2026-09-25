"""
Precision AI - Priority Intelligence
Deterministic impact x severity matrix first; an LLM is consulted only when the rules find
no clear signal, and its answer is clamped to within one level of the rule result.
The user's own priority is never silently overridden: both values are stored and an alert
is produced whenever they differ.
"""

import re
from dataclasses import asdict, dataclass
from typing import Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm import router as llm

logger = get_logger(__name__)

LEVELS = ["low", "medium", "high", "critical"]
RANK = {p: i for i, p in enumerate(LEVELS)}

SCOPE_PATTERNS = [
    (3, "organization", r"\b(everyone|every ?one|all (users|staff|employees)|entire (company|organi[sz]ation|office|building)|whole (company|office|building)|company.?wide|all offices)\b"),
    (2, "department", r"\b(entire|whole|all of (the|our)|our) (department|team|floor|division|branch)\b|\b(multiple|several|many|a lot of) (users|people|colleagues|employees|staff)\b|\bothers? (are|also|too)\b|\b(\d{2,}|[5-9]) (users|people|employees|colleagues)\b|\bnobody (can|is able)\b"),
    (1, "few", r"\b(a (few|couple of) (colleagues|people|users)|my (colleague|teammate|coworker) (also|too)|(2|3|4|two|three|four) (users|people|colleagues))\b"),
]

SEVERITY_PATTERNS = [
    ("breach", r"\b(ransomware|data (breach|leak)|breach|files? (are |were )?encrypted|entered my (password|credentials)|clicked (the|a) (link|attachment)|account (was |is )?(hacked|compromised)|hacked)\b"),
    ("outage", r"\b(completely down|is down|are down|went down|outage|not responding at all|unreachable|offline|crashed|total failure|dead|won.?t (boot|turn on|start))\b"),
    # Cosmetic requests stay LOW even if phrased as "I can't change my wallpaper"
    ("cosmetic", r"\b(wallpaper|theme|font|icon|desktop background|screen ?saver|colou?r scheme|nice to have|when (you|possible|convenient)|not urgent|no rush|low priority|cosmetic|feature request|preference)\b"),
    ("blocked",r"\b(cannot|can.?t|can not|unable to|not able to|won.?t|not working|doesn.?t work|isn.?t working|fails?|failing|failed|blocked|locked out|denied|error|timing out|times out|keeps? (dropping|disconnecting))\b"),
    ("degraded", r"\b(slow|sluggish|intermittent|sometimes|occasionally|laggy|lag|delay|delayed|flicker)\b"),
]

PRODUCTION = r"\b(production|prod\b|customer.?facing|live (site|system)|payroll|checkout|revenue)\b"
URGENCY = r"\b(urgent|asap|immediately|right now|emergency|deadline|in \d+ (minutes|mins|hours)|presentation|client meeting)\b"

# (severity, scope) -> priority
MATRIX = {
    "cosmetic": ["low", "low", "low", "medium"],
    "degraded": ["low", "medium", "medium", "high"],
    "blocked": ["medium", "medium", "high", "critical"],
    "outage": ["medium", "high", "high", "critical"],
    "breach": ["high", "high", "critical", "critical"],
    "none": ["medium", "medium", "high", "high"],
}


@dataclass
class PriorityAssessment:
    user_priority: Optional[str]
    system_priority: str
    confidence: float
    reason: str
    impact: str
    urgency: str
    alert: Optional[str] = None
    method: str = "rules"

    def as_dict(self) -> dict:
        return asdict(self)


class LLMPriority(BaseModel):
    system_priority: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(max_length=400)


def detect_scope(text: str, entities: dict) -> tuple[int, str]:
    for level, label, pat in SCOPE_PATTERNS:
        if re.search(pat, text):
            return level, label
    try:
        n = int(entities.get("affected_users", 0))
        if n >= 50:
            return 3, "organization"
        if n >= 5:
            return 2, "department"
        if n >= 2:
            return 1, "few"
    except ValueError:
        pass
    return 0, "individual"


def _severity(text: str) -> str:
    for label, pat in SEVERITY_PATTERNS:
        if re.search(pat, text):
            return label
    return "none"


IMPACT_TEXT = {
    0: "Single user affected", 1: "A few users affected",
    2: "Team / department-level impact", 3: "Organization-wide impact",
}


def assess_by_rules(text: str, category: Optional[str], entities: dict,
                    user_priority: Optional[str]) -> PriorityAssessment:
    t = text.lower()
    scope_level, scope_label = detect_scope(t, entities)
    severity = _severity(t)
    production = re.search(PRODUCTION, t) is not None

    priority = MATRIX[severity][scope_level]
    reasons = [f"severity signal: {severity}", f"scope: {scope_label}"]

    if production and severity == "outage":
        priority = "critical"  # a production system that is down affects everyone who depends on it
        reasons.append("production / customer-facing system down")
    elif production and severity == "blocked" and RANK[priority] < RANK["high"]:
        priority = "high"
        reasons.append("production / customer-facing system")
    if category in ("Server", "Database") and severity == "outage" and RANK[priority] < RANK["high"]:
        priority = "high"  # shared infrastructure outages are never single-user issues
        reasons.append("shared infrastructure outage")
    if category == "Security" and severity == "breach":
        priority = LEVELS[max(RANK[priority], RANK["high"])]
    if category == "Security" and severity != "breach" and RANK[priority] < RANK["medium"]:
        priority = "medium"  # every security report deserves a timely look
        reasons.append("security report floor")

    strong = severity != "none" and (scope_level > 0 or severity in ("cosmetic", "breach", "outage", "blocked"))
    confidence = 0.9 if strong else 0.6
    urgency = "Time-sensitive (user-stated deadline or urgency)" if re.search(URGENCY, t) else (
        "High - infrastructure or security" if category in ("Security", "Server", "Database") and RANK[priority] >= 2
        else "Standard")

    return PriorityAssessment(
        user_priority=user_priority, system_priority=priority, confidence=confidence,
        reason="; ".join(reasons), impact=IMPACT_TEXT[scope_level] + (" (production system)" if production else ""),
        urgency=urgency,
    )


def priority_alert(user_priority: Optional[str], system_priority: str) -> Optional[str]:
    if not user_priority or user_priority not in RANK:
        return None
    diff = RANK[user_priority] - RANK[system_priority]
    if diff >= 1:
        return (f"Your selected priority ({user_priority.upper()}) appears higher than the assessed impact "
                f"({system_priority.upper()}). Both values are kept on the ticket and IT support can adjust it.")
    if diff <= -1:
        return (f"This issue was assessed as {system_priority.upper()}, higher than your selection "
                f"({user_priority.upper()}), based on its impact.")
    return None


async def assess_priority(
    text: str,
    db: AsyncSession,
    *,
    category: Optional[str],
    entities: dict,
    user_priority: Optional[str] = None,
    ticket_id: Optional[int] = None,
    allow_llm: bool = True,
) -> PriorityAssessment:
    user_priority = user_priority.lower() if user_priority else None
    result = assess_by_rules(text, category, entities, user_priority)

    if allow_llm and result.confidence < 0.7:
        system = ("You assess IT ticket priority objectively. LOW: cosmetic/non-urgent. MEDIUM: one user's work "
                  "affected. HIGH: several users, production systems, or blocking critical work. CRITICAL: "
                  "production outage, security breach, organisation-wide impact. Do not inflate. Respond ONLY "
                  'with JSON: {"system_priority": "...", "confidence": 0-1, "reason": "one sentence"}')
        res = await llm.complete(db=db, purpose="priority", tier=llm.SMALL, system_prompt=system,
                                 prompt=f"Category: {category}\nIssue:\n{text[:2000]}", schema=LLMPriority,
                                 max_tokens=150, ticket_id=ticket_id)
        if res is not None and res.parsed is not None:
            p: LLMPriority = res.parsed  # type: ignore[assignment]
            # Clamp the model's answer to within one level of the deterministic assessment
            lo, hi = max(0, RANK[result.system_priority] - 1), min(3, RANK[result.system_priority] + 1)
            clamped = LEVELS[min(hi, max(lo, RANK[p.system_priority]))]
            result.system_priority = clamped
            result.confidence = round(min(0.9, (p.confidence + result.confidence) / 2 + 0.1), 3)
            result.reason = f"{result.reason}; AI: {p.reason}"
            result.method = "rules+llm"

    result.alert = priority_alert(user_priority, result.system_priority)
    logger.info("priority_assessed", system_priority=result.system_priority, user_priority=user_priority,
                confidence=result.confidence, method=result.method, ticket_id=ticket_id)
    return result
