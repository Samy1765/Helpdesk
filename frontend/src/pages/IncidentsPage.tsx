import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { Incident, Ticket } from "../services/types";
import {
  Card, DefinitionList, EmptyState, ErrorState, Field, FormError, Notice, PageHeader, PriorityBadge, Segmented,
  SkeletonLines, SkeletonTable, Spinner, StatusBadge, TicketId,
} from "../components/ui";
import { dateTime, duration, sentenceCase } from "../lib/format";

interface IncidentDetail {
  incident: Incident;
  affected_users: number;
  affected_departments: string[];
  tickets: Ticket[];
  timeline: { at: string; type: string; description: string; ticket_id: number }[];
  can_manage: boolean;
}

type State = "active" | "resolved" | "all";

function Detail({ id, onChanged }: { id: number; onChanged: () => void }) {
  const { data, error, loading, reload } = useApi<IncidentDetail>(`/incidents/${id}`, 30000);
  const [resolution, setResolution] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (loading && !data) return <div className="card p-4"><SkeletonLines lines={6} /></div>;
  if (!data) return <ErrorState message={error} what="this incident" onRetry={reload} />;
  const { incident: i, tickets } = data;
  const active = i.status !== "resolved";
  const lasted = i.resolved_at ? (new Date(i.resolved_at).getTime() - new Date(i.first_reported).getTime()) / 60000 : null;

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true); setErr(null);
    try { await fn(); setMsg(ok); reload(); onChanged(); } catch (e) { setErr(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(false); }
  };
  const resolve = (e: FormEvent) => {
    e.preventDefault();
    act(() => api.post(`/incidents/${i.id}/resolve`, { resolution, root_cause: rootCause || undefined }),
      "Incident resolved. Linked tickets are closed and everyone affected has been told.");
  };

  return (
    <div className="space-y-4">
      <div className="card p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="mono text-sm font-medium text-ink">{i.incident_number}</span>
          <StatusBadge status={i.status} /><PriorityBadge priority={i.priority} />
        </div>
        <h2 className="mt-2 text-lg">{i.title}</h2>
        <p className="mt-1 text-sm text-meta">
          Started {dateTime(i.first_reported)}{i.resolved_at ? ` · resolved ${dateTime(i.resolved_at)} (${duration(lasted)})` : ` · last report ${dateTime(i.last_reported)}`}
        </p>
      </div>

      {msg && <Notice tone="ok">{msg}</Notice>}
      <FormError message={err} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Impact">
          <DefinitionList items={[
            ["People affected", data.affected_users],
            ["Departments", data.affected_departments.join(", ") || "-"],
            ["Owning team", i.department || "Service Desk"],
            ["Category", i.category || "-"],
          ]} />
        </Card>
        <Card title={i.root_cause ? "Root cause" : "Cause"}>
          <p className="text-sm text-body">{i.root_cause || "Not confirmed yet. The reports share the same symptoms, which points to one service fault."}</p>
          {i.resolution && <><h3 className="mt-4 text-sm font-semibold">Fix</h3><p className="mt-1 text-sm text-body">{i.resolution}</p></>}
        </Card>
      </div>

      <Card title={data.can_manage ? `Linked tickets (${tickets.length})` : "Your linked tickets"} bodyClassName="">
        {tickets.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-line bg-canvas"><tr><th className="th">Ticket</th><th className="th">Reported by</th><th className="th">Department</th><th className="th">Reported</th><th className="th">Status</th></tr></thead>
              <tbody className="divide-y divide-line">
                {tickets.map((t) => (
                  <tr key={t.id} className="hover:bg-canvas">
                    <td className="td"><TicketId number={t.ticket_number} to={`/tickets/${t.id}`} /></td>
                    <td className="td text-body">{t.creator?.name}</td>
                    <td className="td text-body">{t.creator?.department || "-"}</td>
                    <td className="td whitespace-nowrap text-meta">{dateTime(t.created_at)}</td>
                    <td className="td"><StatusBadge status={t.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="px-4 py-4 text-sm text-meta">None of your tickets are part of this incident.</p>}
      </Card>

      {data.timeline.length > 0 && (
        <Card title="Timeline">
          <ol className="space-y-2">
            {data.timeline.slice(0, 12).map((e, idx) => (
              <li key={idx} className="grid grid-cols-[9rem_1fr] gap-4 text-sm">
                <span className="text-meta">{dateTime(e.at)}</span>
                <span className="text-body">{e.description || sentenceCase(e.type)}</span>
              </li>
            ))}
          </ol>
        </Card>
      )}

      {data.can_manage && active && (
        <Card title="Manage">
          <div className="space-y-4">
            {i.status !== "investigating" && (
              <button className="btn-secondary" disabled={busy}
                onClick={() => act(() => api.patch(`/incidents/${i.id}`, { status: "investigating" }), "Marked as investigating.")}>Mark as investigating</button>
            )}
            <form onSubmit={resolve} className="space-y-2 border-t border-line pt-4">
              <h3 className="text-sm font-semibold">Resolve and notify everyone affected</h3>
              <Field label="What fixed it" htmlFor="inc-resolution" hint="Sent to every linked employee and saved as verified knowledge.">
                <textarea id="inc-resolution" className="input min-h-20" value={resolution} onChange={(e) => setResolution(e.target.value)} required minLength={5} />
              </Field>
              <Field label="Confirmed root cause" htmlFor="inc-cause">
                <input id="inc-cause" className="input" value={rootCause} onChange={(e) => setRootCause(e.target.value)} />
              </Field>
              <button className="btn-primary" disabled={busy}>{busy && <Spinner />} Resolve incident</button>
            </form>
          </div>
        </Card>
      )}
    </div>
  );
}

export default function IncidentsPage() {
  const [params, setParams] = useSearchParams();
  const state = (params.get("state") || "active") as State;
  const { data, error, loading, reload } = useApi<Incident[]>(`/incidents?state=${state}`, 30000);
  const byNumber = params.get("number");
  const selectedId = Number(params.get("id")) || data?.find((i) => i.incident_number === byNumber)?.id || data?.[0]?.id;

  useEffect(() => {
    if (byNumber && data && !data.find((i) => i.incident_number === byNumber) && state !== "all") setParams({ state: "all", number: byNumber });
  }, [byNumber, data, state, setParams]);

  return (
    <div>
      <PageHeader title="Incidents"
        description="When several people report the same problem within an hour, their tickets are grouped into one incident so IT fixes it once."
        actions={<Segmented label="Incidents to show" value={state} onChange={(v) => setParams({ state: v })}
          options={[["active", "Active"], ["resolved", "Resolved"], ["all", "All"]]} />} />
      <ErrorState message={error} what="incidents" onRetry={reload} />
      {loading && !data ? <SkeletonTable rows={4} /> : !data?.length ? (
        <EmptyState title={state === "active" ? "No active incidents" : "No incidents"} icon={<ShieldCheck className="size-5" aria-hidden />}
          action={state === "active" ? <button className="btn-secondary" onClick={() => setParams({ state: "resolved" })}>Show resolved incidents</button> : undefined}>
          {state === "active" ? "All services are running normally." : "Incidents appear here once several people report the same problem."}
        </EmptyState>
      ) : (
        <div className="grid gap-8 lg:grid-cols-[20rem_1fr]">
          <nav aria-label="Incident list">
            <ul className="space-y-2">
              {data.map((i) => (
                <li key={i.id}>
                  <Link to={`?state=${state}&id=${i.id}`} aria-current={i.id === selectedId ? "true" : undefined}
                    className={`card block p-4 hover:border-line-strong ${i.id === selectedId ? "border-brand" : ""}`}>
                    <span className="flex items-center justify-between gap-2"><span className="mono text-xs font-medium text-meta">{i.incident_number}</span><StatusBadge status={i.status} /></span>
                    <span className="mt-1 block text-sm font-medium text-ink">{i.title}</span>
                    <span className="mt-1 block text-xs text-meta">{i.ticket_count} ticket{i.ticket_count === 1 ? "" : "s"} · {dateTime(i.first_reported)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          {selectedId && <Detail key={selectedId} id={selectedId} onChanged={reload} />}
        </div>
      )}
    </div>
  );
}
