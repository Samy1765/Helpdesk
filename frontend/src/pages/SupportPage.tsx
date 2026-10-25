import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Check, ChevronDown, Loader2, Plus, X } from "lucide-react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { ActionView, NameCount, Solution, Ticket } from "../services/types";
import { ApprovalCard } from "../components/agent";
import { BarList, ChartCard, Meter } from "../components/charts";
import {
  Empty, ErrorNote, Field, PageHeader, PriorityBadge, SectionTitle, Spinner, StatTile, StatusBadge, TicketId,
  duration, timeAgo, titleCase,
} from "../components/ui";

interface Overview {
  new_tickets: number; open_tickets: number; awaiting_user: number; escalated_open: number; critical_open: number;
  ai_resolved: number; resolved: number; duplicates: number; incident_linked: number; active_incidents: number;
  pending_approvals: number; avg_resolution_hours: number | null; ai_resolution_rate: number; human_escalation_rate: number;
  total_tickets: number; category_distribution: NameCount[]; priority_distribution: NameCount[]; frequent_issues: NameCount[];
}

const VIEWS: [string, string][] = [
  ["all_open", "All open"], ["unassigned", "Unassigned"], ["mine", "Assigned to me"], ["escalated", "Escalated"],
  ["ai_active", "With the assistant"], ["critical", "High and critical"], ["duplicates", "Duplicates and incidents"], ["resolved", "Resolved"],
];
const LEVEL_LABEL: Record<string, string> = { ai_generated: "Suggested by AI", user_confirmed: "Confirmed by users", human_verified: "Verified by IT", admin_verified: "Verified by an administrator" };

