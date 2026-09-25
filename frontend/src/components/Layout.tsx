import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Bell, BookOpen, Bot, Headset, Home, LayoutGrid, LogOut, Menu, Shield, Terminal, Ticket,
  TriangleAlert, User as UserIcon, X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { useApi } from "../hooks/useApi";
import { Avatar, timeAgo } from "./ui";

interface NavItem { to: string; label: string; icon: typeof Home; roles?: string[] }

const NAV: NavItem[] = [
  { to: "/dashboard", label: "Home", icon: Home },
  { to: "/chat", label: "AI Chat", icon: Bot },
  { to: "/tickets", label: "Tickets", icon: Ticket },
  { to: "/incidents", label: "Incidents", icon: TriangleAlert },
  { to: "/knowledge-base", label: "Knowledge Base", icon: BookOpen },
  { to: "/it-support", label: "IT Support", icon: Headset, roles: ["it_support", "admin"] },
  { to: "/admin", label: "Admin Analytics", icon: Shield, roles: ["admin"] },
  { to: "/profile", label: "Profile", icon: UserIcon },
];

const SECTION: Record<string, string> = {
  dashboard: "Ops Dashboard", chat: "AI Support Agent", tickets: "Ticket Center", incidents: "Incidents",
  "knowledge-base": "Knowledge Base", "it-support": "Support Console", admin: "Admin Analytics", profile: "Profile",
};

interface Notification { id: string; type: string; message: string; created_at: string; ticket_id?: number; incident_id?: number; ticket_number?: string }

