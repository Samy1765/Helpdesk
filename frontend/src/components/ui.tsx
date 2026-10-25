import { Fragment, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, CheckCircle2, Info, Loader2, RotateCw } from "lucide-react";
import type { Priority } from "../services/types";
import type { Tone } from "../lib/format";

/* ---------------- labels ---------------- */
const TONES: Record<Tone | "critSolid", string> = {
  neutral: "bg-muted border-line text-body",
  brand: "bg-brand-soft border-brand-line text-brand",
  ok: "bg-ok-soft border-ok-line text-ok",
  warn: "bg-warn-soft border-warn-line text-warn",
  crit: "bg-crit-soft border-crit-line text-crit",
  critSolid: "bg-crit border-crit text-white",
};

export function Badge({ tone = "neutral", children, className = "" }:
  { tone?: Tone | "critSolid"; children: ReactNode; className?: string }) {
  return <span className={`badge ${TONES[tone]} ${className}`}>{children}</span>;
}

const STATUS: Record<string, [string, Tone]> = {
  new: ["New", "neutral"],
  ai_analysis: ["Agent working", "brand"],
  troubleshooting: ["Agent working", "brand"],
  awaiting_user: ["Waiting on employee", "warn"],
  awaiting_approval: ["Waiting for approval", "warn"],
  escalated: ["Escalated", "brand"],
  assigned: ["Assigned", "brand"],
  in_progress: ["In progress", "brand"],
  resolved: ["Resolved", "ok"],
  closed: ["Closed", "neutral"],
  duplicate: ["Duplicate", "neutral"],
  linked_incident: ["Part of incident", "warn"],
  active: ["Active", "crit"],
  investigating: ["Investigating", "warn"],
  pending_approval: ["Waiting for approval", "warn"],
  approved: ["Approved", "ok"],
  rejected: ["Declined", "neutral"],
};

export function statusLabel(status: string): string {
  return (STATUS[status] || [status.replace(/_/g, " ")])[0];
}

export function StatusBadge({ status }: { status: string }) {
  const [label, tone] = STATUS[status] || [status.replace(/_/g, " "), "neutral" as Tone];
  return <Badge tone={tone}>{label}</Badge>;
}

const PRIORITY: Record<Priority, [string, Tone | "critSolid"]> = {
  critical: ["Critical", "critSolid"], high: ["High", "crit"], medium: ["Medium", "warn"], low: ["Low", "neutral"],
};

export function PriorityBadge({ priority }: { priority: Priority | null | undefined }) {
  if (!priority) return null;
  const [label, tone] = PRIORITY[priority];
  return <Badge tone={tone}>{label}</Badge>;
}

export const priorityLabel = (p: Priority | null | undefined) => (p ? PRIORITY[p][0] : "Not set");

export function TicketId({ number, to }: { number: string; to?: string }) {
  return to ? <Link to={to} className="ticket-id hover:underline">{number}</Link> : <span className="ticket-id">{number}</span>;
}

/** Trust label for knowledge: who stands behind a fix */
const TRUST: Record<string, [string, Tone]> = {
  admin_verified: ["Verified by IT", "ok"], human_verified: ["Verified by IT", "ok"],
  user_confirmed: ["Confirmed by employees", "brand"], ai_generated: ["AI suggestion, not reviewed", "warn"],
};

export function TrustBadge({ level }: { level: string }) {
  const [label, tone] = TRUST[level] || ["Unreviewed", "neutral"];
  return <Badge tone={tone}>{label}</Badge>;
}

/** Map the agent's provenance labels (VERIFIED SOLUTION ...) to the same wording */
export function provenance(label: string): string {
  if (label.startsWith("VERIFIED") || label.startsWith("HUMAN")) return "admin_verified";
  if (label.startsWith("USER")) return "user_confirmed";
  return "ai_generated";
}

