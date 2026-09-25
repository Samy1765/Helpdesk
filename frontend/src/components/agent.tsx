import { useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle, BadgeCheck, CheckCircle2, CircleDashed, CircleSlash, Copy, GitMerge, Info, Loader2, Lock,
  Network, Play, ShieldAlert, ShieldCheck, UserCog, Zap,
} from "lucide-react";
import type { ActionView, Alert, ChatPayload, PriorityAssessment, ProgressStep, SolutionCandidate, TicketCard } from "../services/types";
import { Badge, KeyValue, SolutionLabel, pct, priorityTone, titleCase } from "./ui";

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

/* ---------------- autonomous telemetry matrix ---------------- */
export function TelemetryMatrix({ steps, routing, model, compact }:
  { steps: ProgressStep[]; routing?: string | null; model?: string | null; compact?: boolean }) {
  const current = steps.findIndex((s) => s.status === "running");
  const doneCount = steps.filter((s) => s.status === "done" || s.status === "skipped").length;
  const stepNo = current >= 0 ? current + 1 : Math.min(steps.length, doneCount);
  return (
    <div className="card">
      <div className="card-header">
        <span className="label-caps !text-ink flex items-center gap-2"><Network className="size-4 text-cobalt" /> Autonomous telemetry matrix</span>
        <span className="code-chip !text-[0.6875rem] whitespace-nowrap">Step {stepNo} of {steps.length}</span>
      </div>
      <ol className={`px-3 ${compact ? "py-2" : "py-3"} space-y-1`}>
        {steps.map((s, i) => {
          const running = s.status === "running";
          return (
            <li key={s.key} className={`flex items-center gap-2.5 rounded px-2 py-1.5 text-sm ${running ? "border border-cobalt-line bg-cobalt-soft" : ""}`}>
              {s.status === "done" ? <CheckCircle2 className="size-4 text-ok shrink-0" />
                : running ? <span className="flex size-4 items-center justify-center"><span className="dot bg-cobalt animate-pulse-dot" /></span>
                  : s.status === "skipped" ? <CircleSlash className="size-4 text-faint shrink-0" />
                    : <CircleDashed className="size-4 text-faint shrink-0" />}
              <span className={`flex-1 ${running ? "text-cobalt font-medium" : s.status === "pending" ? "text-meta" : "text-body"}`}>{i + 1}. {s.label}</span>
              <span className={`mono text-[0.6875rem] ${running ? "" : "text-meta"}`}>
                {running ? <Badge tone="cobalt">RUNNING</Badge> : s.status === "done" ? "done" : s.status === "skipped" ? "skipped" : "pending"}
              </span>
            </li>
          );
        })}
      </ol>
      <div className="border-t border-muted px-4 py-2 flex flex-wrap justify-between gap-x-4 gap-y-1 mono text-[0.625rem] uppercase text-meta">
        <span>Engine: {routing ? routing.replace(/_/g, " ") : "rules + faiss"}</span>
        <span>Runtime: {model || "deterministic · no LLM call"}</span>
      </div>
    </div>
  );
}

