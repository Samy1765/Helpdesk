import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { BookOpen, Loader2, Plus, Search, X } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { KnowledgeDoc, Solution } from "../services/types";
import Markdown from "../components/Markdown";
import { Badge, Empty, ErrorNote, Field, PageHeader, SectionTitle, Spinner, confidenceText, pct, sentenceCase, shortDate, titleCase } from "../components/ui";

interface SearchResult {
  documents: { chunk_id: number; ref: string; document_id: number; title: string; heading: string | null; excerpt: string; similarity: number; category: string | null }[];
  solutions: Solution[];
}

const TRUST_TONE: Record<string, "ok" | "info" | "warn"> = { admin_verified: "ok", human_verified: "ok", user_confirmed: "info", ai_generated: "warn" };
const trustLabel = (level: string) => sentenceCase(confidenceText(level));

function DocViewer({ id, onClose }: { id: number; onClose: () => void }) {
  const { data, loading } = useApi<KnowledgeDoc>(`/knowledge/documents/${id}`);
  return (
    <div className="card min-w-0">
      <div className="card-header">
        <span className="font-semibold truncate">{data?.title || "Loading"}</span>
        <button className="btn-ghost !p-1.5" onClick={onClose} aria-label="Close"><X className="size-4" /></button>
      </div>
      {loading || !data ? <Spinner /> : (
        <div className="p-5">
          <div className="flex flex-wrap gap-1.5 mb-3">
            {data.category && <Badge>{data.category}</Badge>}
            <Badge>{titleCase(data.doc_type)}</Badge>
            <Badge tone={TRUST_TONE[data.trust_level] || "ok"}>{trustLabel(data.trust_level || "admin_verified")}</Badge>
            <span className="text-xs text-meta self-center">Updated {shortDate(data.updated_at)}</span>
          </div>
          <Markdown source={data.content || ""} />
        </div>
      )}
    </div>
  );
}

