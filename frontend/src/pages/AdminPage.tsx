import { useState, type FormEvent } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { NameCount, User } from "../services/types";
import { BarList, ChartCard, GrowthArea, Meter, SERIES, TrendLines } from "../components/charts";
import { Badge, ErrorNote, Field, PageHeader, SectionTitle, Spinner, StatTile, confidenceText, dateTime, duration, sentenceCase, timeAgo, titleCase } from "../components/ui";

interface Analytics {
  window_days: number;
  overview: {
    total_tickets: number; tickets_in_window: number; ai_resolution_percentage: number; human_escalation_percentage: number;
    duplicates_prevented: number; duplicate_tickets: number; incident_linked_tickets: number; incidents_detected: number;
    avg_resolution_hours: number | null; agent_success_rate: number; retrieval_hit_rate: number; resolved_without_llm: number;
    knowledge_base_size: number;
  };
  tickets_per_day: { date: string; tickets: number; ai_resolved: number }[];
  category_distribution: NameCount[];
  priority_distribution: NameCount[];
  top_intents: NameCount[];
  routing_levels: NameCount[];
  knowledge_growth: { date: string; total: number }[];
  knowledge_by_level: NameCount[];
  llm_usage: { calls: number; successful_calls: number; total_tokens: number; estimated_cost_usd: number; cache_hits: number; cache_hit_rate: number;
    by_purpose: { name: string; calls: number; tokens: number }[]; by_provider: { name: string; calls: number }[] };
  savings: { runs_without_llm: number; tokens_per_call: number; estimate_basis: string; estimated_tokens_saved: number; estimated_cost_saved_usd: number };
}

interface System {
  environment: string; database: string;
  llm: { small: { provider: string; model: string }; large: { provider: string; model: string }; available: { small: string | null; large: string | null } };
  vector_store: { backend: string; embedder: string; dim: number; indexes: Record<string, number> };
  thresholds: Record<string, number>;
  incident_window_minutes: number; incident_min_tickets: number; agent_max_attempts: number; diagnostic_tools_enabled: boolean;
}

