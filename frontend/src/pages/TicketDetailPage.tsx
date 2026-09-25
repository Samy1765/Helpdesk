import { useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft, Bot, CheckCircle2, ChevronDown, CircleDashed, Clock, Copy, FileSearch, Headset, Info, Loader2,
  MessageSquare, Paperclip, Repeat, ShieldCheck, Timer, User as UserIcon, Workflow, XCircle,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { api, downloadAttachment } from "../services/api";
import type { ActionView, Incident, Message, SolutionCandidate, Ticket, User } from "../services/types";
import { ApprovalCard, SolutionCard } from "../components/agent";
import {
  Badge, ErrorNote, Field, PriorityBadge, ProgressBar, RichText, Spinner, StatusBadge, clock, duration, pct,
  shortDate, timeAgo, titleCase,
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

function Card({ icon, title, right, children, tone }: { icon: React.ReactNode; title: string; right?: React.ReactNode; children: React.ReactNode; tone?: "cobalt" }) {
  return (
    <section className={`card ${tone === "cobalt" ? "!border-cobalt-line !bg-[#f8fbff]" : ""}`}>
      <div className="card-header"><span className="label-caps !text-ink flex items-center gap-2">{icon}{title}</span>{right}</div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function ExecutionLog({ d }: { d: Detail }) {
  const steps = d.steps;
  const pendingTail = d.agent?.awaiting_feedback
    ? [{ title: "Resolution state", detail: "Automatic sign-off, or transfer to a human team" }] : [];
  return (
    <ol className="space-y-1">
      {steps.map((s) => {
        const running = s.status === "running";
        return (
          <li key={s.id} className={`flex gap-3 rounded px-2.5 py-2 ${running ? "border border-cobalt-line bg-cobalt-soft" : ""}`}>
            {s.status === "failed" ? <XCircle className="size-4 text-crit shrink-0 mt-0.5" />
              : running ? <Repeat className="size-4 text-cobalt shrink-0 mt-0.5 animate-spin [animation-duration:2.5s]" />
                : <CheckCircle2 className={`size-4 shrink-0 mt-0.5 ${s.performed_by === "it_support" ? "text-violet" : "text-ok"}`} />}
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-2">
                <p className={`text-[0.8125rem] font-semibold uppercase tracking-[0.02em] ${running ? "text-cobalt" : "text-ink"}`}>{s.title}</p>
                <span className="mono text-[0.6875rem] text-meta shrink-0">{clock(s.created_at)}</span>
              </div>
              {s.detail && <p className="text-[0.8125rem] text-body leading-snug">{s.detail}</p>}
            </div>
          </li>
        );
      })}
      {pendingTail.map((p) => (
        <li key={p.title} className="flex gap-3 px-2.5 py-2 opacity-70">
          <CircleDashed className="size-4 text-faint shrink-0 mt-0.5" />
          <div className="flex-1"><div className="flex justify-between"><p className="text-[0.8125rem] font-semibold uppercase text-meta">{p.title}</p><span className="mono text-[0.6875rem] text-faint">Pending</span></div>
            <p className="text-[0.8125rem] text-meta">{p.detail}</p></div>
        </li>
      ))}
    </ol>
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
    <Card icon={<Headset className="size-4 text-violet" />} title="IT support workspace" right={<Badge tone="violet">STAFF</Badge>}>
      <div className="space-y-4">
        <ErrorNote message={error} />
        {t.is_open && (
          <div className="grid gap-2 sm:grid-cols-2">
            <button className="btn-primary" disabled={busy} onClick={() => run(() => api.post(`/support/tickets/${t.id}/accept`))}>Accept & start work</button>
            <select className="select" disabled={busy} value="" onChange={(e) => e.target.value && run(() => api.post(`/support/tickets/${t.id}/assign`, { user_id: Number(e.target.value), reason: "Reassigned" }))}>
              <option value="">Assign to…</option>
              {agents?.map((a) => <option key={a.id} value={a.id}>{a.full_name} · {a.department}</option>)}
            </select>
          </div>
        )}
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Correct category">
            <select className="select" value={t.category_id ?? ""} disabled={busy}
              onChange={(e) => run(() => api.patch(`/support/tickets/${t.id}/classification`, { category_id: Number(e.target.value), reason: "Corrected by IT" }))}>
              {categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Correct priority">
            <select className="select" value={t.priority} disabled={busy}
              onChange={(e) => run(() => api.patch(`/support/tickets/${t.id}/classification`, { priority: e.target.value, reason: "Corrected by IT" }))}>
              {["low", "medium", "high", "critical"].map((p) => <option key={p} value={p}>{titleCase(p)}</option>)}
            </select>
          </Field>
        </div>
        {t.is_open && (
          <form className="space-y-2.5 rounded border border-line bg-canvas p-3"
            onSubmit={(e: FormEvent) => { e.preventDefault(); run(() => api.post(`/support/tickets/${t.id}/resolve`, {
              resolution, root_cause: rootCause || undefined, save_as_knowledge: saveKnowledge, ai_solution_was_wrong: aiWrong })); }}>
            <p className="label-caps !text-ink">Resolve ticket</p>
            <textarea className="input min-h-20" placeholder="What fixed it? Numbered steps become reusable knowledge." value={resolution} onChange={(e) => setResolution(e.target.value)} required minLength={5} />
            <input className="input" placeholder="Root cause (optional)" value={rootCause} onChange={(e) => setRootCause(e.target.value)} />
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-cobalt size-4" checked={saveKnowledge} onChange={(e) => setSaveKnowledge(e.target.checked)} /> Save as verified knowledge (human-verified)</label>
            {d.solution && <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-cobalt size-4" checked={aiWrong} onChange={(e) => setAiWrong(e.target.checked)} /> The AI suggestion was wrong (reject it)</label>}
            <button className="btn-accent w-full" disabled={busy}>{busy ? <Loader2 className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />} Resolve</button>
          </form>
        )}
        {d.agent?.reasoning_summary && (
          <div className="rounded border border-line p-3">
            <p className="label-caps mb-1">Agent decision log (evidence & actions, not hidden reasoning)</p>
            <ul className="text-[0.8125rem] text-body space-y-0.5">{d.agent.reasoning_summary.split(" | ").map((r, i) => <li key={i}>· {r}</li>)}</ul>
            <p className="mono text-[0.6875rem] text-meta mt-2">LLM calls: {d.agent.llm_calls} · tokens: {d.agent.tokens_used} · retrieval hits: {d.agent.retrieval_hits}</p>
          </div>
        )}
        {d.escalation?.package && (
          <div>
            <button className="btn-ghost btn-sm !px-0" onClick={() => setShowPkg((s) => !s)}>
              <ChevronDown className={`size-3.5 transition-transform ${showPkg ? "rotate-180" : ""}`} /> Escalation package (JSON)
            </button>
            {showPkg && <pre className="mt-2 max-h-80 overflow-auto scroll-thin rounded border border-line bg-canvas p-3 mono text-[0.6875rem] leading-relaxed">{JSON.stringify(d.escalation.package, null, 2)}</pre>}
          </div>
        )}
      </div>
    </Card>
  );
}

export default function TicketDetailPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
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
  const topHistory = d.agent?.retrieval.find((r) => r.type === "solution");
  const adjusted = t.user_priority && t.system_priority && t.user_priority !== t.system_priority;

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

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="flex items-center gap-2">
        <button className="btn-ghost !p-2 -ml-2" onClick={() => navigate(-1)} aria-label="Back"><ArrowLeft className="size-5 text-ink" /></button>
        <h1 className="font-display font-bold tracking-tight text-lg uppercase">Ticket details</h1>
      </div>

      <div>
        <div className="flex items-center justify-between gap-2">
          <Link to="/tickets" className="text-sm text-body hover:text-cobalt">‹ {mine ? "My tickets" : "Tickets"}</Link>
          <Badge tone="cobalt" mono>{t.ticket_number}</Badge>
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1.5"><StatusBadge status={t.status} /><PriorityBadge priority={t.priority} long /></div>
          <span className="flex items-center gap-1 mono text-xs text-meta"><Clock className="size-3.5" />{duration(t.sla.elapsed_minutes)} {t.is_open ? "active" : "to resolve"}</span>
        </div>
      </div>

      <ErrorNote message={actionError} />

      <Card icon={<Bot className="size-4 text-cobalt" />} title="AI diagnostics & scope" right={t.ai_confidence ? <Badge tone="cobalt" mono>{pct(t.ai_confidence)} conf.</Badge> : undefined}>
        <h2 className="text-[1.25rem] font-semibold leading-snug">{t.title}</h2>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.8125rem] text-meta">
          <span className="flex items-center gap-1"><UserIcon className="size-3.5" />{t.creator?.name}{t.creator?.job_title ? ` (${t.creator.job_title})` : ""}</span>
          {t.creator?.department && <span>{t.creator.department}</span>}
          <span className="mono">{clock(t.created_at)} ({timeAgo(t.created_at)})</span>
        </p>
        <p className="mt-3 text-sm text-body whitespace-pre-wrap">{t.description}</p>
        <div className="mt-3 rounded border border-line bg-canvas p-3 grid grid-cols-2 gap-y-1 text-[0.8125rem]">
          <span className="label-caps">Telemetry classification</span>
          <span className="text-right text-ok-ink font-medium">{titleCase(t.classification_method || "rules")}</span>
          <span className="mono font-medium truncate">{(t.intent || t.category || "general").toUpperCase()}</span>
          <span className="text-right text-meta">Confidence: <span className="font-semibold text-ink">{pct(t.ai_confidence)}</span></span>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <div className="rounded border border-crit-line bg-crit-soft p-3">
            <p className="label-caps !text-crit-ink">User reported</p>
            <p className="font-display text-lg font-semibold text-crit mt-0.5">{(t.user_priority || "not set").toUpperCase()}</p>
          </div>
          <div className="rounded border border-cobalt-line bg-cobalt-soft p-3">
            <p className="label-caps !text-cobalt">{adjusted ? "AI adjusted" : "AI assessed"}</p>
            <p className="font-display text-lg font-semibold text-cobalt mt-0.5">{(t.system_priority || t.priority).toUpperCase()}</p>
          </div>
        </div>
        {t.priority_reason && (
          <div className="mt-2 flex gap-2 rounded border border-line bg-canvas p-3 text-[0.8125rem] text-body">
            <Info className="size-4 text-cobalt shrink-0 mt-0.5" />
            <span><span className="font-semibold text-ink">Telemetry rationale: </span>{t.priority_impact}. {t.priority_reason}. {t.priority_urgency}.</span>
          </div>
        )}
        {!!Object.keys(t.entities).length && (
          <div className="mt-2 flex flex-wrap gap-1.5">{Object.entries(t.entities).map(([k, v]) => <span key={k} className="code-chip">{k}: {v}</span>)}</div>
        )}
      </Card>

      {(topHistory || d.duplicate_of || d.incident || d.similar.length > 0) && (
        <Card tone="cobalt" icon={<Copy className="size-4 text-cobalt" />} title="Duplicate detection & heuristics"
          right={topHistory ? <Badge tone="cobalt" mono>{pct(topHistory.similarity)} match</Badge> : undefined}>
          <div className="space-y-3">
            {d.duplicate_of && (
              <p className="text-sm">Duplicate of <Link to={`/tickets/${d.duplicate_of.id}`} className="mono text-cobalt">{d.duplicate_of.ticket_number}</Link> - {d.duplicate_of.title}</p>
            )}
            {d.incident && (
              <Link to={`/incidents?id=${d.incident.id}`} className="flex justify-between gap-2 rounded border border-crit-line bg-crit-soft p-3 text-sm">
                <span><span className="mono font-semibold text-crit-ink">{d.incident.incident_number}</span> · {d.incident.title}</span><StatusBadge status={d.incident.status} />
              </Link>
            )}
            {topHistory && (
              <>
                <div className="flex justify-between gap-2 text-sm">
                  <span className="mono font-medium">{topHistory.source_ticket || `SOL-${topHistory.id}`}</span>
                  <span className="text-meta text-xs">{titleCase(topHistory.confidence_level)}</span>
                </div>
                <div className="rounded border border-line bg-surface p-3">
                  <p className="label-caps">Known verified remediation</p>
                  <p className="mono text-[0.8125rem] mt-1">{topHistory.title}</p>
                </div>
              </>
            )}
            {d.similar.length > 0 && (
              <ul className="divide-y divide-muted rounded border border-line bg-surface">
                {d.similar.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
                    <span className="min-w-0 truncate"><Link to={`/tickets/${s.id}`} className="mono text-cobalt">{s.ticket_number}</Link> <span className="text-body">{s.title}</span></span>
                    <span className="flex items-center gap-2 shrink-0"><StatusBadge status={s.status} /><span className="mono text-xs text-meta">{pct(s.similarity)}</span></span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Card>
      )}

      {d.solution && (
        <SolutionCard solution={d.solution} active={mine && !!d.agent?.awaiting_feedback} busy={busy}
          onFixed={() => act(() => api.post(`/tickets/${t.id}/feedback`, { resolved: true }))}
          onTriage={() => act(() => api.post(`/tickets/${t.id}/feedback`, { resolved: false, comment: "Did not work" }))} />
      )}
      {d.actions.filter((a) => a.permission !== "safe").map((a) => (
        <ApprovalCard key={a.id} action={a} onDecide={(ok) => decide(a, ok)} disabled={busy} />
      ))}

      <Card icon={<Workflow className="size-4 text-cobalt" />} title="Autonomous execution log" right={<span className="code-chip">{d.steps.length} steps</span>}>
        <ExecutionLog d={d} />
        {d.actions.filter((a) => a.permission === "safe" && a.status !== "skipped").length > 0 && (
          <div className="mt-3 border-t border-muted pt-3 space-y-1">
            <p className="label-caps mb-1">Safe diagnostics</p>
            {d.actions.filter((a) => a.permission === "safe" && a.status !== "skipped").map((a) => (
              <p key={a.id} className="mono text-xs text-body flex gap-2"><ShieldCheck className={`size-3.5 shrink-0 ${a.result.ok ? "text-ok" : "text-crit"}`} />{a.result.summary}</p>
            ))}
          </div>
        )}
      </Card>

      <Card icon={<Timer className="size-4 text-ink" />} title="SLA & escalation path"
        right={<Badge tone={t.sla.breached ? "crit" : t.is_open ? "warn" : "ok"} mono>
          {!t.is_open ? "Closed" : t.sla.breached ? "Breached" : `${duration(t.sla.remaining_minutes)} left`}</Badge>}>
        <div className="flex justify-between text-xs mb-1.5">
          <span className="label-caps !text-body">Target resolution: {duration(t.sla.target_minutes)}</span>
          <span className="mono font-semibold">{Math.round(t.sla.percent)}% elapsed</span>
        </div>
        <ProgressBar value={t.sla.percent} split={75} />
        <div className="flex justify-between mono text-[0.6875rem] text-meta mt-1.5">
          <span>Elapsed: {duration(t.sla.elapsed_minutes)}</span><span>Due: {shortDate(t.sla.due_at)} {clock(t.sla.due_at).slice(0, 5)}</span>
        </div>
        <div className="mt-3 rounded border border-line bg-canvas p-3">
          <p className="label-caps !text-ink">Target escalation queue</p>
          <p className="text-[0.8125rem] text-body mt-0.5">
            {d.escalation ? <>{d.escalation.department} - {d.escalation.reason}{t.assignee ? ` (assigned to ${t.assignee.name})` : ""}</>
              : t.is_open ? "Auto-escalates to the owning team if the AI cannot resolve it" : t.resolution_summary || "Resolved"}
          </p>
        </div>
        <div className="mt-4 space-y-2">
          {mine && t.is_open && (
            <Link to="/chat" className="btn-accent w-full"><MessageSquare className="size-4" /> Resume chat with AI</Link>
          )}
          {mine && t.is_open && !d.escalation && t.status !== "linked_incident" && (
            <button className="btn-outline w-full" disabled={busy} onClick={() => act(() => api.post(`/tickets/${t.id}/request-human`))}>
              <Headset className="size-4" /> Request human IT agent now
            </button>
          )}
          {(mine || d.can_manage) && (
            <>
              <button className="btn-ghost w-full uppercase text-xs tracking-wide" disabled={busy} onClick={() => fileInput.current?.click()}>
                <Paperclip className="size-3.5" /> Add diagnostic log / screenshot
              </button>
              <input ref={fileInput} type="file" className="hidden" accept="image/*,.pdf,.txt,.log"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
            </>
          )}
          {d.attachments.length > 0 && (
            <div className="flex flex-wrap gap-1.5">{d.attachments.map((a) => (
              <button key={a.token} className="code-chip flex items-center gap-1 hover:border-cobalt-line" onClick={() => downloadAttachment(a.token, a.filename)}>
                <FileSearch className="size-3" />{a.filename}</button>))}</div>
          )}
        </div>
      </Card>

      {d.can_manage && <StaffPanel d={d} reload={reload} />}

      <Card icon={<MessageSquare className="size-4 text-ink" />} title="Conversation & notes" right={<span className="code-chip">{d.messages.length}</span>}>
        <div className="space-y-3 max-h-[28rem] overflow-y-auto scroll-thin pr-1">
          {d.messages.map((m) => (
            <div key={m.id} className={`rounded border p-3 text-sm ${m.is_internal ? "border-warn-line bg-warn-soft" : m.role === "user" ? "border-cobalt-line bg-cobalt-soft" : "border-line bg-surface"}`}>
              <p className="mono text-[0.6875rem] text-meta mb-1 uppercase">
                {m.is_internal ? "Internal note · " : ""}{m.role === "assistant" ? "Precision AI" : m.author || m.role} · {timeAgo(m.created_at)}
              </p>
              <RichText text={m.content} className="text-body" />
            </div>
          ))}
        </div>
        <form className="mt-3 space-y-2" onSubmit={(e) => { e.preventDefault(); act(async () => {
          await api.post(`/tickets/${t.id}/comments`, { content: comment, internal }); setComment(""); }); }}>
          <textarea className="input min-h-16" placeholder={d.can_manage ? "Reply to the employee or add an internal note" : "Add details for IT support"} value={comment} onChange={(e) => setComment(e.target.value)} required />
          <div className="flex items-center justify-between">
            {d.can_manage ? <label className="flex items-center gap-2 text-xs text-meta"><input type="checkbox" className="accent-cobalt" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Internal note (IT only)</label> : <span />}
            <button className="btn-primary btn-sm" disabled={busy || !comment.trim()}>Post</button>
          </div>
        </form>
      </Card>

      <details className="card">
        <summary className="card-header cursor-pointer list-none"><span className="label-caps !text-ink">Audit trail</span><span className="code-chip">{d.events.length}</span></summary>
        <ul className="divide-y divide-muted">
          {d.events.map((e) => (
            <li key={e.id} className="px-4 py-2 text-[0.8125rem] flex justify-between gap-3">
              <span><span className="mono text-xs text-cobalt">{e.type}</span> <span className="text-body">{e.description}</span></span>
              <span className="mono text-[0.6875rem] text-meta shrink-0">{e.actor} · {timeAgo(e.created_at)}</span>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
