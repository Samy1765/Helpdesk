import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Paperclip, RotateCcw, Send, X } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { api, clientEnvironment } from "../services/api";
import type { ActionView, ChatPayload, ChatReply, Message, Priority } from "../services/types";
import {
  Alerts, ApprovalCard, EscalationNote, IncidentLink, ProgressChecklist, SimilarList, SolutionCard, TicketSummary,
} from "../components/agent";
import { ErrorState, FormError, Notice, PageHeader, RichText, SkeletonLines, Spinner } from "../components/ui";
import { firstName, time } from "../lib/format";

interface Conversation { id: number; stage: string; ticket_id: number | null; ticket_number: string | null; messages: Message[] }

const PRIORITIES: [Priority | "", string][] = [["", "Let the agent assess"], ["low", "Low"], ["medium", "Medium"], ["high", "High"], ["critical", "Critical"]];
const STARTERS = [
  "Outlook closes as soon as I open it",
  "GlobalProtect VPN drops every few minutes",
  "My account is locked after a password change",
  "Print jobs are stuck in the queue",
];

function latest<K extends keyof ChatPayload>(messages: Message[], key: K): ChatPayload[K] | undefined {
  for (let i = messages.length - 1; i >= 0; i--) {
    const v = messages[i].payload?.[key];
    if (v !== undefined && v !== null) return v;
  }
  return undefined;
}

function author(m: Message): string {
  if (m.role === "user") return "You";
  if (m.role === "agent") return m.author ? `${m.author} (IT support)` : "IT support";
  if (m.role === "system") return "Update";
  return "Help desk agent";
}

