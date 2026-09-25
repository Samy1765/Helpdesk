"""
Precision AI - Solution candidates and grounded generation (the "G" of RAG).

Every candidate carries a provenance label shown to the user:
  VERIFIED SOLUTION          admin-verified solution or official IT documentation
  HUMAN-APPROVED SOLUTION    verified by an IT support engineer
  USER-CONFIRMED SOLUTION    worked for other users, not yet reviewed by IT
  AI-GENERATED SUGGESTION    produced by an LLM (grounded in cited KB sources when available)

The LLM is instructed to use ONLY the supplied context; its JSON is schema-validated, its
citations must reference supplied sources, and every step passes the safety filter.
"""

from dataclasses import asdict, dataclass, field
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm import router as llm
from app.models.ticket import SolutionConfidence, Ticket
from app.rag.retriever import ChunkHit, Retrieval, SolutionHit
from app.services.knowledge import steps_from_text
from app.tools.registry import get_tool
from app.tools.safety import filter_steps, screen_text

logger = get_logger(__name__)

LABELS = {
    SolutionConfidence.ADMIN_VERIFIED: "VERIFIED SOLUTION",
    SolutionConfidence.HUMAN_VERIFIED: "HUMAN-APPROVED SOLUTION",
    SolutionConfidence.USER_CONFIRMED: "USER-CONFIRMED SOLUTION",
    SolutionConfidence.AI_GENERATED: "AI-GENERATED SUGGESTION",
}


@dataclass
class Candidate:
    kind: str  # solution | kb_procedure | ai_grounded | ai_generated
    label: str
    title: str
    summary: str
    steps: list[str]
    routing_level: str
    confidence: float
    solution_id: Optional[int] = None
    source_ticket: Optional[str] = None
    sources: list[str] = field(default_factory=list)
    automated_actions: list[str] = field(default_factory=list)
    similarity: Optional[float] = None
    model: Optional[str] = None
    safety_flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


class GeneratedSolution(BaseModel):
    summary: str = Field(min_length=10, max_length=600)
    steps: list[str] = Field(min_length=1, max_length=8)
    sources: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    can_resolve: bool = True


def from_solution(hit: SolutionHit, routing_level: str) -> Candidate:
    s = hit.solution
    steps, flags = filter_steps(list(s.steps or []) or steps_from_text(s.solution_description))
    actions = [a for a in (s.automated_actions or []) if get_tool(a) is not None]
    return Candidate(
        kind="solution", label=LABELS.get(s.confidence_level, "USER-CONFIRMED SOLUTION"), title=s.title,
        summary=s.solution_description, steps=steps, routing_level=routing_level,
        confidence=round(min(0.99, hit.score), 3), solution_id=s.id, source_ticket=hit.source_ticket_number,
        sources=[f"SOL-{s.id}"], automated_actions=actions, similarity=round(hit.similarity, 3),
        safety_flags=flags,
    )


def from_chunk(hit: ChunkHit) -> Candidate:
    """Deterministic fallback when no LLM is available: present the documented procedure verbatim."""
    steps, flags = filter_steps(steps_from_text(hit.chunk.content))
    title = hit.chunk.document.title + (f" - {hit.chunk.heading}" if hit.chunk.heading else "")
    return Candidate(
        kind="kb_procedure", label="VERIFIED SOLUTION", title=title,
        summary=f"Documented procedure from the IT knowledge base ({hit.ref}).", steps=steps,
        routing_level="L3_verified_retrieval", confidence=round(hit.similarity, 3), sources=[hit.ref],
        similarity=round(hit.similarity, 3), safety_flags=flags,
    )


SYSTEM_GROUNDED = (
    "You are an IT support troubleshooting assistant. Using ONLY the numbered context sources, write "
    "clear steps an employee can safely perform themselves. Never invent procedures, commands, URLs or "
    "phone numbers that are not in the context. Never ask for passwords or MFA codes. Never suggest "
    "disabling security software, deleting system files, editing the registry or running admin commands. "
    "If the context does not cover the issue, set can_resolve to false. Respond ONLY with JSON: "
    '{"summary": "...", "steps": ["..."], "sources": ["KB-1"], "confidence": 0-1, "can_resolve": true}'
)

