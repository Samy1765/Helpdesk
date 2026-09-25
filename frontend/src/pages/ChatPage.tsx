import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, ChevronDown, Loader2, Paperclip, Plus, RotateCcw, TriangleAlert, UserCog, X } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { api, clientEnvironment } from "../services/api";
import type { ActionView, ChatPayload, ChatReply, Message, Priority } from "../services/types";
import { Alerts, ApprovalCard, SessionHeader, SimilarList, SolutionCard, TelemetryMatrix, TicketContextCard } from "../components/agent";
import { ErrorNote, RichText, Spinner, clock } from "../components/ui";

interface Conversation { id: number; stage: string; ticket_id: number | null; ticket_number: string | null; messages: Message[] }

const PRIORITIES: (Priority | "")[] = ["", "low", "medium", "high", "critical"];
const STARTERS = [
  "My VPN keeps timing out after I enter my 2FA code",
  "Outlook crashes every time I open it",
  "I'm locked out of my account",
  "The printer on my floor isn't printing",
];

function latest<K extends keyof ChatPayload>(messages: Message[], key: K): ChatPayload[K] | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    const v = messages[i].payload?.[key];
    if (v !== undefined && v !== null) return v;
  }
  return undefined;
}

function Bubble({ m, isLast, busy, onQuick, onFixed, onTriage, onDecide }: {
  m: Message; isLast: boolean; busy: boolean; onQuick: (t: string) => void; onFixed: () => void; onTriage: () => void;
  onDecide: (a: ActionView, approve: boolean) => Promise<void>;
}) {
  const { user } = useAuth();
  if (m.role === "user") {
    return (
      <div className="flex flex-col items-end">
        <span className="mono text-[0.625rem] uppercase text-meta mb-1">{user?.username} · {clock(m.created_at)}</span>
        <div className="max-w-[85%] rounded-lg rounded-tr-sm bg-cobalt px-3.5 py-2.5 text-sm text-white shadow-hover">
          <RichText text={m.content} />
          {!!m.payload?.attachments?.length && (
            <p className="mt-1.5 flex items-center gap-1 text-xs text-white/80"><Paperclip className="size-3" /> {m.payload.attachments.map((a) => a.filename).join(", ")}</p>
          )}
        </div>
      </div>
    );
  }
  const p = m.payload || {};
  const verify = isLast && p.agent?.state === "verify";
  return (
    <div className="flex flex-col items-start gap-2 max-w-full">
      <span className="flex items-center gap-1.5 mono text-[0.625rem] uppercase text-cobalt">
        <span className="flex size-4 items-center justify-center rounded-sm bg-cobalt text-[0.5rem] font-bold text-white">P</span>
        {m.role === "agent" ? `IT support${m.author ? ` · ${m.author}` : ""}` : m.role === "system" ? "System" : "Precision core agent"}
        <span className="text-meta">{clock(m.created_at)}</span>
      </span>
      <div className="w-full sm:max-w-[92%] space-y-2">
        <div className="card px-3.5 py-3 text-sm text-body leading-relaxed"><RichText text={m.content} /></div>
        <Alerts alerts={p.alerts} />
        {p.solution && <SolutionCard solution={p.solution} active={verify} busy={busy} onFixed={onFixed} onTriage={onTriage} />}
        {p.approvals?.map((a) => <ApprovalCard key={a.id} action={a} disabled={!isLast || busy} onDecide={(ok) => onDecide(a, ok)} />)}
        {p.escalation && (
          <div className="rounded-lg border border-violet-line bg-violet-soft p-3.5 text-sm">
            <p className="label-caps !text-violet flex items-center gap-2"><UserCog className="size-4" /> Escalated to human support</p>
            <p className="mt-1.5 text-body"><span className="font-semibold text-ink">{p.escalation.department}</span>{p.escalation.assignee ? ` · assigned to ${p.escalation.assignee}` : " · awaiting assignment"}</p>
          </div>
        )}
        {p.incident && (
          <Link to={`/incidents?number=${p.incident.number}`} className="flex items-center justify-between gap-2 rounded-lg border border-crit-line bg-crit-soft p-3.5 text-sm hover:border-crit">
            <span><span className="mono font-semibold text-crit-ink">{p.incident.number}</span><span className="block text-body">{p.incident.title}</span></span>
            <ArrowRight className="size-4 text-crit" />
          </Link>
        )}
        {p.ticket && !p.escalation && !p.incident && isLast && p.agent?.state !== "verify" && (
          <Link to={`/tickets/${p.ticket.id}`} className="btn-outline btn-sm">View ticket {p.ticket.number} <ArrowRight className="size-3.5" /></Link>
        )}
        {isLast && !!p.quick_replies?.length && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {p.quick_replies.map((q, i) => (
              <button key={q} disabled={busy} onClick={() => onQuick(q)}
                className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-[0.8125rem] font-medium transition-colors disabled:opacity-50 ${
                  /still|no,/i.test(q) ? "border-crit-line bg-surface text-crit-ink hover:bg-crit-soft" : "border-cobalt-line bg-surface text-cobalt hover:bg-cobalt-soft"}`}>
                <span className={`dot size-1.5 ${/still|no,/i.test(q) ? "bg-crit" : i === 0 ? "bg-cobalt" : "bg-cobalt/60"}`} />{q}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const { user } = useAuth();
  const [conv, setConv] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [priority, setPriority] = useState<Priority | "">("");
  const [files, setFiles] = useState<{ token: string; filename: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTelemetry, setShowTelemetry] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.get<Conversation>("/chat/conversation").then((c) => { setConv(c); setMessages(c.messages); })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages, busy]);

  const progress = latest(messages, "progress");
  const ticket = latest(messages, "ticket");
  const agent = latest(messages, "agent");
  const assessment = latest(messages, "priority_assessment");
  const similar = latest(messages, "similar");
  const solution = latest(messages, "solution");
  const lastPayload = useMemo(() => ({ ticket, classification: latest(messages, "classification") }), [messages, ticket]);

  const append = (m: Partial<Message>) => setMessages((prev) => [...prev, {
    id: m.id ?? -Date.now() - Math.random(), role: m.role || "assistant", content: m.content || "", payload: m.payload || {},
    is_internal: false, author: null, created_at: new Date().toISOString(), ticket_id: null,
  }]);

  const send = async (message: string) => {
    if (!message.trim() || busy) return;
    setError(null);
    append({ role: "user", content: message, payload: { attachments: files.map((f) => ({ ...f, content_type: "", size: 0 })) } });
    setText("");
    setBusy(true);
    try {
      const r = await api.post<ChatReply>("/chat/message", {
        message, user_priority: priority || undefined, client_env: clientEnvironment(), attachment_tokens: files.map((f) => f.token),
      });
      setFiles([]);
      if (conv && r.conversation_id !== conv.id) setConv({ ...conv, id: r.conversation_id });
      append({ id: r.message_id ?? undefined, role: "assistant", content: r.message, payload: { ...r.payload, quick_replies: r.quick_replies } });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Message failed");
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => { e.preventDefault(); send(text); };

  const newChat = async () => {
    const c = await api.post<Conversation>("/chat/new");
    setConv({ ...c, ticket_id: null, ticket_number: null });
    setMessages([]);
    setPriority("");
  };

  const triage = async () => {
    if (!ticket) return;
    setBusy(true);
    try {
      const r = await api.post<{ message: string }>(`/tickets/${ticket.id}/request-human`);
      append({ role: "system", content: `${r.message}. A human IT agent now owns ${ticket.number}; you can follow progress on the ticket page.`,
        payload: { alerts: [{ type: "escalation", message: "Manual triage requested." }] } });
    } catch (e) { setError(e instanceof Error ? e.message : "Request failed"); }
    finally { setBusy(false); }
  };

  const decide = async (a: ActionView, approve: boolean) => {
    try {
      const r = await api.post<{ action: ActionView; message: string; payload: ChatPayload; quick_replies: string[] }>(`/actions/${a.id}/decision`, { approve });
      setMessages((prev) => prev.map((m) => m.payload?.approvals?.some((x) => x.id === a.id)
        ? { ...m, payload: { ...m.payload, approvals: m.payload.approvals!.map((x) => (x.id === a.id ? r.action : x)) } } : m));
      append({ role: "assistant", content: r.message, payload: { ...r.payload, approvals: [], quick_replies: r.quick_replies } });
    } catch (e) { setError(e instanceof Error ? e.message : "Decision failed"); }
  };

  const upload = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    try {
      const r = await api.post<{ token: string; filename: string }>("/attachments", fd);
      setFiles((f) => [...f, r]);
    } catch (e) { setError(e instanceof Error ? e.message : "Upload failed"); }
  };

  if (!conv && !error) return <Spinner label="Connecting to agent" />;

  const inspector = (
    <div className="space-y-3">
      {progress && <TelemetryMatrix steps={progress} routing={agent?.routing_level} model={solution?.model} />}
      {ticket && <TicketContextCard ticket={ticket} assessment={assessment} />}
      <SimilarList items={similar} />
      {!progress && (
        <div className="card p-4 text-sm text-meta">
          <p className="label-caps !text-ink mb-1.5">How this works</p>
          The agent classifies your issue, checks for duplicates and outages, searches verified fixes, and only then asks an AI model - escalating to the right team if it can't solve it safely.
        </div>
      )}
    </div>
  );

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
      <div className="min-w-0 flex flex-col">
        <div className="space-y-3">
          <SessionHeader conversationId={conv?.id ?? null} payload={lastPayload} />
          {progress && (
            <button className="lg:hidden btn-outline w-full justify-between" onClick={() => setShowTelemetry((s) => !s)}>
              <span className="label-caps !text-ink">Agent telemetry & ticket context</span>
              <ChevronDown className={`size-4 transition-transform ${showTelemetry ? "rotate-180" : ""}`} />
            </button>
          )}
          {showTelemetry && <div className="lg:hidden">{inspector}</div>}
        </div>

        <div className="flex-1 space-y-5 py-5">
          {!messages.length && (
            <div className="card p-5">
              <p className="font-display font-semibold text-[1.0625rem]">Hi {user?.full_name.split(" ")[0]}, what's going wrong?</p>
              <p className="text-sm text-meta mt-1">Describe the problem in your own words. I'll ask only what I need, then try verified fixes before involving IT.</p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {STARTERS.map((s) => (
                  <button key={s} className="text-left rounded border border-line px-3 py-2.5 text-sm text-body hover:border-cobalt-line hover:bg-cobalt-soft" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <Bubble key={m.id} m={m} isLast={i === messages.length - 1} busy={busy} onQuick={send}
              onFixed={() => send("Yes, it's fixed")} onTriage={triage} onDecide={decide} />
          ))}
          {busy && (
            <div className="flex items-center gap-2 mono text-xs text-cobalt">
              <Loader2 className="size-3.5 animate-spin" /> Precision core agent is analysing - classifying, checking duplicates, searching knowledge…
            </div>
          )}
          <ErrorNote message={error} />
          <div ref={bottom} />
        </div>

        <form onSubmit={submit} className="sticky bottom-20 lg:bottom-4 z-10 card shadow-pop p-2">
          {!!files.length && (
            <div className="flex flex-wrap gap-1.5 px-1 pb-2">
              {files.map((f) => (
                <span key={f.token} className="code-chip flex items-center gap-1"><Paperclip className="size-3" />{f.filename}
                  <button type="button" onClick={() => setFiles(files.filter((x) => x.token !== f.token))} aria-label="Remove"><X className="size-3" /></button></span>
              ))}
            </div>
          )}
          <div className="flex items-center gap-2">
            <button type="button" className="btn-outline !p-2" onClick={() => fileInput.current?.click()} aria-label="Attach screenshot or log"><Plus className="size-4" /></button>
            <input ref={fileInput} type="file" className="hidden" accept="image/*,.pdf,.txt,.log"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
            <input className="input" placeholder="Type IT issue or terminal command..." value={text} onChange={(e) => setText(e.target.value)} disabled={busy} maxLength={4000} />
            <button className="btn-accent !p-2.5" disabled={busy || !text.trim()} aria-label="Send">{busy ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}</button>
          </div>
          <div className="flex items-center justify-between gap-2 px-1 pt-2">
            <label className="flex items-center gap-2 text-xs text-meta">
              <TriangleAlert className="size-3.5" /> Your priority
              <select className="rounded border border-line bg-surface px-1.5 py-0.5 text-xs text-body" value={priority} onChange={(e) => setPriority(e.target.value as Priority | "")}>
                {PRIORITIES.map((p) => <option key={p} value={p}>{p ? p[0].toUpperCase() + p.slice(1) : "Let AI assess"}</option>)}
              </select>
            </label>
            <button type="button" className="btn-ghost btn-sm" onClick={newChat}><RotateCcw className="size-3.5" /> New chat</button>
          </div>
        </form>
      </div>

      <aside className="hidden lg:block">
        <div className="sticky top-20">{inspector}</div>
      </aside>
    </div>
  );
}