function MessageItem({ m, isLast, busy, onQuick, onDecide }: {
  m: Message; isLast: boolean; busy: boolean; onQuick: (t: string) => void;
  onDecide: (a: ActionView, approve: boolean) => Promise<void>;
}) {
  const mine = m.role === "user";
  const p = m.payload || {};
  return (
    <li className={`flex flex-col gap-2 ${mine ? "items-end" : "items-start"}`}>
      <p className="text-xs text-meta">{author(m)} · {time(m.created_at)}</p>
      <div className={`max-w-2xl rounded-md px-4 py-2 text-sm ${mine ? "bg-brand text-white" : "border border-line bg-surface text-body"}`}>
        <RichText text={m.content} />
        {!!p.attachments?.length && (
          <p className={`mt-1 flex items-center gap-1 text-xs ${mine ? "text-white" : "text-meta"}`}>
            <Paperclip className="size-3" aria-hidden /> {p.attachments.map((a) => a.filename).join(", ")}
          </p>
        )}
      </div>
      {!mine && (
        <div className="w-full max-w-2xl space-y-2">
          <Alerts alerts={p.alerts?.filter((a) => a.type !== "escalation" && a.type !== "incident")} />
          {p.solution && <SolutionCard solution={p.solution} />}
          {p.approvals?.map((a) => <ApprovalCard key={a.id} action={a} disabled={!isLast || busy} onDecide={(ok) => onDecide(a, ok)} />)}
          {p.escalation && <EscalationNote department={p.escalation.department} assignee={p.escalation.assignee} />}
          {p.incident && <IncidentLink number={p.incident.number} title={p.incident.title} />}
          {p.ticket && !p.escalation && !p.incident && isLast && p.agent?.state !== "verify" && (
            <Link to={`/tickets/${p.ticket.id}`} className="btn-secondary btn-sm">Open ticket {p.ticket.number}</Link>
          )}
          {isLast && !!p.quick_replies?.length && (
            <div className="flex flex-wrap gap-2 pt-1" role="group" aria-label="Suggested replies">
              {p.quick_replies.map((q) => (
                <button key={q} disabled={busy} onClick={() => onQuick(q)} className="btn-secondary btn-sm">{q}</button>
              ))}
            </div>
          )}
        </div>
      )}
    </li>
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
  const [loadError, setLoadError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = () => {
    setLoadError(null);
    api.get<Conversation>("/chat/conversation").then((c) => { setConv(c); setMessages(c.messages); })
      .catch((e) => setLoadError(e.message));
  };
  useEffect(load, []);
  useEffect(() => { bottom.current?.scrollIntoView({ block: "end" }); }, [messages, busy]);

  const progress = latest(messages, "progress");
  const ticket = latest(messages, "ticket");
  const agent = latest(messages, "agent");
  const assessment = latest(messages, "priority_assessment");
  const similar = latest(messages, "similar");

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
      setError(`Your message was not sent: ${e instanceof Error ? e.message : "request failed"}. Try again.`);
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => { e.preventDefault(); send(text); };

  const newChat = async () => {
    try {
      const c = await api.post<Conversation>("/chat/new");
      setConv({ ...c, ticket_id: null, ticket_number: null });
      setMessages([]);
      setPriority("");
      setError(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not start a new conversation"); }
  };

  const talkToPerson = async () => {
    if (!ticket) return;
    setBusy(true);
    try {
      const r = await api.post<{ message: string }>(`/tickets/${ticket.id}/request-human`);
      append({ role: "system", content: `${r.message}. An IT engineer now owns ${ticket.number}; follow it on the ticket page.` });
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
    } catch (e) { setError(`${file.name} was not attached: ${e instanceof Error ? e.message : "upload failed"}`); }
  };

  const canTalkToPerson = ticket && ticket.status !== "escalated" && ticket.status !== "assigned" && ticket.status !== "in_progress"
    && !["resolved", "closed", "duplicate", "linked_incident"].includes(ticket.status);

  return (
    <div>
      <PageHeader title="Get help"
        description="Describe the problem in your own words. The agent asks at most two questions, tries known fixes first and passes the ticket to the right IT team if it can't solve it."
        actions={<>
          {canTalkToPerson && <button className="btn-secondary" disabled={busy} onClick={talkToPerson}>Talk to a person</button>}
          <button className="btn-secondary" onClick={newChat}><RotateCcw className="size-4" aria-hidden /> New conversation</button>
        </>} />

      <div className="grid gap-8 xl:grid-cols-[1fr_20rem]">
        <div className="min-w-0">
          <div className="card flex min-h-96 flex-col">
            <div className="flex-1 p-4" aria-live="polite">
              {loadError ? <ErrorState message={loadError} what="the conversation" onRetry={load} />
                : !conv ? <SkeletonLines lines={4} />
                  : !messages.length ? (
                    <div className="py-8">
                      <p className="text-base font-semibold text-ink">What's not working, {firstName(user?.full_name)}?</p>
                      <p className="mt-1 text-sm text-meta">Include any error message you see. Some common requests:</p>
                      <div className="mt-4 flex flex-wrap gap-2">
                        {STARTERS.map((s) => <button key={s} className="btn-secondary btn-sm" onClick={() => send(s)}>{s}</button>)}
                      </div>
                    </div>
                  ) : (
                    <ol className="space-y-6">
                      {messages.map((m, i) => (
                        <MessageItem key={m.id} m={m} isLast={i === messages.length - 1} busy={busy} onQuick={send} onDecide={decide} />
                      ))}
                    </ol>
                  )}
              {busy && <p className="mt-4 flex items-center gap-2 text-sm text-meta"><Spinner /> Checking known fixes and similar tickets</p>}
              <div ref={bottom} />
            </div>

            <form onSubmit={submit} className="border-t border-line p-4">
              {error && <div className="mb-2"><FormError message={error} /></div>}
              {!!files.length && (
                <ul className="mb-2 flex flex-wrap gap-2" aria-label="Attached files">
                  {files.map((f) => (
                    <li key={f.token} className="badge border-line bg-muted text-body">
                      <Paperclip className="size-3" aria-hidden />{f.filename}
                      <button type="button" onClick={() => setFiles(files.filter((x) => x.token !== f.token))} aria-label={`Remove ${f.filename}`}><X className="size-3" aria-hidden /></button>
                    </li>
                  ))}
                </ul>
              )}
              <label htmlFor="message" className="sr-only">Describe your problem</label>
              <textarea id="message" className="input min-h-20 resize-y" placeholder="For example: Outlook closes as soon as I open it, since this morning's update"
                value={text} onChange={(e) => setText(e.target.value)} disabled={busy} maxLength={4000}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }} />
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" className="btn-ghost btn-sm" onClick={() => fileInput.current?.click()}>
                    <Paperclip className="size-4" aria-hidden /> Attach screenshot or log
                  </button>
                  <input ref={fileInput} type="file" className="hidden" accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.log"
                    onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f); e.target.value = ""; }} />
                  <label className="flex items-center gap-2 text-sm text-meta" htmlFor="urgency">
                    How urgent is it for you?
                    <select id="urgency" className="select w-auto py-1" value={priority} onChange={(e) => setPriority(e.target.value as Priority | "")}>
                      {PRIORITIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    </select>
                  </label>
                </div>
                <button className="btn-primary" disabled={busy || !text.trim()}><Send className="size-4" aria-hidden /> Send</button>
              </div>
              <p className="mt-2 text-xs text-meta">Enter sends, Shift+Enter adds a line. Never type passwords or codes here; IT will not ask for them.</p>
            </form>
          </div>
        </div>

        <aside className="space-y-4" aria-label="Ticket details">
          {ticket ? <TicketSummary ticket={ticket} assessment={assessment} /> : (
            <Notice tone="info">A ticket is created as soon as the agent understands the problem. You can follow it here and on the Tickets page.</Notice>
          )}
          {progress && <ProgressChecklist steps={progress} routing={agent?.routing_level} />}
          <SimilarList items={similar} />
        </aside>
      </div>
    </div>
  );
}