SYSTEM_UNGROUNDED = (
    "You are an IT support troubleshooting assistant. No verified documentation matched this issue. "
    "Suggest only generic, low-risk, user-level checks (restart the app, check connectivity, sign out/in, "
    "update). Never ask for passwords or MFA codes, never suggest disabling security software, deleting "
    "files, editing the registry or running admin commands. If unsure, set can_resolve to false. "
    'Respond ONLY with JSON: {"summary": "...", "steps": ["..."], "sources": [], "confidence": 0-1, '
    '"can_resolve": true}'
)


def _issue_block(ticket: Ticket, previous: list[Candidate], evidence: list[dict]) -> str:
    lines = [f"Ticket: {ticket.title}", f"Category: {ticket.category_name}", f"Description: {ticket.description[:1500]}"]
    if ticket.entities:
        lines.append("Details: " + ", ".join(f"{k}={v}" for k, v in ticket.entities.items()))
    if evidence:
        lines.append("Automated check results: " + "; ".join(f"{e['tool']}: {e['summary']}" for e in evidence[:6]))
    if previous:
        lines.append("Already tried WITHOUT success (do not repeat): " + " | ".join(
            "; ".join(c.steps[:4]) for c in previous))
    return "\n".join(lines)


async def generate(db: AsyncSession, ticket: Ticket, retrieval: Retrieval, *, previous: list[Candidate],
                   evidence: list[dict], tier: str, run_id: Optional[int]) -> Optional[Candidate]:
    """LEVEL 4/5: grounded generation when context exists, otherwise a generic low-risk suggestion."""
    context_items: list[tuple[str, str]] = [
        (h.ref, f"{h.chunk.document.title}: {h.chunk.content}") for h in retrieval.chunks[:4]
    ] + [
        (f"SOL-{h.solution.id}", f"{h.solution.title}: {h.solution.solution_description}")
        for h in retrieval.solutions[:2]
    ]
    grounded = bool(context_items)
    prompt = _issue_block(ticket, previous, evidence)
    if grounded:
        prompt = "Context sources:\n" + "\n\n".join(f"[{ref}] {txt[:1200]}" for ref, txt in context_items) \
                 + "\n\n" + prompt
    res = await llm.complete(
        db=db, purpose="troubleshooting", tier=tier, prompt=prompt,
        system_prompt=SYSTEM_GROUNDED if grounded else SYSTEM_UNGROUNDED, schema=GeneratedSolution,
        max_tokens=700, temperature=0.2, ticket_id=ticket.id, agent_run_id=run_id,
    )
    if res is None or res.parsed is None:
        return None
    out: GeneratedSolution = res.parsed  # type: ignore[assignment]
    if not out.can_resolve:
        return None

    valid_refs = {ref for ref, _ in context_items}
    cited = [s for s in out.sources if s in valid_refs]
    if grounded and not cited:
        logger.warning("generation_rejected_no_valid_citation", ticket_id=ticket.id)
        return None
    steps, flags = filter_steps(out.steps)
    if screen_text(out.summary):
        flags = sorted(set(flags + screen_text(out.summary)))
        out.summary = "Suggested troubleshooting steps."
    if not steps:
        return None
    if flags:
        logger.warning("unsafe_generated_steps_removed", ticket_id=ticket.id, flags=flags)

    level = "L4_small_llm" if res.tier == llm.SMALL else "L5_large_llm"
    return Candidate(
        kind="ai_grounded" if grounded else "ai_generated", label="AI-GENERATED SUGGESTION",
        title=ticket.title, summary=out.summary, steps=steps, routing_level=level,
        confidence=round(out.confidence * (0.85 if grounded else 0.6), 3), sources=cited,
        model=f"{res.provider}:{res.model}", safety_flags=flags,
    )
