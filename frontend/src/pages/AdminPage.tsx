import { useState, type FormEvent } from "react";
import { Cpu, Database, Loader2, RefreshCw, Shield } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { NameCount, User } from "../services/types";
import { BarList, ChartCard, GrowthArea, Meter, SERIES, TrendLines } from "../components/charts";
import { Badge, ErrorNote, Field, PageHeader, SectionTitle, Spinner, StatTile, duration, timeAgo, titleCase } from "../components/ui";

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
  L0_policy: "L0 · deterministic policy", L1_rules: "L1 · rules only", L2_similarity: "L2 · similarity (dup/incident)",
  L3_verified_retrieval: "L3 · verified retrieval (no LLM)", L4_small_llm: "L4 · small / local LLM", L5_large_llm: "L5 · large LLM",
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
      <div className="flex justify-between items-center"><span className="label-caps">{label}</span>
        <Badge tone={avail ? "ok" : "neutral"}><span className={`dot size-1.5 ${avail ? "bg-ok" : "bg-faint"}`} />{avail ? "Available" : "Unavailable"}</Badge></div>
      <p className="mono text-sm mt-1">{t.provider}:{t.model}</p>
    </div>
  );
  return (
    <section className="card">
      <div className="card-header"><span className="label-caps !text-ink flex items-center gap-2"><Cpu className="size-4" /> System status</span><Badge mono>{s.environment} · {s.database}</Badge></div>
      <div className="p-4 space-y-3">
        <div className="grid gap-2 sm:grid-cols-2">
          {tier("LLM small tier (L4)", s.llm.small, s.llm.available.small)}
          {tier("LLM large tier (L5)", s.llm.large, s.llm.available.large)}
        </div>
        {!s.llm.available.small && !s.llm.available.large && (
          <p className="text-xs text-warn-ink rounded border border-warn-line bg-warn-soft px-3 py-2">No LLM reachable: the system is running in deterministic mode (rules, FAISS retrieval, verified knowledge). Start Ollama or set an API key to enable levels 4-5.</p>
        )}
        <div className="rounded border border-line p-3">
          <div className="flex justify-between items-center gap-2">
            <span className="label-caps flex items-center gap-1.5"><Database className="size-3.5" /> Vector store · {s.vector_store.backend}</span>
            <button className="btn-outline btn-sm" disabled={busy} onClick={rebuild}>{busy ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />} Rebuild from DB</button>
          </div>
          <p className="mono text-xs text-meta mt-1">{s.vector_store.embedder} · {s.vector_store.dim}-d</p>
          <div className="grid grid-cols-3 gap-2 mt-2">
            {Object.entries(s.vector_store.indexes).map(([k, v]) => (
              <div key={k} className="rounded bg-canvas px-2.5 py-2"><p className="label-caps">{k}</p><p className="font-semibold">{v}</p></div>
            ))}
          </div>
          {report && <p className="mono text-xs text-ok-ink mt-2">Rebuilt - {report}</p>}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
          {Object.entries(s.thresholds).map(([k, v]) => <div key={k} className="rounded bg-canvas px-2.5 py-1.5"><span className="text-meta">{titleCase(k)} sim ≥ </span><b>{v}</b></div>)}
          <div className="rounded bg-canvas px-2.5 py-1.5"><span className="text-meta">Incident: </span><b>{s.incident_min_tickets}+ in {s.incident_window_minutes}m</b></div>
          <div className="rounded bg-canvas px-2.5 py-1.5"><span className="text-meta">Agent attempts: </span><b>{s.agent_max_attempts}</b></div>
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
      <div className="card-header"><span className="label-caps !text-ink">Users & roles</span><input className="input !py-1 max-w-48 text-xs" placeholder="Filter users" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      <ErrorNote message={error} />
      <div className="overflow-x-auto max-h-96 scroll-thin">
        <table className="w-full text-sm min-w-[40rem]">
          <thead className="bg-canvas border-b border-line sticky top-0"><tr className="text-left">{["User", "Role", "Department", "Last login", "Active"].map((h) => <th key={h} className="label-caps px-3 py-2">{h}</th>)}</tr></thead>
          <tbody className="divide-y divide-muted">
            {rows.map((u) => (
              <tr key={u.id} className="h-11">
                <td className="px-3"><p className="font-medium">{u.full_name}</p><p className="mono text-[0.6875rem] text-meta">{u.username}</p></td>
                <td className="px-3"><select className="rounded border border-line bg-surface px-1.5 py-1 text-xs" value={u.role} disabled={u.id === me?.id}
                  onChange={(e) => update(u.id, { role: e.target.value })}>{["employee", "it_support", "admin"].map((r) => <option key={r} value={r}>{titleCase(r)}</option>)}</select></td>
                <td className="px-3"><select className="rounded border border-line bg-surface px-1.5 py-1 text-xs max-w-44" value={u.department_id ?? ""}
                  onChange={(e) => update(u.id, { department_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">-</option>{departments?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></td>
                <td className="px-3 mono text-xs text-meta">{u.last_login_at ? timeAgo(u.last_login_at) : "never"}</td>
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
      <div className="card-header"><span className="label-caps !text-ink">Ticket categories</span><span className="code-chip">{cats?.length}</span></div>
      <div className="p-4 space-y-3">
        <div className="flex flex-wrap gap-1.5">{cats?.map((c) => <Badge key={c.id}>{c.name} → {c.department || "Service Desk"}</Badge>)}</div>
        <form onSubmit={submit} className="grid gap-2 sm:grid-cols-[1fr_1fr_1.4fr_auto] items-end border-t border-muted pt-3">
          <Field label="New category"><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required minLength={2} /></Field>
          <Field label="Owning team"><select className="select" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
            <option value="">Service Desk</option>{departments?.filter((d) => d.is_support_team).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>
          <Field label="Keywords (comma-separated)"><input className="input" value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} placeholder="badge, door access, turnstile" /></Field>
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
      <summary className="card-header cursor-pointer list-none"><span className="label-caps !text-ink">Audit log</span><span className="code-chip">{data?.length ?? 0}</span></summary>
      <ul className="divide-y divide-muted max-h-80 overflow-y-auto scroll-thin">
        {data?.map((a) => (
          <li key={a.id} className="px-4 py-2 flex justify-between gap-3 text-[0.8125rem]">
            <span><span className="mono text-xs text-cobalt">{a.action}</span> <span className="text-body">{a.user || "anonymous"}</span>{a.resource_type && <span className="text-meta"> · {a.resource_type} #{a.resource_id}</span>}</span>
            <span className="mono text-[0.6875rem] text-meta shrink-0">{timeAgo(a.created_at)}</span>
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
      <PageHeader eyebrow={<Badge tone="ink"><Shield className="size-3" /> ADMINISTRATOR</Badge>} title="Admin analytics"
        subtitle="Computed live from PostgreSQL rows - no hard-coded numbers. Estimates are labelled with their basis."
        right={
          <div className="flex gap-1 rounded border border-line bg-surface p-0.5">
            {[7, 30, 90].map((d) => (
              <button key={d} onClick={() => setDays(d)} className={`rounded px-3 py-1 text-xs font-semibold ${days === d ? "bg-ink text-white" : "text-body hover:bg-muted"}`}>Last {d} days</button>
            ))}
          </div>} />

      <ErrorNote message={error} />
      {loading && !a ? <Spinner /> : a && (
        <div className={`space-y-6 transition-opacity ${loading ? "opacity-60" : ""}`}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatTile label="Total tickets" value={a.overview.total_tickets} sub={<span className="mono text-xs text-meta">{a.overview.tickets_in_window} in window</span>} />
            <StatTile label="AI resolution" value={`${a.overview.ai_resolution_percentage}%`} sub={<span className="mono text-xs text-meta">of resolved tickets</span>} />
            <StatTile label="Human escalation" value={`${a.overview.human_escalation_percentage}%`} sub={<span className="mono text-xs text-meta">of chatbot tickets</span>} />
            <StatTile label="Duplicates prevented" value={a.overview.duplicates_prevented} sub={<span className="mono text-xs text-meta">{a.overview.incidents_detected} incident(s) correlated</span>} />
            <StatTile label="Avg resolution" value={a.overview.avg_resolution_hours === null ? "-" : duration(a.overview.avg_resolution_hours * 60)} sub={<span className="mono text-xs text-meta">resolved in window</span>} />
            <StatTile label="Agent success rate" value={`${a.overview.agent_success_rate}%`} sub={<span className="mono text-xs text-meta">resolved / (resolved + escalated)</span>} />
            <StatTile label="Retrieval hit rate" value={`${a.overview.retrieval_hit_rate}%`} sub={<span className="mono text-xs text-meta">runs with ≥1 knowledge hit</span>} />
            <StatTile label="Knowledge base" value={a.overview.knowledge_base_size} sub={<span className="mono text-xs text-meta">solutions + documents</span>} />
          </div>

          <ChartCard title="Tickets per day" subtitle={`Created vs resolved by the AI agent · last ${a.window_days} days`}
            legend={[{ label: "Tickets created", color: SERIES[0] }, { label: "AI-resolved", color: SERIES[1] }]}
            table={{ columns: ["Date", "Created", "AI-resolved"], rows: a.tickets_per_day.map((d) => [d.date, d.tickets, d.ai_resolved]) }}>
            <TrendLines data={a.tickets_per_day} series={[{ key: "tickets", label: "Tickets created" }, { key: "ai_resolved", label: "AI-resolved" }]} />
          </ChartCard>

          <section>
            <SectionTitle>LLM cost optimisation</SectionTitle>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              <StatTile label="LLM calls" value={compact(a.llm_usage.calls)} sub={<span className="mono text-xs text-meta">{a.llm_usage.cache_hits} cache hits ({a.llm_usage.cache_hit_rate}%)</span>} />
              <StatTile label="Tokens used" value={compact(a.llm_usage.total_tokens)} sub={<span className="mono text-xs text-meta">${a.llm_usage.estimated_cost_usd.toFixed(4)} est. cost</span>} />
              <StatTile label="Resolved without LLM" value={a.overview.resolved_without_llm} sub={<span className="mono text-xs text-meta">{a.savings.runs_without_llm} runs skipped the LLM</span>} />
              <StatTile label="Est. tokens saved" value={compact(a.savings.estimated_tokens_saved)} sub={<span className="mono text-xs text-meta">≈ ${a.savings.estimated_cost_saved_usd.toFixed(4)}</span>} />
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              <ChartCard title="Deepest routing level per agent run" subtitle="Lower levels cost nothing; L4/L5 call a model"
                table={{ columns: ["Level", "Runs"], rows: a.routing_levels.map((r) => [ROUTING_LABEL[r.name] || r.name, r.count]) }}>
                <BarList items={a.routing_levels.map((r) => ({ ...r, label: ROUTING_LABEL[r.name] || r.name }))}
                  total={a.routing_levels.reduce((s, r) => s + r.count, 0)} />
              </ChartCard>
              <div className="card p-4 space-y-3">
                <p className="label-caps !text-ink">Usage by purpose</p>
                {a.llm_usage.by_purpose.length ? (
                  <table className="w-full text-sm"><tbody className="divide-y divide-muted">
                    {a.llm_usage.by_purpose.map((p) => <tr key={p.name}><td className="py-1.5">{titleCase(p.name)}</td><td className="tabular-nums text-right">{p.calls} calls</td><td className="tabular-nums text-right text-meta">{compact(p.tokens)} tok</td></tr>)}
                  </tbody></table>
                ) : <p className="text-sm text-meta">No LLM calls in this window - every ticket was handled by rules, retrieval and verified knowledge.</p>}
                <p className="text-xs text-meta border-t border-muted pt-3">
                  Savings estimate = runs that skipped the LLM × {a.savings.tokens_per_call} tokens per troubleshooting call
                  ({a.savings.estimate_basis}) × the configured reference price of the large model.
                </p>
              </div>
            </div>
          </section>

          <div className="grid gap-3 lg:grid-cols-3">
            <ChartCard title="Most common categories" subtitle="Tickets created in window"
              table={{ columns: ["Category", "Tickets"], rows: a.category_distribution.map((c) => [c.name, c.count]) }}>
              <BarList items={a.category_distribution} total={a.overview.tickets_in_window} />
            </ChartCard>
            <ChartCard title="Most common intents" table={{ columns: ["Intent", "Tickets"], rows: a.top_intents.map((c) => [c.label || c.name, c.count]) }}>
              <BarList items={a.top_intents} />
            </ChartCard>
            <ChartCard title="Priority distribution" subtitle="Effective (validated) priority"
              table={{ columns: ["Priority", "Tickets"], rows: a.priority_distribution.map((c) => [c.name, c.count]) }}>
              <BarList items={["critical", "high", "medium", "low"].map((p) => ({ name: titleCase(p), count: a.priority_distribution.find((x) => x.name === p)?.count || 0 }))} />
            </ChartCard>
          </div>

          <div className="grid gap-3 lg:grid-cols-[1.6fr_1fr]">
            <ChartCard title="Knowledge-base growth" subtitle="Cumulative solutions + documents"
              table={{ columns: ["Date", "Total"], rows: a.knowledge_growth.map((d) => [d.date, d.total]) }}>
              <GrowthArea data={a.knowledge_growth} dataKey="total" label="Knowledge items" />
            </ChartCard>
            <div className="card p-4 space-y-3">
              <p className="label-caps !text-ink">Solutions by trust level</p>
              {a.knowledge_by_level.map((l) => {
                const total = a.knowledge_by_level.reduce((s, x) => s + x.count, 0) || 1;
                return <Meter key={l.name} label={`${titleCase(l.name)} (${l.count})`} value={Math.round((l.count / total) * 100)} />;
              })}
              <p className="text-xs text-meta">Only user-confirmed and above are retrievable; human/admin-verified fixes are reused with no LLM call.</p>
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
