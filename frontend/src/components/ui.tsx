import { Fragment, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import type { Priority } from "../services/types";

/* ---------------- formatting ---------------- */
// One date style across the app: "25 Oct 2026", "25 Oct 2026, 10:42", 24-hour clock.
const LOCALE = "en-GB";

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "-";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 2) return "yesterday";
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} days ago`;
  return shortDate(iso);
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" });
}

// Built by hand: browsers disagree on the short month ("Sep" vs "Sept").
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return `${shortDate(iso)}, ${clock(iso)}`;
}

export function duration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "-";
  const m = Math.abs(minutes);
  if (m < 60) return `${Math.round(m)} min`;
  if (m < 60 * 48) return `${(m / 60).toFixed(m < 600 ? 1 : 0)} h`;
  return `${Math.round(m / 1440)} days`;
}

export const pct = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? "-" : `${(v * 100).toFixed(digits)}%`;

export const titleCase = (s: string | null | undefined) =>
  (s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** "password_reset" / "PASSWORD RESET" -> "Password reset" */
export const sentenceCase = (s: string | null | undefined) => {
  const t = (s || "").replace(/_/g, " ").toLowerCase();
  return t.charAt(0).toUpperCase() + t.slice(1);
};

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
    <span className={`badge ${TONES[tone]} ${mono ? "font-mono" : ""} ${className}`}>
      {dot && <span className="dot size-1.5 bg-current" />}
      {children}
    </span>
  );
}

const STATUS: Record<string, [string, Tone]> = {
  new: ["New", "neutral"],
  ai_analysis: ["Analysing", "cobalt"],
  troubleshooting: ["Troubleshooting", "cobalt"],
  awaiting_user: ["Waiting for user", "warn"],
  awaiting_approval: ["Needs approval", "warn"],
  escalated: ["Escalated", "violet"],
  assigned: ["Assigned", "violet"],
  in_progress: ["In progress", "violet"],
  resolved: ["Resolved", "ok"],
  closed: ["Closed", "neutral"],
  duplicate: ["Duplicate", "neutral"],
  linked_incident: ["Part of incident", "crit"],
  active: ["Active", "crit"],
  investigating: ["Investigating", "warn"],
};

export function StatusBadge({ status }: { status: string }) {
  const [label, tone] = STATUS[status] || [sentenceCase(status), "neutral" as Tone];
  return <Badge tone={tone}>{label}</Badge>;
}

const PRIORITY: Record<Priority, [string, Tone]> = {
  low: ["Low", "neutral"], medium: ["Medium", "warn"], high: ["High", "crit"], critical: ["Critical", "solidCrit"],
};

export function PriorityBadge({ priority, long }: { priority: Priority | null | undefined; long?: boolean }) {
  if (!priority) return null;
  const [label, tone] = PRIORITY[priority];
  return <Badge tone={tone}>{long ? `${label} priority` : label}</Badge>;
}

export function priorityTone(p: Priority | null | undefined): string {
  return p === "critical" || p === "high" ? "text-crit" : p === "medium" ? "text-warn-ink" : "text-body";
}

export function TicketId({ number, to }: { number: string; to?: string }) {
  const chip = <span className="mono text-[0.8125rem] text-cobalt">{number}</span>;
  return to ? <Link to={to} className="hover:underline">{chip}</Link> : chip;
}

// The API labels solutions in capitals (e.g. "HUMAN-APPROVED SOLUTION"); show them in plain words.
const SOLUTION_LABELS: [string, string, Tone][] = [
  ["VERIFIED", "Verified fix", "ok"],
  ["HUMAN", "Approved by IT", "ok"],
  ["USER", "Confirmed by users", "info"],
  ["AI", "Suggested by AI, not yet verified", "warn"],
];

export function solutionLabelText(label: string): string {
  return SOLUTION_LABELS.find(([key]) => label.startsWith(key))?.[1] ?? sentenceCase(label);
}

// Trust level of a stored solution (SolutionConfidence on the API)
const CONFIDENCE_TEXT: Record<string, string> = {
  ai_generated: "suggested by AI", user_confirmed: "confirmed by users",
  human_verified: "verified by IT", admin_verified: "verified by an administrator",
};
export const confidenceText = (level: string | null | undefined) => CONFIDENCE_TEXT[level || ""] || sentenceCase(level).toLowerCase();

export function SolutionLabel({ label }: { label: string }) {
  const [, text, tone] = SOLUTION_LABELS.find(([key]) => label.startsWith(key)) ?? ["", sentenceCase(label), "neutral" as Tone];
  return <Badge tone={tone}>{text}</Badge>;
}

/* ---------------- layout pieces ---------------- */
export function SectionTitle({ children, right, icon }: { children: ReactNode; right?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 mb-2.5">
      <h2 className="text-sm font-semibold text-ink flex items-center gap-2">{icon}{children}</h2>
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
        <h1 className="text-xl md:text-2xl font-semibold leading-tight">{title}</h1>
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
        <span className={`text-[0.8125rem] ${tone === "crit" ? "text-crit-ink" : "text-meta"}`}>{label}</span>
        {icon}
      </div>
      <div className={`mt-1.5 text-2xl font-semibold leading-none tabular-nums ${tone === "crit" ? "text-crit" : ""}`}>{value}</div>
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
      <p className="font-semibold">{title}</p>
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
      <span className="text-sm font-medium text-body block mb-1.5">{label}</span>
      {children}
      {hint && <span className="text-xs text-meta mt-1 block">{hint}</span>}
    </label>
  );
}

export function KeyValue({ k, v, mono }: { k: string; v: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded border border-line bg-surface px-3 py-2">
      <span className="text-sm text-meta">{k}</span>
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
