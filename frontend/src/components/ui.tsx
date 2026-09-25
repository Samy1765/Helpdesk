import { Fragment, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import type { Priority } from "../services/types";

/* ---------------- formatting ---------------- */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "-";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 86400 * 2) return "Yesterday";
  return `${Math.floor(s / 86400)} days ago`;
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

export function duration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "-";
  const m = Math.abs(minutes);
  if (m < 60) return `${Math.round(m)}m`;
  if (m < 60 * 48) return `${(m / 60).toFixed(m < 600 ? 1 : 0)}h`;
  return `${Math.round(m / 1440)}d`;
}

export const pct = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? "-" : `${(v * 100).toFixed(digits)}%`;

export const titleCase = (s: string | null | undefined) =>
  (s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/* ---------------- badges ---------------- */
type Tone = "neutral" | "info" | "ok" | "warn" | "crit" | "violet" | "cobalt" | "solidCrit" | "ink";
const TONES: Record<Tone, string> = {
  neutral: "bg-muted border-line text-body",
  info: "bg-info-soft border-info-line text-info",
  cobalt: "bg-cobalt-soft border-cobalt-line text-[#1d4ed8]",
  ok: "bg-ok-soft border-ok-line text-ok-ink",
  warn: "bg-warn-soft border-warn-line text-warn-ink",
  crit: "bg-crit-soft border-crit-line text-crit",
  violet: "bg-violet-soft border-violet-line text-violet",
  solidCrit: "bg-crit border-crit text-white",
  ink: "bg-ink border-ink text-white",
};

export function Badge({ tone = "neutral", children, dot, mono, className = "" }:
  { tone?: Tone; children: ReactNode; dot?: boolean; mono?: boolean; className?: string }) {
  return (
    <span className={`badge ${TONES[tone]} ${mono ? "font-mono tracking-normal" : ""} ${className}`}>
      {dot && <span className="dot size-1.5 bg-current" />}
      {children}
    </span>
  );
}

const STATUS: Record<string, [string, Tone]> = {
  new: ["New", "neutral"],
  ai_analysis: ["AI Analysis", "cobalt"],
  troubleshooting: ["AI Troubleshooting", "cobalt"],
  awaiting_user: ["Awaiting Confirmation", "warn"],
  awaiting_approval: ["Awaiting Approval", "warn"],
  escalated: ["Escalated to IT", "violet"],
  assigned: ["Assigned to IT", "violet"],
  in_progress: ["In Progress", "violet"],
  resolved: ["Resolved", "ok"],
  closed: ["Closed", "neutral"],
  duplicate: ["Duplicate", "neutral"],
  linked_incident: ["Linked to Incident", "crit"],
  active: ["Active", "crit"],
  investigating: ["Investigating", "warn"],
};

export function StatusBadge({ status }: { status: string }) {
  const [label, tone] = STATUS[status] || [titleCase(status), "neutral" as Tone];
  return <Badge tone={tone}>{label}</Badge>;
}

const PRIORITY: Record<Priority, [string, Tone]> = {
  low: ["Low", "neutral"], medium: ["Med", "warn"], high: ["High", "crit"], critical: ["Critical", "solidCrit"],
};

export function PriorityBadge({ priority, long }: { priority: Priority | null | undefined; long?: boolean }) {
  if (!priority) return null;
  const [label, tone] = PRIORITY[priority];
  return <Badge tone={tone} dot={long}>{long ? `Priority: ${titleCase(priority)}` : label}</Badge>;
}

export function priorityTone(p: Priority | null | undefined): string {
  return p === "critical" || p === "high" ? "text-crit" : p === "medium" ? "text-warn-ink" : "text-body";
}

export function TicketId({ number, to }: { number: string; to?: string }) {
  const chip = <span className="mono text-[0.8125rem] font-medium text-cobalt">{number}</span>;
  return to ? <Link to={to} className="hover:underline">{chip}</Link> : chip;
}

export function SolutionLabel({ label }: { label: string }) {
  const tone: Tone = label.startsWith("VERIFIED") ? "ok" : label.startsWith("HUMAN") ? "ok"
    : label.startsWith("USER") ? "info" : "warn";
  return <Badge tone={tone} mono>{label}</Badge>;
}

/* ---------------- layout pieces ---------------- */
export function SectionTitle({ children, right, icon }: { children: ReactNode; right?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 mb-2.5">
      <h2 className="label-caps !text-body flex items-center gap-2">{icon}{children}</h2>
      {right}
    </div>
  );
}

export function PageHeader({ eyebrow, title, subtitle, right }:
  { eyebrow?: ReactNode; title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && <div className="mb-1.5">{eyebrow}</div>}
        <h1 className="text-[1.375rem] md:text-[1.75rem] font-semibold tracking-[-0.02em] leading-tight">{title}</h1>
        {subtitle && <p className="text-sm text-meta mt-1">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function StatTile({ label, value, sub, icon, tone = "default", to }:
  { label: string; value: ReactNode; sub?: ReactNode; icon?: ReactNode; tone?: "default" | "crit"; to?: string }) {
  const body = (
    <div className={`card card-hover p-3.5 h-full ${tone === "crit" ? "!bg-crit-soft !border-crit-line" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <span className={`text-[0.8125rem] font-medium ${tone === "crit" ? "text-crit-ink" : "text-body"}`}>{label}</span>
        {icon}
      </div>
      <div className={`mt-1 font-display text-[1.75rem] font-semibold leading-none ${tone === "crit" ? "text-crit" : ""}`}>{value}</div>
      {sub && <div className="mt-1.5">{sub}</div>}
    </div>
  );
  return to ? <Link to={to} className="block">{body}</Link> : body;
}

export function ProgressBar({ value, tone = "cobalt", split }: { value: number; tone?: "cobalt" | "ok" | "warn" | "crit"; split?: number }) {
  const color = { cobalt: "bg-cobalt", ok: "bg-ok", warn: "bg-warn", crit: "bg-crit" }[tone];
  const v = Math.max(0, Math.min(100, value));
  return (
    <div className="h-1.5 w-full rounded-sm bg-muted overflow-hidden flex">
      {split !== undefined ? (
        <>
          <div className="h-full bg-cobalt" style={{ width: `${Math.min(v, split)}%` }} />
          {v > split && <div className="h-full bg-warn" style={{ width: `${v - split}%` }} />}
        </>
      ) : <div className={`h-full ${color} transition-[width] duration-500`} style={{ width: `${v}%` }} />}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-meta">
      <Loader2 className="size-4 animate-spin" /> {label || "Loading"}
    </div>
  );
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="card px-6 py-10 text-center">
      {icon && <div className="mx-auto mb-3 flex size-10 items-center justify-center rounded-lg bg-muted text-meta">{icon}</div>}
      <p className="font-display font-semibold">{title}</p>
      {children && <div className="text-sm text-meta mt-1">{children}</div>}
    </div>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="rounded border border-crit-line bg-crit-soft px-3 py-2 text-sm text-crit-ink">{message}</div>;
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="label-caps block mb-1.5">{label}</span>
      {children}
      {hint && <span className="text-xs text-meta mt-1 block">{hint}</span>}
    </label>
  );
}

export function KeyValue({ k, v, mono }: { k: string; v: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded border border-line bg-surface px-3 py-2">
      <span className="label-caps">{k}</span>
      <span className={`text-sm text-right ${mono ? "mono text-[0.8125rem]" : ""}`}>{v}</span>
    </div>
  );
}

/* Minimal, safe rich text: **bold** and line breaks rendered as React nodes (never raw HTML). */
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
    <span className={`inline-flex items-center justify-center rounded-full border border-line bg-muted font-semibold text-body ${size === "sm" ? "size-7 text-[0.6875rem]" : "size-9 text-xs"}`}>
      {initials}
    </span>
  );
}
