import { useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Check, FileText, Paperclip, Star, X } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { api, downloadAttachment } from "../services/api";
import type { ActionView, Incident, Message, SolutionCandidate, Ticket, User } from "../services/types";
import { ApprovalCard, SolutionCard } from "../components/agent";
import {
  Card, DefinitionList, ErrorState, Field, FormError, Notice, PriorityBadge, ProgressBar, RichText, SkeletonPage,
  Spinner, StatusBadge, TicketId, priorityLabel, statusLabel,
} from "../components/ui";
import { ownerLine } from "../components/tickets";
import { dateTime, percent, relative, sentenceCase, slaText } from "../lib/format";

interface Detail {
  ticket: Ticket;
  messages: Message[];
  steps: { id: number; key: string; title: string; detail: string | null; status: string; performed_by: string; created_at: string }[];
  events: { id: number; type: string; description: string | null; actor: string; created_at: string }[];
  agent: null | {
    state: string; attempt: number; routing_level: string | null; llm_calls: number; tokens_used: number;
    confidence: number | null; retrieval_hits: number; awaiting_feedback: boolean; reasoning_summary: string | null;
    resolution_status: string | null;
  };
  solution: SolutionCandidate | null;
  actions: ActionView[];
  escalation: { department: string; reason: string; package: Record<string, unknown> | null; created_at: string } | null;
  incident: Incident | null;
  duplicate_of: { id: number; ticket_number: string; title: string } | null;
  similar: { id: number; ticket_number: string; title: string; status: string; similarity: number }[];
  attachments: { token: string; filename: string; content_type: string; size: number }[];
  rating: number | null;
  can_manage: boolean;
}

const AUTHOR: Record<string, string> = { assistant: "Help desk agent", system: "Update" };

function Rating({ ticketId, current, onSaved }: { ticketId: number; current: number | null; onSaved: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rate = async (score: number) => {
    setBusy(true); setError(null);
    try { await api.post(`/tickets/${ticketId}/rating`, { rating: score }); onSaved(); }
    catch (e) { setError(e instanceof Error ? e.message : "Rating failed"); } finally { setBusy(false); }
  };
  return (
    <Card title="How was this handled?">
      <div role="radiogroup" aria-label="Rate the resolution from 1 to 5" className="flex gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} role="radio" aria-checked={current === n} aria-label={`${n} out of 5`} disabled={busy}
            onClick={() => rate(n)} className="btn-ghost btn-icon">
            <Star className={`size-5 ${current && n <= current ? "fill-current text-warn-dot" : "text-faint"}`} aria-hidden />
          </button>
        ))}
      </div>
      <p className="mt-2 text-xs text-meta">{current ? `You rated this ${current} out of 5. Click to change.` : "Your rating helps the IT team improve the fixes it publishes."}</p>
      <FormError message={error} />
    </Card>
  );
}

