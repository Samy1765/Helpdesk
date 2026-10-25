import { useState, type FormEvent } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { NameCount, User } from "../services/types";
import { BarList, ChartCard, GrowthArea, Meter, SERIES, SplitBar, TrendLines } from "../components/charts";
import {
  Badge, Card, DefinitionList, ErrorState, Field, FormError, Notice, PageHeader, Section, Segmented, SkeletonPage,
  SkeletonTable, StatTile, priorityLabel,
} from "../components/ui";
import { dateTime, duration, relative, sentenceCase } from "../lib/format";

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
  sla: { compliance: number; met: number; breached: number; open_breached: number; by_priority: { name: string; met: number; breached: number; compliance: number }[] };
  satisfaction: { responses: number; rated: number; average_rating: number | null; distribution: NameCount[]; fix_confirmed_rate: number };
  approvals: { approved: number; rejected: number; pending: number };
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
  L0_policy: "Policy: sent straight to a team", L1_rules: "Rules only, no known fix", L2_similarity: "Duplicate or incident match",
  L3_verified_retrieval: "Known fix reused, no AI model", L4_small_llm: "Small AI model", L5_large_llm: "Large AI model",
};
const LEVEL_LABEL: Record<string, string> = {
  ai_generated: "AI suggestions", user_confirmed: "Confirmed by employees", human_verified: "Verified by IT", admin_verified: "Verified by admins",
};
const AUDIT_LABEL: Record<string, string> = {
  login: "Signed in", login_failed: "Failed sign-in", login_locked: "Locked after failed sign-ins", logout: "Signed out",
  register: "Registered", password_changed: "Changed password", password_change_failed: "Wrong current password",
  refresh_token_reuse: "Reused sign-in token (session ended)", role_changed: "Changed role", user_deactivated: "Deactivated account",
  user_reactivated: "Reactivated account", user_department_changed: "Changed department", action_approved: "Approved an action",
  action_rejected: "Declined an action", incident_resolved: "Resolved an incident", incident_updated: "Updated an incident",
  solution_verified: "Verified a fix", solution_rejected: "Declined a fix", solution_created: "Added a verified fix",
  category_created: "Added a category", kb_document_created: "Published an article", kb_document_updated: "Edited an article",
  vector_index_rebuilt: "Rebuilt the search index", demo_company_seeded: "Loaded demo data",
};

