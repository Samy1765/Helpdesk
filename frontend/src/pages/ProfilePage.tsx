import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { Avatar, Badge, ErrorNote, Field, KeyValue, PageHeader, shortDate, titleCase } from "../components/ui";

export default function ProfilePage() {
  const { user, refreshUser, logout } = useAuth();
  const navigate = useNavigate();
  const { data: departments } = useApi<{ id: number; name: string }[]>("/meta/departments");
  const [form, setForm] = useState({ full_name: user?.full_name || "", job_title: user?.job_title || "", location: user?.location || "", department_id: user?.department_id ?? "" });
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!user) return null;

  const save = async (e: FormEvent) => {
    e.preventDefault(); setMsg(null); setErr(null);
    try {
      await api.patch("/auth/me", { ...form, department_id: form.department_id === "" ? null : Number(form.department_id) });
      await refreshUser(); setMsg("Profile updated");
    } catch (e2) { setErr(e2 instanceof Error ? e2.message : "Failed"); }
  };
  const changePw = async (e: FormEvent) => {
    e.preventDefault(); setMsg(null); setErr(null);
    try { await api.post("/auth/change-password", pw); setPw({ current_password: "", new_password: "" }); setMsg("Password changed"); }
    catch (e2) { setErr(e2 instanceof Error ? e2.message : "Failed"); }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <PageHeader title="Profile" />
      <div className="card p-4 flex items-center gap-4">
        <Avatar name={user.full_name} />
        <div className="flex-1 min-w-0">
          <p className="font-display font-semibold">{user.full_name}</p>
          <p className="mono text-xs text-meta">{user.email}</p>
        </div>
        <Badge tone={user.role === "admin" ? "ink" : user.role === "it_support" ? "violet" : "cobalt"}>{titleCase(user.role)}</Badge>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <KeyValue k="Username" v={user.username} mono />
        <KeyValue k="Member since" v={shortDate(user.created_at)} />
      </div>
      {msg && <div className="rounded border border-ok-line bg-ok-soft px-3 py-2 text-sm text-ok-ink">{msg}</div>}
      <ErrorNote message={err} />
      <form onSubmit={save} className="card p-4 space-y-3">
        <p className="label-caps !text-ink">Details</p>
        <Field label="Full name"><input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} minLength={2} required /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Job title"><input className="input" value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} /></Field>
          <Field label="Location"><input className="input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></Field>
        </div>
        <Field label="Department"><select className="select" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
          <option value="">-</option>{departments?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></Field>
        <button className="btn-primary">Save profile</button>
      </form>
      <form onSubmit={changePw} className="card p-4 space-y-3">
        <p className="label-caps !text-ink">Change password</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Current password"><input className="input" type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} required /></Field>
          <Field label="New password"><input className="input" type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required minLength={8} /></Field>
        </div>
        <button className="btn-outline">Update password</button>
      </form>
      <button className="btn-danger w-full" onClick={async () => { await logout(); navigate("/login"); }}><LogOut className="size-4" /> Log out</button>
    </div>
  );
}