function NewDocument({ onCreated }: { onCreated: (id: number) => void }) {
  const { data: categories } = useApi<{ id: number; name: string }[]>("/meta/categories");
  const [form, setForm] = useState({ title: "", content: "## Symptoms\n\n## Resolution\n1. \n", category_id: "", doc_type: "runbook" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const doc = await api.post<KnowledgeDoc>("/knowledge/documents", { ...form, category_id: form.category_id ? Number(form.category_id) : null });
      onCreated(doc.id);
    } catch (err) { setError(err instanceof Error ? err.message : "Failed"); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="card p-4 space-y-3">
      <p className="font-semibold">New article</p>
      <Field label="Title"><input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required minLength={3} /></Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Category">
          <select className="select" value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
            <option value="">General</option>{categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Field label="Type">
          <select className="select" value={form.doc_type} onChange={(e) => setForm({ ...form, doc_type: e.target.value })}>
            {["runbook", "faq", "guide", "policy"].map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Content (Markdown)" hint="Each heading becomes a separate searchable section. Numbered lists are shown to employees as steps.">
        <textarea className="input min-h-48 mono text-[0.8125rem]" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} required minLength={20} />
      </Field>
      <ErrorNote message={error} />
      <button className="btn-accent" disabled={busy}>{busy && <Loader2 className="size-4 animate-spin" />} Publish</button>
    </form>
  );
}

function groupByCategory(docs: KnowledgeDoc[]): [string, KnowledgeDoc[]][] {
  const groups = new Map<string, KnowledgeDoc[]>();
  for (const d of docs) {
    const key = d.category || "General";
    groups.set(key, [...(groups.get(key) || []), d]);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

export default function KnowledgePage() {
  const { isStaff } = useAuth();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [creating, setCreating] = useState(false);
  const [category, setCategory] = useState("");
  const { data: docs, loading, error, reload } = useApi<KnowledgeDoc[]>(`/knowledge/documents${category ? `?category_id=${category}` : ""}`);
  const { data: categories } = useApi<{ id: number; name: string }[]>("/meta/categories");
  const docId = Number(params.get("doc")) || null;

  const search = async (e: FormEvent) => {
    e.preventDefault();
    if (q.trim().length < 3) return;
    setSearching(true);
    try { setResults(await api.get<SearchResult>(`/knowledge/search?q=${encodeURIComponent(q.trim())}`)); } finally { setSearching(false); }
  };

  return (
    <div>
      <PageHeader title="Knowledge base" subtitle="Step-by-step guides written by IT, and fixes that worked on earlier tickets."
        right={isStaff && <button className="btn-outline" onClick={() => setCreating((c) => !c)}><Plus className="size-4" /> New article</button>} />

      <form onSubmit={search} className="card p-3 flex gap-2 mb-5">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-faint" />
          <input className="input pl-9" placeholder="Describe the problem, for example: second monitor stays black" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <button className="btn-accent" disabled={searching}>{searching && <Loader2 className="size-4 animate-spin" />} Search</button>
      </form>

      {creating && <div className="mb-5"><NewDocument onCreated={(id) => { setCreating(false); reload(); setParams({ doc: String(id) }); }} /></div>}

      {results && (
        <section className="mb-6">
          <SectionTitle right={<button className="btn-ghost btn-sm" onClick={() => setResults(null)}>Clear</button>}>Search results</SectionTitle>
          {!results.documents.length && !results.solutions.length && <Empty title="Nothing close enough">Try describing what you see in different words, or use Get help.</Empty>}
          <div className="grid gap-3 md:grid-cols-2">
            {results.solutions.map((s) => (
              <div key={`s${s.id}`} className="card p-4">
                <div className="flex justify-between gap-2"><Badge tone={TRUST_TONE[s.confidence_level]}>Past fix, {confidenceText(s.confidence_level)}</Badge><span className="text-xs text-meta">{pct(s.similarity)} match</span></div>
                <p className="font-semibold mt-2">{s.title}</p>
                <p className="text-sm text-body mt-1">{s.solution_description}</p>
                <p className="text-xs text-meta mt-2">{s.category} · used {s.times_used} {s.times_used === 1 ? "time" : "times"}{s.success_rate !== null ? `, worked ${pct(s.success_rate)} of the time` : ""}{s.ticket_number ? ` · from ${s.ticket_number}` : ""}</p>
              </div>
            ))}
            {results.documents.map((d) => (
              <button key={`d${d.chunk_id}`} className="card card-hover p-4 text-left" onClick={() => setParams({ doc: String(d.document_id) })}>
                <div className="flex justify-between gap-2"><Badge>Guide{d.category ? ` · ${d.category}` : ""}</Badge><span className="text-xs text-meta">{pct(d.similarity)} match</span></div>
                <p className="font-semibold mt-2">{d.title}{d.heading ? `: ${d.heading}` : ""}</p>
                <p className="text-sm text-body mt-1 line-clamp-3">{d.excerpt}</p>
              </button>
            ))}
          </div>
        </section>
      )}

      <div className={`grid grid-cols-1 gap-4 items-start ${docId ? "lg:grid-cols-[20rem_1fr]" : ""}`}>
        <section className="min-w-0">
          <SectionTitle right={
            <select className="rounded border border-line bg-surface px-2 py-1 text-sm" value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Category">
              <option value="">All categories</option>{categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>}>{docs ? `${docs.length} ${docs.length === 1 ? "article" : "articles"}` : "Articles"}</SectionTitle>
          <ErrorNote message={error} />
          {loading && !docs ? <Spinner /> : !docs?.length ? <Empty title="No articles" icon={<BookOpen className="size-5" />} /> : (
            <div className={`grid gap-4 ${docId ? "" : "md:grid-cols-2"}`}>
              {groupByCategory(docs).map(([cat, items]) => (
                <div key={cat} className="card overflow-hidden">
                  <h3 className="px-4 py-2 text-xs font-medium text-meta bg-canvas border-b border-line">{cat}</h3>
                  <ul className="divide-y divide-muted">
                    {items.map((d) => (
                      <li key={d.id}>
                        <button onClick={() => setParams({ doc: String(d.id) })}
                          className={`w-full text-left px-4 py-2.5 text-sm hover:bg-canvas ${d.id === docId ? "bg-cobalt-soft text-cobalt font-medium" : "text-ink"}`}>
                          {d.title}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </section>
        {docId && <DocViewer key={docId} id={docId} onClose={() => setParams({})} />}
      </div>
    </div>
  );
}
