import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { Avatar, Card, DefinitionList, Field, FormError, Notice, PageHeader, Spinner } from "../components/ui";
import { date, relative } from "../lib/format";

const ROLE_LABEL: Record<string, string> = { employee: "Employee", it_support: "IT support", admin: "Administrator" };

export default function ProfilePage() {
  const { user, refreshUser, logout, changePassword } = useAuth();
  const navigate = useNavigate();
  const { data: departments } = useApi<{ id: number; name: string; is_support_team: boolean }[]>("/meta/departments");
  const [form, setForm] = useState({ full_name: user?.full_name || "", job_title: user?.job_title || "", location: user?.location || "", department_id: user?.department_id ?? "" });
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pwMsg, setPwMsg] = useState<string | null>(null);
  const [pwErr, setPwErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<"profile" | "password" | null>(null);
  if (!user) return null;
  const employee = user.role === "employee";

  const save = async (e: FormEvent) => {
    e.preventDefault(); setMsg(null); setErr(null); setBusy("profile");
    try {
      const body: Record<string, unknown> = { full_name: form.full_name, job_title: form.job_title, location: form.location };
      if (employee) body.department_id = form.department_id === "" ? null : Number(form.department_id);
      await api.patch("/auth/me", body);
      await refreshUser(); setMsg("Profile saved.");
    } catch (e2) { setErr(e2 instanceof Error ? e2.message : "Saving failed"); } finally { setBusy(null); }
  };
  const changePw = async (e: FormEvent) => {
    e.preventDefault(); setPwMsg(null); setPwErr(null); setBusy("password");
    try { await changePassword(pw.current_password, pw.new_password); setPw({ current_password: "", new_password: "" }); setPwMsg("Password changed. You have been signed out on your other devices."); }
    catch (e2) { setPwErr(e2 instanceof Error ? e2.message : "Password change failed"); } finally { setBusy(null); }
  };

  return (
    <div className="max-w-3xl">
      <PageHeader title="Profile" />
      <div className="space-y-6">
        <Card>
          <div className="flex flex-wrap items-center gap-4">
            <Avatar name={user.full_name} />
            <div className="min-w-0 flex-1">
              <p className="text-base font-semibold text-ink">{user.full_name}</p>
              <p className="text-sm text-meta">{user.email}</p>
            </div>
          </div>
          <div className="mt-4 border-t border-line pt-4">
            <DefinitionList items={[
              ["Username", <span className="mono">{user.username}</span>],
              ["Role", ROLE_LABEL[user.role]],
              ["Department or team", user.department || "-"],
              ["Member since", date(user.created_at)],
              ["Last sign-in", user.last_login_at ? relative(user.last_login_at) : "-"],
            ]} />
          </div>
        </Card>

        <Card title="Your details">
          <form onSubmit={save} className="space-y-4">
            <Field label="Full name" htmlFor="p-name"><input id="p-name" className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} minLength={2} required autoComplete="name" /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Job title" htmlFor="p-title"><input id="p-title" className="input" value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} /></Field>
              <Field label="Location" htmlFor="p-location"><input id="p-location" className="input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></Field>
            </div>
            {employee ? (
              <Field label="Department" htmlFor="p-dept">
                <select id="p-dept" className="select" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>
                  <option value="">Not set</option>{departments?.filter((d) => !d.is_support_team).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </Field>
            ) : <p className="text-sm text-meta">Your IT team is set by an administrator.</p>}
            {msg && <Notice tone="ok">{msg}</Notice>}
            <FormError message={err} />
            <button className="btn-primary" disabled={busy !== null}>{busy === "profile" && <Spinner />} Save details</button>
          </form>
        </Card>

        <Card title="Password">
          <form onSubmit={changePw} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Current password" htmlFor="p-current"><input id="p-current" className="input" type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} required /></Field>
              <Field label="New password" htmlFor="p-new" hint="At least 8 characters with an upper-case letter, a lower-case letter and a number.">
                <input id="p-new" className="input" type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required minLength={8} />
              </Field>
            </div>
            {pwMsg && <Notice tone="ok">{pwMsg}</Notice>}
            <FormError message={pwErr} />
            <button className="btn-secondary" disabled={busy !== null}>{busy === "password" && <Spinner />} Change password</button>
          </form>
        </Card>

        <button className="btn-danger" onClick={async () => { await logout(); navigate("/login"); }}><LogOut className="size-4" aria-hidden /> Sign out</button>
      </div>
    </div>
  );
}
