import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Check, Inbox, Plus, X } from "lucide-react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { ActionView, NameCount, Solution, Ticket } from "../services/types";
import { BarList, ChartCard } from "../components/charts";
import {
  Card, EmptyState, ErrorState, Field, FormError, PageHeader, PriorityBadge, Section, Segmented, SkeletonPage,
  SkeletonTable, Spinner, StatTile, StatusBadge, TicketId, TrustBadge, priorityLabel,
} from "../components/ui";
import { SlaLabel, ownerLine } from "../components/tickets";
import { duration, relative } from "../lib/format";

interface Overview {
  new_tickets: number; open_tickets: number; awaiting_user: number; escalated_open: number; critical_open: number;
  ai_resolved: number; resolved: number; duplicates: number; incident_linked: number; active_incidents: number;
  pending_approvals: number; avg_resolution_hours: number | null; ai_resolution_rate: number; human_escalation_rate: number;
  total_tickets: number; sla_breached_open: number;
  category_distribution: NameCount[]; priority_distribution: NameCount[]; frequent_issues: NameCount[];
}

type View = "all_open" | "unassigned" | "mine" | "escalated" | "ai_active" | "critical" | "duplicates" | "resolved";
const VIEWS: [View, string][] = [
  ["all_open", "All open"], ["unassigned", "Unassigned"], ["mine", "Assigned to me"], ["escalated", "With IT"],
  ["ai_active", "Agent working"], ["critical", "High and critical"], ["duplicates", "Duplicates and incidents"], ["resolved", "Resolved"],
];