function StaffPanel({ d, reload }: { d: Detail; reload: () => void }) {
  const t = d.ticket;
  const { data: agents } = useApi<User[]>("/support/agents");
  const { data: categories } = useApi<{ id: number; name: string }[]>("/meta/categories");
  const [resolution, setResolution] = useState("");
  const [rootCause, setRootCause] = useState("");
  const [saveKnowledge, setSaveKnowledge] = useState(true);
  const [aiWrong, setAiWrong] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await fn(); reload(); } catch (e) { setError(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(false); }
  };

  return (
    <Card title="IT support">
      <div className="space-y-4">
        <FormError message={error} />
        {t.is_open && (
          <div className="space-y-2">
            {!t.assignee && <button className="btn-primary w-full" disabled={busy} onClick={() => run(() => api.post(`/support/tickets/${t.id}/accept`))}>Assign to me and start</button>}
            <Field label="Reassign to" htmlFor="assignee">
              <select id="assignee" className="select" disabled={busy} value="" onChange={(e) => e.target.value && run(() => api.post(`/support/tickets/${t.id}/assign`, { user_id: Number(e.target.value), reason: "Reassigned by IT support" }))}>
                <option value="">Choose an engineer</option>
                {agents?.map((a) => <option key={a.id} value={a.id}>{a.full_name} · {a.department}</option>)}
              </select>
            </Field>
          </div>
        )}
        <Field label="Category" htmlFor="fix-category">
          <select id="fix-category" className="select" value={t.category_id ?? ""} disabled={busy}
            onChange={(e) => run(() => api.patch(`/support/tickets/${t.id}/classification`, { category_id: Number(e.target.value), reason: "Corrected by IT" }))}>
            {categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Field label="Priority" htmlFor="fix-priority">
          <select id="fix-priority" className="select" value={t.priority} disabled={busy}
            onChange={(e) => run(() => api.patch(`/support/tickets/${t.id}/classification`, { priority: e.target.value, reason: "Corrected by IT" }))}>
            {(["critical", "high", "medium", "low"] as const).map((p) => <option key={p} value={p}>{priorityLabel(p)}</option>)}
          </select>
        </Field>
        {t.is_open && (
          <form className="space-y-2 border-t border-line pt-4"
            onSubmit={(e: FormEvent) => { e.preventDefault(); run(() => api.post(`/support/tickets/${t.id}/resolve`, {
              resolution, root_cause: rootCause || undefined, save_as_knowledge: saveKnowledge, ai_solution_was_wrong: aiWrong })); }}>
            <h3 className="text-sm font-semibold">Resolve</h3>
            <Field label="What fixed it" htmlFor="resolution" hint="Numbered steps become reusable knowledge.">
              <textarea id="resolution" className="input min-h-24" value={resolution} onChange={(e) => setResolution(e.target.value)} required minLength={5} />
            </Field>
            <Field label="Root cause (optional)" htmlFor="root-cause">
              <input id="root-cause" className="input" value={rootCause} onChange={(e) => setRootCause(e.target.value)} />
            </Field>
            <label className="flex items-center gap-2 text-sm text-body"><input type="checkbox" className="size-4 accent-[var(--color-brand)]" checked={saveKnowledge} onChange={(e) => setSaveKnowledge(e.target.checked)} /> Save as verified knowledge</label>
            {d.solution && <label className="flex items-center gap-2 text-sm text-body"><input type="checkbox" className="size-4 accent-[var(--color-brand)]" checked={aiWrong} onChange={(e) => setAiWrong(e.target.checked)} /> The suggested fix was wrong; remove it from search</label>}
            <button className="btn-primary w-full" disabled={busy}>{busy && <Spinner />} Resolve ticket</button>
          </form>
        )}
        {d.agent?.reasoning_summary && (
          <details className="border-t border-line pt-4">
            <summary className="cursor-pointer text-sm font-medium text-ink">Agent decisions</summary>
            <ul className="mt-2 space-y-1 text-sm text-body">{d.agent.reasoning_summary.split(" | ").map((r, i) => <li key={i}>{r}</li>)}</ul>
            <p className="mt-2 text-xs text-meta">{d.agent.llm_calls} AI model call{d.agent.llm_calls === 1 ? "" : "s"} · {d.agent.retrieval_hits} knowledge matches</p>
          </details>
        )}
        {d.escalation?.package && (
          <details className="border-t border-line pt-4">
            <summary className="cursor-pointer text-sm font-medium text-ink">Hand-off package</summary>
            <pre className="mt-2 max-h-80 overflow-auto rounded-sm border border-line bg-canvas p-2 font-mono text-xs scroll-thin">{JSON.stringify(d.escalation.package, null, 2)}</pre>
          </details>
        )}
      </div>
    </Card>
  );
}

