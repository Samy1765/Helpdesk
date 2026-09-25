import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { ErrorNote, Field } from "../components/ui";
import AuthShell from "./AuthShell";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const { data: departments } = useApi<{ id: number; name: string; is_support_team: boolean }[]>("/meta/departments");
  const [form, setForm] = useState({ full_name: "", email: "", username: "", password: "", department_id: "", job_title: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await register({ ...form, department_id: form.department_id ? Number(form.department_id) : null, job_title: form.job_title || undefined });
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Create account" subtitle="Employee accounts can chat with the agent and track their tickets.">
      <form onSubmit={submit} className="space-y-3.5">
        <Field label="Full name"><input className="input" value={form.full_name} onChange={set("full_name")} required minLength={2} /></Field>
        <Field label="Work email"><input className="input" type="email" value={form.email} onChange={set("email")} required /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Username"><input className="input" value={form.username} onChange={set("username")} required minLength={3} pattern="[A-Za-z0-9_.]+" /></Field>
          <Field label="Department">
            <select className="select" value={form.department_id} onChange={set("department_id")}>
              <option value="">-</option>
              {departments?.filter((d) => !d.is_support_team).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Job title (optional)"><input className="input" value={form.job_title} onChange={set("job_title")} /></Field>
        <Field label="Password" hint="At least 8 characters with upper-case, lower-case and a digit.">
          <input className="input" type="password" autoComplete="new-password" value={form.password} onChange={set("password")} required minLength={8} />
        </Field>
        <ErrorNote message={error} />
        <button className="btn-accent w-full" disabled={busy}>{busy ? <Loader2 className="size-4 animate-spin" /> : "Create account"}</button>
      </form>
      <p className="text-sm text-meta mt-5">Already registered? <Link to="/login" className="text-cobalt font-medium hover:underline">Sign in</Link></p>
    </AuthShell>
  );
}