function Logo({ section }: { section: string }) {
  return (
    <Link to="/dashboard" className="flex items-center gap-2.5 min-w-0">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-cobalt text-white">
        <Terminal className="size-4" strokeWidth={2.5} />
      </span>
      <span className="min-w-0 leading-tight">
        <span className="block font-display text-[0.95rem] font-extrabold tracking-tight">PRECISION<span className="text-cobalt">.AI</span></span>
        <span className="block font-mono text-[0.625rem] uppercase tracking-[0.08em] text-meta truncate">{section}</span>
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
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const count = data?.count || 0;
  return (
    <div className="relative" ref={ref}>
      <button className="btn-ghost !p-2 relative" aria-label={`Notifications (${count})`} onClick={() => setOpen((o) => !o)}>
        <Bell className="size-5 text-ink" />
        {count > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex min-w-4 h-4 items-center justify-center rounded-full bg-crit px-1 text-[0.625rem] font-bold text-white">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-50 w-[min(22rem,calc(100vw-2rem))] card shadow-pop">
          <div className="card-header"><span className="label-caps !text-body">Alerts</span><span className="mono text-xs text-meta">{count}</span></div>
          <div className="max-h-96 overflow-y-auto scroll-thin divide-y divide-muted">
            {!data?.items.length && <p className="px-4 py-6 text-sm text-meta text-center">You're all caught up.</p>}
            {data?.items.map((n) => (
              <button key={n.id} className="w-full text-left px-4 py-2.5 hover:bg-canvas flex gap-2.5"
                onClick={() => {
                  setOpen(false);
                  navigate(n.incident_id ? `/incidents?id=${n.incident_id}` : n.ticket_id ? `/tickets/${n.ticket_id}` : "/dashboard");
                }}>
                <span className={`dot mt-1.5 shrink-0 ${n.type === "incident" ? "bg-crit" : n.type === "approval" ? "bg-warn" : "bg-cobalt"}`} />
                <span className="min-w-0">
                  <span className="block text-sm text-body leading-snug">{n.message}</span>
                  <span className="block mono text-[0.6875rem] text-meta mt-0.5">{n.ticket_number ? `${n.ticket_number} · ` : ""}{timeAgo(n.created_at)}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const items = NAV.filter((n) => !n.roles || (user && n.roles.includes(user.role)));
  const section = SECTION[location.pathname.split("/")[1]] || "Ops Dashboard";

  useEffect(() => setDrawer(false), [location.pathname]);

  const navList = (
    <nav className="flex flex-col gap-0.5">
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink key={to} to={to}
          className={({ isActive }) => `flex items-center gap-3 rounded px-3 py-2 text-sm font-medium transition-colors ${
            isActive ? "bg-cobalt-soft text-cobalt" : "text-body hover:bg-muted hover:text-ink"}`}>
          <Icon className="size-4" /> {label}
        </NavLink>
      ))}
    </nav>
  );

  const doLogout = async () => { await logout(); navigate("/login"); };

  return (
    <div className="min-h-dvh lg:pl-60">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-60 flex-col border-r border-line bg-surface">
        <div className="h-16 flex items-center px-4 border-b border-line"><Logo section="IT Automated Support" /></div>
        <div className="flex-1 overflow-y-auto p-3 scroll-thin">
          <p className="label-caps px-3 mb-2">Workspace</p>
          {navList}
        </div>
        {user && (
          <div className="border-t border-line p-3 flex items-center gap-2.5">
            <Avatar name={user.full_name} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium truncate">{user.full_name}</p>
              <p className="mono text-[0.6875rem] text-meta uppercase">{user.role.replace("_", " ")}</p>
            </div>
            <button className="btn-ghost !p-2" onClick={doLogout} aria-label="Log out"><LogOut className="size-4" /></button>
          </div>
        )}
      </aside>

      {/* Top bar */}
      <header className="sticky top-0 z-40 h-16 border-b border-line bg-surface/95 backdrop-blur">
        <div className="h-full mx-auto max-w-6xl flex items-center gap-3 px-4">
          <button className="btn-ghost !p-2 lg:hidden -ml-2" aria-label="Menu" onClick={() => setDrawer(true)}><Menu className="size-5 text-ink" /></button>
          <div className="lg:hidden min-w-0"><Logo section={section} /></div>
          <div className="hidden lg:block">
            <p className="font-mono text-[0.6875rem] uppercase tracking-[0.08em] text-meta">{section}</p>
          </div>
          <div className="flex-1" />
          <Notifications />
          {user && <Link to="/profile" aria-label="Profile"><Avatar name={user.full_name} /></Link>}
        </div>
      </header>

      {/* Mobile drawer */}
      {drawer && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-[rgba(15,23,42,0.4)]" onClick={() => setDrawer(false)} />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] bg-surface shadow-modal flex flex-col">
            <div className="h-16 flex items-center justify-between px-4 border-b border-line">
              <Logo section={section} />
              <button className="btn-ghost !p-2" onClick={() => setDrawer(false)} aria-label="Close menu"><X className="size-5" /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-3">{navList}</div>
            <button className="m-3 btn-outline" onClick={doLogout}><LogOut className="size-4" /> Log out</button>
          </div>
        </div>
      )}

      <main className="mx-auto max-w-6xl px-4 py-5 pb-28 lg:pb-10">
        <Outlet />
      </main>

      {/* Mobile bottom tab bar */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-40 border-t border-line bg-surface/95 backdrop-blur pb-[env(safe-area-inset-bottom)]">
        <div className="grid grid-cols-5">
          {[NAV[0], NAV[1], NAV[2], NAV[3]].map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) =>
              `flex flex-col items-center gap-1 py-2.5 text-[0.625rem] font-semibold uppercase tracking-[0.06em] ${isActive ? "text-cobalt" : "text-meta"}`}>
              <Icon className="size-5" /> {label}
            </NavLink>
          ))}
          <button onClick={() => setDrawer(true)} className="flex flex-col items-center gap-1 py-2.5 text-[0.625rem] font-semibold uppercase tracking-[0.06em] text-meta">
            <LayoutGrid className="size-5" /> More
          </button>
        </div>
      </nav>
    </div>
  );
}