/* ---------------- page structure ---------------- */
export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-xl">{title}</h1>
        {description && <p className="mt-1 text-sm text-meta">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Section({ title, description, actions, children, className = "" }:
  { title: string; description?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={className}>
      <div className="mb-2 flex items-end justify-between gap-4">
        <div>
          <h2 className="text-base">{title}</h2>
          {description && <p className="text-sm text-meta">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function Card({ title, actions, children, className = "", bodyClassName = "p-4" }:
  { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClassName?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <div className="card-header">
          {typeof title === "string" ? <h2 className="card-title">{title}</h2> : title}
          {actions}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

export function StatTile({ label, value, hint, tone, to }:
  { label: string; value: ReactNode; hint?: ReactNode; tone?: "crit"; to?: string }) {
  const body = (
    <div className={`card h-full p-4 ${to ? "hover:border-line-strong" : ""}`}>
      <p className="text-sm text-meta">{label}</p>
      <p className={`mt-1 text-xl font-semibold tabular-nums ${tone === "crit" ? "text-crit" : "text-ink"}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-meta">{hint}</p>}
    </div>
  );
  return to ? <Link to={to} className="block">{body}</Link> : body;
}

export function DefinitionList({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
      {items.map(([k, v]) => (
        <Fragment key={k}>
          <dt className="text-meta">{k}</dt>
          <dd className="text-ink min-w-0">{v}</dd>
        </Fragment>
      ))}
    </dl>
  );
}

export function ProgressBar({ value, tone = "brand", label }: { value: number; tone?: Tone; label: string }) {
  const color = { neutral: "bg-faint", brand: "bg-brand", ok: "bg-ok-dot", warn: "bg-warn-dot", crit: "bg-crit" }[tone];
  const v = Math.max(0, Math.min(100, value));
  return (
    <div className="h-2 w-full overflow-hidden rounded-sm bg-muted" role="progressbar" aria-label={label}
      aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`h-full ${color}`} style={{ width: `${v}%` }} />
    </div>
  );
}

/* ---------------- states ---------------- */
export function Spinner({ className = "size-4" }: { className?: string }) {
  return <Loader2 className={`${className} animate-spin`} aria-hidden />;
}

export function SkeletonLines({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2" aria-hidden>
      {Array.from({ length: lines }, (_, i) => <div key={i} className="skeleton h-4" style={{ width: `${92 - i * 14}%` }} />)}
    </div>
  );
}

export function SkeletonPage({ tiles = 4, rows = 6 }: { tiles?: number; rows?: number }) {
  return (
    <div className="space-y-6" role="status" aria-label="Loading">
      <div className="space-y-2"><div className="skeleton h-8 w-64" /><div className="skeleton h-4 w-96 max-w-full" /></div>
      {tiles > 0 && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: tiles }, (_, i) => <div key={i} className="card h-24 p-4"><div className="skeleton h-4 w-24" /><div className="skeleton mt-4 h-6 w-16" /></div>)}
        </div>
      )}
      <SkeletonTable rows={rows} />
    </div>
  );
}

export function SkeletonTable({ rows = 6 }: { rows?: number }) {
  return (
    <div className="card divide-y divide-line" aria-hidden>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3">
          <div className="skeleton h-4 w-24" /><div className="skeleton h-4 flex-1" /><div className="skeleton h-4 w-20" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({ title, children, action, icon }:
  { title: string; children?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="card px-6 py-12 text-center">
      {icon && <div className="mx-auto mb-4 flex size-10 items-center justify-center rounded-md bg-muted text-meta">{icon}</div>}
      <p className="text-base font-semibold text-ink">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-md text-sm text-meta">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

const NOTICE: Record<"info" | "ok" | "warn" | "crit", [string, typeof Info]> = {
  info: ["border-brand-line bg-brand-soft text-ink", Info],
  ok: ["border-ok-line bg-ok-soft text-ok", CheckCircle2],
  warn: ["border-warn-line bg-warn-soft text-warn", AlertCircle],
  crit: ["border-crit-line bg-crit-soft text-crit", AlertCircle],
};

export function Notice({ tone = "info", children, action }: { tone?: keyof typeof NOTICE; children: ReactNode; action?: ReactNode }) {
  const [cls, Icon] = NOTICE[tone];
  return (
    <div className={`flex items-start gap-2 rounded-sm border px-3 py-2 text-sm ${cls}`} role={tone === "crit" ? "alert" : "status"}>
      <span className="flex h-5 shrink-0 items-center"><Icon className="size-4" aria-hidden /></span>
      <div className="min-w-0 flex-1">{children}</div>
      {action}
    </div>
  );
}

/** A failed request: says what failed and offers a retry instead of a dead end */
export function ErrorState({ message, what = "this page", onRetry }: { message: string | null; what?: string; onRetry?: () => void }) {
  if (!message) return null;
  return (
    <Notice tone="crit" action={onRetry && (
      <button className="btn-secondary btn-sm" onClick={onRetry}><RotateCw className="size-4" aria-hidden /> Try again</button>)}>
      <p className="font-medium">Couldn't load {what}.</p>
      <p className="text-body">{message}</p>
    </Notice>
  );
}

export function FormError({ message }: { message: string | null }) {
  return message ? <Notice tone="crit">{message}</Notice> : null;
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: string; children: ReactNode; htmlFor?: string }) {
  return (
    <div>
      <label className="field-label" htmlFor={htmlFor}>{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-meta">{hint}</p>}
    </div>
  );
}

/* Minimal rich text: **bold** and line breaks rendered as React nodes (never raw HTML). */
export function RichText({ text, className = "" }: { text: string; className?: string }) {
  return (
    <div className={`whitespace-pre-wrap break-words ${className}`}>
      {text.split("\n").map((line, i) => (
        <Fragment key={i}>
          {i > 0 && "\n"}
          {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
            part.startsWith("**") && part.endsWith("**")
              ? <strong key={j} className="font-semibold text-ink">{part.slice(2, -2)}</strong>
              : <Fragment key={j}>{part}</Fragment>)}
        </Fragment>
      ))}
    </div>
  );
}

export function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" }) {
  const initials = name.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return (
    <span aria-hidden className={`inline-flex shrink-0 items-center justify-center rounded-full bg-muted font-medium text-body ${size === "sm" ? "size-6 text-xs" : "size-8 text-xs"}`}>
      {initials}
    </span>
  );
}

/** Segmented control for views and filters (one selected option, keyboard accessible as a radio group) */
export function Segmented<T extends string>({ value, onChange, options, label }:
  { value: T; onChange: (v: T) => void; options: [T, string][]; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap rounded-sm border border-line-strong bg-surface p-1">
      {options.map(([k, text]) => (
        <button key={k} role="radio" aria-checked={value === k} onClick={() => onChange(k)}
          className={`rounded-sm px-3 py-1 text-sm font-medium ${value === k ? "bg-brand text-white" : "text-body hover:bg-muted"}`}>
          {text}
        </button>
      ))}
    </div>
  );
}
