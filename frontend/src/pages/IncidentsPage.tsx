import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowDown, CheckCircle2, Clock, Files, Loader2, Radar, Share2, ShieldCheck, TriangleAlert, Users, Zap,
} from "lucide-react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { Incident, Ticket } from "../services/types";
import {
  Badge, Empty, ErrorNote, PageHeader, ProgressBar, SectionTitle, Spinner, StatusBadge, TicketId, clock, pct, timeAgo,
} from "../components/ui";

interface IncidentDetail {
  incident: Incident;
  affected_users: number;
  affected_departments: string[];
  tickets: Ticket[];
  timeline: { at: string; type: string; description: string; ticket_id: number }[];
  can_manage: boolean;
}

function TopologyNode({ icon, title, sub, right, tone }: { icon: React.ReactNode; title: string; sub: string; right?: React.ReactNode; tone?: "cobalt" | "crit" }) {
  return (
    <div className={`flex items-center gap-3 rounded border px-3 py-2.5 ${tone === "cobalt" ? "border-cobalt-line bg-cobalt-soft" : tone === "crit" ? "border-crit-line bg-crit-soft" : "border-line bg-surface"}`}>
      <span className={`flex size-8 shrink-0 items-center justify-center rounded-md border ${tone === "crit" ? "border-crit-line bg-surface text-crit" : "border-cobalt-line bg-surface text-cobalt"}`}>{icon}</span>
      <div className="min-w-0 flex-1">
        <p className={`text-sm font-semibold ${tone === "cobalt" ? "text-cobalt" : "text-ink"}`}>{title}</p>
        <p className="mono text-xs text-meta truncate">{sub}</p>
      </div>
      {right}
    </div>
  );
}

