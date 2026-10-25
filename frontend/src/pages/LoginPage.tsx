import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { ErrorNote, Field } from "../components/ui";
import AuthShell from "./AuthShell";

const DEMO = [
  { label: "Employee", who: "Amit Sharma, Engineering", username: "asharma", password: "Employee@123" },
  { label: "IT support agent", who: "Rohit Kumar, Network Team", username: "itsupport", password: "Support@123" },
  { label: "Administrator", who: "Vandana Iyer, IT Operations", username: "admin", password: "Admin@123" },
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
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Sign in" subtitle="Use your company username or email address.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Username or email">
          <input className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
        </Field>
        <Field label="Password">
          <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <ErrorNote message={error} />
        <button className="btn-accent w-full" disabled={busy}>
          {busy ? <Loader2 className="size-4 animate-spin" /> : "Sign in"}
        </button>
      </form>
      <p className="text-sm text-meta mt-5">New here? <Link to="/register" className="text-cobalt font-medium hover:underline">Create an account</Link></p>

      <div className="mt-8 border-t border-line pt-5">
        <p className="text-sm font-medium">Demo accounts</p>
        <p className="text-xs text-meta mt-0.5 mb-2">Sample data for this demonstration. Select one to fill in the form.</p>
        <div className="grid gap-1">
          {DEMO.map((d) => (
            <button key={d.username} type="button" className="flex items-center justify-between gap-3 rounded border border-line px-3 py-2 text-left hover:bg-canvas hover:border-line-strong"
              onClick={() => { setUsername(d.username); setPassword(d.password); }}>
              <span className="min-w-0">
                <span className="block text-sm font-medium">{d.label}</span>
                <span className="block text-xs text-meta truncate">{d.who}</span>
              </span>
              <span className="mono text-xs text-meta">{d.username}</span>
            </button>
          ))}
        </div>
      </div>
    </AuthShell>
  );
}
