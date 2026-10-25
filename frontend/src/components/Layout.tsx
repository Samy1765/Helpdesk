import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3, Bell, BookOpen, Headset, Home, LogOut, Menu, MessageSquare, Search, Ticket, TriangleAlert, User as UserIcon, X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { relative } from "../lib/format";
import { Avatar } from "./ui";

interface NavItem { to: string; label: string; icon: typeof Home; roles?: string[] }

const NAV: NavItem[] = [
  { to: "/dashboard", label: "Home", icon: Home },
  { to: "/chat", label: "Get help", icon: MessageSquare },
  { to: "/tickets", label: "Tickets", icon: Ticket },
  { to: "/incidents", label: "Incidents", icon: TriangleAlert },
  { to: "/knowledge-base", label: "Knowledge base", icon: BookOpen },
  { to: "/it-support", label: "Support queue", icon: Headset, roles: ["it_support", "admin"] },
  { to: "/admin", label: "Analytics & admin", icon: BarChart3, roles: ["admin"] },
];

const ROLE_LABEL: Record<string, string> = { employee: "Employee", it_support: "IT support", admin: "Administrator" };

interface Notification { id: string; type: string; message: string; created_at: string; ticket_id?: number; incident_id?: number; ticket_number?: string }

function Wordmark() {
  return (
    <Link to="/dashboard" className="flex items-center gap-2 rounded-sm">
      <svg viewBox="0 0 24 24" className="size-6 shrink-0" aria-hidden>
        <rect width="24" height="24" rx="4" fill="var(--color-brand)" />
        <path d="M7 6h6a4 4 0 0 1 0 8h-2.5v4H7V6zm3.5 3v2H13a1 1 0 0 0 0-2h-2.5z" fill="#fff" />
      </svg>
      <span className="leading-tight">
        <span className="block text-sm font-semibold text-ink">Precision</span>
        <span className="block text-xs text-meta">IT Service Desk</span>
      </span>
    </Link>
  );
}

function Notifications() {
  const [open, setOpen] = useState(false);
  const { data } = useApi<{ items: Notification[]; count: number }>("/notifications", 30000);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  useEffect(() => {
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, []);
  const count = data?.count || 0;
  return (
    <div className="relative" ref={ref}>
      <button className="btn-ghost btn-icon relative" aria-label={`Notifications, ${count} new`} aria-expanded={open}
        onClick={() => setOpen((o) => !o)}>
        <Bell className="size-5" aria-hidden />
        {count > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-crit px-1 text-xs font-medium leading-none text-white">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-12 z-50 w-96 max-w-[calc(100vw-2rem)] card shadow-pop">
          <div className="card-header"><h2 className="card-title">Notifications</h2><span className="text-xs text-meta">Last 7 days</span></div>
          <ul className="max-h-96 overflow-y-auto scroll-thin divide-y divide-line">
            {!data?.items.length && <li className="px-4 py-8 text-center text-sm text-meta">Nothing new in the last 7 days.</li>}
            {data?.items.map((n) => (
              <li key={n.id}>
                <button className="flex w-full gap-2 px-4 py-2 text-left hover:bg-canvas"
                  onClick={() => {
                    setOpen(false);
                    navigate(n.incident_id ? `/incidents?id=${n.incident_id}` : n.ticket_id ? `/tickets/${n.ticket_id}` : "/dashboard");
                  }}>
                  <span className={`dot mt-2 ${n.type === "incident" ? "bg-crit" : n.type === "approval" ? "bg-warn-dot" : "bg-brand"}`} aria-hidden />
                  <span className="min-w-0">
                    <span className="block text-sm text-ink">{n.message}</span>
                    <span className="block text-xs text-meta">{n.ticket_number ? <span className="mono">{n.ticket_number} · </span> : null}{relative(n.created_at)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function TicketSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  return (
    <form role="search" className="relative hidden w-80 md:block"
      onSubmit={(e) => { e.preventDefault(); if (q.trim()) { navigate(`/tickets?q=${encodeURIComponent(q.trim())}`); setQ(""); } }}>
      <label htmlFor="global-search" className="sr-only">Find a ticket</label>
      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-meta" aria-hidden />
      <input id="global-search" className="input py-1 pl-8" placeholder="Find a ticket by number or subject" value={q} onChange={(e) => setQ(e.target.value)} />
    </form>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const items = NAV.filter((n) => !n.roles || (user && n.roles.includes(user.role)));

  useEffect(() => setDrawer(false), [location.pathname]);

  const doLogout = async () => { await logout(); navigate("/login"); };

  const navList = (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to}
          className={({ isActive }) => `flex items-center gap-3 rounded-sm px-3 py-2 text-sm font-medium ${
            isActive ? "bg-brand-soft text-brand" : "text-body hover:bg-muted hover:text-ink"}`}>
          <Icon className="size-4" aria-hidden /> {label}
        </NavLink>
      ))}
    </nav>
  );

  const account = user && (
    <div className="flex items-center gap-2 border-t border-line p-4">
      <Avatar name={user.full_name} />
      <Link to="/profile" className="min-w-0 flex-1 rounded-sm hover:underline">
        <span className="block truncate text-sm font-medium text-ink">{user.full_name}</span>
        <span className="block truncate text-xs text-meta" title={user.department || undefined}>{ROLE_LABEL[user.role]}</span>
      </Link>
      <button className="btn-ghost btn-icon" onClick={doLogout} aria-label="Sign out" title="Sign out"><LogOut className="size-4" aria-hidden /></button>
    </div>
  );

  return (
    <div className="min-h-dvh lg:pl-60">
      <a href="#main" className="skip-link btn-primary">Skip to main content</a>

      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col border-r border-line bg-surface lg:flex">
        <div className="flex h-16 items-center border-b border-line px-4"><Wordmark /></div>
        <div className="flex-1 overflow-y-auto p-4 scroll-thin">{navList}</div>
        {account}
      </aside>

      <header className="sticky top-0 z-40 h-16 border-b border-line bg-surface">
        <div className="mx-auto flex h-full max-w-[96rem] items-center gap-2 px-4 lg:px-8">
          <button className="btn-ghost btn-icon lg:hidden" aria-label="Open menu" onClick={() => setDrawer(true)}><Menu className="size-5" aria-hidden /></button>
          <div className="lg:hidden"><Wordmark /></div>
          <TicketSearch />
          <div className="flex-1" />
          <Notifications />
          {user && (
            <Link to="/profile" className="btn-ghost btn-icon" aria-label="Your profile" title="Your profile">
              <UserIcon className="size-5" aria-hidden />
            </Link>
          )}
        </div>
      </header>

      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="absolute inset-0 bg-[rgba(24,32,47,0.4)]" onClick={() => setDrawer(false)} />
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col bg-surface shadow-pop">
            <div className="flex h-16 items-center justify-between border-b border-line px-4">
              <Wordmark />
              <button className="btn-ghost btn-icon" onClick={() => setDrawer(false)} aria-label="Close menu"><X className="size-5" aria-hidden /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">{navList}</div>
            {account}
          </div>
        </div>
      )}

      <main id="main" tabIndex={-1} className="mx-auto max-w-[96rem] px-4 py-8 outline-none lg:px-8">
        <Outlet />
      </main>
    </div>
  );
}
