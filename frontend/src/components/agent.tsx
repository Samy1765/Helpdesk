import { useState } from "react";
import { Link } from "react-router-dom";
import { Check, CircleDashed, Loader2, Minus, ShieldAlert } from "lucide-react";
import type { ActionView, Alert, PriorityAssessment, ProgressStep, SolutionCandidate, TicketCard } from "../services/types";
import { dateTime, percent } from "../lib/format";
import { Card, DefinitionList, Notice, PriorityBadge, StatusBadge, TicketId, TrustBadge, priorityLabel, provenance } from "./ui";

/* ---------------- alerts from the agent ---------------- */
const ALERT_TONE: Record<Alert["type"], "info" | "ok" | "warn" | "crit"> = {
  warning: "warn", info: "info", success: "ok", incident: "warn", duplicate: "info", approval: "warn",
  escalation: "info", error: "crit",
};

export function Alerts({ alerts }: { alerts?: Alert[] }) {
  if (!alerts?.length) return null;
  return <div className="space-y-2">{alerts.map((a, i) => <Notice key={i} tone={ALERT_TONE[a.type] || "info"}>{a.message}</Notice>)}</div>;
}

/* ---------------- progress checklist ---------------- */
const ROUTING: Record<string, string> = {
  L0_policy: "Sent straight to the owning team by policy",
  L1_rules: "Classified by rules",
  L2_similarity: "Matched to an existing ticket or incident",
  L3_verified_retrieval: "Known fix reused, no AI model needed",
  L4_small_llm: "Answer drafted by the small AI model",
  L5_large_llm: "Answer drafted by the large AI model",
};

export function ProgressChecklist({ steps, routing }: { steps: ProgressStep[]; routing?: string | null }) {
  const done = steps.filter((s) => s.status === "done" || s.status === "skipped").length;
  return (
    <Card title="Progress" actions={<span className="text-xs text-meta">{done} of {steps.length} steps</span>}>
      <ol className="space-y-2">
        {steps.map((s) => (
          <li key={s.key} className="flex items-center gap-2 text-sm">
            {s.status === "done" ? <Check className="size-4 text-ok" aria-hidden />
              : s.status === "running" ? <Loader2 className="size-4 animate-spin text-brand" aria-hidden />
                : s.status === "skipped" ? <Minus className="size-4 text-faint" aria-hidden />
                  : <CircleDashed className="size-4 text-faint" aria-hidden />}
            <span className={s.status === "pending" || s.status === "skipped" ? "text-meta" : "text-ink"}>{s.label}</span>
            <span className="sr-only">: {s.status}</span>
            {s.status === "skipped" && <span className="text-xs text-meta">not needed</span>}
          </li>
        ))}
      </ol>
      {routing && <p className="mt-4 border-t border-line pt-2 text-xs text-meta">{ROUTING[routing] || routing}</p>}
    </Card>
  );
}

/* ---------------- suggested fix ---------------- */
export function SolutionCard({ solution, onFixed, onNotFixed, busy }:
  { solution: SolutionCandidate; onFixed?: () => void; onNotFixed?: () => void; busy?: boolean }) {
  const match = solution.similarity ?? solution.confidence;
  const fromKb = solution.kind === "kb_procedure";
  const ai = solution.kind === "ai_grounded" || solution.kind === "ai_generated";
  return (
    <section className="card" aria-label="Suggested fix">
      <div className="card-header flex-wrap">
        <h3 className="card-title">Suggested fix</h3>
        <div className="flex items-center gap-2">
          <TrustBadge level={provenance(solution.label)} />
          <span className="text-xs text-meta">{percent(match)} match</span>
        </div>
      </div>
      <div className="p-4">
        <p className="font-medium text-ink">{solution.title}</p>
        <p className="mt-1 text-xs text-meta">
          {fromKb ? "From the IT knowledge base"
            : ai ? `AI-written from ${solution.sources.length ? solution.sources.join(", ") : "general guidance"}; not yet reviewed by IT`
              : solution.source_ticket ? `Worked for ${solution.source_ticket}` : "Verified by the IT team"}
        </p>
        {!fromKb && solution.summary && !solution.summary.startsWith("Verified fix:") && <p className="mt-2 text-sm text-body">{solution.summary}</p>}
        <ol className="mt-4 space-y-2">
          {solution.steps.map((s, i) => (
            <li key={i} className="flex gap-2 text-sm text-body">
              <span className="mono w-4 shrink-0 text-right text-meta">{i + 1}.</span><span>{s}</span>
            </li>
          ))}
        </ol>
        {!!solution.safety_flags.length && (
          <p className="mt-2 flex items-center gap-1 text-xs text-warn"><ShieldAlert className="size-4" aria-hidden />
            {solution.safety_flags.length} unsafe step{solution.safety_flags.length === 1 ? " was" : "s were"} removed before showing this.</p>
        )}
        {(onFixed || onNotFixed) && (
          <div className="mt-4 flex flex-wrap gap-2">
            {onFixed && <button className="btn-primary" disabled={busy} onClick={onFixed}>This fixed it</button>}
            {onNotFixed && <button className="btn-secondary" disabled={busy} onClick={onNotFixed}>Still not working</button>}
          </div>
        )}
      </div>
    </section>
  );
}