/* ---------------- diagnostic match / solution ---------------- */
export function SolutionCard({ solution, active, onFixed, onTriage, busy }:
  { solution: SolutionCandidate; active?: boolean; onFixed?: () => void; onTriage?: () => void; busy?: boolean }) {
  const match = solution.similarity ?? solution.confidence;
  const isReuse = solution.kind === "solution" || solution.kind === "kb_procedure";
  return (
    <div className="rounded-lg border border-cobalt-line bg-[#f5f9ff] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="label-caps !text-ink flex items-center gap-2">
          {isReuse ? <BadgeCheck className="size-4 text-cobalt" /> : <Zap className="size-4 text-warn" />}
          {isReuse ? "Exact diagnostic match" : "Suggested remediation"}
        </span>
        <Badge tone="cobalt" mono>{Math.round(match * 100)}% {solution.similarity !== null ? "similarity" : "confidence"}</Badge>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <SolutionLabel label={solution.label} />
        {solution.source_ticket && <span className="text-xs text-meta">from <span className="code-chip">{solution.source_ticket}</span></span>}
        {solution.sources.filter((s) => s.startsWith("KB")).map((s) => <span key={s} className="code-chip">{s}</span>)}
      </div>
      <p className="mt-2.5 font-display font-semibold text-[0.95rem]">{solution.title}</p>
      {solution.kind !== "kb_procedure" && <p className="text-sm text-body mt-1">{solution.summary}</p>}
      <div className="mt-3 rounded border border-cobalt-line bg-surface p-3">
        <p className="label-caps !text-cobalt mb-2">{isReuse ? "Resolution protocol" : "Suggested steps"}</p>
        <ol className="space-y-1.5">
          {solution.steps.map((s, i) => (
            <li key={i} className="flex gap-2 text-[0.8125rem] leading-snug text-body">
              <span className="mono text-cobalt font-semibold shrink-0">{String(i + 1).padStart(2, "0")}</span><span>{s}</span>
            </li>
          ))}
        </ol>
      </div>
      {!!solution.safety_flags.length && (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-warn-ink"><ShieldAlert className="size-3.5" /> {solution.safety_flags.length} unsafe step(s) were removed by the safety filter.</p>
      )}
      {active && (onFixed || onTriage) && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button className="btn-accent" disabled={busy} onClick={onFixed}><CheckCircle2 className="size-4" /> It worked</button>
          <button className="btn-outline" disabled={busy} onClick={onTriage}><UserCog className="size-4" /> Manual triage</button>
        </div>
      )}
    </div>
  );
}

