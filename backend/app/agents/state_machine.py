"""
Precision AI - Agent state machine definition.

  NEW -> UNDERSTAND -> CLASSIFY -> CHECK_DUPLICATE -> SEARCH_HISTORY -> PLAN -> TROUBLESHOOT -> VERIFY
                                        |  |                               |          |           |
                                        |  +-> LINKED_INCIDENT             +-> ESCALATE <---------+-> RETRY -> TROUBLESHOOT
                                        +----> DUPLICATE                                          +-> RESOLVED
  ESCALATE -> ESCALATED

Duplicate/incident checks run before the knowledge search so that repeated reports stop early and
cost nothing. Any non-terminal state may move to CLOSED when a human takes the ticket over.
"""

from enum import StrEnum


class AgentState(StrEnum):
    NEW = "new"
    UNDERSTAND = "understand"
    CLASSIFY = "classify"
    CHECK_DUPLICATE = "check_duplicate"
    SEARCH_HISTORY = "search_history"
    PLAN = "plan"
    TROUBLESHOOT = "troubleshoot"
    VERIFY = "verify"
    RETRY = "retry"
    ESCALATE = "escalate"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    DUPLICATE = "duplicate"
    LINKED_INCIDENT = "linked_incident"
    CLOSED = "closed"


S = AgentState

TRANSITIONS: dict[AgentState, set[AgentState]] = {
    S.NEW: {S.UNDERSTAND},
    S.UNDERSTAND: {S.CLASSIFY},
    S.CLASSIFY: {S.CHECK_DUPLICATE},
    S.CHECK_DUPLICATE: {S.SEARCH_HISTORY, S.DUPLICATE, S.LINKED_INCIDENT},
    S.SEARCH_HISTORY: {S.PLAN},
    S.PLAN: {S.TROUBLESHOOT, S.ESCALATE},
    S.TROUBLESHOOT: {S.VERIFY, S.ESCALATE},
    S.VERIFY: {S.RESOLVED, S.RETRY, S.ESCALATE, S.LINKED_INCIDENT},
    S.RETRY: {S.TROUBLESHOOT, S.ESCALATE},
    S.ESCALATE: {S.ESCALATED},
    S.RESOLVED: set(),
    S.ESCALATED: set(),
    S.DUPLICATE: set(),
    S.LINKED_INCIDENT: set(),
    S.CLOSED: set(),
}

TERMINAL = {s for s, nxt in TRANSITIONS.items() if not nxt}


class InvalidTransition(Exception):
    pass


def can_transition(current: str, target: str) -> bool:
    cur, tgt = AgentState(current), AgentState(target)
    if tgt == S.CLOSED:
        return cur not in TERMINAL
    return tgt in TRANSITIONS[cur]


def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise InvalidTransition(f"{current} -> {target} is not allowed")


# User-facing progress checklist (high-level status only, never internal reasoning)
PROGRESS_STEPS: list[tuple[str, str]] = [
    ("understand", "Understanding issue"),
    ("classify", "Classifying category"),
    ("priority", "Validating priority"),
    ("duplicates", "Checking duplicate tickets"),
    ("knowledge", "Searching knowledge base"),
    ("troubleshoot", "Troubleshooting"),
    ("verify", "Verification"),
    ("outcome", "Resolution / escalation"),
]
