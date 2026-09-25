import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { BookOpen, FileText, Loader2, Plus, Search, Sparkles, X } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import type { KnowledgeDoc, Solution } from "../services/types";
import Markdown from "../components/Markdown";
import { Badge, Empty, ErrorNote, Field, PageHeader, SectionTitle, Spinner, pct, shortDate, titleCase } from "../components/ui";

interface SearchResult {
  documents: { chunk_id: number; ref: string; document_id: number; title: string; heading: string | null; excerpt: string; similarity: number; category: string | null }[];
  solutions: Solution[];
}

const TRUST_TONE: Record<string, "ok" | "info" | "warn"> = { admin_verified: "ok", human_verified: "ok", user_confirmed: "info", ai_generated: "warn" };
const TRUST_LABEL: Record<string, string> = { admin_verified: "VERIFIED", human_verified: "HUMAN-APPROVED", user_confirmed: "USER-CONFIRMED", ai_generated: "AI-GENERATED" };

function DocViewer({ id, onClose }: { id: number; onClose: () => void }) {
  const { data, loading } = useApi<KnowledgeDoc>(`/knowledge/documents/${id}`);
  return (
    <div className="card">
      <div className="card-header">
        <span className="flex items-center gap-2 min-w-0"><FileText className="size-4 text-cobalt shrink-0" /><span className="font-display font-semibold truncate">{data?.title || "Loading"}</span></span>
        <button className="btn-ghost !p-1.5" onClick={onClose} aria-label="Close"><X className="size-4" /></button>
      </div>
      {loading || !data ? <Spinner /> : (
        <div className="p-5">
          <div className="flex flex-wrap gap-1.5 mb-3">
            <Badge tone={TRUST_TONE[data.trust_level] || "ok"} mono>{TRUST_LABEL[data.trust_level] || "VERIFIED"}</Badge>
            {data.category && <Badge>{data.category}</Badge>}
            <Badge>{titleCase(data.doc_type)}</Badge>
            <span className="mono text-xs text-meta self-center">Updated {shortDate(data.updated_at)}</span>
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
      <p className="label-caps !text-ink">New knowledge document</p>
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
      <Field label="Content (markdown)" hint="Headings split the document into retrievable chunks; numbered steps are shown to employees as procedures.">
        <textarea className="input min-h-48 mono text-[0.8125rem]" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} required minLength={20} />
      </Field>
      <ErrorNote message={error} />
      <button className="btn-accent w-full" disabled={busy}>{busy ? <Loader2 className="size-4 animate-spin" /> : "Publish & index"}</button>
    </form>
  );
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
      <PageHeader title="Knowledge base" subtitle="Verified IT procedures and solutions the agent uses - searchable by meaning, not just keywords."
        right={isStaff && <button className="btn-outline" onClick={() => setCreating((c) => !c)}><Plus className="size-4" /> New document</button>} />

      <form onSubmit={search} className="card p-3 flex gap-2 mb-5">
        <div className="relative flex-1">
          <Sparkles className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-cobalt" />
          <input className="input pl-9" placeholder="Describe a problem, e.g. 'outlook keeps crashing after update'" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <button className="btn-accent" disabled={searching}>{searching ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />} Search</button>
      </form>

      {creating && <div className="mb-5"><NewDocument onCreated={(id) => { setCreating(false); reload(); setParams({ doc: String(id) }); }} /></div>}

      {results && (
        <section className="mb-6">
          <SectionTitle right={<button className="btn-ghost btn-sm" onClick={() => setResults(null)}>Clear</button>}>Semantic matches</SectionTitle>
          {!results.documents.length && !results.solutions.length && <Empty title="No confident match">Try describing the symptom differently, or ask the AI agent.</Empty>}
          <div className="grid gap-3 md:grid-cols-2">
            {results.solutions.map((s) => (
              <div key={`s${s.id}`} className="card p-4">
                <div className="flex justify-between gap-2"><Badge tone={TRUST_TONE[s.confidence_level]} mono>{TRUST_LABEL[s.confidence_level]} SOLUTION</Badge><span className="mono text-xs text-meta">{pct(s.similarity)} match</span></div>
                <p className="font-display font-semibold mt-2">{s.title}</p>
                <p className="text-sm text-body mt-1">{s.solution_description}</p>
                <p className="mono text-[0.6875rem] text-meta mt-2">{s.category} · used {s.times_used}× · {s.success_rate !== null ? `${pct(s.success_rate)} success` : "no outcomes yet"}{s.ticket_number ? ` · from ${s.ticket_number}` : ""}</p>
              </div>
            ))}
            {results.documents.map((d) => (
              <button key={`d${d.chunk_id}`} className="card card-hover p-4 text-left" onClick={() => setParams({ doc: String(d.document_id) })}>
                <div className="flex justify-between gap-2"><Badge tone="ok" mono>DOC · {d.ref}</Badge><span className="mono text-xs text-meta">{pct(d.similarity)} match</span></div>
                <p className="font-display font-semibold mt-2">{d.title}{d.heading ? ` - ${d.heading}` : ""}</p>
                <p className="text-sm text-body mt-1 line-clamp-3">{d.excerpt}</p>
              </button>
            ))}
          </div>
        </section>
      )}

      <div className={`grid gap-4 ${docId ? "lg:grid-cols-[20rem_1fr]" : ""}`}>
        <section>
          <SectionTitle right={
            <select className="rounded border border-line bg-surface px-2 py-1 text-xs" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All</option>{categories?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>}>Documents</SectionTitle>
          <ErrorNote message={error} />
          {loading && !docs ? <Spinner /> : !docs?.length ? <Empty title="No documents" icon={<BookOpen className="size-5" />} /> : (
            <div className={`grid gap-2.5 ${docId ? "" : "sm:grid-cols-2 lg:grid-cols-3"}`}>
              {docs.map((d) => (
                <button key={d.id} onClick={() => setParams({ doc: String(d.id) })}
                  className={`card card-hover p-3.5 text-left ${d.id === docId ? "!border-cobalt ring-1 ring-cobalt" : ""}`}>
                  <span className="mono text-[0.625rem] uppercase text-meta">{d.category || "General"} · {d.doc_type}</span>
                  <p className="font-semibold text-sm leading-snug mt-0.5">{d.title}</p>
                  {!docId && <p className="text-xs text-meta mt-1 line-clamp-2">{d.excerpt}</p>}
                </button>
              ))}
            </div>
          )}
        </section>
        {docId && <DocViewer key={docId} id={docId} onClose={() => setParams({})} />}
      </div>
    </div>
  );
}
