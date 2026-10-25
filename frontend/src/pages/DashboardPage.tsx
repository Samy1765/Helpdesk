import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, BookOpen, MessageSquare, TriangleAlert } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import {
  Empty, ErrorNote, PriorityBadge, SectionTitle, Spinner, StatTile, StatusBadge, TicketId,
  clock, duration, sentenceCase, timeAgo,
} from "../components/ui";
import type { Incident, Ticket } from "../services/types";

interface Dashboard {
  user: { name: string; role: string };
  my_tickets: { open: number; in_analysis: number; awaiting_me: number; resolved: number; avg_resolution_minutes: number | null };
  recent_tickets: (Ticket & { pipeline_progress: number | null })[];
  active_incidents: Incident[];
  guides: { id: number; title: string; category: string | null; doc_type: string }[];
  support?: Record<string, number | null | unknown[]>;
}

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function nextStep(t: Dashboard["recent_tickets"][number]): { text: string; to: string } | null {
  if (t.status === "awaiting_user") return { text: "Tell us if the fix worked", to: `/tickets/${t.id}` };
  if (t.status === "awaiting_approval") return { text: "Approval needed", to: `/tickets/${t.id}` };
  if (t.status === "ai_analysis" || t.status === "troubleshooting") return { text: "Continue in chat", to: "/chat" };
  return null;
}

function TicketRow({ t }: { t: Dashboard["recent_tickets"][number] }) {
  const step = nextStep(t);
  const owner = t.assignee?.name || t.department;
  return (
    <li className="px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
      <div className="min-w-0 flex-1 basis-64">
        <div className="flex items-center gap-2">
          <TicketId number={t.ticket_number} to={`/tickets/${t.id}`} />
          <span className="text-xs text-meta">{t.category || "General"} · opened {timeAgo(t.created_at)}</span>
        </div>
        <Link to={`/tickets/${t.id}`} className="block mt-0.5 font-medium leading-snug hover:text-cobalt truncate">{t.title}</Link>
        {t.status === "resolved" && t.resolution_summary && (
          <p className="text-xs text-meta mt-0.5 line-clamp-1">{t.resolution_summary}</p>
        )}
        {owner && t.status !== "resolved" && <p className="text-xs text-meta mt-0.5">With {owner}</p>}
      </div>
      <div className="flex items-center gap-1.5">
        <PriorityBadge priority={t.priority} />
        <StatusBadge status={t.status} />
      </div>
      {step && <Link to={step.to} className="btn-outline btn-sm">{step.text}</Link>}
    </li>
  );
}

function OutageNotice({ incident }: { incident: Incident }) {
  return (
    <div className="rounded-lg border border-crit-line bg-crit-soft px-4 py-3 flex flex-wrap items-center gap-x-4 gap-y-2">
      <TriangleAlert className="size-5 text-crit shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-crit-ink">Known problem: {incident.title}</p>
        <p className="text-sm text-body">
          {incident.department ? `${incident.department} is working on it. ` : ""}
          {incident.ticket_count} {incident.ticket_count === 1 ? "report" : "reports"} so far, the latest at {clock(incident.last_reported)}.
          You do not need to report it again.
        </p>
      </div>
      <Link to={`/incidents?id=${incident.id}`} className="btn-outline btn-sm">Details</Link>
    </div>
  );
}

export default function DashboardPage() {
  const { user, isStaff } = useAuth();
  const { data, error, loading } = useApi<Dashboard>("/dashboard", 20000);
  const navigate = useNavigate();
  if (loading && !data) return <Spinner />;
  if (!data) return <ErrorNote message={error} />;

  const firstName = (user?.full_name || data.user.name).split(" ")[0];
  const s = data.support as Record<string, number> | undefined;
  const mine = data.my_tickets;
  const role = user?.role === "it_support" ? "IT support" : sentenceCase(user?.role);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl md:text-2xl font-semibold">{greeting()}, {firstName}</h1>
          <p className="text-sm text-meta mt-0.5">{[user?.department, role].filter(Boolean).join(" · ")}</p>
        </div>
        <button className="btn-accent" onClick={() => navigate("/chat")}><MessageSquare className="size-4" /> Get help with a problem</button>
      </div>

      {data.active_incidents.map((i) => <OutageNotice key={i.id} incident={i} />)}

      <section>
        <SectionTitle>Your tickets</SectionTitle>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatTile label="Open" value={mine.open} to="/tickets"
            sub={<span className="text-xs text-meta">{mine.in_analysis ? `${mine.in_analysis} being looked at` : "none in progress"}</span>} />
          <StatTile label="Waiting for you" value={mine.awaiting_me} to="/tickets"
            sub={<span className={`text-xs ${mine.awaiting_me ? "text-warn-ink" : "text-meta"}`}>{mine.awaiting_me ? "needs your reply" : "nothing to do"}</span>} />
          <StatTile label="Resolved" value={mine.resolved}
            sub={<span className="text-xs text-meta">{mine.avg_resolution_minutes !== null ? `typically in ${duration(mine.avg_resolution_minutes)}` : "none yet"}</span>} />
          <StatTile label="Known problems" value={data.active_incidents.length} tone={data.active_incidents.length ? "crit" : "default"} to="/incidents"
            sub={<span className="text-xs text-meta">{data.active_incidents.length ? "affecting the company" : "all systems normal"}</span>} />
        </div>
      </section>

      {isStaff && s && (
        <section>
          <SectionTitle right={<Link to="/it-support" className="text-sm text-cobalt hover:underline">Open support queue</Link>}>Support team</SectionTitle>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatTile label="With IT (escalated or assigned)" value={s.escalated_open as number} to="/it-support" />
            <StatTile label="Critical and open" value={s.critical_open as number} tone={(s.critical_open as number) ? "crit" : "default"} to="/it-support" />
            <StatTile label="Waiting for approval" value={s.pending_approvals as number} to="/it-support" />
            <StatTile label="Solved without IT staff" value={`${s.ai_resolution_rate}%`} sub={<span className="text-xs text-meta">of all resolved tickets</span>} />
          </div>
        </section>
      )}

      <section>
        <SectionTitle right={<Link to="/tickets" className="text-sm text-cobalt hover:underline">All tickets</Link>}>Recent tickets</SectionTitle>
        {data.recent_tickets.length ? (
          <ul className="card divide-y divide-muted">{data.recent_tickets.map((t) => <TicketRow key={t.id} t={t} />)}</ul>
        ) : (
          <Empty title="No tickets yet" icon={<MessageSquare className="size-5" />}>When something stops working, start with "Get help" above.</Empty>
        )}
      </section>

      <section>
        <SectionTitle right={<Link to="/knowledge-base" className="text-sm text-cobalt hover:underline">Knowledge base</Link>}>Fix it yourself</SectionTitle>
        <ul className="card grid sm:grid-cols-2 divide-y divide-muted sm:divide-y-0">
          {data.guides.map((g) => (
            <li key={g.id} className="sm:border-b sm:border-muted">
              <Link to={`/knowledge-base?doc=${g.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-canvas">
                <BookOpen className="size-4 text-meta shrink-0" />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium truncate">{g.title}</span>
                  <span className="block text-xs text-meta">{g.category || "General"}</span>
                </span>
                <ArrowRight className="size-4 text-faint" />
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