const ROUTING_LABEL: Record<string, string> = {
  L0_policy: "L0 Policy rule", L1_rules: "L1 Rules", L2_similarity: "L2 Duplicate or incident",
  L3_verified_retrieval: "L3 Verified fix, no model", L4_small_llm: "L4 Small model", L5_large_llm: "L5 Large model",
};
const compact = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}K` : String(n);

function SystemPanel() {
  const { data: s, reload } = useApi<System>("/admin/system");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  if (!s) return <Spinner />;
  const rebuild = async () => {
    setBusy(true);
    try {
      const r = await api.post<Record<string, { count: number }>>("/admin/index/rebuild");
      setReport(Object.entries(r).map(([k, v]) => `${k}: ${v.count}`).join(" · "));
      reload();
    } finally { setBusy(false); }
  };
  const tier = (label: string, t: { provider: string; model: string }, avail: string | null) => (
    <div className="rounded border border-line p-3">
      <div className="flex justify-between items-center"><span className="text-sm text-meta">{label}</span>
        <Badge tone={avail ? "ok" : "neutral"}>{avail ? "Reachable" : "Not reachable"}</Badge></div>
      <p className="mono text-sm mt-1">{t.provider}:{t.model}</p>
    </div>
  );
  return (
    <section className="card">
      <div className="card-header"><h2 className="text-sm font-semibold">System</h2><span className="text-xs text-meta">{s.environment} · {s.database}</span></div>
      <div className="p-4 space-y-3">
        <div className="grid gap-2 sm:grid-cols-2">
          {tier("Small model (L4)", s.llm.small, s.llm.available.small)}
          {tier("Large model (L5)", s.llm.large, s.llm.available.large)}
        </div>
        {!s.llm.available.small && !s.llm.available.large && (
          <p className="text-sm text-warn-ink rounded border border-warn-line bg-warn-soft px-3 py-2">No language model is reachable, so the assistant uses rules, search and verified fixes only. Start Ollama or add an API key to enable levels 4 and 5.</p>
        )}
        <div className="rounded border border-line p-3">
          <div className="flex justify-between items-center gap-2">
            <span className="text-sm text-meta">Search index ({s.vector_store.backend})</span>
            <button className="btn-outline btn-sm" disabled={busy} onClick={rebuild}>{busy ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />} Rebuild</button>
          </div>
          <p className="mono text-xs text-meta mt-1">{s.vector_store.embedder} · {s.vector_store.dim}-d</p>
          <div className="grid grid-cols-3 gap-2 mt-2">
            {Object.entries(s.vector_store.indexes).map(([k, v]) => (
              <div key={k} className="rounded bg-canvas px-2.5 py-2"><p className="text-xs text-meta">{sentenceCase(k)}</p><p className="font-semibold tabular-nums">{v}</p></div>
            ))}
          </div>
          {report && <p className="text-xs text-ok-ink mt-2">Rebuilt: {report}</p>}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
          {Object.entries(s.thresholds).map(([k, v]) => <div key={k} className="rounded bg-canvas px-2.5 py-1.5"><span className="text-meta">{sentenceCase(k)} threshold </span><b className="font-medium">{v}</b></div>)}
          <div className="rounded bg-canvas px-2.5 py-1.5"><span className="text-meta">Incident: </span><b className="font-medium">{s.incident_min_tickets}+ reports in {s.incident_window_minutes} min</b></div>
          <div className="rounded bg-canvas px-2.5 py-1.5"><span className="text-meta">Fix attempts before escalation: </span><b className="font-medium">{s.agent_max_attempts}</b></div>
        </div>
      </div>
    </section>
  );
}

function Users() {
  const { user: me } = useAuth();
  const { data, reload } = useApi<User[]>("/admin/users");
  const { data: departments } = useApi<{ id: number; name: string }[]>("/meta/departments");
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const update = async (id: number, body: Record<string, unknown>) => {
    setError(null);
    try { await api.patch(`/admin/users/${id}`, body); reload(); } catch (e) { setError(e instanceof Error ? e.message : "Update failed"); }
  };
  const rows = (data || []).filter((u) => !q || `${u.full_name} ${u.username} ${u.email}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <section className="card">
      <div className="card-header"><h2 className="text-sm font-semibold">Users and roles <span className="font-normal text-meta">({data?.length ?? 0})</span></h2><input className="input !py-1 max-w-56" placeholder="Search by name or email" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <ErrorNote message={error} />
      <div className="overflow-x-auto max-h-96 scroll-thin">
        <table className="w-full text-sm min-w-[40rem]">
          <thead className="sticky top-0"><tr>{["Name", "Role", "Department or team", "Last sign-in", "Active"].map((h) => <th key={h} className="th">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-muted">
            {rows.map((u) => (
              <tr key={u.id} className="h-11">
                <td className="px-3 py-1.5"><p className="font-medium">{u.full_name}</p><p className="text-xs text-meta">{u.email}</p></td>
                <td className="px-3"><select className="rounded border border-line bg-surface px-1.5 py-1 text-sm" value={u.role} disabled={u.id === me?.id} aria-label="Role"
                  onChange={(e) => update(u.id, { role: e.target.value })}>{[["employee", "Employee"], ["it_support", "IT support"], ["admin", "Administrator"]].map(([r, l]) => <option key={r} value={r}>{l}</option>)}</select></td>
                <td className="px-3"><select className="rounded border border-line bg-surface px-1.5 py-1 text-sm max-w-48" value={u.department_id ?? ""} aria-label="Department"
                  onChange={(e) => update(u.id, { department_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">-</option>{departments?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></td>
                <td className="px-3 text-xs text-meta">{u.last_login_at ? timeAgo(u.last_login_at) : "never"}</td>
                <td className="px-3"><input type="checkbox" className="accent-cobalt size-4" checked={u.is_active} disabled={u.id === me?.id}
                  onChange={(e) => update(u.id, { is_active: e.target.checked })} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Categories() {
  const { data: cats, reload } = useApi<{ id: number; name: string; department: string | null }[]>("/meta/categories");
  const { data: departments } = useApi<{ id: number; name: string; is_support_team: boolean }[]>("/meta/departments");
  const [form, setForm] = useState({ name: "", keywords: "", department_id: "" });
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setError(null);
    try {
      await api.post("/admin/categories", { name: form.name, department_id: form.department_id ? Number(form.department_id) : null,
        keywords: form.keywords.split(",").map((k) => k.trim()).filter(Boolean) });
      setForm({ name: "", keywords: "", department_id: "" }); reload();
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); }
  };
  return (
    <section className="card">
      <div className="card-header"><h2 className="text-sm font-semibold">Ticket categories</h2><span className="text-xs text-meta">{cats?.length}</span></div>
      <div className="p-4 space-y-3">
        <ul className="grid sm:grid-cols-2 gap-x-4 text-sm">{cats?.map((c) => (
          <li key={c.id} className="flex justify-between gap-2 py-1 border-b border-muted"><span>{c.name}</span><span className="text-meta">{c.department || "Service Desk"}</span></li>))}</ul>
        <form onSubmit={submit} className="grid gap-2 sm:grid-cols-[1fr_1fr_1.4fr_auto] items-end border-t border-muted pt-3">
          <Field label="New category"><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required minLength={2} /></Field>
          <Field label="Owning team"><select className="select" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
            <option value="">Service Desk</option>{departments?.filter((d) => d.is_support_team).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>
          <Field label="Keywords, separated by commas"><input className="input" value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} placeholder="badge, door access, turnstile" /></Field>
          <button className="btn-primary">Add</button>
        </form>
        <ErrorNote message={error} />
      </div>
    </section>
  );
}

function AuditLog() {
  const { data } = useApi<{ id: number; action: string; user: string | null; resource_type: string | null; resource_id: number | null; created_at: string }[]>("/admin/audit-logs?limit=40");
  return (
    <details className="card">
      <summary className="card-header cursor-pointer list-none"><h2 className="text-sm font-semibold">Audit log</h2><span className="text-xs text-meta">latest {data?.length ?? 0} entries</span></summary>
      <ul className="divide-y divide-muted max-h-80 overflow-y-auto scroll-thin">
        {data?.map((a) => (
          <li key={a.id} className="px-4 py-2 flex justify-between gap-3 text-[0.8125rem]">
            <span><span className="text-ink">{sentenceCase(a.action)}</span> <span className="text-meta">· {a.user || "unknown user"}{a.resource_type && ` · ${a.resource_type} ${a.resource_id ?? ""}`}</span></span>
            <span className="text-xs text-meta shrink-0">{dateTime(a.created_at)}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function AdminPage() {
  const [days, setDays] = useState(30);
  const { data: a, error, loading } = useApi<Analytics>(`/admin/analytics?days=${days}`, 60000);

  return (
    <div className="space-y-6">
      <PageHeader title="Administration"
        subtitle="All figures are calculated from the database when the page loads. Estimates say how they were worked out."
        right={
          <div className="flex gap-1 rounded border border-line bg-surface p-0.5">
            {[7, 30, 90].map((d) => (
              <button key={d} onClick={() => setDays(d)} className={`rounded px-3 py-1 text-sm ${days === d ? "bg-cobalt-soft text-cobalt font-medium" : "text-body hover:bg-muted"}`}>{d} days</button>
            ))}
          </div>} />

      <ErrorNote message={error} />
      {loading && !a ? <Spinner /> : a && (
        <div className={`space-y-6 transition-opacity ${loading ? "opacity-60" : ""}`}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile label="Tickets" value={a.overview.tickets_in_window} sub={<span className="text-xs text-meta">{a.overview.total_tickets} in total</span>} />
            <StatTile label="Resolved by the assistant" value={`${a.overview.ai_resolution_percentage}%`} sub={<span className="text-xs text-meta">of resolved tickets</span>} />
            <StatTile label="Passed to IT staff" value={`${a.overview.human_escalation_percentage}%`} sub={<span className="text-xs text-meta">of chat tickets</span>} />
            <StatTile label="Repeat reports grouped" value={a.overview.duplicates_prevented} sub={<span className="text-xs text-meta">{a.overview.incidents_detected} {a.overview.incidents_detected === 1 ? "incident" : "incidents"} found</span>} />
            <StatTile label="Average time to resolve" value={a.overview.avg_resolution_hours === null ? "-" : duration(a.overview.avg_resolution_hours * 60)} sub={<span className="text-xs text-meta">tickets resolved in period</span>} />
            <StatTile label="Assistant success rate" value={`${a.overview.agent_success_rate}%`} sub={<span className="text-xs text-meta">resolved out of resolved + escalated</span>} />
            <StatTile label="Knowledge found" value={`${a.overview.retrieval_hit_rate}%`} sub={<span className="text-xs text-meta">of requests had a relevant article or fix</span>} />
            <StatTile label="Knowledge base" value={a.overview.knowledge_base_size} sub={<span className="text-xs text-meta">articles and verified fixes</span>} />
          </div>

          <ChartCard title="Tickets per day" subtitle={`New tickets and tickets the assistant resolved, last ${a.window_days} days`}
            legend={[{ label: "New tickets", color: SERIES[0] }, { label: "Resolved by the assistant", color: SERIES[1] }]}
            table={{ columns: ["Date", "New", "Resolved by the assistant"], rows: a.tickets_per_day.map((d) => [d.date, d.tickets, d.ai_resolved]) }}>
            <TrendLines data={a.tickets_per_day} series={[{ key: "tickets", label: "New tickets" }, { key: "ai_resolved", label: "Resolved by the assistant" }]} />
          </ChartCard>

          <section>
            <SectionTitle>Language model usage and cost</SectionTitle>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <StatTile label="Model calls" value={compact(a.llm_usage.calls)} sub={<span className="text-xs text-meta">{a.llm_usage.cache_hits} answered from cache ({a.llm_usage.cache_hit_rate}%)</span>} />
              <StatTile label="Tokens used" value={compact(a.llm_usage.total_tokens)} sub={<span className="text-xs text-meta">about ${a.llm_usage.estimated_cost_usd.toFixed(4)}</span>} />
              <StatTile label="Resolved without a model" value={a.overview.resolved_without_llm} sub={<span className="text-xs text-meta">{a.savings.runs_without_llm} requests needed no model</span>} />
              <StatTile label="Tokens saved (estimate)" value={compact(a.savings.estimated_tokens_saved)} sub={<span className="text-xs text-meta">about ${a.savings.estimated_cost_saved_usd.toFixed(4)}</span>} />
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              <ChartCard title="How requests were answered" subtitle="Highest level each request reached. Levels 0 to 3 cost nothing; 4 and 5 call a model."
                table={{ columns: ["Level", "Runs"], rows: a.routing_levels.map((r) => [ROUTING_LABEL[r.name] || r.name, r.count]) }}>
                <BarList items={a.routing_levels.map((r) => ({ ...r, label: ROUTING_LABEL[r.name] || r.name }))}
                  total={a.routing_levels.reduce((s, r) => s + r.count, 0)} />
              </ChartCard>
              <div className="card p-4 space-y-3">
                <h3 className="text-sm font-semibold">Usage by purpose</h3>
                {a.llm_usage.by_purpose.length ? (
                  <table className="w-full text-sm"><tbody className="divide-y divide-muted">
                    {a.llm_usage.by_purpose.map((p) => <tr key={p.name}><td className="py-1.5">{sentenceCase(p.name)}</td><td className="tabular-nums text-right">{p.calls} calls</td><td className="tabular-nums text-right text-meta">{compact(p.tokens)} tokens</td></tr>)}
                  </tbody></table>
                ) : <p className="text-sm text-meta">No model calls in this period. Every request was handled by rules, search and verified fixes.</p>}
                <p className="text-xs text-meta border-t border-muted pt-3">
                  Savings estimate: requests that needed no model × {a.savings.tokens_per_call} tokens per troubleshooting call
                  ({a.savings.estimate_basis}) × the configured price of the large model.
                </p>
              </div>
            </div>
          </section>

          <div className="grid gap-3 lg:grid-cols-3">
            <ChartCard title="Tickets by category" subtitle="New tickets in this period"
              table={{ columns: ["Category", "Tickets"], rows: a.category_distribution.map((c) => [c.name, c.count]) }}>
              <BarList items={a.category_distribution} total={a.overview.tickets_in_window} />
            </ChartCard>
            <ChartCard title="Most common problems" table={{ columns: ["Problem", "Tickets"], rows: a.top_intents.map((c) => [c.label || c.name, c.count]) }}>
              <BarList items={a.top_intents} />
            </ChartCard>
            <ChartCard title="Tickets by priority" subtitle="After the priority check"
              table={{ columns: ["Priority", "Tickets"], rows: a.priority_distribution.map((c) => [c.name, c.count]) }}>
              <BarList items={["critical", "high", "medium", "low"].map((p) => ({ name: titleCase(p), count: a.priority_distribution.find((x) => x.name === p)?.count || 0 }))} />
            </ChartCard>
          </div>

          <div className="grid gap-3 lg:grid-cols-[1.6fr_1fr]">
            <ChartCard title="Knowledge base growth" subtitle="Articles and saved fixes, running total"
              table={{ columns: ["Date", "Total"], rows: a.knowledge_growth.map((d) => [d.date, d.total]) }}>
              <GrowthArea data={a.knowledge_growth} dataKey="total" label="Knowledge items" />
            </ChartCard>
            <div className="card p-4 space-y-3">
              <h3 className="text-sm font-semibold">Solutions by trust level</h3>
              {a.knowledge_by_level.map((l) => {
                const total = a.knowledge_by_level.reduce((s, x) => s + x.count, 0) || 1;
                return <Meter key={l.name} label={`${sentenceCase(confidenceText(l.name))} (${l.count})`} value={Math.round((l.count / total) * 100)} />;
              })}
              <p className="text-xs text-meta">Fixes suggested by AI are never offered again until a user confirms them. Fixes verified by IT are offered straight away, without a model call.</p>
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <SystemPanel />
        <Categories />
      </div>
      <Users />
      <AuditLog />
    </div>
  );
}
