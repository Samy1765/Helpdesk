import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { Loader2, ShieldCheck } from "lucide-react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { Incident, Ticket } from "../services/types";
import {
  Badge, Empty, ErrorNote, PageHeader, Spinner, StatusBadge, TicketId, clock, dateTime, pct, sentenceCase, timeAgo,
} from "../components/ui";

interface IncidentDetail {
  incident: Incident;
  affected_users: number;
  affected_departments: string[];
  tickets: Ticket[];
  timeline: { at: string; type: string; description: string; ticket_id: number }[];
  can_manage: boolean;
}

/** Merge entries that say the same thing in the same minute (e.g. one fix closing twelve tickets). */
function groupTimeline(events: IncidentDetail["timeline"]) {
  const groups: { at: string; text: string; tickets: number[] }[] = [];
  for (const e of events) {
    const text = e.description || sentenceCase(e.type);
    const last = groups[groups.length - 1];
    if (last && last.text === text && clock(last.at) === clock(e.at)) last.tickets.push(e.ticket_id);
    else groups.push({ at: e.at, text, tickets: [e.ticket_id] });
  }
  return groups;
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-meta">{label}</dt>
      <dd className="text-sm text-ink mt-0.5">{children}</dd>
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
  const numbers = new Map(tickets.map((t) => [t.id, t.ticket_number]));

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true); setErr(null);
    try { await fn(); setMsg(ok); reload(); onChanged(); } catch (e) { setErr(e instanceof Error ? e.message : "Failed"); } finally { setBusy(false); }
  };
  const resolve = (e: FormEvent) => {
    e.preventDefault();
    act(() => api.post(`/incidents/${i.id}/resolve`, { resolution, root_cause: rootCause || undefined }),
      "Incident resolved. The linked tickets are closed and the fix is saved to the knowledge base.");
  };

  return (
    <div className="space-y-4 min-w-0">
      <section className="card p-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="mono text-sm text-meta">{i.incident_number}</span>
          <StatusBadge status={i.status} />
          {i.priority && <Badge tone={i.priority === "critical" ? "solidCrit" : i.priority === "high" ? "crit" : "warn"}>{sentenceCase(i.priority)} priority</Badge>}
        </div>
        <h2 className="mt-2 text-xl font-semibold leading-snug">{i.title}</h2>
        <p className="mt-1 text-sm text-body">
          {data.affected_users} {data.affected_users === 1 ? "person has" : "people have"} reported this
          {data.affected_departments.length ? ` from ${data.affected_departments.join(", ")}` : ""}.
          {i.department && (active ? ` ${i.department} is working on it.` : ` Fixed by ${i.department}.`)}
        </p>
        <dl className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-4 border-t border-muted pt-4">
          <Fact label="First report">{dateTime(i.first_reported)}</Fact>
          <Fact label="Latest report">{timeAgo(i.last_reported)}</Fact>
          <Fact label="Service">{i.category || "Unknown"}</Fact>
          <Fact label="Grouped because">{i.detection_similarity ? `${pct(i.detection_similarity)} similar wording` : "Same symptoms"}</Fact>
        </dl>
        {(i.root_cause || i.resolution) ? (
          <div className="mt-4 rounded border border-ok-line bg-ok-soft p-3 text-sm text-ok-ink space-y-1">
            {i.root_cause && <p><span className="font-medium">Cause:</span> {i.root_cause}</p>}
            {i.resolution && <p><span className="font-medium">Fix:</span> {i.resolution}</p>}
          </div>
        ) : active && (
          <p className="mt-4 text-sm text-meta">Cause not confirmed yet. Updates appear here and on each linked ticket.</p>
        )}
      </section>

      {data.timeline.length > 0 && (
        <section className="card">
          <div className="card-header"><h3 className="text-sm font-semibold">Timeline</h3></div>
          <ol className="px-4 py-3 space-y-2.5">
            {groupTimeline(data.timeline).slice(0, 15).map((g, idx) => (
              <li key={idx} className="grid grid-cols-[3.5rem_7rem_1fr] gap-3 text-sm">
                <span className="text-meta tabular-nums">{clock(g.at)}</span>
                <span className="mono text-xs text-cobalt pt-0.5">
                  {g.tickets.length === 1 ? numbers.get(g.tickets[0]) : `${g.tickets.length} tickets`}
                </span>
                <span className="text-body">{g.text}</span>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="card">
        <div className="card-header"><h3 className="text-sm font-semibold">{data.can_manage ? "Linked tickets" : "Your linked tickets"}</h3><span className="text-xs text-meta">{tickets.length}</span></div>
        {tickets.length ? (
          <ul className="divide-y divide-muted">
            {tickets.map((t) => (
              <li key={t.id} className="px-4 py-2.5 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2"><TicketId number={t.ticket_number} to={`/tickets/${t.id}`} /><span className="text-sm truncate">{t.creator?.name}</span></div>
                  <p className="text-xs text-meta truncate">{t.creator?.department ? `${t.creator.department} · ` : ""}{t.title}</p>
                </div>
                <span className="text-xs text-meta shrink-0">{timeAgo(t.created_at)}</span>
              </li>
            ))}
          </ul>
        ) : <p className="px-4 py-4 text-sm text-meta">None of your tickets are linked to this incident.</p>}
      </section>

      {msg && <div className="rounded border border-ok-line bg-ok-soft px-3 py-2 text-sm text-ok-ink">{msg}</div>}
      <ErrorNote message={err} />
      {data.can_manage && active && (
        <section className="card p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold">Resolve this incident</h3>
            <button className="btn-outline btn-sm" disabled={busy || i.status === "investigating"}
              onClick={() => act(() => api.patch(`/incidents/${i.id}`, { status: "investigating" }), "Marked as investigating")}>Mark as investigating</button>
          </div>
          <form onSubmit={resolve} className="space-y-2">
            <textarea className="input min-h-20" placeholder="What fixed it? Everyone with a linked ticket is told, and the fix is saved for next time." value={resolution} onChange={(e) => setResolution(e.target.value)} required minLength={5} />
            <input className="input" placeholder="Cause (optional)" value={rootCause} onChange={(e) => setRootCause(e.target.value)} />
            <button className="btn-primary" disabled={busy}>{busy && <Loader2 className="size-4 animate-spin" />} Resolve and notify {tickets.length} {tickets.length === 1 ? "person" : "people"}</button>
          </form>
        </section>
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
      <PageHeader title="Incidents"
        subtitle="When several people report the same problem, their tickets are grouped into one incident so the right team fixes it once." />
      <div className="flex gap-1 mb-4">
        {(["active", "resolved", "all"] as const).map((s) => (
          <button key={s} onClick={() => setState(s)} className={`rounded px-3 py-1.5 text-sm ${state === s ? "bg-cobalt-soft text-cobalt font-medium" : "text-body hover:bg-muted"}`}>
            {s === "active" ? "Ongoing" : s === "resolved" ? "Resolved" : "All"}
          </button>
        ))}
      </div>
      <ErrorNote message={error} />
      {loading && !data ? <Spinner /> : !data?.length ? (
        <Empty title={state === "active" ? "No ongoing incidents" : "No incidents"} icon={<ShieldCheck className="size-5" />}>
          Everything is running normally.
        </Empty>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[18rem_1fr] items-start">
          <ul className="card divide-y divide-muted overflow-hidden">
            {data.map((i) => (
              <li key={i.id}>
                <button onClick={() => setParams({ id: String(i.id) })}
                  className={`w-full text-left px-4 py-3 hover:bg-canvas ${i.id === selectedId ? "bg-cobalt-soft" : ""}`}>
                  <div className="flex justify-between gap-2"><span className="mono text-xs text-meta">{i.incident_number}</span><StatusBadge status={i.status} /></div>
                  <p className="text-sm font-medium mt-1 line-clamp-2">{i.title}</p>
                  <p className="text-xs text-meta mt-1">{i.ticket_count} {i.ticket_count === 1 ? "report" : "reports"} · {timeAgo(i.last_reported)}</p>
                </button>
              </li>
            ))}
          </ul>
          {selectedId && <Detail key={selectedId} id={selectedId} onChanged={reload} />}
        </div>
      )}
    </div>
  );
}