export default function TicketDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const { data: d, error, loading, reload } = useApi<Detail>(`/tickets/${id}`, 20000);
  const [comment, setComment] = useState("");
  const [internal, setInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  if (loading && !d) return <SkeletonPage tiles={0} rows={5} />;
  if (!d) return <ErrorState message={error || "Ticket not found"} what="this ticket" onRetry={reload} />;
  const t = d.ticket;
  const mine = t.creator?.id === user?.id;
  const sla = slaText(t.sla, t.is_open);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setActionError(null);
    try { await fn(); reload(); } catch (e) { setActionError(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(false); }
  };
  const upload = (file: File) => act(async () => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("ticket_id", String(t.id));
    await api.post("/attachments", fd);
  });
  const approvals = d.actions.filter((a) => a.permission !== "safe");

  return (
    <div>
      <Link to="/tickets" className="mb-4 inline-flex items-center gap-1 text-sm text-meta hover:text-ink"><ArrowLeft className="size-4" aria-hidden /> Tickets</Link>
      <div className="mb-6">
        <h1 className="text-xl">{t.title}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-meta">
          <TicketId number={t.ticket_number} /><StatusBadge status={t.status} /><PriorityBadge priority={t.priority} />
          <span>Opened {dateTime(t.created_at)} by {mine ? "you" : t.creator?.name}{t.creator?.department ? ` (${t.creator.department})` : ""}</span>
        </div>
      </div>

      {actionError && <div className="mb-4"><FormError message={actionError} /></div>}

      <div className="grid gap-8 xl:grid-cols-[1fr_22rem]">
        <div className="min-w-0 space-y-6">
          {d.duplicate_of && (
            <Notice tone="info">This is a repeat of <Link to={`/tickets/${d.duplicate_of.id}`} className="mono font-medium text-brand hover:underline">{d.duplicate_of.ticket_number}</Link>, {d.duplicate_of.title}. Work continues there.</Notice>
          )}
          {d.incident && (
            <Notice tone="warn" action={<Link to={`/incidents?id=${d.incident.id}`} className="btn-secondary btn-sm">View incident</Link>}>
              Part of <span className="mono font-medium">{d.incident.incident_number}</span>: {d.incident.title} ({statusLabel(d.incident.status).toLowerCase()}).
            </Notice>
          )}

          <Card title="Description">
            <p className="whitespace-pre-wrap text-sm text-body">{t.description}</p>
            {!!Object.keys(t.entities).length && (
              <div className="mt-4 flex flex-wrap gap-2">{Object.entries(t.entities).map(([k, v]) => <span key={k} className="badge border-line bg-muted text-body">{sentenceCase(k)}: {v}</span>)}</div>
            )}
          </Card>

          {d.solution && (
            <SolutionCard solution={d.solution} busy={busy}
              onFixed={mine && d.agent?.awaiting_feedback ? () => act(() => api.post(`/tickets/${t.id}/feedback`, { resolved: true })) : undefined}
              onNotFixed={mine && d.agent?.awaiting_feedback ? () => act(() => api.post(`/tickets/${t.id}/feedback`, { resolved: false, comment: "Did not work" })) : undefined} />
          )}
          {mine && !t.is_open && t.status !== "duplicate" && <Rating ticketId={t.id} current={d.rating} onSaved={reload} />}
          {approvals.map((a) => <ApprovalCard key={a.id} action={a} disabled={busy} viewer={mine ? "requester" : "staff"}
            onDecide={(ok) => act(() => api.post(`/actions/${a.id}/decision`, { approve: ok }))} />)}

          <Card title="Conversation" actions={<span className="text-xs text-meta">{d.messages.length} message{d.messages.length === 1 ? "" : "s"}</span>}>
            <ol className="space-y-4">
              {d.messages.map((m) => (
                <li key={m.id} className={`rounded-sm border p-3 ${m.is_internal ? "border-warn-line bg-warn-soft" : "border-line"}`}>
                  <p className="mb-1 text-xs text-meta">
                    {m.is_internal && <span className="font-medium text-warn">Internal note · </span>}
                    {m.role === "user" ? (m.author || "Employee") : AUTHOR[m.role] || `${m.author || "IT support"} (IT support)`} · {dateTime(m.created_at)}
                  </p>
                  <RichText text={m.content} className="text-sm text-body" />
                </li>
              ))}
            </ol>
            <form className="mt-4 space-y-2 border-t border-line pt-4" onSubmit={(e) => { e.preventDefault(); act(async () => {
              await api.post(`/tickets/${t.id}/comments`, { content: comment, internal }); setComment(""); }); }}>
              <label htmlFor="reply" className="field-label">{d.can_manage ? "Reply or add a note" : "Add information for IT"}</label>
              <textarea id="reply" className="input min-h-20" value={comment} onChange={(e) => setComment(e.target.value)} required />
              <div className="flex flex-wrap items-center justify-between gap-2">
                {d.can_manage ? <label className="flex items-center gap-2 text-sm text-body"><input type="checkbox" className="size-4 accent-[var(--color-brand)]" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal note, visible to IT only</label> : <span />}
                <button className="btn-primary" disabled={busy || !comment.trim()}>Send</button>
              </div>
            </form>
          </Card>

          <Card title="What has happened" actions={<span className="text-xs text-meta">{d.steps.length} steps</span>}>
            <ol className="space-y-2">
              {d.steps.map((s) => (
                <li key={s.id} className="flex gap-2 text-sm">
                  <span className="flex h-5 shrink-0 items-center">
                    {s.status === "failed" ? <X className="size-4 text-crit" aria-label="Failed" />
                      : s.status === "running" ? <Spinner className="size-4 text-brand" />
                        : <Check className="size-4 text-ok" aria-label="Done" />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap justify-between gap-2"><span className="font-medium text-ink">{s.title}</span><span className="text-xs text-meta">{dateTime(s.created_at)}</span></p>
                    {s.detail && <p className="text-body">{s.detail}</p>}
                  </div>
                </li>
              ))}
            </ol>
            <details className="mt-4 border-t border-line pt-4">
              <summary className="cursor-pointer text-sm font-medium text-ink">Full history ({d.events.length} events)</summary>
              <ul className="mt-2 divide-y divide-line">
                {d.events.map((e) => (
                  <li key={e.id} className="flex flex-wrap justify-between gap-2 py-2 text-sm">
                    <span className="text-body">{e.description || sentenceCase(e.type)}</span>
                    <span className="text-xs text-meta">{e.actor} · {dateTime(e.created_at)}</span>
                  </li>
                ))}
              </ul>
            </details>
          </Card>
        </div>

        <aside className="space-y-4" aria-label="Ticket details">
          <Card title="Details">
            <DefinitionList items={[
              ["Status", statusLabel(t.status)],
              ["Owner", ownerLine(t, d.can_manage ? "staff" : "employee")],
              ["Priority", <span>{priorityLabel(t.priority)}{t.user_priority && t.user_priority !== t.priority ? <span className="text-meta"> (requested {priorityLabel(t.user_priority).toLowerCase()})</span> : null}</span>],
              ["Category", `${t.category || "General"}${t.sub_category ? ` · ${t.sub_category}` : ""}`],
              ["Requester", `${t.creator?.name || "-"}${t.creator?.job_title ? `, ${t.creator.job_title}` : ""}`],
              ["Created", dateTime(t.created_at)],
              ...(t.resolved_at ? [["Resolved", dateTime(t.resolved_at)] as [string, string]] : []),
            ]} />
            {t.status !== "duplicate" && t.status !== "linked_incident" && (
              <div className="mt-4 border-t border-line pt-4">
                <p className={`text-sm font-medium ${sla.tone === "crit" ? "text-crit" : sla.tone === "ok" ? "text-ok" : "text-ink"}`}>{sla.text}</p>
                {t.is_open && <><div className="mt-2"><ProgressBar value={t.sla.percent} tone={sla.tone === "crit" ? "crit" : sla.tone === "warn" ? "warn" : "brand"} label="Time used against the SLA target" /></div>
                  <p className="mt-1 text-xs text-meta">Due {dateTime(t.sla.due_at)} ({priorityLabel(t.priority).toLowerCase()} priority)</p></>}
              </div>
            )}
            {t.priority_reason && <p className="mt-4 border-t border-line pt-2 text-xs text-meta">Priority assessed from: {t.priority_impact}. {t.priority_reason}.</p>}
          </Card>

          {t.resolution_summary && (
            <Card title="Resolution"><p className="text-sm text-body">{t.resolution_summary}</p></Card>
          )}

          {d.escalation && (
            <Card title="Hand-off">
              <p className="text-sm text-body">Passed to <span className="font-medium text-ink">{d.escalation.department}</span> on {dateTime(d.escalation.created_at)}.</p>
              <p className="mt-1 text-sm text-meta">{d.escalation.reason}</p>
            </Card>
          )}

          <Card title="Attachments">
            {d.attachments.length ? (
              <ul className="space-y-2">{d.attachments.map((a) => (
                <li key={a.token}>
                  <button className="flex items-center gap-2 text-sm text-brand hover:underline" onClick={() => downloadAttachment(a.token, a.filename)}>
                    <FileText className="size-4" aria-hidden />{a.filename}<span className="text-xs text-meta">{Math.max(1, Math.round(a.size / 1024))} KB</span>
                  </button>
                </li>))}
              </ul>
            ) : <p className="text-sm text-meta">No files attached.</p>}
            {(mine || d.can_manage) && t.is_open && (
              <>
                <button className="btn-secondary btn-sm mt-4" disabled={busy} onClick={() => fileInput.current?.click()}><Paperclip className="size-4" aria-hidden /> Attach a file</button>
                <input ref={fileInput} type="file" className="hidden" accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.log"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
                <p className="mt-1 text-xs text-meta">PNG, JPG, GIF, WEBP, PDF, TXT or LOG, up to 5 MB.</p>
              </>
            )}
          </Card>

          {mine && t.is_open && !d.escalation && t.status !== "linked_incident" && (
            <button className="btn-secondary w-full" disabled={busy} onClick={() => act(() => api.post(`/tickets/${t.id}/request-human`))}>Talk to a person instead</button>
          )}

          {!!d.similar.length && (
            <Card title="Similar tickets" bodyClassName="">
              <ul className="divide-y divide-line">
                {d.similar.map((s) => (
                  <li key={s.id} className="flex items-start justify-between gap-2 px-4 py-2">
                    <span className="min-w-0"><TicketId number={s.ticket_number} to={`/tickets/${s.id}`} /><span className="block truncate text-sm text-body">{s.title}</span></span>
                    <span className="shrink-0 text-xs text-meta">{percent(s.similarity)}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {d.can_manage && <StaffPanel d={d} reload={reload} />}
          <p className="text-xs text-meta">Last updated {relative(t.updated_at)}.</p>
        </aside>
      </div>
    </div>
  );
}