/* ---------------- approval request ---------------- */
export function ApprovalCard({ action, onDecide, disabled, viewer = "requester" }:
  { action: ActionView; onDecide?: (approve: boolean) => Promise<void>; disabled?: boolean; viewer?: "requester" | "staff" }) {
  const [busy, setBusy] = useState(false);
  const pending = action.status === "pending_approval";
  const decide = async (approve: boolean) => {
    if (!onDecide) return;
    setBusy(true);
    try { await onDecide(approve); } finally { setBusy(false); }
  };
  const dangerous = action.permission === "dangerous";
  return (
    <section className={`card ${pending ? "border-warn-line" : ""}`} aria-label={`Approval: ${action.label}`}>
      <div className="p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="text-sm font-semibold text-ink">{pending ? (dangerous ? "Administrator approval needed" : viewer === "staff" ? "Waiting for approval" : "Your approval is needed") : action.label}</p>
            <p className="mt-1 text-sm text-body">
              <span className="font-medium text-ink">{action.label}:</span> {action.description}.{action.risk_note ? ` ${action.risk_note}.` : ""}
            </p>
          </div>
          {!pending && <StatusBadge status={action.status} />}
        </div>
        {pending && (
          <p className="mt-2 text-xs text-meta">
            Nothing runs until {dangerous ? "an administrator approves it" : viewer === "staff" ? "the employee or IT approves it" : "you approve it"}. Requested {dateTime(action.created_at)}.
          </p>
        )}
        {action.result?.summary && !pending && <p className="mt-2 text-xs text-meta">{action.result.summary}</p>}
        {pending && onDecide && (
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="btn-primary" disabled={busy || disabled} onClick={() => decide(true)}>{busy && <Loader2 className="size-4 animate-spin" aria-hidden />} Approve</button>
            <button className="btn-secondary" disabled={busy || disabled} onClick={() => decide(false)}>Decline</button>
          </div>
        )}
      </div>
    </section>
  );
}

/* ---------------- ticket summary beside the chat ---------------- */
export function TicketSummary({ ticket, assessment }: { ticket: TicketCard; assessment?: PriorityAssessment }) {
  const changed = ticket.user_priority && ticket.system_priority && ticket.user_priority !== ticket.system_priority;
  return (
    <Card title={<h2 className="card-title flex items-center gap-2">Ticket <TicketId number={ticket.number} to={`/tickets/${ticket.id}`} /></h2>}
      actions={<StatusBadge status={ticket.status} />}>
      <DefinitionList items={[
        ["Category", `${ticket.category || "General"}${ticket.sub_category ? ` · ${ticket.sub_category}` : ""}`],
        ["Priority", <span className="flex flex-wrap items-center gap-2"><PriorityBadge priority={ticket.priority} />
          {changed && <span className="text-xs text-meta">you chose {priorityLabel(ticket.user_priority).toLowerCase()}</span>}</span>],
        ...(ticket.department ? [["Team", ticket.department] as [string, string]] : []),
      ]} />
      {assessment && <p className="mt-4 border-t border-line pt-2 text-xs text-meta">Why this priority: {assessment.impact}. {assessment.reason}.</p>}
    </Card>
  );
}

export function SimilarList({ items }: { items?: { number: string; title: string; status: string; similarity: number }[] }) {
  if (!items?.length) return null;
  return (
    <Card title="Similar tickets" bodyClassName="">
      <ul className="divide-y divide-line">
        {items.map((s) => (
          <li key={s.number} className="flex items-start justify-between gap-4 px-4 py-2">
            <span className="min-w-0">
              <span className="block mono text-xs text-meta">{s.number}</span>
              <span className="block truncate text-sm text-ink">{s.title}</span>
            </span>
            <span className="shrink-0 text-xs text-meta">{percent(s.similarity)}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function EscalationNote({ department, assignee }: { department: string; assignee: string | null }) {
  return (
    <Notice tone="info">
      Passed to <span className="font-medium">{department}</span>{assignee ? `, assigned to ${assignee}` : ", waiting to be assigned"}.
      They can see everything tried so far.
    </Notice>
  );
}

export function IncidentLink({ number, title }: { number: string; title: string }) {
  return (
    <Notice tone="warn" action={<Link to={`/incidents?number=${number}`} className="btn-secondary btn-sm">View incident</Link>}>
      Part of <span className="mono font-medium">{number}</span>: {title}
    </Notice>
  );
}
