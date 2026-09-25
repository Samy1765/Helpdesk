import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { MessageSquare, Search, Ticket as TicketIcon } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { Empty, ErrorNote, PageHeader, PriorityBadge, Spinner, StatusBadge, TicketId, timeAgo } from "../components/ui";
import type { Ticket } from "../services/types";

const SCOPES = [["default", "All"], ["open", "Open"], ["closed", "Closed"]] as const;

export default function TicketsPage() {
  const { isStaff } = useAuth();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const scope = params.get("scope") || "default";
  const category = params.get("category") || "";
  const priority = params.get("priority") || "";
  const page = Number(params.get("page") || 1);
  const qs = new URLSearchParams({ scope, page: String(page), per_page: "20" });
  if (params.get("q")) qs.set("q", params.get("q")!);
  if (category) qs.set("category", category);
  if (priority) qs.set("priority", priority);
  const { data, error, loading } = useApi<{ items: Ticket[]; total: number; page: number; per_page: number }>(`/tickets?${qs}`);
  const { data: categories } = useApi<{ id: number; name: string }[]>("/meta/categories");

  const update = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    if (k !== "page") next.delete("page");
    setParams(next);
  };

  return (
    <div>
      <PageHeader title={isStaff ? "Ticket center" : "My tickets"}
        subtitle={isStaff ? "Tickets assigned to you, escalated work and critical issues." : "Every issue you've raised, with live AI and IT status."}
        right={<Link to="/chat" className="btn-accent"><MessageSquare className="size-4" /> New issue</Link>} />

      <div className="card p-3 mb-4 space-y-3">
        <div className="flex gap-1 overflow-x-auto">
          {SCOPES.map(([k, label]) => (
            <button key={k} onClick={() => update("scope", k === "default" ? "" : k)}
              className={`rounded px-3 py-1.5 text-sm font-medium whitespace-nowrap ${scope === k ? "bg-ink text-white" : "text-body hover:bg-muted"}`}>{label}</button>
          ))}
        </div>
        <div className="grid gap-2 sm:grid-cols-[1fr_10rem_10rem]">
          <form onSubmit={(e) => { e.preventDefault(); update("q", q.trim()); }} className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-faint" />
            <input className="input pl-9" placeholder="Search INC number, title or description" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
          <select className="select" value={category} onChange={(e) => update("category", e.target.value)}>
            <option value="">All categories</option>
            {categories?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
          </select>
          <select className="select" value={priority} onChange={(e) => update("priority", e.target.value)}>
            <option value="">All priorities</option>
            {["critical", "high", "medium", "low"].map((p) => <option key={p} value={p}>{p[0].toUpperCase() + p.slice(1)}</option>)}
          </select>
        </div>
      </div>

      <ErrorNote message={error} />
      {loading && !data ? <Spinner /> : !data?.items.length ? (
        <Empty title="No tickets match" icon={<TicketIcon className="size-5" />}>Try another filter, or start a chat to report an issue.</Empty>
      ) : (
        <>
          <div className="hidden md:block card overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-canvas border-b border-line">
                <tr className="text-left">
                  {["ID", "Issue", "Category", "Status", "Priority", isStaff ? "Requester" : "Owner", "Updated"].map((h) => (
                    <th key={h} className="label-caps px-4 py-2.5 font-semibold">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-muted">
                {data.items.map((t) => (
                  <tr key={t.id} className="h-11 hover:bg-canvas">
                    <td className="px-4 whitespace-nowrap">
                      <span className="flex items-center gap-2">
                        <span className={`dot size-1.5 ${t.sla.breached && t.is_open ? "bg-crit" : t.is_open ? "bg-ok" : "bg-faint"}`} title="SLA status" />
                        <TicketId number={t.ticket_number} to={`/tickets/${t.id}`} />
                      </span>
                    </td>
                    <td className="px-4 max-w-80"><Link to={`/tickets/${t.id}`} className="font-medium hover:text-cobalt line-clamp-1">{t.title}</Link></td>
                    <td className="px-4 text-meta whitespace-nowrap">{t.category || "-"}</td>
                    <td className="px-4"><StatusBadge status={t.status} /></td>
                    <td className="px-4"><PriorityBadge priority={t.priority} /></td>
                    <td className="px-4 text-meta whitespace-nowrap">{isStaff ? t.creator?.name : t.assignee?.name || (t.resolved_by_ai ? "AI agent" : t.department || "AI agent")}</td>
                    <td className="px-4 mono text-xs text-meta whitespace-nowrap">{timeAgo(t.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="md:hidden space-y-2.5">
            {data.items.map((t) => (
              <Link key={t.id} to={`/tickets/${t.id}`} className="card card-hover block p-3.5">
                <div className="flex items-center justify-between gap-2">
                  <TicketId number={t.ticket_number} />
                  <div className="flex gap-1.5"><StatusBadge status={t.status} /><PriorityBadge priority={t.priority} /></div>
                </div>
                <p className="mt-1.5 font-display font-semibold leading-snug">{t.title}</p>
                <p className="mono text-xs text-meta mt-1">{t.category || "General"} · {timeAgo(t.created_at)}</p>
              </Link>
            ))}
          </div>
          <div className="flex items-center justify-between mt-4 text-sm text-meta">
            <span className="mono text-xs">{data.total} ticket(s)</span>
            <div className="flex gap-2">
              <button className="btn-outline btn-sm" disabled={page <= 1} onClick={() => update("page", String(page - 1))}>Previous</button>
              <button className="btn-outline btn-sm" disabled={page * data.per_page >= data.total} onClick={() => update("page", String(page + 1))}>Next</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