function Detail({ id, onChanged }: { id: number; onChanged: () => void }) {
  const { data, error, loading, reload } = useApi<IncidentDetail>(`/incidents/${id}`, 20000);
  const [resolution, setResolution] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (loading && !data) return <Spinner />;
  if (!data) return <ErrorNote message={error} />;
  const { incident: i, tickets } = data;
  const active = i.status !== "resolved";
  const first = tickets[0];
  const last = tickets[tickets.length - 1];

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true); setErr(null);
    try { await fn(); setMsg(ok); reload(); onChanged(); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(false); }
  };
  const resolve = (e: FormEvent) => {
    e.preventDefault();
    act(() => api.post(`/incidents/${i.id}/resolve`, { resolution, root_cause: rootCause || undefined }),
      "Incident resolved - linked tickets closed and the fix saved as verified knowledge.");
  };

  return (
    <div className="space-y-4">
      <div className={`rounded-lg border p-4 ${active ? "border-crit-line bg-crit-soft" : "border-ok-line bg-ok-soft"}`}>
        <div className="flex items-center justify-between gap-2">
          <span className={`flex items-center gap-2 label-caps ${active ? "!text-crit-ink" : "!text-ok-ink"}`}>
            <span className={`dot ${active ? "bg-crit animate-pulse-dot" : "bg-ok"}`} />
            {active ? `${(i.priority || "high").toUpperCase()} incident detected` : "Incident resolved"}
          </span>
          <span className="code-chip !bg-surface">{i.incident_number}</span>
        </div>
        <h2 className="mt-2 text-[1.25rem] font-semibold leading-snug">{i.title}</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <StatusBadge status={i.status} />
          {i.priority && <Badge tone={i.priority === "critical" ? "solidCrit" : "crit"}>{i.priority.toUpperCase()}</Badge>}
          <span className="ml-auto flex items-center gap-1 mono text-xs text-meta"><Clock className="size-3.5" />{timeAgo(i.first_reported)}</span>
        </div>
        <div className="mt-3 flex items-center justify-between gap-2 rounded border border-line bg-surface px-3 py-2 text-sm">
          <span className="flex items-center gap-2"><Users className="size-4 text-meta" /><b>{data.affected_users} employees affected</b> · {data.affected_departments.length || 1} department(s)</span>
          <span className="mono text-xs text-meta">Clustered semantic</span>
        </div>
      </div>

      <section className="card">
        <div className="card-header">
          <span className="label-caps !text-ink flex items-center gap-2"><Share2 className="size-4 text-cobalt" /> Correlation topology</span>
          {i.detection_similarity && <Badge tone="cobalt" mono>{pct(i.detection_similarity, 1)} similarity</Badge>}
        </div>
        <div className="p-4 space-y-1">
          <TopologyNode icon={<Files className="size-4" />} title={`${tickets.length || "?"} ingested tickets`}
            sub={tickets.map((t) => t.ticket_number).join(", ") || "restricted"}
            right={first && <span className="code-chip">{clock(first.created_at).slice(0, 5)}-{clock(last.created_at).slice(0, 5)}</span>} />
          <ArrowDown className="mx-auto size-4 text-faint" />
          <TopologyNode tone="cobalt" icon={<Radar className="size-4" />} title="Semantic match"
            sub={`Vector embedding match · ${i.category || "cross-category"} reports within the correlation window`}
            right={i.detection_similarity ? <span className="mono text-xs text-cobalt">{pct(i.detection_similarity, 1)}</span> : undefined} />
          <ArrowDown className="mx-auto size-4 text-faint" />
          <TopologyNode icon={<TriangleAlert className="size-4" />} tone="crit" title={`${i.incident_number} created`}
            sub="Correlation cluster established" right={<Badge tone="crit">AUTOMATED</Badge>} />
          <ArrowDown className="mx-auto size-4 text-faint" />
          <TopologyNode icon={<ShieldCheck className="size-4" />} title={i.department || "IT operations"}
            sub={active ? "Owning team notified" : `Resolved ${timeAgo(i.resolved_at)}`}
            right={<CheckCircle2 className={`size-4 ${active ? "text-meta" : "text-ok"}`} />} />
        </div>
      </section>

      <section className="card">
        <div className="card-header">
          <span className="label-caps !text-ink flex items-center gap-2"><Zap className="size-4 text-cobalt" /> Root-cause telemetry</span>
        </div>
        <div className="p-4 space-y-2.5">
          <div className="rounded border border-line bg-canvas p-3">
            <p className="label-caps">Affected service</p>
            <p className="mono text-sm font-medium mt-0.5">{i.category || "Unknown"}{i.department ? ` / ${i.department}` : ""}</p>
          </div>
          <div className="rounded border border-line bg-canvas p-3">
            <p className="label-caps">{i.root_cause ? "Confirmed root cause" : "Root cause hypothesis"}</p>
            <p className="text-sm mt-0.5 flex gap-1.5"><Zap className="size-4 text-warn shrink-0" />{i.root_cause || "Not confirmed yet - shared symptoms point to a common service fault."}</p>
          </div>
          {i.detection_similarity && (
            <div className="rounded border border-line p-3">
              <div className="flex justify-between text-sm mb-1.5"><span>AI corroboration metric</span><span className="mono font-semibold text-cobalt">{pct(i.detection_similarity)}</span></div>
              <ProgressBar value={i.detection_similarity * 100} />
            </div>
          )}
          {i.resolution && <div className="rounded border border-ok-line bg-ok-soft p-3 text-sm text-ok-ink"><b>Resolution:</b> {i.resolution}</div>}
        </div>
      </section>

      {data.timeline.length > 0 && (
        <section className="card">
          <div className="card-header"><span className="label-caps !text-ink">Detection timeline</span><span className="mono text-[0.6875rem] text-meta">{Intl.DateTimeFormat().resolvedOptions().timeZone}</span></div>
          <ol className="p-4 space-y-3 border-l border-line ml-6">
            {data.timeline.slice(0, 10).map((e, idx) => (
              <li key={idx} className="relative pl-4">
                <span className={`absolute -left-[1.4rem] top-1 dot size-3 border-2 border-white ${idx === 0 ? "bg-cobalt" : "bg-faint"}`} />
                <div className="rounded border border-line p-2.5">
                  <p className="mono text-xs text-cobalt">{clock(e.at)}</p>
                  <p className="text-sm font-medium">{e.type.replace(/_/g, " ")}</p>
                  <p className="text-xs text-meta">{e.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="card">
        <div className="card-header"><span className="label-caps !text-ink">{data.can_manage ? `Merged tickets (${tickets.length} total)` : "Your linked tickets"}</span></div>
        {tickets.length ? (
          <ul className="divide-y divide-muted">
            {tickets.map((t) => (
              <li key={t.id} className="px-4 py-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2"><TicketId number={t.ticket_number} to={`/tickets/${t.id}`} /><span className="text-sm font-medium truncate">{t.creator?.name}</span></div>
                  <p className="mono text-xs text-meta truncate">{t.creator?.department || "-"} · {t.title}</p>
                </div>
                <span className="mono text-xs text-meta shrink-0">{timeAgo(t.created_at)}</span>
              </li>
            ))}
          </ul>
        ) : <p className="px-4 py-4 text-sm text-meta">None of your tickets are linked to this incident.</p>}
      </section>

      {msg && <div className="rounded border border-ok-line bg-ok-soft px-3 py-2 text-sm text-ok-ink">{msg}</div>}
      <ErrorNote message={err} />
      {data.can_manage && active && (
        <div className="card p-4 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <button className="btn-outline" disabled={busy || i.status === "investigating"}
              onClick={() => act(() => api.patch(`/incidents/${i.id}`, { status: "investigating" }), "Marked as investigating")}>Mark investigating</button>
            <a className="btn-accent" href="#resolve-incident">Resolve incident</a>
          </div>
          <form id="resolve-incident" onSubmit={resolve} className="space-y-2 border-t border-muted pt-3">
            <p className="label-caps !text-ink">Broadcast resolution to all linked employees</p>
            <textarea className="input min-h-20" placeholder="What fixed it? This closes every linked ticket and becomes verified knowledge." value={resolution} onChange={(e) => setResolution(e.target.value)} required minLength={5} />
            <input className="input" placeholder="Confirmed root cause" value={rootCause} onChange={(e) => setRootCause(e.target.value)} />
            <button className="btn-primary w-full" disabled={busy}>{busy ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />} Resolve & notify</button>
          </form>
        </div>
      )}
    </div>
  );
}

export default function IncidentsPage() {
  const [params, setParams] = useSearchParams();
  const [state, setState] = useState<"active" | "resolved" | "all">("active");
  const { data, error, loading, reload } = useApi<Incident[]>(`/incidents?state=${state}`, 20000);
  const byNumber = params.get("number");
  const selectedId = Number(params.get("id")) || data?.find((i) => i.incident_number === byNumber)?.id || data?.[0]?.id;

  useEffect(() => { if (byNumber && data && !data.find((i) => i.incident_number === byNumber) && state !== "all") setState("all"); }, [byNumber, data, state]);

  return (
    <div>
      <PageHeader
        eyebrow={<span className="flex items-center gap-2 label-caps !text-cobalt"><span className="dot bg-cobalt animate-pulse-dot" /> Live correlation feed</span>}
        title="Incident correlation center" subtitle="Real-time automated issue clustering & root-cause detection" />
      <div className="flex gap-1 mb-4">
        {(["active", "resolved", "all"] as const).map((s) => (
          <button key={s} onClick={() => setState(s)} className={`rounded px-3 py-1.5 text-sm font-medium ${state === s ? "bg-ink text-white" : "text-body hover:bg-muted"}`}>
            {s[0].toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>
      <ErrorNote message={error} />
      {loading && !data ? <Spinner /> : !data?.length ? (
        <Empty title={state === "active" ? "No active incidents" : "No incidents"} icon={<ShieldCheck className="size-5" />}>
          When several employees report the same problem, it appears here automatically.
        </Empty>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
          <div>
            <SectionTitle>Incidents</SectionTitle>
            <div className="space-y-2">
              {data.map((i) => (
                <button key={i.id} onClick={() => setParams({ id: String(i.id) })}
                  className={`card card-hover w-full text-left p-3 ${i.id === selectedId ? "!border-cobalt ring-1 ring-cobalt" : ""}`}>
                  <div className="flex justify-between gap-2"><span className="mono text-xs font-semibold text-cobalt">{i.incident_number}</span><StatusBadge status={i.status} /></div>
                  <p className="text-sm font-medium mt-1 line-clamp-2">{i.title}</p>
                  <p className="mono text-[0.6875rem] text-meta mt-1">{i.ticket_count} tickets · {timeAgo(i.last_reported)}</p>
                </button>
              ))}
            </div>
          </div>
          {selectedId && <Detail key={selectedId} id={selectedId} onChanged={reload} />}
        </div>
      )}
      <p className="mt-6 text-xs text-meta">Tickets from different employees that are semantically similar within the correlation window are grouped automatically, so the incident is fixed once. <Link to="/knowledge-base" className="text-cobalt">Learn about self-service →</Link></p>
    </div>
  );
}
