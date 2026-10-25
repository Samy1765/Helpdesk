import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BookOpen, Plus, Search, X } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { KnowledgeDoc, Solution } from "../services/types";
import Markdown from "../components/Markdown";
import {
  Badge, Card, DefinitionList, EmptyState, ErrorState, Field, FormError, PageHeader, Section, SkeletonLines, SkeletonTable,
  Spinner, TrustBadge,
} from "../components/ui";
import { date, percent, sentenceCase } from "../lib/format";

interface SearchResult {
  documents: { chunk_id: number; ref: string; document_id: number; title: string; heading: string | null; excerpt: string; similarity: number; category: string | null }[];
  solutions: Solution[];
}

const REVIEW_DUE_DAYS = 180;
const reviewDue = (d: string | null) => !d || (Date.now() - new Date(`${d}T00:00:00`).getTime()) / 86400000 > REVIEW_DUE_DAYS;

function DocViewer({ id, onClose }: { id: number; onClose: () => void }) {
  const { data, loading, error, reload } = useApi<KnowledgeDoc>(`/knowledge/documents/${id}`);
  return (
    <article className="card" aria-label={data?.title || "Article"}>
      <div className="card-header">
        <span className="text-xs text-meta">Article</span>
        <button className="btn-ghost btn-icon" onClick={onClose} aria-label="Close article"><X className="size-4" aria-hidden /></button>
      </div>
      {error ? <div className="p-4"><ErrorState message={error} what="the article" onRetry={reload} /></div>
        : loading || !data ? <div className="p-4"><SkeletonLines lines={8} /></div> : (
          <div className="p-6">
            <h2 className="text-lg">{data.title}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <TrustBadge level={data.trust_level} />
              {data.category && <Badge>{data.category}</Badge>}
              <Badge>{sentenceCase(data.doc_type)}</Badge>
              {reviewDue(data.last_reviewed) && <Badge tone="warn">Review due</Badge>}
            </div>
            <div className="mt-4 rounded-sm border border-line bg-canvas p-4">
              <DefinitionList items={[["Owner", data.owner], ["Last reviewed", date(data.last_reviewed)], ["Updated", date(data.updated_at)]]} />
            </div>
            <div className="mt-6"><Markdown source={data.content || ""} /></div>
          </div>
        )}
    </article>
  );
}

