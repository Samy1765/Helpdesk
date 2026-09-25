import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight, ArrowUpRight, BookOpen, CheckCircle2, ClipboardList, Eye, FileText, KeyRound, Laptop,
  MessageSquare, Network, Sparkles, SquareAsterisk, TriangleAlert, Wifi,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import {
  Badge, Empty, ErrorNote, PriorityBadge, ProgressBar, SectionTitle, Spinner, StatTile, StatusBadge, TicketId,
  duration, timeAgo,
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

const GUIDE_ICON: Record<string, typeof KeyRound> = { Password: KeyRound, VPN: Network, Network: Wifi, Hardware: Laptop };

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

function RecentTicket({ t }: { t: Dashboard["recent_tickets"][number] }) {
  const navigate = useNavigate();
  const aiActive = ["ai_analysis", "troubleshooting", "awaiting_user", "awaiting_approval"].includes(t.status);
  const escalated = ["escalated", "assigned", "in_progress"].includes(t.status);
  return (
    <div className="card card-hover p-4">
      <div className="flex items-start justify-between gap-2">
        <TicketId number={t.ticket_number} to={`/tickets/${t.id}`} />
        <div className="flex gap-1.5">
          <StatusBadge status={t.status} />
          <PriorityBadge priority={t.priority} />
        </div>
      </div>
      <Link to={`/tickets/${t.id}`} className="block mt-2 font-display font-semibold leading-snug hover:text-cobalt">{t.title}</Link>
      <p className="mono text-xs text-meta mt-1">{t.category || "General"}{t.sub_category ? ` / ${t.sub_category}` : ""} · Created {timeAgo(t.created_at)}</p>

      {aiActive && t.pipeline_progress !== null && (
        <>
          <div className="mt-3 rounded border border-line bg-canvas px-3 py-2.5">
            <div className="flex justify-between mb-1.5">
              <span className="mono text-xs text-meta">Diagnostic pipeline</span>
              <span className="mono text-xs font-semibold text-cobalt">{t.pipeline_progress}% COMPLETED</span>
            </div>
            <ProgressBar value={t.pipeline_progress} />
          </div>
          <div className="flex justify-end mt-3">
            <button className="btn-accent btn-sm" onClick={() => navigate(t.status === "awaiting_user" ? `/tickets/${t.id}` : "/chat")}>
              <MessageSquare className="size-3.5" /> {t.status === "awaiting_user" ? "Confirm fix" : "Resume chat"}
            </button>
          </div>
        </>
      )}
      {t.status === "resolved" && t.resolution_summary && (
        <>
          <div className="mt-3 flex gap-2 rounded border border-ok-line bg-ok-soft px-3 py-2.5 text-[0.8125rem] text-ok-ink">
            <CheckCircle2 className="size-4 shrink-0 mt-0.5" />
            <span className="mono leading-snug">{t.resolved_by_ai ? "Verified fix: " : "Resolved: "}{t.resolution_summary}</span>
          </div>
          <div className="flex justify-end mt-3">
            <Link className="btn-outline btn-sm" to={`/tickets/${t.id}`}><Eye className="size-3.5" /> View resolution</Link>
          </div>
        </>
      )}
      {(escalated || t.status === "linked_incident" || t.status === "duplicate") && (
        <div className="mt-3 flex items-center justify-between gap-2 border-t border-muted pt-3">
          <span className="text-xs text-meta">
            {t.assignee ? <>Assigned · <span className="text-body font-medium">{t.assignee.name}</span></> : t.department || "IT support"}
          </span>
          <Link className="btn-outline btn-sm" to={`/tickets/${t.id}`}>Status <ArrowRight className="size-3.5" /></Link>
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { user, isStaff } = useAuth();
  const { data, error, loading } = useApi<Dashboard>("/dashboard", 20000);
  const navigate = useNavigate();
  if (loading && !data) return <Spinner />;
  if (!data) return <ErrorNote message={error} />;

  const incident = data.active_incidents[0];
  const firstName = (user?.full_name || data.user.name).split(" ")[0];
  const s = data.support as Record<string, number> | undefined;

  return (
    <div className="space-y-6">
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          {incident ? (
            <Badge tone="crit" className="!px-2.5 !py-1"><span className="dot size-1.5 bg-crit animate-pulse-dot" /> SYSTEM STATUS: ACTIVE INCIDENT</Badge>
          ) : (
            <Badge tone="ok" className="!px-2.5 !py-1"><span className="dot size-1.5 bg-ok animate-pulse-dot" /> SYSTEM STATUS: NOMINAL</Badge>
          )}
          <span className="mono text-[0.6875rem] text-meta uppercase">{user?.department || "Enterprise"} · {user?.role.replace("_", " ")}</span>
        </div>
        <h1 className="text-[1.375rem] md:text-[1.75rem] font-semibold tracking-[-0.02em]">{greeting()}, {firstName}</h1>
        <p className="text-sm text-meta">Precision AI automated enterprise assistance & IT ops hub</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="card p-5">
          <div className="flex items-start justify-between">
            <span className="flex size-10 items-center justify-center rounded-md border border-cobalt-line bg-cobalt-soft text-cobalt"><Sparkles className="size-5" /></span>
            <Badge tone="cobalt"><span className="dot size-1.5 bg-cobalt" /> AGENT ACTIVE</Badge>
          </div>
          <h2 className="mt-3 text-[1.0625rem] font-semibold">Start support session</h2>
          <p className="text-sm text-meta mt-1">Instant AI-guided diagnosis, verified fixes, automatic ticket creation and escalation to the right team.</p>
          <button className="btn-accent w-full mt-4 justify-between" onClick={() => navigate("/chat")}>
            <span className="flex items-center gap-2"><MessageSquare className="size-4" /> Start new AI chat</span><ArrowRight className="size-4" />
          </button>
        </div>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-1">
          <Link to="/chat" className="card card-hover p-4 flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-md border border-line bg-canvas"><ClipboardList className="size-4 text-body" /></span>
            <span><span className="block text-sm font-semibold">Report issue</span><span className="block mono text-[0.6875rem] text-meta">Hardware / gear</span></span>
          </Link>
          <Link to="/knowledge-base" className="card card-hover p-4 flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-md border border-line bg-canvas"><BookOpen className="size-4 text-body" /></span>
            <span><span className="block text-sm font-semibold">Knowledge base</span><span className="block mono text-[0.6875rem] text-meta">Docs & manuals</span></span>
          </Link>
        </div>
      </div>

      <section>
        <SectionTitle right={<span className="mono text-[0.6875rem] text-meta">LIVE · 20s refresh</span>}>Telemetry hub</SectionTitle>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatTile label="Open tickets" value={data.my_tickets.open} icon={<FileText className="size-4 text-meta" />}
            sub={<span className="mono text-xs text-cobalt">{data.my_tickets.in_analysis} in analysis</span>} to="/tickets" />
          <StatTile label="Resolved" value={data.my_tickets.resolved} icon={<CheckCircle2 className="size-4 text-ok" />}
            sub={<span className="mono text-xs text-meta">avg {duration(data.my_tickets.avg_resolution_minutes)}</span>} />
          <StatTile label="Pending you" value={data.my_tickets.awaiting_me} icon={<ClipboardList className="size-4 text-warn" />}
            sub={data.my_tickets.awaiting_me ? <Badge tone="warn">ACTION</Badge> : <span className="mono text-xs text-meta">nothing to do</span>} to="/tickets" />
          <StatTile label="Active incidents" value={data.active_incidents.length} tone={data.active_incidents.length ? "crit" : "default"}
            icon={<SquareAsterisk className={`size-4 ${data.active_incidents.length ? "text-crit" : "text-meta"}`} />}
            sub={incident?.priority ? <Badge tone="crit">{incident.priority.toUpperCase()}</Badge> : <span className="mono text-xs text-meta">all clear</span>} to="/incidents" />
        </div>
      </section>

      {incident && (
        <div className="rounded-lg border border-crit-line bg-crit-soft p-4">
          <div className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-2 mono text-sm font-semibold text-crit-ink"><TriangleAlert className="size-4" /> {incident.incident_number}</span>
            <Badge tone="crit">{incident.status.toUpperCase()} · {incident.priority?.toUpperCase()}</Badge>
          </div>
          <p className="mt-2 font-display font-semibold">{incident.title}</p>
          <p className="text-sm text-body mt-1">{incident.ticket_count} report(s) correlated automatically. {incident.department ? `${incident.department} is working on it.` : ""}</p>
          <div className="mt-3 rounded border border-crit-line bg-surface px-3 py-2 mono text-xs text-body truncate">
            <span className="text-cobalt">{new Date(incident.last_reported).toLocaleTimeString()}</span> · last correlated report · similarity {incident.detection_similarity ? `${Math.round(incident.detection_similarity * 100)}%` : "-"}
          </div>
          <Link to={`/incidents?id=${incident.id}`} className="btn w-full mt-3 bg-surface border border-crit-line text-crit-ink hover:bg-white">
            View incident details <ArrowRight className="size-4" />
          </Link>
        </div>
      )}

      {isStaff && s && (
        <section>
          <SectionTitle right={<Link to="/it-support" className="text-xs font-semibold text-cobalt">Open console →</Link>}>Support queue</SectionTitle>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatTile label="Escalated / assigned" value={s.escalated_open as number} to="/it-support" />
            <StatTile label="Critical open" value={s.critical_open as number} tone={(s.critical_open as number) ? "crit" : "default"} to="/it-support" />
            <StatTile label="Pending approvals" value={s.pending_approvals as number} to="/it-support" />
            <StatTile label="AI resolution rate" value={`${s.ai_resolution_rate}%`} />
          </div>
        </section>
      )}

      <section>
        <SectionTitle right={<Link to="/tickets" className="text-xs font-semibold text-cobalt">View all →</Link>}>
          Recent tickets <span className="code-chip !text-[0.6875rem] !py-0">{data.recent_tickets.length}</span>
        </SectionTitle>
        {data.recent_tickets.length ? (
          <div className="grid gap-3 lg:grid-cols-2">{data.recent_tickets.map((t) => <RecentTicket key={t.id} t={t} />)}</div>
        ) : (
          <Empty title="No tickets yet" icon={<MessageSquare className="size-5" />}>Start a chat with the agent when something breaks.</Empty>
        )}
      </section>

      <section>
        <SectionTitle right={<Link to="/knowledge-base" className="text-xs font-semibold text-cobalt">QUICK SOLUTIONS</Link>}>Self-service guides</SectionTitle>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {data.guides.map((g) => {
            const Icon = GUIDE_ICON[g.category || ""] || BookOpen;
            return (
              <Link key={g.id} to={`/knowledge-base?doc=${g.id}`} className="card card-hover p-3.5 flex flex-col">
                <span className="flex size-8 items-center justify-center rounded-md border border-cobalt-line bg-cobalt-soft text-cobalt"><Icon className="size-4" /></span>
                <span className="mono text-[0.625rem] text-meta mt-3 uppercase">{g.category || "General"} · {g.doc_type}</span>
                <span className="text-sm font-semibold leading-snug mt-0.5 flex-1">{g.title}</span>
                <ArrowUpRight className="size-3.5 text-cobalt mt-2 self-end" />
              </Link>
            );
          })}
        </div>
      </section>

      <div className="card px-4 py-2.5 flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 mono text-[0.6875rem] text-meta"><span className="dot size-1.5 bg-ok" /> Precision AI agent v1.0</span>
        <span className="mono text-[0.6875rem] text-meta uppercase">Knowledge synced from database</span>
      </div>
    </div>
  );
}
