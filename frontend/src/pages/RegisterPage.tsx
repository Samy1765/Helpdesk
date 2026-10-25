import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { Field, FormError, Spinner } from "../components/ui";
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
    <AuthShell title="Create an account" subtitle="For employees. IT support and admin access is granted by an administrator.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Full name" htmlFor="full_name"><input id="full_name" className="input" value={form.full_name} onChange={set("full_name")} required minLength={2} autoComplete="name" /></Field>
        <Field label="Work email" htmlFor="email"><input id="email" className="input" type="email" value={form.email} onChange={set("email")} required autoComplete="email" /></Field>
        <Field label="Username" htmlFor="username" hint="Letters, numbers, dots and underscores.">
          <input id="username" className="input" value={form.username} onChange={set("username")} required minLength={3} pattern="[A-Za-z0-9_.]+" autoComplete="username" />
        </Field>
        <Field label="Department" htmlFor="department">
          <select id="department" className="select" value={form.department_id} onChange={set("department_id")}>
            <option value="">Choose your department</option>
            {departments?.filter((d) => !d.is_support_team).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </Field>
        <Field label="Job title (optional)" htmlFor="job_title"><input id="job_title" className="input" value={form.job_title} onChange={set("job_title")} autoComplete="organization-title" /></Field>
        <Field label="Password" htmlFor="password" hint="At least 8 characters, with an upper-case letter, a lower-case letter and a number.">
          <input id="password" className="input" type="password" autoComplete="new-password" value={form.password} onChange={set("password")} required minLength={8} />
        </Field>
        <FormError message={error} />
        <button className="btn-primary w-full" disabled={busy}>{busy && <Spinner />} Create account</button>
      </form>
      <p className="mt-4 text-sm text-meta">Already registered? <Link to="/login" className="font-medium text-brand hover:underline">Sign in</Link></p>
    </AuthShell>
  );
}
