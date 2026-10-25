import { Clock } from "lucide-react";
import type { Ticket } from "../services/types";
import { slaText } from "../lib/format";

/** Who has the ticket now, in one plain line: "Assigned to Network Team · Alex Kumar" */
export function ownerLine(t: Ticket, viewer: "employee" | "staff" = "employee"): string {
  if (t.status === "linked_incident") return "Handled as part of an incident";
  if (t.status === "duplicate") return "Merged into your earlier ticket";
  if (t.status === "awaiting_user") return viewer === "employee" ? "Waiting for your reply" : "Waiting for the employee to confirm the fix";
  if (t.assignee) return `Assigned to ${t.department ? `${t.department} · ` : ""}${t.assignee.name}`;
  if (t.status === "escalated") return `Escalated to ${t.department || "IT"}, not yet assigned`;
  if (!t.is_open) return t.resolved_by_ai ? "Resolved by the help desk agent" : t.department ? `Resolved by ${t.department}` : "Closed";
  return "The help desk agent is working on it";
}

const TONE = { neutral: "text-meta", brand: "text-brand", ok: "text-ok", warn: "text-warn", crit: "text-crit" } as const;

export function SlaLabel({ ticket }: { ticket: Ticket }) {
  if (ticket.status === "duplicate" || ticket.status === "linked_incident") return null;
  const { text, tone } = slaText(ticket.sla, ticket.is_open);
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap text-xs ${TONE[tone]}`}>
      <Clock className="size-3" aria-hidden /> {text}
    </span>
  );
}
