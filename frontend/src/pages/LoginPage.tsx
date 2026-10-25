import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../services/api";
import { Field, FormError, Spinner } from "../components/ui";
import AuthShell from "./AuthShell";

const DEMO = [
  { label: "Employee", username: "johndoe", password: "Employee@123", note: "John Doe, Engineering" },
  { label: "IT support", username: "itsupport", password: "Support@123", note: "Alex Kumar, Network Team" },
  { label: "Administrator", username: "admin", password: "Admin@123", note: "Morgan Admin, Service Desk" },
];

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
      navigate((location.state as { from?: string } | null)?.from || "/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError && err.status >= 500
        ? "The service desk is not responding. Try again in a minute."
        : err instanceof Error ? err.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Sign in" subtitle="Use your company username or email address."
      footer={
        <div className="card mt-4">
          <div className="card-header">
            <h2 className="card-title">Demo sign-ins</h2>
            <span className="text-xs text-meta">Fictional data</span>
          </div>
          <ul className="divide-y divide-line">
            {DEMO.map((d) => (
              <li key={d.username}>
                <button type="button" className="flex w-full items-center justify-between gap-4 px-4 py-2 text-left hover:bg-canvas"
                  onClick={() => { setUsername(d.username); setPassword(d.password); }}>
                  <span>
                    <span className="block text-sm font-medium text-ink">{d.label}</span>
                    <span className="block text-xs text-meta">{d.note}</span>
                  </span>
                  <span className="mono text-xs text-meta">{d.username}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="border-t border-line px-4 py-2 text-xs text-meta">The other 59 employee accounts use the password Employee@123.</p>
        </div>
      }>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field label="Username or email" htmlFor="username">
          <input id="username" className="input" autoComplete="username" value={username}
            onChange={(e) => setUsername(e.target.value)} required autoFocus />
        </Field>
        <Field label="Password" htmlFor="password">
          <input id="password" className="input" type="password" autoComplete="current-password" value={password}
            onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <FormError message={error} />
        <button className="btn-primary w-full" disabled={busy || !username || !password}>
          {busy && <Spinner />} Sign in
        </button>
      </form>
      <p className="mt-4 text-sm text-meta">No account yet? <Link to="/register" className="font-medium text-brand hover:underline">Register</Link></p>
    </AuthShell>
  );
}