function NewDocument({ onCreated, onCancel }: { onCreated: (id: number) => void; onCancel: () => void }) {
  const { data: categories } = useApi<{ id: number; name: string }[]>("/meta/categories");
  const [form, setForm] = useState({ title: "", content: "## Symptoms\n- \n\n## Resolution\n1. \n\n## Escalation criteria\n- \n", category_id: "", doc_type: "runbook" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const doc = await api.post<KnowledgeDoc>("/knowledge/documents", { ...form, category_id: form.category_id ? Number(form.category_id) : null });
      onCreated(doc.id);
    } catch (err) { setError(err instanceof Error ? err.message : "Publishing failed"); } finally { setBusy(false); }
  };
  return (
    <Card title="New article">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Title" htmlFor="doc-title"><input id="doc-title" className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required minLength={3} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Category" htmlFor="doc-category">
            <select id="doc-category" className="select" value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
              <option value="">General</option>{categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="Type" htmlFor="doc-type">
            <select id="doc-type" className="select" value={form.doc_type} onChange={(e) => setForm({ ...form, doc_type: e.target.value })}>
              {["runbook", "guide", "faq", "policy"].map((t) => <option key={t} value={t}>{t === "faq" ? "FAQ" : sentenceCase(t)}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Content (Markdown)" htmlFor="doc-content" hint="Each heading becomes a searchable section. Numbered steps under Resolution are shown to employees as the fix.">
          <textarea id="doc-content" className="input min-h-48 font-mono" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} required minLength={20} />
        </Field>
        <FormError message={error} />
        <div className="flex gap-2">
          <button className="btn-primary" disabled={busy}>{busy && <Spinner />} Publish</button>
          <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
        </div>
      </form>
    </Card>
  );
}

export default function KnowledgePage() {
  const { isStaff } = useAuth();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const category = params.get("category") || "";
  const { data: docs, loading, error, reload } = useApi<KnowledgeDoc[]>(`/knowledge/documents${category ? `?category_id=${category}` : ""}`);
  const { data: categories } = useApi<{ id: number; name: string }[]>("/meta/categories");
  const docId = Number(params.get("doc")) || null;

  const setParam = (k: string, v: string | null) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v); else next.delete(k);
    setParams(next);
  };

  const search = async (e: FormEvent) => {
    e.preventDefault();
    if (q.trim().length < 3) { setSearchError("Type at least three characters."); return; }
    setSearching(true); setSearchError(null);
    try { setResults(await api.get<SearchResult>(`/knowledge/search?q=${encodeURIComponent(q.trim())}`)); }
    catch (err) { setSearchError(err instanceof Error ? err.message : "Search failed"); }
    finally { setSearching(false); }
  };

  return (
    <div>
      <PageHeader title="Knowledge base"
        description={`${docs?.length ?? "-"} IT articles and the fixes the help desk agent reuses. Search by describing the problem.`}
        actions={isStaff && !creating && <button className="btn-secondary" onClick={() => setCreating(true)}><Plus className="size-4" aria-hidden /> New article</button>} />

      <form role="search" onSubmit={search} className="mb-6 flex flex-wrap gap-2">
        <div className="relative min-w-64 flex-1">
          <label htmlFor="kb-search" className="sr-only">Describe the problem</label>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-meta" aria-hidden />
          <input id="kb-search" className="input pl-8" placeholder="Describe the problem, for example: Outlook keeps asking for my password" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <button className="btn-primary" disabled={searching}>{searching && <Spinner />} Search</button>
      </form>
      {searchError && <div className="mb-4"><FormError message={searchError} /></div>}

      {creating && <div className="mb-6"><NewDocument onCancel={() => setCreating(false)} onCreated={(id) => { setCreating(false); reload(); setParam("doc", String(id)); }} /></div>}

      {results && (
        <Section className="mb-8" title={`Results for "${q.trim()}"`} actions={<button className="btn-ghost btn-sm" onClick={() => setResults(null)}>Clear results</button>}>
          {!results.documents.length && !results.solutions.length ? (
            <EmptyState title="Nothing close enough">Try describing what you see on screen, or <Link to="/chat" className="text-brand hover:underline">ask the help desk agent</Link>.</EmptyState>
          ) : (
            <div className="grid gap-4 lg:grid-cols-2">
              {results.solutions.map((s) => (
                <div key={`s${s.id}`} className="card p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2"><TrustBadge level={s.confidence_level} /><span className="text-xs text-meta">{percent(s.similarity)} match</span></div>
                  <p className="mt-2 font-medium text-ink">{s.title}</p>
                  <ol className="mt-2 list-decimal space-y-1 pl-4 text-sm text-body">{s.steps.slice(0, 4).map((st, i) => <li key={i}>{st}</li>)}</ol>
                  <p className="mt-2 text-xs text-meta">{s.category} · worked {s.times_successful} of {s.times_used} times{s.ticket_number ? ` · from ${s.ticket_number}` : ""}</p>
                </div>
              ))}
              {results.documents.map((d) => (
                <button key={`d${d.chunk_id}`} className="card p-4 text-left hover:border-line-strong" onClick={() => setParam("doc", String(d.document_id))}>
                  <div className="flex flex-wrap items-center justify-between gap-2"><Badge tone="brand">Article</Badge><span className="text-xs text-meta">{percent(d.similarity)} match</span></div>
                  <p className="mt-2 font-medium text-ink">{d.title}</p>
                  {d.heading && <p className="text-xs text-meta">Section: {d.heading}</p>}
                  <p className="mt-1 line-clamp-3 text-sm text-body">{d.excerpt}</p>
                </button>
              ))}
            </div>
          )}
        </Section>
      )}

      <div className={`grid gap-8 ${docId ? "xl:grid-cols-[1fr_1fr]" : ""}`}>
        <Section title="All articles" actions={
          <div>
            <label htmlFor="kb-category" className="sr-only">Category</label>
            <select id="kb-category" className="select w-48 py-1" value={category} onChange={(e) => setParam("category", e.target.value || null)}>
              <option value="">All categories</option>{categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>}>
          <ErrorState message={error} what="articles" onRetry={reload} />
          {loading && !docs ? <SkeletonTable rows={8} /> : !docs?.length ? (
            <EmptyState title="No articles in this category" icon={<BookOpen className="size-5" aria-hidden />} />
          ) : (
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-line bg-canvas"><tr><th className="th">Article</th><th className="th">Category</th>{!docId && <th className="th">Owner</th>}<th className="th">Last reviewed</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {docs.map((d) => (
                    <tr key={d.id} className={d.id === docId ? "bg-brand-soft" : "hover:bg-canvas"}>
                      <td className="td">
                        <button className="text-left font-medium text-ink hover:underline" aria-current={d.id === docId ? "true" : undefined}
                          onClick={() => setParam("doc", String(d.id))}>{d.title}</button>
                        {!docId && <p className="mt-1 line-clamp-1 text-xs text-meta">{d.excerpt}</p>}
                      </td>
                      <td className="td whitespace-nowrap text-body">{d.category || "General"}</td>
                      {!docId && <td className="td whitespace-nowrap text-body">{d.owner}</td>}
                      <td className="td whitespace-nowrap">
                        <span className={reviewDue(d.last_reviewed) ? "text-warn" : "text-meta"}>{date(d.last_reviewed)}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
        {docId && <div className="xl:sticky xl:top-24 xl:self-start"><DocViewer key={docId} id={docId} onClose={() => setParam("doc", null)} /></div>}
      </div>
    </div>
  );
}