function SystemPanel() {
  const { data: s, reload, error } = useApi<System>("/admin/system");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  if (error) return <ErrorState message={error} what="system status" onRetry={reload} />;
  if (!s) return <Card title="System status"><SkeletonTable rows={3} /></Card>;
  const rebuild = async () => {
    setBusy(true);
    try {
      const r = await api.post<Record<string, { count: number }>>("/admin/index/rebuild");
      setReport(Object.entries(r).map(([k, v]) => `${sentenceCase(k)}: ${v.count}`).join(", "));
      reload();
    } finally { setBusy(false); }
  };
  const tier = (t: { provider: string; model: string }, avail: string | null) =>
    <span>{t.provider === "none" ? "Not configured" : `${t.provider} · ${t.model}`} <Badge tone={avail ? "ok" : "neutral"}>{avail ? "Reachable" : "Not reachable"}</Badge></span>;
  return (
    <Card title="System status" actions={<span className="text-xs text-meta">{s.environment} · {s.database === "postgresql" ? "PostgreSQL" : "SQLite"}</span>}>
      <div className="space-y-4">
        <DefinitionList items={[
          ["Small AI model", tier(s.llm.small, s.llm.available.small)],
          ["Large AI model", tier(s.llm.large, s.llm.available.large)],
          ["Search index", `${s.vector_store.embedder} (${s.vector_store.dim} dimensions)`],
          ["Indexed", Object.entries(s.vector_store.indexes).map(([k, v]) => `${v} ${k}`).join(", ")],
          ["Incident rule", `${s.incident_min_tickets} similar reports within ${s.incident_window_minutes} min`],
          ["Network checks", s.diagnostic_tools_enabled ? "On" : "Off"],
        ]} />
        {!s.llm.available.small && !s.llm.available.large && (
          <Notice tone="info">No AI model is reachable, so tickets are handled by rules, search and verified fixes only. Start Ollama or add an API key to enable model-written suggestions.</Notice>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn-secondary btn-sm" disabled={busy} onClick={rebuild}>{busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <RefreshCw className="size-4" aria-hidden />} Rebuild search index</button>
          {report && <span className="text-xs text-ok">Rebuilt from the database: {report}</span>}
        </div>
      </div>
    </Card>
  );
}

function Users() {
  const { user: me } = useAuth();
  const { data, reload, error, loading } = useApi<User[]>("/admin/users");
  const { data: departments } = useApi<{ id: number; name: string; is_support_team: boolean }[]>("/meta/departments");
  const [actionError, setActionError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const update = async (id: number, body: Record<string, unknown>) => {
    setActionError(null);
    try { await api.patch(`/admin/users/${id}`, body); reload(); } catch (e) { setActionError(e instanceof Error ? e.message : "Update failed"); }
  };
  const rows = (data || []).filter((u) => !q || `${u.full_name} ${u.username} ${u.email} ${u.department}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <Card title={`People (${data?.length ?? "-"})`} bodyClassName="" actions={
      <div><label htmlFor="user-filter" className="sr-only">Filter people</label>
        <input id="user-filter" className="input w-64 py-1" placeholder="Filter by name, username or department" value={q} onChange={(e) => setQ(e.target.value)} /></div>}>
      <ErrorState message={error} what="people" onRetry={reload} />
      {actionError && <div className="p-4"><FormError message={actionError} /></div>}
      {loading && !data ? <SkeletonTable rows={6} /> : (
        <div className="max-h-96 overflow-auto scroll-thin" tabIndex={0} role="region" aria-label="People">
          <table className="w-full text-sm">
            <thead className="sticky top-0 border-b border-line bg-canvas"><tr><th className="th">Person</th><th className="th">Role</th><th className="th">Department or team</th><th className="th">Last sign-in</th><th className="th">Active</th></tr></thead>
            <tbody className="divide-y divide-line">
              {rows.map((u) => (
                <tr key={u.id}>
                  <td className="td"><p className="font-medium text-ink">{u.full_name}</p><p className="mono text-xs text-meta">{u.username}</p></td>
                  <td className="td">
                    <select className="select w-36 py-1" aria-label={`Role for ${u.full_name}`} value={u.role} disabled={u.id === me?.id}
                      onChange={(e) => update(u.id, { role: e.target.value })}>
                      <option value="employee">Employee</option><option value="it_support">IT support</option><option value="admin">Administrator</option>
                    </select>
                  </td>
                  <td className="td">
                    <select className="select w-56 py-1" aria-label={`Department for ${u.full_name}`} value={u.department_id ?? ""}
                      onChange={(e) => update(u.id, { department_id: e.target.value ? Number(e.target.value) : null })}>
                      <option value="">None</option>{departments?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                    </select>
                  </td>
                  <td className="td whitespace-nowrap text-meta">{u.last_login_at ? relative(u.last_login_at) : "Never"}</td>
                  <td className="td">
                    <input type="checkbox" className="size-4 accent-[var(--color-brand)]" aria-label={`${u.full_name} can sign in`} checked={u.is_active}
                      disabled={u.id === me?.id} onChange={(e) => update(u.id, { is_active: e.target.checked })} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
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
    } catch (err) { setError(err instanceof Error ? err.message : "Could not add the category"); }
  };
  return (
    <Card title={`Ticket categories (${cats?.length ?? "-"})`}>
      <div className="space-y-4">
        <table className="w-full text-sm">
          <thead><tr><th className="th px-0">Category</th><th className="th px-0">Owning team</th></tr></thead>
          <tbody className="divide-y divide-line">{cats?.map((c) => <tr key={c.id}><td className="py-1 text-ink">{c.name}</td><td className="py-1 text-body">{c.department || "Service Desk"}</td></tr>)}</tbody>
        </table>
        <form onSubmit={submit} className="space-y-2 border-t border-line pt-4">
          <h3 className="text-sm font-semibold">Add a category</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            <Field label="Name" htmlFor="cat-name"><input id="cat-name" className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required minLength={2} /></Field>
            <Field label="Owning team" htmlFor="cat-team"><select id="cat-team" className="select" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
              <option value="">Service Desk</option>{departments?.filter((d) => d.is_support_team).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>
          </div>
          <Field label="Keywords" htmlFor="cat-keywords" hint="Comma-separated words that identify this category, for example: badge, door access, turnstile">
            <input id="cat-keywords" className="input" value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} />
          </Field>
          <FormError message={error} />
          <button className="btn-secondary">Add category</button>
        </form>
      </div>
    </Card>
  );
}

function AuditLog() {
  const { data, error, reload } = useApi<{ id: number; action: string; user: string | null; resource_type: string | null; resource_id: number | null; details: Record<string, unknown>; ip_address: string | null; created_at: string }[]>("/admin/audit-logs?limit=50");
  return (
    <Card title="Audit log" actions={<span className="text-xs text-meta">Latest 50 entries</span>} bodyClassName="">
      <ErrorState message={error} what="the audit log" onRetry={reload} />
      <div className="max-h-96 overflow-auto scroll-thin" tabIndex={0} role="region" aria-label="Audit log entries">
        <table className="w-full text-sm">
          <thead className="sticky top-0 border-b border-line bg-canvas"><tr><th className="th">When</th><th className="th">Who</th><th className="th">What</th><th className="th">Detail</th><th className="th">IP address</th></tr></thead>
          <tbody className="divide-y divide-line">
            {data?.map((a) => (
              <tr key={a.id}>
                <td className="td whitespace-nowrap text-meta">{dateTime(a.created_at)}</td>
                <td className="td whitespace-nowrap text-ink">{a.user || "Unknown user"}</td>
                <td className="td text-body">{AUDIT_LABEL[a.action] || sentenceCase(a.action)}</td>
                <td className="td text-meta">
                  {a.action === "role_changed" ? `${sentenceCase(String(a.details.from))} to ${sentenceCase(String(a.details.to))}`
                    : a.details?.reason ? sentenceCase(String(a.details.reason)) : a.resource_type ? `${sentenceCase(a.resource_type)} ${a.resource_id ?? ""}` : ""}
                </td>
                <td className="td mono text-xs text-meta">{a.ip_address || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function AdminPage() {
  const [days, setDays] = useState<"7" | "30" | "90">("90");
  const { data: a, error, loading, reload } = useApi<Analytics>(`/admin/analytics?days=${days}`, 60000);
  const o = a?.overview;
  const period = days === "90" ? "last 90 days" : `last ${days} days`;

  return (
    <div className="space-y-8">
      <PageHeader title="Analytics and administration" description="Every figure is counted from the ticket database when the page loads."
        actions={<Segmented label="Period" value={days} onChange={setDays} options={[["7", "7 days"], ["30", "30 days"], ["90", "90 days"]]} />} />

      <ErrorState message={error} what="analytics" onRetry={reload} />
      {loading && !a ? <SkeletonPage tiles={6} rows={0} /> : a && o && (
        <div className={`space-y-8 ${loading ? "opacity-60" : ""}`} aria-busy={loading}>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 2xl:grid-cols-6">
            <StatTile label="Tickets" value={o.tickets_in_window} hint={`${period} · ${o.total_tickets} all time`} />
            <StatTile label="Resolved by the agent" value={`${o.ai_resolution_percentage}%`} hint="Share of resolved tickets" />
            <StatTile label="Within SLA" value={`${a.sla.compliance}%`} hint={`${a.sla.breached} breached · ${a.sla.open_breached} open past target`} />
            <StatTile label="Satisfaction" value={a.satisfaction.average_rating ? `${a.satisfaction.average_rating} / 5` : "-"} hint={`${a.satisfaction.rated} ratings`} />
            <StatTile label="Average time to resolve" value={duration((o.avg_resolution_hours ?? 0) * 60)} hint={`Resolved in the ${period}`} />
            <StatTile label="Repeat reports absorbed" value={o.duplicates_prevented} hint={`${o.duplicate_tickets} duplicates · ${o.incident_linked_tickets} in incidents`} />
          </div>

          <ChartCard title="Tickets per day" description={`Created and resolved by the agent, ${period}`}
            legend={[{ label: "Created", color: SERIES[0] }, { label: "Resolved by the agent", color: SERIES[1] }]}
            table={{ columns: ["Date", "Created", "Resolved by the agent"], rows: a.tickets_per_day.map((d) => [d.date, d.tickets, d.ai_resolved]) }}>
            <TrendLines data={a.tickets_per_day} series={[{ key: "tickets", label: "Created" }, { key: "ai_resolved", label: "Resolved by the agent" }]} />
          </ChartCard>

          <div className="grid gap-4 lg:grid-cols-3">
            <ChartCard title="SLA by priority" description="Tickets resolved in the period against their target"
              table={{ columns: ["Priority", "Met", "Breached", "Within SLA"], rows: a.sla.by_priority.map((p) => [priorityLabel(p.name as "low"), p.met, p.breached, `${p.compliance}%`]) }}>
              <div className="space-y-4">
                {a.sla.by_priority.map((p) => <SplitBar key={p.name} label={priorityLabel(p.name as "low")} met={p.met} breached={p.breached} />)}
              </div>
            </ChartCard>
            <ChartCard title="Employee ratings" description={`${a.satisfaction.rated} ratings · fix confirmed in ${a.satisfaction.fix_confirmed_rate}% of replies`}
              table={{ columns: ["Rating", "Responses"], rows: a.satisfaction.distribution.map((d) => [`${d.name} of 5`, d.count]) }}>
              <BarList items={a.satisfaction.distribution.map((d) => ({ ...d, label: `${d.name} of 5` }))} total={a.satisfaction.rated} />
            </ChartCard>
            <ChartCard title="How tickets were handled" description="Deepest step the agent needed per ticket"
              table={{ columns: ["Step", "Tickets"], rows: a.routing_levels.map((r) => [ROUTING_LABEL[r.name] || r.name, r.count]) }}>
              <BarList items={a.routing_levels.map((r) => ({ ...r, label: ROUTING_LABEL[r.name] || r.name }))} total={a.routing_levels.reduce((s, r) => s + r.count, 0)} />
            </ChartCard>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <ChartCard title="Tickets by category" description={`Created in the ${period}`} table={{ columns: ["Category", "Tickets"], rows: a.category_distribution.map((c) => [c.name, c.count]) }}>
              <BarList items={a.category_distribution} total={o.tickets_in_window} />
            </ChartCard>
            <ChartCard title="Most common issues" table={{ columns: ["Issue", "Tickets"], rows: a.top_intents.map((c) => [c.label || c.name, c.count]) }}>
              <BarList items={a.top_intents} />
            </ChartCard>
            <Card title="Approvals and AI model use">
              <div className="space-y-4">
                <DefinitionList items={[
                  ["Actions approved", a.approvals.approved], ["Actions declined", a.approvals.rejected], ["Waiting now", a.approvals.pending],
                ]} />
                <div className="border-t border-line pt-4">
                  {a.llm_usage.calls ? (
                    <DefinitionList items={[
                      ["Model calls", `${a.llm_usage.calls} (${a.llm_usage.cache_hits} answered from cache)`],
                      ["Tokens", a.llm_usage.total_tokens.toLocaleString("en-IN")],
                      ["Estimated cost", `$${a.llm_usage.estimated_cost_usd.toFixed(4)}`],
                    ]} />
                  ) : <p className="text-sm text-body">No AI model calls in this period. Every ticket was handled by rules, search, verified fixes or people.</p>}
                  <p className="mt-2 text-xs text-meta">{a.savings.runs_without_llm} tickets needed no model call. At {a.savings.tokens_per_call} tokens per call ({a.savings.estimate_basis}) that avoided about {a.savings.estimated_tokens_saved.toLocaleString("en-IN")} tokens.</p>
                </div>
              </div>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
            <ChartCard title="Knowledge base size" description="Articles and fixes available to the agent" table={{ columns: ["Date", "Items"], rows: a.knowledge_growth.map((d) => [d.date, d.total]) }}>
              <GrowthArea data={a.knowledge_growth} dataKey="total" label="Knowledge items" />
            </ChartCard>
            <Card title="Fixes by trust level">
              <div className="space-y-4">
                {a.knowledge_by_level.map((l) => {
                  const total = a.knowledge_by_level.reduce((s, x) => s + x.count, 0) || 1;
                  return <Meter key={l.name} label={`${LEVEL_LABEL[l.name] || l.name} (${l.count})`} value={Math.round((l.count / total) * 100)} />;
                })}
                <p className="text-xs text-meta">Fixes verified by IT or admins are reused without an AI model. Employee-confirmed fixes need two successes first.</p>
              </div>
            </Card>
          </div>
        </div>
      )}

      <Section title="Administration">
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2"><SystemPanel /><Categories /></div>
          <Users />
          <AuditLog />
        </div>
      </Section>
    </div>
  );
}
