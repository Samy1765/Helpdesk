import type { ReactNode } from "react";

export default function AuthShell({ title, subtitle, children, footer }:
  { title: string; subtitle: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 py-12">
      <main className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2">
          <svg viewBox="0 0 24 24" className="size-8" aria-hidden>
            <rect width="24" height="24" rx="4" fill="var(--color-brand)" />
            <path d="M7 6h6a4 4 0 0 1 0 8h-2.5v4H7V6zm3.5 3v2H13a1 1 0 0 0 0-2h-2.5z" fill="#fff" />
          </svg>
          <span className="leading-tight">
            <span className="block text-base font-semibold text-ink">Precision</span>
            <span className="block text-xs text-meta">IT Service Desk</span>
          </span>
        </div>
        <div className="card p-6">
          <h1 className="text-xl">{title}</h1>
          <p className="mb-6 mt-1 text-sm text-meta">{subtitle}</p>
          {children}
        </div>
        {footer}
      </main>
    </div>
  );
}
