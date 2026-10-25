import { useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle, CheckCircle2, Circle, CircleSlash, Copy, Info, Loader2, ShieldAlert, UserCog,
} from "lucide-react";
import type { ActionView, Alert, ChatPayload, PriorityAssessment, ProgressStep, SolutionCandidate, TicketCard } from "../services/types";
import { Badge, KeyValue, SolutionLabel, StatusBadge, clock, sentenceCase } from "./ui";

/* ---------------- alerts ---------------- */
const ALERT_STYLE: Record<string, [string, typeof Info]> = {
  warning: ["border-warn-line bg-warn-soft text-warn-ink", AlertTriangle],
  info: ["border-info-line bg-info-soft text-info", Info],
  success: ["border-ok-line bg-ok-soft text-ok-ink", CheckCircle2],
  incident: ["border-crit-line bg-crit-soft text-crit-ink", AlertTriangle],
  duplicate: ["border-line bg-muted text-body", Copy],
  approval: ["border-warn-line bg-warn-soft text-warn-ink", ShieldAlert],
  escalation: ["border-violet-line bg-violet-soft text-violet", UserCog],
  error: ["border-crit-line bg-crit-soft text-crit-ink", AlertTriangle],
};

export function Alerts({ alerts }: { alerts?: Alert[] }) {
  if (!alerts?.length) return null;
  return (
    <div className="space-y-1.5">
      {alerts.map((a, i) => {
        const [cls, Icon] = ALERT_STYLE[a.type] || ALERT_STYLE.info;
        return (
          <div key={i} className={`flex items-start gap-2 rounded border px-3 py-2 text-[0.8125rem] leading-snug ${cls}`}>
            <Icon className="size-4 shrink-0 mt-px" /> <span>{a.message}</span>
          </div>
        );
      })}
    </div>
  );
}

/* ---------------- how the request was handled ---------------- */
// Routing levels of the agent (cheapest first), in words an employee or reviewer understands.
const ROUTING: Record<string, string> = {
  L0: "Company policy rule",
  L1: "Matched a known pattern",
  L2: "Similar past ticket",
  L3: "Fix verified by IT",
  L4: "Small language model",
  L5: "Large language model",
};

export function routingText(level: string | null | undefined): string {
  return level ? ROUTING[level.slice(0, 2)] || sentenceCase(level) : "Rules and search only";
}

export function TelemetryMatrix({ steps, routing, model, compact }:
  { steps: ProgressStep[]; routing?: string | null; model?: string | null; compact?: boolean }) {
  const done = steps.filter((s) => s.status === "done" || s.status === "skipped").length;
  return (
    <div className="card">
      <div className="card-header">
        <span className="text-sm font-semibold">Progress</span>
        <span className="text-xs text-meta whitespace-nowrap">{done} of {steps.length} done</span>
      </div>
      <ol className={`px-4 ${compact ? "py-2" : "py-3"} space-y-2`}>
        {steps.map((s) => {
          const running = s.status === "running";
          return (
            <li key={s.key} className="flex items-center gap-2.5 text-sm">
              {s.status === "done" ? <CheckCircle2 className="size-4 text-ok shrink-0" />
                : running ? <Loader2 className="size-4 text-cobalt animate-spin shrink-0" />
                  : s.status === "skipped" ? <CircleSlash className="size-4 text-faint shrink-0" />
                    : <Circle className="size-4 text-line-strong shrink-0" />}
              <span className={`flex-1 ${running ? "text-ink font-medium" : s.status === "pending" ? "text-meta" : "text-body"}`}>{s.label}</span>
              {s.status === "skipped" && <span className="text-xs text-faint">not needed</span>}
            </li>
          );
        })}
      </ol>
      <div className="border-t border-muted px-4 py-2 text-xs text-meta">
        Answered using: <span className="text-body">{routingText(routing)}</span>
        {model && <span className="text-faint"> ({model})</span>}
      </div>
    </div>
  );
}

/* ---------------- suggested fix ---------------- */
export function SolutionCard({ solution, active, onFixed, onTriage, busy }:
  { solution: SolutionCandidate; active?: boolean; onFixed?: () => void; onTriage?: () => void; busy?: boolean }) {
  const match = solution.similarity ?? solution.confidence;
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SolutionLabel label={solution.label} />
        <span className="text-xs text-meta">
          {solution.similarity !== null ? `${Math.round(match * 100)}% match` : `${Math.round(match * 100)}% confidence`}
          {solution.source_ticket && <> · from {solution.source_ticket}</>}
          {solution.sources.filter((s) => s.startsWith("KB")).map((s) => <span key={s}> · {s}</span>)}
        </span>
      </div>
      <p className="mt-3 font-semibold">{solution.title}</p>
      {solution.kind !== "kb_procedure" && <p className="text-sm text-body mt-1">{solution.summary}</p>}
      <ol className="mt-3 space-y-2 list-decimal pl-5 marker:text-meta">
        {solution.steps.map((s, i) => <li key={i} className="text-sm leading-snug text-body pl-1">{s}</li>)}
      </ol>
      {!!solution.safety_flags.length && (
        <p className="mt-3 flex items-center gap-1.5 text-xs text-warn-ink"><ShieldAlert className="size-3.5" /> {solution.safety_flags.length === 1 ? "One step was" : `${solution.safety_flags.length} steps were`} removed because it could be unsafe.</p>
      )}
      {active && (onFixed || onTriage) && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button className="btn-accent" disabled={busy} onClick={onFixed}><CheckCircle2 className="size-4" /> That fixed it</button>
          <button className="btn-outline" disabled={busy} onClick={onTriage}>Still not working</button>
        </div>
      )}
    </div>
  );
}

