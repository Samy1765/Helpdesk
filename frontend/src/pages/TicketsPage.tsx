import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { MessageSquare, Search, Ticket as TicketIcon } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { dateTime } from "../lib/format";
import {
  EmptyState, ErrorState, PageHeader, PriorityBadge, Segmented, SkeletonTable, StatusBadge, TicketId,
} from "../components/ui";
import { SlaLabel, ownerLine } from "../components/tickets";
import type { Ticket } from "../services/types";

const SCOPES: ["default" | "open" | "closed", string][] = [["default", "All"], ["open", "Open"], ["closed", "Closed"]];
const PER_PAGE = 20;

export default function TicketsPage() {
  const { isStaff } = useAuth();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const scope = (params.get("scope") || "default") as "default" | "open" | "closed";
  const category = params.get("category") || "";
  const priority = params.get("priority") || "";
  const page = Number(params.get("page") || 1);
  const qs = new URLSearchParams({ scope, page: String(page), per_page: String(PER_PAGE) });
  if (params.get("q")) qs.set("q", params.get("q")!);
  if (category) qs.set("category", category);
  if (priority) qs.set("priority", priority);
  const { data, error, loading, reload } = useApi<{ items: Ticket[]; total: number; page: number; per_page: number }>(`/tickets?${qs}`);
  const { data: categories } = useApi<{ id: number; name: string }[]>("/meta/categories");
  const filtered = !!(params.get("q") || category || priority);

  const update = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    if (k !== "page") next.delete("page");
    setParams(next);
  };

  const from = data ? (data.page - 1) * data.per_page + 1 : 0;
  const to = data ? Math.min(data.total, data.page * data.per_page) : 0;

  return (
    <div>
      <PageHeader title={isStaff ? "Tickets" : "Your requests"}
        description={isStaff ? "Tickets assigned to you, escalated work and critical issues." : "Every request you've raised and who is working on it."}
        actions={<Link to="/chat" className="btn-primary"><MessageSquare className="size-4" aria-hidden /> Report a problem</Link>} />

      <div className="mb-4 flex flex-wrap items-end gap-4">
        <Segmented label="Show" value={scope} onChange={(v) => update("scope", v === "default" ? "" : v)} options={SCOPES} />
        <form role="search" onSubmit={(e) => { e.preventDefault(); update("q", q.trim()); }} className="relative min-w-64 flex-1">
          <label htmlFor="ticket-search" className="sr-only">Search tickets</label>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-meta" aria-hidden />
          <input id="ticket-search" className="input pl-8" placeholder="Search by ticket number, subject or description" value={q} onChange={(e) => setQ(e.target.value)} />
        </form>
        <div>
          <label htmlFor="category" className="sr-only">Category</label>
          <select id="category" className="select w-48" value={category} onChange={(e) => update("category", e.target.value)}>
            <option value="">All categories</option>
            {categories?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="priority" className="sr-only">Priority</label>
          <select id="priority" className="select w-40" value={priority} onChange={(e) => update("priority", e.target.value)}>
            <option value="">All priorities</option>
            {[["critical", "Critical"], ["high", "High"], ["medium", "Medium"], ["low", "Low"]].map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
      </div>

      <ErrorState message={error} what="tickets" onRetry={reload} />
      {loading && !data ? <SkeletonTable rows={8} /> : !data?.items.length ? (
        <EmptyState title={filtered ? "No tickets match these filters" : scope === "open" ? "No open requests" : "No requests yet"}
          icon={<TicketIcon className="size-5" aria-hidden />}
          action={filtered ? <button className="btn-secondary" onClick={() => { setQ(""); setParams({}); }}>Clear filters</button>
            : <Link to="/chat" className="btn-primary">Report a problem</Link>}>
          {filtered ? "Try a different ticket number, word or category." : "Requests you raise through Get help appear here with their status."}
        </EmptyState>
      ) : (
        <>
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Tickets</caption>
              <thead className="border-b border-line bg-canvas">
                <tr>
                  <th className="th" scope="col">Ticket</th>
                  <th className="th" scope="col">Subject</th>
                  {isStaff && <th className="th" scope="col">Requester</th>}
                  <th className="th" scope="col">Category</th>
                  <th className="th" scope="col">Status</th>
                  <th className="th" scope="col">Priority</th>
                  <th className="th" scope="col">Updated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.items.map((t) => (
                  <tr key={t.id} className="hover:bg-canvas">
                    <td className="td whitespace-nowrap"><TicketId number={t.ticket_number} to={`/tickets/${t.id}`} /></td>
                    <td className="td min-w-72">
                      <Link to={`/tickets/${t.id}`} className="font-medium text-ink hover:underline">{t.title}</Link>
                      <span className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-meta">{ownerLine(t, isStaff ? "staff" : "employee")} <SlaLabel ticket={t} /></span>
                    </td>
                    {isStaff && <td className="td whitespace-nowrap text-body">{t.creator?.name}</td>}
                    <td className="td whitespace-nowrap text-body">{t.category || "-"}</td>
                    <td className="td"><StatusBadge status={t.status} /></td>
                    <td className="td"><PriorityBadge priority={t.priority} /></td>
                    <td className="td whitespace-nowrap text-meta">{dateTime(t.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav aria-label="Pages" className="mt-4 flex flex-wrap items-center justify-between gap-2 text-sm text-meta">
            <span>{from}–{to} of {data.total} tickets</span>
            <div className="flex gap-2">
              <button className="btn-secondary btn-sm" disabled={page <= 1} onClick={() => update("page", String(page - 1))}>Previous</button>
              <button className="btn-secondary btn-sm" disabled={page * data.per_page >= data.total} onClick={() => update("page", String(page + 1))}>Next</button>
            </div>
          </nav>
        </>
      )}
    </div>
  );
}