/* ---------------- human approval gate ---------------- */
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
  return (
    <div className={`rounded-lg border p-4 ${pending ? "border-warn-line bg-[#fffdf5]" : "border-line bg-surface"}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex gap-2.5">
          <span className={`flex size-8 shrink-0 items-center justify-center rounded-md border ${dangerous ? "border-crit-line bg-crit-soft text-crit" : "border-warn-line bg-warn-soft text-warn"}`}>
            <ShieldAlert className="size-4" />
          </span>
          <div>
            <p className="label-caps !text-ink">{pending ? "Human approval required" : `Action ${titleCase(action.status)}`}</p>
            <p className="text-xs text-meta mt-0.5">{dangerous ? "Dangerous action · administrator approval" : "Tier-1 automated remediation action"}</p>
          </div>
        </div>
        <span className="code-chip">GATE-{action.id}</span>
      </div>
      <div className="mt-3 space-y-1.5">
        <KeyValue k="Target task" v={<span className="font-medium">{action.label}</span>} />
        <KeyValue k="Safety level" v={
          <span className={`inline-flex items-center gap-1 text-xs font-semibold ${dangerous ? "text-crit" : "text-ok-ink"}`}>
            {dangerous ? <ShieldAlert className="size-3.5" /> : <Lock className="size-3.5" />}
            {dangerous ? "HIGH RISK" : "LOW RISK"}{action.risk_note ? ` (${action.risk_note})` : ""}
          </span>} />
      </div>
      <p className="text-[0.8125rem] text-body mt-2.5">{action.description}. Nothing runs until {dangerous ? "an administrator approves" : "you authorise it"}.</p>
      {action.result?.summary && !pending && (
        <p className="mt-2 rounded border border-line bg-canvas px-3 py-2 mono text-xs text-body">
          {action.result.summary}
        </p>
      )}
      {pending && onDecide && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button className="btn-outline" disabled={busy || disabled} onClick={() => decide(false)}>Dismiss</button>
          <button className="btn-accent" disabled={busy || disabled} onClick={() => decide(true)}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-3.5" />} Authorize safe fix
          </button>
        </div>
      )}
    </div>
  );
}

/* ---------------- ticket context ---------------- */
export function TicketContextCard({ ticket, assessment }: { ticket: TicketCard; assessment?: PriorityAssessment }) {
  const downgraded = ticket.user_priority && ticket.system_priority && ticket.user_priority !== ticket.system_priority;
  return (
    <div className="card">
      <div className="card-header">
        <Link to={`/tickets/${ticket.id}`} className="min-w-0 hover:text-cobalt">
          <span className="label-caps !text-ink block">Ticket context</span>
          <span className="mono text-xs text-cobalt">#{ticket.number}</span>
        </Link>
        <Badge tone="cobalt" mono>{ticket.status.toUpperCase()}</Badge>
      </div>
      <div className="p-3 space-y-1.5">
        <KeyValue k="Intent category" v={(ticket.intent || ticket.category || "general").toUpperCase()} mono />
        {ticket.user_priority && (
          <KeyValue k="Submitted priority" v={<span className={`mono text-[0.8125rem] font-semibold ${priorityTone(ticket.user_priority)}`}>{ticket.user_priority.toUpperCase()} (User)</span>} />
        )}
        <KeyValue k="Normalized priority" v={<span className="mono text-[0.8125rem] font-semibold text-cobalt">{(ticket.system_priority || ticket.priority).toUpperCase()} (Precision AI)</span>} />
        {ticket.department && <KeyValue k="Routed to" v={ticket.department} />}
        {assessment && (
          <div className="rounded border border-line bg-canvas p-3 text-[0.8125rem] text-body leading-snug">
            <span className="font-semibold text-ink">{downgraded ? "AI priority reasoning: " : "Priority reasoning: "}</span>
            {assessment.impact}; {assessment.reason}. Urgency: {assessment.urgency}.
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- session header (chat top card) ---------------- */
const RANK: Record<string, number> = { low: 0, medium: 1, high: 2, critical: 3 };
const SHORT: Record<string, string> = { low: "LOW", medium: "MED", high: "HIGH", critical: "CRIT" };

export function SessionHeader({ conversationId, payload }: { conversationId: number | null; payload?: ChatPayload }) {
  const t = payload?.ticket;
  const cls = payload?.classification;
  const system = cls?.entities?.application || cls?.entities?.os || t?.category || "Awaiting input";
  const p = t?.system_priority || t?.priority;
  const drift = t?.user_priority && p && t.user_priority !== p;
  return (
    <div className="card p-3.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="relative flex size-9 items-center justify-center rounded-md border border-cobalt-line bg-cobalt-soft text-cobalt">
            <ShieldCheck className="size-4" />
            <span className="absolute -top-0.5 -right-0.5 dot size-2.5 bg-ok border-2 border-white" />
          </span>
          <div className="min-w-0">
            <p className="font-display font-semibold leading-tight flex items-center gap-2">Precision AI Agent <Badge tone="ok">ONLINE</Badge></p>
            <p className="mono text-[0.6875rem] text-meta truncate">Session #S-{conversationId ?? "-"} · Continuous observability</p>
          </div>
        </div>
        <GitMerge className="size-4 text-faint" />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <div className="rounded border border-line bg-canvas px-2.5 py-2 min-w-0">
          <p className="label-caps !text-[0.625rem]">System</p>
          <p className="mono text-xs font-medium truncate">{system}</p>
        </div>
        <div className="rounded border border-line bg-canvas px-2.5 py-2 min-w-0">
          <p className="label-caps !text-[0.625rem]">Priority</p>
          <p className={`mono text-xs font-semibold truncate ${priorityTone(p)}`}>
            {p ? SHORT[p] : "-"}{drift ? ` (AI ${RANK[t!.user_priority!] > RANK[p!] ? "↓" : "↑"} from ${SHORT[t!.user_priority!]})` : ""}
          </p>
        </div>
        <div className="rounded border border-line bg-canvas px-2.5 py-2 min-w-0">
          <p className="label-caps !text-[0.625rem]">Confidence</p>
          <p className="mono text-xs font-medium truncate">{t?.confidence ? `${pct(t.confidence, 1)} Index` : "-"}</p>
        </div>
      </div>
    </div>
  );
}

export function SimilarList({ items }: { items?: { number: string; title: string; status: string; similarity: number }[] }) {
  if (!items?.length) return null;
  return (
    <div className="card">
      <div className="card-header"><span className="label-caps !text-ink">Similar historical tickets</span></div>
      <ul className="divide-y divide-muted">
        {items.map((s) => (
          <li key={s.number} className="px-4 py-2.5 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="mono text-xs text-cobalt">{s.number}</p>
              <p className="text-sm truncate">{s.title}</p>
            </div>
            <span className="mono text-xs text-meta shrink-0">{Math.round(s.similarity * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
