/**
 * One format for every date, time, duration and SLA message in the UI.
 *   date        25 Oct 2026
 *   time        14:05 (24-hour)
 *   dateTime    25 Oct 2026, 14:05
 *   relative    12 min ago / 3 h ago / yesterday / 4 days ago, then the date (activity feeds only)
 *   duration    45 min / 4 h / 4 h 10 min / 2 d 3 h
 */
import type { Sla } from "../services/types";

const LOCALE = "en-IN";
const DATE = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short", year: "numeric" });
const TIME = new Intl.DateTimeFormat(LOCALE, { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const DAY = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short" });

// A bare calendar date (2026-09-22) is a local date, not UTC midnight
const parse = (iso: string | null | undefined) =>
  iso ? new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso) : null;

export function date(iso: string | null | undefined): string {
  const d = parse(iso);
  return d ? DATE.format(d) : "-";
}

export function time(iso: string | null | undefined): string {
  const d = parse(iso);
  return d ? TIME.format(d) : "-";
}

export function dateTime(iso: string | null | undefined): string {
  const d = parse(iso);
  return d ? `${DATE.format(d)}, ${TIME.format(d)}` : "-";
}

/** Short day label for chart axes: 25 Oct */
export function day(isoDate: string): string {
  return DAY.format(new Date(`${isoDate}T00:00:00`));
}

export function relative(iso: string | null | undefined): string {
  const d = parse(iso);
  if (!d) return "-";
  const minutes = Math.max(0, (Date.now() - d.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${Math.floor(minutes)} min ago`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} h ago`;
  if (minutes < 48 * 60) return "yesterday";
  if (minutes < 7 * 24 * 60) return `${Math.floor(minutes / 1440)} days ago`;
  return date(iso);
}

export function duration(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined || Number.isNaN(minutes)) return "-";
  const m = Math.round(Math.abs(minutes));
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  if (h < 48) return m % 60 && h < 10 ? `${h} h ${m % 60} min` : `${h} h`;
  const d = Math.floor(h / 24);
  return h % 24 ? `${d} d ${h % 24} h` : `${d} d`;
}

export type Tone = "neutral" | "brand" | "ok" | "warn" | "crit";

/** "SLA 4 h left", "Overdue by 1 h 20 min", "Resolved in 2 h (target 8 h)" */
export function slaText(sla: Sla, isOpen: boolean): { text: string; tone: Tone } {
  if (!isOpen) {
    const within = !sla.breached;
    return { text: `Resolved in ${duration(sla.elapsed_minutes)}${within ? "" : ` (target ${duration(sla.target_minutes)})`}`,
      tone: within ? "ok" : "warn" };
  }
  if (sla.breached) return { text: `Overdue by ${duration(-sla.remaining_minutes)}`, tone: "crit" };
  return { text: `SLA ${duration(sla.remaining_minutes)} left`, tone: sla.percent >= 75 ? "warn" : "neutral" };
}

export const percent = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? "-" : `${(v * 100).toFixed(digits)}%`;

export const titleCase = (s: string | null | undefined) =>
  (s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

export const sentenceCase = (s: string | null | undefined) => {
  const t = (s || "").replace(/_/g, " ");
  return t ? t[0].toUpperCase() + t.slice(1) : t;
};

export const firstName = (name: string | null | undefined) => (name || "").split(" ")[0];