/* ---------------- approval request ---------------- */
export function ApprovalCard({ action, onDecide, disabled }:
  { action: ActionView; onDecide?: (approve: boolean) => Promise<void>; disabled?: boolean }) {
  const [busy, setBusy] = useState(false);
  const pending = action.status === "pending_approval";
  const decide = async (approve: boolean) => {
    if (!onDecide) return;
    setBusy(true);
    try { await onDecide(approve); } finally { setBusy(false); }
  };
  const dangerous = action.permission === "dangerous";
  const who = dangerous ? "an administrator" : "you";
  return (
    <div className={`rounded-lg border p-4 ${pending ? "border-warn-line bg-warn-soft/40" : "border-line bg-surface"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs text-meta">
            {pending ? "Approval needed" : `Request ${sentenceCase(action.status).toLowerCase()}`}
            {action.created_at && ` · ${clock(action.created_at)}`}
          </p>
          <p className="font-semibold mt-0.5">{action.label}</p>
        </div>
        {dangerous ? <Badge tone="crit">High risk</Badge> : <Badge tone="neutral">Low risk</Badge>}
      </div>
      <p className="text-sm text-body mt-2">{action.description}.</p>
      {action.risk_note && <p className="text-xs text-meta mt-1">{action.risk_note}.</p>}
      {pending && <p className="text-xs text-meta mt-2">Nothing runs until {who} {dangerous ? "approves" : "approve"} it.</p>}
      {action.result?.summary && !pending && (
        <p className="mt-2 rounded border border-line bg-canvas px-3 py-2 text-xs text-body">{action.result.summary}</p>
      )}
      {pending && onDecide && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button className="btn-accent" disabled={busy || disabled} onClick={() => decide(true)}>
            {busy && <Loader2 className="size-4 animate-spin" />} Approve
          </button>
          <button className="btn-outline" disabled={busy || disabled} onClick={() => decide(false)}>Decline</button>
        </div>
      )}
    </div>
  );
}

/* ---------------- ticket summary ---------------- */
export function TicketContextCard({ ticket, assessment }: { ticket: TicketCard; assessment?: PriorityAssessment }) {
  const system = ticket.system_priority || ticket.priority;
  const changed = ticket.user_priority && system && ticket.user_priority !== system;
  return (
    <div className="card">
      <div className="card-header">
        <Link to={`/tickets/${ticket.id}`} className="min-w-0 hover:text-cobalt">
          <span className="text-sm font-semibold block">Your ticket</span>
          <span className="mono text-xs text-cobalt">{ticket.number}</span>
        </Link>
        <StatusBadge status={ticket.status} />
      </div>
      <div className="p-3 space-y-1.5">
        <KeyValue k="Category" v={ticket.category || "General"} />
        {(ticket.sub_category || ticket.intent) && <KeyValue k="Issue type" v={ticket.sub_category || sentenceCase(ticket.intent)} />}
        {ticket.user_priority && <KeyValue k="You said" v={sentenceCase(ticket.user_priority)} />}
        <KeyValue k={changed ? "Priority set to" : "Priority"} v={<span className="font-medium">{sentenceCase(system)}</span>} />
        {ticket.department && <KeyValue k="Team" v={ticket.department} />}
        {assessment && (
          <p className="pt-1 text-xs text-meta leading-relaxed">
            {changed ? "Why the priority changed: " : "Why this priority: "}{assessment.impact}; {assessment.reason}.
          </p>
        )}
      </div>
    </div>
  );
}

/* ---------------- chat header ---------------- */
export function SessionHeader({ conversationId, payload }: { conversationId: number | null; payload?: ChatPayload }) {
  const t = payload?.ticket;
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line pb-3">
      <div className="min-w-0">
        <p className="font-semibold leading-tight">IT support assistant</p>
        <p className="text-xs text-meta truncate">
          {t ? <>Working on <span className="mono">{t.number}</span> · {t.category}</> : "Describe what is not working and the assistant will take it from there."}
        </p>
      </div>
      {conversationId !== null && <span className="text-xs text-faint shrink-0">Conversation {conversationId}</span>}
    </div>
  );
}

export function SimilarList({ items }: { items?: { number: string; title: string; status: string; similarity: number }[] }) {
  if (!items?.length) return null;
  return (
    <div className="card">
      <div className="card-header"><span className="text-sm font-semibold">Similar past tickets</span></div>
      <ul className="divide-y divide-muted">
        {items.map((s) => (
          <li key={s.number} className="px-4 py-2.5 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="mono text-xs text-cobalt">{s.number}</p>
              <p className="text-sm truncate">{s.title}</p>
            </div>
            <span className="text-xs text-meta shrink-0 tabular-nums">{Math.round(s.similarity * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
