import { useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CheckCircle2, ChevronDown, Circle, FileText, Headset, Loader2, MessageSquare, Paperclip, ShieldCheck, XCircle,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { api, downloadAttachment } from "../services/api";
import type { ActionView, Incident, Message, SolutionCandidate, Ticket, User } from "../services/types";
import { ApprovalCard, SolutionCard, routingText } from "../components/agent";
import {
  ErrorNote, Field, PriorityBadge, ProgressBar, RichText, Spinner, StatusBadge, clock, dateTime, duration, pct,
  confidenceText, sentenceCase, timeAgo, titleCase,
} from "../components/ui";

interface Detail {
  ticket: Ticket;
  messages: Message[];
  steps: { id: number; key: string; title: string; detail: string | null; status: string; performed_by: string; created_at: string }[];
  events: { id: number; type: string; description: string | null; actor: string; created_at: string }[];
  agent: null | {
    state: string; attempt: number; routing_level: string | null; llm_calls: number; tokens_used: number;
    confidence: number | null; retrieval_hits: number; awaiting_feedback: boolean; reasoning_summary: string | null;
    retrieval: { type: string; id: number; title: string; similarity: number; confidence_level?: string; source_ticket?: string | null; ref?: string }[];
    resolution_status: string | null;
  };
  solution: SolutionCandidate | null;
  actions: ActionView[];
  escalation: { department: string; reason: string; package: Record<string, unknown> | null; created_at: string } | null;
  incident: Incident | null;
  duplicate_of: { id: number; ticket_number: string; title: string } | null;
  similar: { id: number; ticket_number: string; title: string; status: string; similarity: number }[];
  attachments: { token: string; filename: string; content_type: string; size: number }[];
  can_manage: boolean;
}

function Panel({ title, right, children, className = "" }: { title: string; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      <div className="card-header"><h2 className="text-sm font-semibold">{title}</h2>{right}</div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[7rem_1fr] gap-2 py-1.5 text-sm">
      <dt className="text-meta">{label}</dt>
      <dd className="text-body min-w-0">{children}</dd>
    </div>
  );
}

function Timeline({ d }: { d: Detail }) {
  const safeChecks = d.actions.filter((a) => a.permission === "safe" && a.status !== "skipped");
  return (
    <>
      <ol className="space-y-3">
        {d.steps.map((s) => (
          <li key={s.id} className="flex gap-3">
            {s.status === "failed" ? <XCircle className="size-4 text-crit shrink-0 mt-0.5" />
              : s.status === "running" ? <Loader2 className="size-4 text-cobalt shrink-0 mt-0.5 animate-spin" />
                : <CheckCircle2 className="size-4 shrink-0 mt-0.5 text-ok" />}
            <div className="min-w-0 flex-1">
              <div className="flex items-baseline justify-between gap-2">
                <p className="text-sm font-medium text-ink">{s.title}</p>
                <span className="text-xs text-meta shrink-0">{clock(s.created_at)}</span>
              </div>
              {s.detail && <p className="text-sm text-body leading-snug">{s.detail}</p>}
              {s.performed_by === "it_support" && <p className="text-xs text-meta mt-0.5">by IT support</p>}
            </div>
          </li>
        ))}
        {d.agent?.awaiting_feedback && (
          <li className="flex gap-3 text-meta">
            <Circle className="size-4 shrink-0 mt-0.5 text-line-strong" />
            <p className="text-sm">Waiting for the requester to say whether the fix worked</p>
          </li>
        )}
      </ol>
      {safeChecks.length > 0 && (
        <div className="mt-4 border-t border-muted pt-3">
          <p className="text-xs font-medium text-meta mb-1.5">Automatic checks</p>
          <ul className="space-y-1">
            {safeChecks.map((a) => (
              <li key={a.id} className="text-sm text-body flex gap-2">
                <ShieldCheck className={`size-4 shrink-0 mt-0.5 ${a.result.ok ? "text-ok" : "text-crit"}`} />{a.result.summary}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
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
  const [showPkg, setShowPkg] = useState(false);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setError(null);
    try { await fn(); reload(); } catch (e) { setError(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(false); }
  };

  return (
    <Panel title="IT support" right={<span className="text-xs text-meta">visible to IT staff only</span>}>
      <div className="space-y-4">
        <ErrorNote message={error} />
        {t.is_open && (
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary" disabled={busy} onClick={() => run(() => api.post(`/support/tickets/${t.id}/accept`))}>Take this ticket</button>
            <select className="select !w-auto" disabled={busy} value="" onChange={(e) => e.target.value && run(() => api.post(`/support/tickets/${t.id}/assign`, { user_id: Number(e.target.value), reason: "Reassigned" }))}>
              <option value="">Assign to someone else…</option>
              {agents?.map((a) => <option key={a.id} value={a.id}>{a.full_name} ({a.department})</option>)}
            </select>
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Category">
            <select className="select" value={t.category_id ?? ""} disabled={busy}
              onChange={(e) => run(() => api.patch(`/support/tickets/${t.id}/classification`, { category_id: Number(e.target.value), reason: "Corrected by IT" }))}>
              {categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Priority">
            <select className="select" value={t.priority} disabled={busy}
              onChange={(e) => run(() => api.patch(`/support/tickets/${t.id}/classification`, { priority: e.target.value, reason: "Corrected by IT" }))}>
              {["low", "medium", "high", "critical"].map((p) => <option key={p} value={p}>{titleCase(p)}</option>)}
            </select>
          </Field>
        </div>
        {t.is_open && (
          <form className="space-y-2.5 border-t border-muted pt-4"
            onSubmit={(e: FormEvent) => { e.preventDefault(); run(() => api.post(`/support/tickets/${t.id}/resolve`, {
              resolution, root_cause: rootCause || undefined, save_as_knowledge: saveKnowledge, ai_solution_was_wrong: aiWrong })); }}>
            <p className="text-sm font-medium">Resolve</p>
            <textarea className="input min-h-20" placeholder="What fixed it? Write numbered steps so the fix can be reused." value={resolution} onChange={(e) => setResolution(e.target.value)} required minLength={5} />
            <input className="input" placeholder="Root cause (optional)" value={rootCause} onChange={(e) => setRootCause(e.target.value)} />
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-cobalt size-4" checked={saveKnowledge} onChange={(e) => setSaveKnowledge(e.target.checked)} /> Save this fix to the knowledge base as verified by IT</label>
            {d.solution && <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-cobalt size-4" checked={aiWrong} onChange={(e) => setAiWrong(e.target.checked)} /> The suggested fix was wrong; stop suggesting it</label>}
            <button className="btn-accent" disabled={busy}>{busy && <Loader2 className="size-4 animate-spin" />} Mark as resolved</button>
          </form>
        )}
        {d.agent?.reasoning_summary && (
          <div className="border-t border-muted pt-4">
            <p className="text-sm font-medium mb-1">What the assistant did</p>
            <ul className="text-sm text-body space-y-1 list-disc pl-5">{d.agent.reasoning_summary.split(" | ").map((r, i) => <li key={i}>{r}</li>)}</ul>
            <p className="text-xs text-meta mt-2">
              Answered using: {routingText(d.agent.routing_level)} · language model calls: {d.agent.llm_calls} · tokens: {d.agent.tokens_used} · knowledge matches: {d.agent.retrieval_hits}
            </p>
          </div>
        )}
        {d.escalation?.package && (
          <div>
            <button className="btn-ghost btn-sm !px-0" onClick={() => setShowPkg((s) => !s)}>
              <ChevronDown className={`size-3.5 transition-transform ${showPkg ? "rotate-180" : ""}`} /> Hand-over details sent to the team
            </button>
            {showPkg && <pre className="mt-2 max-h-80 overflow-auto scroll-thin rounded border border-line bg-canvas p-3 mono text-xs leading-relaxed">{JSON.stringify(d.escalation.package, null, 2)}</pre>}
          </div>
        )}
      </div>
    </Panel>
  );
}

export default function TicketDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const { data: d, error, loading, reload } = useApi<Detail>(`/tickets/${id}`, 15000);
  const [comment, setComment] = useState("");
  const [internal, setInternal] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  if (loading && !d) return <Spinner />;
  if (!d) return <ErrorNote message={error || "Ticket not found"} />;
  const t = d.ticket;
  const mine = t.creator?.id === user?.id;
  const reusedFix = d.agent?.retrieval.find((r) => r.type === "solution");
  const adjusted = t.user_priority && t.system_priority && t.user_priority !== t.system_priority;
  const priorityWhy = [t.priority_impact, t.priority_reason]
    .filter((x) => x && x !== "historical import").map((x) => x!.replace(/\.$/, "")).join(". ");

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true); setActionError(null);
    try { await fn(); reload(); } catch (e) { setActionError(e instanceof Error ? e.message : "Action failed"); } finally { setBusy(false); }
  };

  const decide = async (a: ActionView, approve: boolean) => { await act(() => api.post(`/actions/${a.id}/decision`, { approve })); };

  const upload = (file: File) => act(async () => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("ticket_id", String(t.id));
    await api.post("/attachments", fd);
  });

  const related = d.duplicate_of || d.incident || d.similar.length > 0 || reusedFix;

  return (
    <div className="space-y-4">
      <div>
        <Link to="/tickets" className="text-sm text-meta hover:text-cobalt">‹ {mine ? "My tickets" : "Tickets"}</Link>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="mono text-sm text-meta">{t.ticket_number}</p>
            <h1 className="text-xl md:text-2xl font-semibold leading-snug">{t.title}</h1>
          </div>
          <div className="flex gap-1.5 pt-1"><StatusBadge status={t.status} /><PriorityBadge priority={t.priority} long /></div>
        </div>
      </div>

      <ErrorNote message={actionError} />

      <div className="grid gap-4 lg:grid-cols-[1fr_20rem] items-start">
        <div className="space-y-4 min-w-0">
          <Panel title="Description" right={<span className="text-xs text-meta">{dateTime(t.created_at)}</span>}>
            <p className="text-sm text-body whitespace-pre-wrap">{t.description}</p>
            {!!Object.keys(t.entities).length && (
              <div className="mt-3 flex flex-wrap gap-1.5">{Object.entries(t.entities).map(([k, v]) => <span key={k} className="code-chip">{sentenceCase(k)}: {v}</span>)}</div>
            )}
            {priorityWhy && (
              <p className="mt-3 border-t border-muted pt-3 text-sm text-meta">
                <span className="text-body font-medium">{adjusted ? `Priority changed from ${t.user_priority} to ${t.system_priority}: ` : "Why this priority: "}</span>
                {priorityWhy}
              </p>
            )}
          </Panel>

          {d.solution && (
            <SolutionCard solution={d.solution} active={mine && !!d.agent?.awaiting_feedback} busy={busy}
              onFixed={() => act(() => api.post(`/tickets/${t.id}/feedback`, { resolved: true }))}
              onTriage={() => act(() => api.post(`/tickets/${t.id}/feedback`, { resolved: false, comment: "Did not work" }))} />
          )}
          {d.actions.filter((a) => a.permission !== "safe").map((a) => (
            <ApprovalCard key={a.id} action={a} onDecide={(ok) => decide(a, ok)} disabled={busy} />
          ))}

          {related && (
            <Panel title="Related">
              <div className="space-y-3 text-sm">
                {d.incident && (
                  <Link to={`/incidents?id=${d.incident.id}`} className="flex items-center justify-between gap-2 rounded border border-crit-line bg-crit-soft px-3 py-2">
                    <span>Part of known problem <span className="mono">{d.incident.incident_number}</span>: {d.incident.title}</span><StatusBadge status={d.incident.status} />
                  </Link>
                )}
                {d.duplicate_of && (
                  <p>Same problem as <Link to={`/tickets/${d.duplicate_of.id}`} className="mono text-cobalt">{d.duplicate_of.ticket_number}</Link>: {d.duplicate_of.title}</p>
                )}
                {reusedFix && (
                  <p className="text-body">
                    Fix reused from {reusedFix.source_ticket ? <span className="mono">{reusedFix.source_ticket}</span> : "the knowledge base"} ({pct(reusedFix.similarity)} match
                    {reusedFix.confidence_level ? `, ${confidenceText(reusedFix.confidence_level)}` : ""}): {reusedFix.title}
                  </p>
                )}
                {d.similar.length > 0 && (
                  <div>
                    <p className="text-xs font-medium text-meta mb-1">Similar tickets</p>
                    <ul className="divide-y divide-muted">
                      {d.similar.map((s) => (
                        <li key={s.id} className="flex items-center justify-between gap-2 py-1.5">
                          <span className="min-w-0 truncate"><Link to={`/tickets/${s.id}`} className="mono text-cobalt">{s.ticket_number}</Link> <span className="text-body">{s.title}</span></span>
                          <span className="flex items-center gap-2 shrink-0"><StatusBadge status={s.status} /><span className="text-xs text-meta tabular-nums">{pct(s.similarity)}</span></span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </Panel>
          )}

          <Panel title="What has happened" right={<span className="text-xs text-meta">{d.steps.length} {d.steps.length === 1 ? "step" : "steps"}</span>}>
            {d.steps.length ? <Timeline d={d} /> : <p className="text-sm text-meta">Nothing yet.</p>}
          </Panel>

          {d.can_manage && <StaffPanel d={d} reload={reload} />}

          <Panel title="Comments" right={<span className="text-xs text-meta">{d.messages.length}</span>}>
            <div className="space-y-3 max-h-[28rem] overflow-y-auto scroll-thin pr-1">
              {d.messages.map((m) => (
                <div key={m.id} className={`rounded border p-3 text-sm ${m.is_internal ? "border-warn-line bg-warn-soft" : "border-line bg-surface"}`}>
                  <p className="text-xs text-meta mb-1">
                    <span className="font-medium text-body">{m.role === "assistant" ? "Assistant" : m.author || (m.role === "user" ? t.creator?.name : sentenceCase(m.role))}</span>
                    {m.is_internal && " · internal note"} · {timeAgo(m.created_at)}
                  </p>
                  <RichText text={m.content} className="text-body" />
                </div>
              ))}
            </div>
            <form className="mt-3 space-y-2" onSubmit={(e) => { e.preventDefault(); act(async () => {
              await api.post(`/tickets/${t.id}/comments`, { content: comment, internal }); setComment(""); }); }}>
              <textarea className="input min-h-16" placeholder={d.can_manage ? "Reply to the requester or add an internal note" : "Add more details for IT"} value={comment} onChange={(e) => setComment(e.target.value)} required />
              <div className="flex items-center justify-between">
                {d.can_manage ? <label className="flex items-center gap-2 text-sm text-meta"><input type="checkbox" className="accent-cobalt" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal note, IT only</label> : <span />}
                <button className="btn-primary btn-sm" disabled={busy || !comment.trim()}>Add comment</button>
              </div>
            </form>
          </Panel>

          <details className="card">
            <summary className="card-header cursor-pointer list-none"><span className="text-sm font-semibold">History</span><span className="text-xs text-meta">{d.events.length} entries</span></summary>
            <ul className="divide-y divide-muted">
              {d.events.map((e) => (
                <li key={e.id} className="px-4 py-2 text-sm flex justify-between gap-3">
                  <span className="text-body">{e.description || sentenceCase(e.type)}</span>
                  <span className="text-xs text-meta shrink-0">{e.actor} · {dateTime(e.created_at)}</span>
                </li>
              ))}
            </ul>
          </details>
        </div>

        <aside className="space-y-4 lg:sticky lg:top-20">
          <Panel title="Details">
            <dl className="-my-1.5">
              <Row label="Reported by">{t.creator?.name}{t.creator?.department ? <span className="block text-xs text-meta">{t.creator.department}{t.creator.job_title ? `, ${t.creator.job_title}` : ""}</span> : null}</Row>
              <Row label="Category">{t.category || "General"}{(t.sub_category || t.intent) && <span className="block text-xs text-meta">{t.sub_category || sentenceCase(t.intent)}</span>}</Row>
              <Row label="Team">{t.department || "Not assigned yet"}</Row>
              <Row label="Assignee">{t.assignee?.name || (t.resolved_by_ai ? "Resolved by the assistant" : "Nobody yet")}</Row>
              <Row label="Opened">{dateTime(t.created_at)}</Row>
              {t.resolved_at && <Row label="Resolved">{dateTime(t.resolved_at)}</Row>}
              <Row label="Classified">{sentenceCase(t.classification_method || "rules")}{t.ai_confidence ? `, ${pct(t.ai_confidence)} sure` : ""}</Row>
            </dl>
          </Panel>

          <Panel title="Time to resolve" right={<span className={`text-xs ${t.sla.breached ? "text-crit" : "text-meta"}`}>
            {!t.is_open ? `took ${duration(t.sla.elapsed_minutes)}` : t.sla.breached ? "overdue" : `${duration(t.sla.remaining_minutes)} left`}</span>}>
            <ProgressBar value={t.sla.percent} tone={t.sla.breached ? "crit" : t.sla.percent > 75 ? "warn" : "cobalt"} />
            <p className="text-xs text-meta mt-2">Target {duration(t.sla.target_minutes)} for {t.priority} priority · due {dateTime(t.sla.due_at)}</p>
            {d.escalation && <p className="text-sm text-body mt-3">With {d.escalation.department}: {d.escalation.reason}</p>}
          </Panel>

          {(mine || d.can_manage) && (
            <div className="card p-4 space-y-2">
              {mine && t.is_open && <Link to="/chat" className="btn-accent w-full"><MessageSquare className="size-4" /> Continue in chat</Link>}
              {mine && t.is_open && !d.escalation && t.status !== "linked_incident" && (
                <button className="btn-outline w-full" disabled={busy} onClick={() => act(() => api.post(`/tickets/${t.id}/request-human`))}>
                  <Headset className="size-4" /> Ask a person from IT
                </button>
              )}
              <button className="btn-outline w-full" disabled={busy} onClick={() => fileInput.current?.click()}>
                <Paperclip className="size-4" /> Attach a screenshot or log
              </button>
              <input ref={fileInput} type="file" className="hidden" accept="image/*,.pdf,.txt,.log"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
              {d.attachments.length > 0 && (
                <ul className="pt-1 space-y-1">{d.attachments.map((a) => (
                  <li key={a.token}>
                    <button className="flex items-center gap-1.5 text-sm text-cobalt hover:underline" onClick={() => downloadAttachment(a.token, a.filename)}>
                      <FileText className="size-3.5" />{a.filename}</button>
                  </li>))}</ul>
              )}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