function Queue() {
  const [view, setView] = useState<View>("all_open");
  const [category, setCategory] = useState("");
  const { data, loading, error, reload } = useApi<Ticket[]>(`/support/queue?view=${view}${category ? `&category=${category}` : ""}`, 30000);
  const { data: categories } = useApi<{ id: number; name: string }[]>("/meta/categories");
  const [busy, setBusy] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const accept = async (id: number) => {
    setBusy(id); setActionError(null);
    try { await api.post(`/support/tickets/${id}/accept`); reload(); }
    catch (e) { setActionError(e instanceof Error ? e.message : "Could not assign the ticket"); } finally { setBusy(null); }
  };

  return (
    <Section title="Queue" description="Most urgent first. Updates every 30 seconds."
      actions={<div>
        <label htmlFor="queue-category" className="sr-only">Category</label>
        <select id="queue-category" className="select w-48 py-1" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">All categories</option>{categories?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
        </select>
      </div>}>
      <div className="mb-4"><Segmented label="Queue view" value={view} onChange={setView} options={VIEWS} /></div>
      <ErrorState message={error} what="the queue" onRetry={reload} />
      {actionError && <div className="mb-2"><FormError message={actionError} /></div>}
      {loading && !data ? <SkeletonTable rows={8} /> : !data?.length ? (
        <EmptyState title="Nothing in this view" icon={<Inbox className="size-5" aria-hidden />}>Choose another view or category.</EmptyState>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Ticket queue</caption>
            <thead className="border-b border-line bg-canvas">
              <tr><th className="th">Ticket</th><th className="th">Subject</th><th className="th">Requester</th><th className="th">Status</th><th className="th">Priority</th><th className="th">SLA</th><th className="th"><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {data.map((t) => (
                <tr key={t.id} className="hover:bg-canvas">
                  <td className="td whitespace-nowrap"><TicketId number={t.ticket_number} to={`/tickets/${t.id}`} /></td>
                  <td className="td min-w-72">
                    <Link to={`/tickets/${t.id}`} className="font-medium text-ink hover:underline">{t.title}</Link>
                    <span className="mt-1 block text-xs text-meta">{t.category} · {ownerLine(t, "staff")} · opened {relative(t.created_at)}</span>
                  </td>
                  <td className="td whitespace-nowrap text-body">{t.creator?.name}<span className="block text-xs text-meta">{t.creator?.department}</span></td>
                  <td className="td"><StatusBadge status={t.status} /></td>
                  <td className="td"><PriorityBadge priority={t.priority} /></td>
                  <td className="td"><SlaLabel ticket={t} /></td>
                  <td className="td text-right">
                    {t.is_open && !t.assignee && (
                      <button className="btn-secondary btn-sm" disabled={busy === t.id} onClick={() => accept(t.id)} aria-label={`Assign ${t.ticket_number} to me`}>
                        {busy === t.id && <Spinner />} Assign to me
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Section>
  );
}

function Approvals() {
  const { data, reload } = useApi<ActionView[]>("/actions/pending", 30000);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!data?.length) return null;
  const decide = async (a: ActionView, approve: boolean) => {
    setBusy(a.id); setError(null);
    try { await api.post(`/actions/${a.id}/decision`, { approve }); reload(); }
    catch (e) { setError(e instanceof Error ? e.message : "Decision failed"); } finally { setBusy(null); }
  };
  return (
    <Section title={`Approvals waiting (${data.length})`} description="Restricted actions wait for the employee or IT; dangerous ones for an administrator.">
      <FormError message={error} />
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">Approvals waiting</caption>
          <thead className="border-b border-line bg-canvas"><tr><th className="th">Ticket</th><th className="th">Action</th><th className="th">Approver</th><th className="th">Requested</th><th className="th"><span className="sr-only">Decision</span></th></tr></thead>
          <tbody className="divide-y divide-line">
            {data.map((a) => (
              <tr key={a.id}>
                <td className="td"><TicketId number={a.ticket_number || ""} to={`/tickets/${a.ticket_id}`} /><span className="block max-w-64 truncate text-xs text-meta">{a.ticket_title}</span></td>
                <td className="td"><span className="font-medium text-ink">{a.label}</span><span className="block text-xs text-meta">{a.risk_note}</span></td>
                <td className="td whitespace-nowrap text-body">{a.permission === "dangerous" ? "Administrator" : "Employee or IT"}</td>
                <td className="td whitespace-nowrap text-meta">{relative(a.created_at)}</td>
                <td className="td text-right">
                  {a.can_decide ? (
                    <span className="inline-flex gap-2">
                      <button className="btn-secondary btn-sm" disabled={busy === a.id} onClick={() => decide(a, true)} aria-label={`Approve ${a.label} for ${a.ticket_number}`}>Approve</button>
                      <button className="btn-ghost btn-sm" disabled={busy === a.id} onClick={() => decide(a, false)} aria-label={`Decline ${a.label} for ${a.ticket_number}`}>Decline</button>
                    </span>
                  ) : <span className="text-xs text-meta">Administrator only</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

const LEVELS: [string, string][] = [["user_confirmed", "Confirmed by employees"], ["human_verified", "Verified by IT"], ["admin_verified", "Verified by admins"], ["ai_generated", "AI suggestions"]];

function KnowledgeReview() {
  const [level, setLevel] = useState("user_confirmed");
  const { data, reload, loading } = useApi<Solution[]>(`/support/solutions?level=${level}`);
  const { data: categories } = useApi<{ id: number; name: string }[]>("/meta/categories");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", problem_description: "", solution_description: "", category_id: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const act = async (fn: () => Promise<unknown>) => { setBusy(true); setError(null); try { await fn(); reload(); } catch (e) { setError(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(false); } };
  const add = (e: FormEvent) => { e.preventDefault(); act(async () => {
    await api.post("/support/solutions", { ...form, category_id: Number(form.category_id) });
    setForm({ title: "", problem_description: "", solution_description: "", category_id: "" }); setOpen(false); setLevel("human_verified");
  }); };

  return (
    <Card title="Knowledge review" actions={
      <div className="flex flex-wrap gap-2">
        <label htmlFor="review-level" className="sr-only">Trust level</label>
        <select id="review-level" className="select w-56 py-1" value={level} onChange={(e) => setLevel(e.target.value)}>
          {LEVELS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <button className="btn-secondary btn-sm" onClick={() => setOpen((o) => !o)}><Plus className="size-4" aria-hidden /> Add a fix</button>
      </div>}>
      <div className="space-y-4">
        <p className="text-sm text-meta">Fixes confirmed by employees have worked at least once but nobody in IT has checked them. Verifying one lets the agent reuse it without an AI model; declining removes it from search.</p>
        <FormError message={error} />
        {open && (
          <form onSubmit={add} className="space-y-4 rounded-sm border border-line bg-canvas p-4">
            <div className="grid gap-4 sm:grid-cols-[1fr_12rem]">
              <Field label="Title" htmlFor="sol-title"><input id="sol-title" className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required minLength={5} /></Field>
              <Field label="Category" htmlFor="sol-category"><select id="sol-category" className="select" value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })} required>
                <option value="">Choose</option>{categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
            </div>
            <Field label="Problem, as employees describe it" htmlFor="sol-problem"><textarea id="sol-problem" className="input min-h-16" value={form.problem_description} onChange={(e) => setForm({ ...form, problem_description: e.target.value })} required minLength={10} /></Field>
            <Field label="Fix (numbered steps)" htmlFor="sol-fix"><textarea id="sol-fix" className="input min-h-24" value={form.solution_description} onChange={(e) => setForm({ ...form, solution_description: e.target.value })} required minLength={10} /></Field>
            <button className="btn-primary" disabled={busy}>{busy && <Spinner />} Save as verified fix</button>
          </form>
        )}
        {loading && !data ? <SkeletonTable rows={3} /> : !data?.length ? <p className="py-4 text-center text-sm text-meta">Nothing to review at this level.</p> : (
          <ul className="divide-y divide-line">
            {data.slice(0, 10).map((s) => (
              <li key={s.id} className="flex flex-wrap items-start justify-between gap-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-sm font-medium text-ink">{s.title} <TrustBadge level={s.confidence_level} /></p>
                  <p className="mt-1 line-clamp-2 text-sm text-body">{s.solution_description}</p>
                  <p className="mt-1 text-xs text-meta">{s.category} · used {s.times_used} times, worked {s.times_successful}{s.ticket_number ? ` · from ${s.ticket_number}` : ""}</p>
                </div>
                {s.confidence_level !== "admin_verified" && (
                  <div className="flex gap-2">
                    {s.confidence_level !== "human_verified" && <button className="btn-secondary btn-sm" disabled={busy} onClick={() => act(() => api.post(`/support/solutions/${s.id}/verify`))}><Check className="size-4 text-ok" aria-hidden /> Verify</button>}
                    <button className="btn-danger btn-sm" disabled={busy} onClick={() => act(() => api.post(`/support/solutions/${s.id}/reject`))}><X className="size-4" aria-hidden /> Decline</button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

export default function SupportPage() {
  const { data: o, loading, error, reload } = useApi<Overview>("/support/overview", 30000);
  if (loading && !o) return <SkeletonPage />;
  if (!o) return <ErrorState message={error} what="the support queue" onRetry={reload} />;
  const openTotal = o.category_distribution.reduce((s, c) => s + c.count, 0);

  return (
    <div className="space-y-8">
      <PageHeader title="Support queue" description="Open work for every IT team, the approvals waiting on people, and fixes to review." />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatTile label="Open tickets" value={o.open_tickets} hint={`${o.awaiting_user} waiting on the employee`} />
        <StatTile label="With IT" value={o.escalated_open} hint="Escalated, assigned or in progress" />
        <StatTile label="Past SLA" value={o.sla_breached_open} tone={o.sla_breached_open ? "crit" : undefined} hint="Open tickets over their target" />
        <StatTile label="Critical open" value={o.critical_open} tone={o.critical_open ? "crit" : undefined} hint={`${o.active_incidents} active incident${o.active_incidents === 1 ? "" : "s"}`} />
        <StatTile label="Resolved by the agent" value={`${o.ai_resolution_rate}%`} hint={`${o.ai_resolved} of ${o.resolved} resolved · avg ${duration((o.avg_resolution_hours ?? 0) * 60)}`} />
      </div>

      <Approvals />
      <Queue />

      <div className="grid gap-4 lg:grid-cols-3">
        <ChartCard title="Open tickets by category" table={{ columns: ["Category", "Open"], rows: o.category_distribution.map((c) => [c.name, c.count]) }}>
          <BarList items={o.category_distribution} total={openTotal} />
        </ChartCard>
        <ChartCard title="Open tickets by priority" table={{ columns: ["Priority", "Open"], rows: o.priority_distribution.map((c) => [c.name, c.count]) }}>
          <BarList items={(["critical", "high", "medium", "low"] as const).map((p) => ({ name: priorityLabel(p), count: o.priority_distribution.find((x) => x.name === p)?.count || 0 }))} />
        </ChartCard>
        <ChartCard title="Most reported this week" description="By issue type, last 7 days" table={{ columns: ["Issue", "Tickets"], rows: o.frequent_issues.map((c) => [c.label || c.name, c.count]) }}>
          <BarList items={o.frequent_issues} />
        </ChartCard>
      </div>

      <KnowledgeReview />
    </div>
  );
}
