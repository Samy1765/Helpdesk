import { Link } from "react-router-dom";
import { BookOpen, MessageSquare } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { dateTime, duration, firstName } from "../lib/format";
import {
  EmptyState, ErrorState, Notice, PageHeader, PriorityBadge, Section, SkeletonPage, StatTile, StatusBadge, TicketId,
} from "../components/ui";
import { SlaLabel, ownerLine } from "../components/tickets";
import type { Incident, Ticket } from "../services/types";

interface Dashboard {
  user: { name: string; role: string };
  my_tickets: { open: number; in_analysis: number; awaiting_me: number; resolved: number; avg_resolution_minutes: number | null };
  recent_tickets: (Ticket & { pipeline_progress: number | null })[];
  active_incidents: Incident[];
  guides: { id: number; title: string; category: string | null; doc_type: string }[];
  support?: {
    escalated_open: number; critical_open: number; pending_approvals: number; sla_breached_open: number;
    ai_resolution_rate: number; open_tickets: number;
  };
}

export default function DashboardPage() {
  const { user, isStaff } = useAuth();
  const { data, error, loading, reload } = useApi<Dashboard>("/dashboard", 30000);
  if (loading && !data) return <SkeletonPage />;
  if (!data) return <ErrorState message={error} what="your home page" onRetry={reload} />;

  const mine = data.my_tickets;
  const s = data.support;

  return (
    <div className="space-y-8">
      <PageHeader title={`Hello, ${firstName(user?.full_name || data.user.name)}`}
        description={mine.open ? `You have ${mine.open} open request${mine.open === 1 ? "" : "s"}${mine.awaiting_me ? `, ${mine.awaiting_me} waiting for you` : ""}.`
          : "You have no open requests."}
        actions={<>
          <Link to="/knowledge-base" className="btn-secondary"><BookOpen className="size-4" aria-hidden /> Knowledge base</Link>
          <Link to="/chat" className="btn-primary"><MessageSquare className="size-4" aria-hidden /> Report a problem</Link>
        </>} />

      {data.active_incidents.map((i) => (
        <Notice key={i.id} tone="warn" action={<Link to={`/incidents?id=${i.id}`} className="btn-secondary btn-sm">View incident</Link>}>
          <p className="font-medium text-ink"><span className="mono">{i.incident_number}</span> · {i.title}</p>
          <p className="text-body">
            {i.ticket_count} people affected since {dateTime(i.first_reported)}.
            {i.department ? ` ${i.department} is working on it; you don't need to report it again.` : ""}
          </p>
        </Notice>
      ))}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Open requests" value={mine.open} to="/tickets?scope=open" />
        <StatTile label="Waiting for you" value={mine.awaiting_me} hint={mine.awaiting_me ? "Confirm a fix or approve an action" : "Nothing to do"} to="/tickets?scope=open" />
        <StatTile label="Resolved" value={mine.resolved} hint="All time" to="/tickets?scope=closed" />
        <StatTile label="Average time to resolve" value={duration(mine.avg_resolution_minutes)} hint="Your resolved requests" />
      </div>

      {isStaff && s && (
        <Section title="Support queue" actions={<Link to="/it-support" className="text-sm font-medium text-brand hover:underline">Open the support queue</Link>}>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatTile label="With IT (escalated or assigned)" value={s.escalated_open} to="/it-support" />
            <StatTile label="Past SLA" value={s.sla_breached_open} tone={s.sla_breached_open ? "crit" : undefined} to="/it-support" />
            <StatTile label="Critical open" value={s.critical_open} tone={s.critical_open ? "crit" : undefined} to="/it-support" />
            <StatTile label="Approvals waiting" value={s.pending_approvals} to="/it-support" />
          </div>
        </Section>
      )}

      <div className="grid gap-8 xl:grid-cols-[2fr_1fr]">
        <Section title="Your recent requests" actions={<Link to="/tickets" className="text-sm font-medium text-brand hover:underline">All requests</Link>}>
          {data.recent_tickets.length ? (
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line bg-canvas">
                  <tr><th className="th">Ticket</th><th className="th">Request</th><th className="th">Status</th><th className="th">Priority</th><th className="th">Created</th></tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {data.recent_tickets.map((t) => (
                    <tr key={t.id} className="hover:bg-canvas">
                      <td className="td whitespace-nowrap"><TicketId number={t.ticket_number} to={`/tickets/${t.id}`} /></td>
                      <td className="td min-w-64">
                        <Link to={`/tickets/${t.id}`} className="font-medium text-ink hover:underline">{t.title}</Link>
                        <span className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-meta">{ownerLine(t)} <SlaLabel ticket={t} /></span>
                      </td>
                      <td className="td"><StatusBadge status={t.status} /></td>
                      <td className="td"><PriorityBadge priority={t.priority} /></td>
                      <td className="td whitespace-nowrap text-meta">{dateTime(t.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No requests yet" icon={<MessageSquare className="size-5" aria-hidden />}
              action={<Link to="/chat" className="btn-primary">Report a problem</Link>}>
              When something stops working, describe it in your own words. Known fixes are suggested straight away.
            </EmptyState>
          )}
        </Section>

        <Section title="Popular guides" actions={<Link to="/knowledge-base" className="text-sm font-medium text-brand hover:underline">Knowledge base</Link>}>
          <ul className="card divide-y divide-line">
            {data.guides.map((g) => (
              <li key={g.id}>
                <Link to={`/knowledge-base?doc=${g.id}`} className="block px-4 py-3 hover:bg-canvas">
                  <span className="block text-sm font-medium text-ink">{g.title}</span>
                  <span className="block text-xs text-meta">{g.category || "General"}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </div>
  );
}