function Queue() {
  const [view, setView] = useState("all_open");
  const [category, setCategory] = useState("");
  const { data, loading, error, reload } = useApi<Ticket[]>(`/support/queue?view=${view}${category ? `&category=${category}` : ""}`, 20000);
  const { data: categories } = useApi<{ id: number; name: string }[]>("/meta/categories");
  const [busy, setBusy] = useState<number | null>(null);
  const accept = async (id: number) => { setBusy(id); try { await api.post(`/support/tickets/${id}/accept`); reload(); } finally { setBusy(null); } };

  return (
    <section className="card">
      <div className="card-header flex-wrap">
        <h2 className="text-sm font-semibold">Queue</h2>
        <select className="rounded border border-line bg-surface px-2 py-1 text-sm" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
          <option value="">All categories</option>{categories?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
        </select>
      </div>
      <div className="flex gap-1 overflow-x-auto px-3 py-2 border-b border-muted scroll-thin">
        {VIEWS.map(([k, label]) => (
          <button key={k} onClick={() => setView(k)} className={`rounded px-2.5 py-1 text-sm whitespace-nowrap ${view === k ? "bg-cobalt-soft text-cobalt font-medium" : "text-body hover:bg-muted"}`}>{label}</button>
        ))}
      </div>
      <ErrorNote message={error} />
      {loading && !data ? <Spinner /> : !data?.length ? <p className="px-4 py-8 text-center text-sm text-meta">No tickets in this view.</p> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[46rem]">
            <thead>
              <tr>{["Ticket", "Problem", "Reported by", "Status", "Priority", "With", "Time left", ""].map((h, i) => <th key={i} className={`th ${h === "Time left" ? "!text-right" : ""}`}>{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y divide-muted">
              {data.map((t) => (
                <tr key={t.id} className="h-11 hover:bg-canvas">
                  <td className="px-3 whitespace-nowrap"><TicketId number={t.ticket_number} to={`/tickets/${t.id}`} /></td>
                  <td className="px-3 py-1.5 max-w-72"><Link to={`/tickets/${t.id}`} className="font-medium hover:text-cobalt line-clamp-1">{t.title}</Link>
                    <span className="text-xs text-meta">{t.category} · {timeAgo(t.created_at)}</span></td>
                  <td className="px-3 text-body whitespace-nowrap">{t.creator?.name}</td>
                  <td className="px-3"><StatusBadge status={t.status} /></td>
                  <td className="px-3"><PriorityBadge priority={t.priority} /></td>
                  <td className="px-3 text-meta whitespace-nowrap">{t.assignee?.name || t.department || "-"}</td>
                  <td className={`px-3 text-right text-xs tabular-nums whitespace-nowrap ${t.sla.breached && t.is_open ? "text-crit font-medium" : "text-meta"}`}>
                    {t.is_open ? (t.sla.breached ? `${duration(-t.sla.remaining_minutes)} over` : duration(t.sla.remaining_minutes)) : "-"}</td>
                  <td className="px-3 text-right">
                    {t.is_open && !t.assignee && <button className="btn-outline btn-sm" disabled={busy === t.id} onClick={() => accept(t.id)}>
                      {busy === t.id ? <Loader2 className="size-3.5 animate-spin" /> : "Take"}</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Approvals() {
  const { data, reload } = useApi<ActionView[]>("/actions/pending", 20000);
  if (!data?.length) return null;
  return (
    <section>
      <SectionTitle right={<span className="text-xs text-meta">{data.length} waiting</span>}>Waiting for approval</SectionTitle>
      <div className="grid gap-3 md:grid-cols-2">
        {data.map((a) => (
          <div key={a.id}>
            <p className="text-xs text-meta mb-1"><Link to={`/tickets/${a.ticket_id}`} className="mono text-cobalt">{a.ticket_number}</Link> · {a.ticket_title}</p>
            <ApprovalCard action={a} onDecide={a.can_decide ? async (ok) => { await api.post(`/actions/${a.id}/decision`, { approve: ok }); reload(); } : undefined} />
          </div>
        ))}
      </div>
    </section>
  );
}

function KnowledgeReview() {
  const [level, setLevel] = useState("user_confirmed");
  const { data, reload } = useApi<Solution[]>(`/support/solutions?level=${level}`);
  const { data: categories } = useApi<{ id: number; name: string }[]>("/meta/categories");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", problem_description: "", solution_description: "", category_id: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const act = async (fn: () => Promise<unknown>) => { setBusy(true); setError(null); try { await fn(); reload(); } catch (e) { setError(e instanceof Error ? e.message : "Failed"); } finally { setBusy(false); } };
  const add = (e: FormEvent) => { e.preventDefault(); act(async () => {
    await api.post("/support/solutions", { ...form, category_id: Number(form.category_id) });
    setForm({ title: "", problem_description: "", solution_description: "", category_id: "" }); setOpen(false); setLevel("human_verified");
  }); };

  return (
    <section className="card">
      <div className="card-header flex-wrap">
        <h2 className="text-sm font-semibold">Review past fixes</h2>
        <div className="flex gap-2">
          <select className="rounded border border-line bg-surface px-2 py-1 text-sm" value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Trust level">
            {Object.entries(LEVEL_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <button className="btn-outline btn-sm" onClick={() => setOpen((o) => !o)}><Plus className="size-3.5" /> Add a fix</button>
        </div>
      </div>
      <div className="p-4 space-y-3">
        <p className="text-sm text-meta">Fixes confirmed by users worked for someone but have not been checked by IT. Once verified, the assistant offers them straight away without using a language model. Rejected fixes are never suggested again.</p>
        <ErrorNote message={error} />
        {open && (
          <form onSubmit={add} className="rounded border border-line bg-canvas p-3 space-y-2.5">
            <div className="grid gap-2 sm:grid-cols-[1fr_12rem]">
              <Field label="Title"><input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required minLength={5} /></Field>
              <Field label="Category"><select className="select" value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })} required>
                <option value="">Choose</option>{categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
            </div>
            <Field label="Problem / symptoms"><textarea className="input min-h-16" value={form.problem_description} onChange={(e) => setForm({ ...form, problem_description: e.target.value })} required minLength={10} /></Field>
            <Field label="Fix (numbered steps work best)"><textarea className="input min-h-24" value={form.solution_description} onChange={(e) => setForm({ ...form, solution_description: e.target.value })} required minLength={10} /></Field>
            <button className="btn-accent" disabled={busy}>Save as verified</button>
          </form>
        )}
        {!data?.length ? <p className="text-sm text-meta text-center py-4">Nothing to review here.</p> : (
          <ul className="divide-y divide-muted">
            {data.slice(0, 12).map((s) => (
              <li key={s.id} className="py-3 flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{s.title}</p>
                  <p className="text-sm text-body line-clamp-2">{s.solution_description}</p>
                  <p className="text-xs text-meta mt-0.5">{s.category} · used {s.times_used} {s.times_used === 1 ? "time" : "times"}, worked {s.times_successful}, failed {s.times_failed}{s.ticket_number ? ` · from ${s.ticket_number}` : ""}</p>
                </div>
                {!["admin_verified"].includes(s.confidence_level) && (
                  <div className="flex gap-1.5">
                    {s.confidence_level !== "human_verified" && <button className="btn-outline btn-sm" disabled={busy} onClick={() => act(() => api.post(`/support/solutions/${s.id}/verify`))}><Check className="size-3.5 text-ok" /> Verify</button>}
                    <button className="btn-danger btn-sm" disabled={busy} onClick={() => act(() => api.post(`/support/solutions/${s.id}/reject`))}><X className="size-3.5" /> Reject</button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export default function SupportPage() {
  const { data: o, loading, error } = useApi<Overview>("/support/overview", 20000);
  const [showCharts, setShowCharts] = useState(true);
  if (loading && !o) return <Spinner />;
  if (!o) return <ErrorNote message={error} />;
  const openTotal = o.category_distribution.reduce((s, c) => s + c.count, 0);

  return (
    <div className="space-y-6">
      <PageHeader title="Support queue" subtitle="Tickets that need IT staff, requests waiting for approval and fixes to review." />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatTile label="Open" value={o.open_tickets} sub={<span className="text-xs text-meta">{o.new_tickets} new, {o.awaiting_user} waiting for the user</span>} />
        <StatTile label="With IT staff" value={o.escalated_open} sub={<span className="text-xs text-meta">{o.pending_approvals} waiting for approval</span>} />
        <StatTile label="Critical and open" value={o.critical_open} tone={o.critical_open ? "crit" : "default"} sub={<span className="text-xs text-meta">{o.active_incidents} ongoing {o.active_incidents === 1 ? "incident" : "incidents"}</span>} />
        <StatTile label="Solved by the assistant" value={o.ai_resolved} sub={<span className="text-xs text-meta">of {o.resolved} resolved</span>} />
        <StatTile label="Repeat reports grouped" value={o.duplicates + o.incident_linked} sub={<span className="text-xs text-meta">{o.duplicates} duplicates, {o.incident_linked} in incidents</span>} />
        <StatTile label="Average time to resolve" value={o.avg_resolution_hours === null ? "-" : duration(o.avg_resolution_hours * 60)} sub={<span className="text-xs text-meta">all resolved tickets</span>} />
        <div className="card p-3.5 col-span-2 space-y-3">
          <Meter label="Resolved without IT staff (share of resolved tickets)" value={o.ai_resolution_rate} />
          <Meter label="Passed to IT staff (share of chat tickets)" value={o.human_escalation_rate} />
        </div>
      </div>

      <Approvals />
      <Queue />

      <section>
        <button className="btn-ghost btn-sm !px-0 mb-2" onClick={() => setShowCharts((s) => !s)}>
          <ChevronDown className={`size-3.5 transition-transform ${showCharts ? "" : "-rotate-90"}`} /> Open tickets by category and priority
        </button>
        {showCharts && (
          <div className="grid gap-3 lg:grid-cols-3">
            <ChartCard title="Open by category" subtitle="Currently open tickets"
              table={{ columns: ["Category", "Open"], rows: o.category_distribution.map((c) => [c.name, c.count]) }}>
              <BarList items={o.category_distribution} total={openTotal} />
            </ChartCard>
            <ChartCard title="Open by priority" subtitle="After the priority check"
              table={{ columns: ["Priority", "Open"], rows: o.priority_distribution.map((c) => [c.name, c.count]) }}>
              <BarList items={["critical", "high", "medium", "low"].map((p) => ({ name: titleCase(p), count: o.priority_distribution.find((x) => x.name === p)?.count || 0 }))} />
            </ChartCard>
            <ChartCard title="Most common problems" subtitle="Last 7 days"
              table={{ columns: ["Issue", "Tickets"], rows: o.frequent_issues.map((c) => [c.label || c.name, c.count]) }}>
              <BarList items={o.frequent_issues} />
            </ChartCard>
          </div>
        )}
      </section>

      <KnowledgeReview />
      {!o.total_tickets && <Empty title="No tickets yet" />}
    </div>
  );
}
