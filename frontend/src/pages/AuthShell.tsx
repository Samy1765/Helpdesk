import type { ReactNode } from "react";
import { Activity, Bot, GitMerge, ShieldCheck, Terminal } from "lucide-react";

const POINTS = [
  { icon: Bot, title: "AI-first troubleshooting", text: "Describe the problem in plain words; the agent collects details and tries verified fixes." },
  { icon: GitMerge, title: "Duplicate & incident correlation", text: "Reports of the same outage are grouped, so IT fixes it once." },
  { icon: ShieldCheck, title: "Human approval for risky actions", text: "Anything that changes your device or account waits for your consent." },
];

export default function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="min-h-dvh grid lg:grid-cols-[1fr_28rem] xl:grid-cols-[1fr_32rem]">
      <section className="hidden lg:flex flex-col justify-between bg-ink text-white p-10">
        <div className="flex items-center gap-2.5">
          <span className="flex size-9 items-center justify-center rounded-md bg-cobalt"><Terminal className="size-4" strokeWidth={2.5} /></span>
          <span className="font-display text-lg font-extrabold tracking-tight">PRECISION<span className="text-[#93c5fd]">.AI</span></span>
        </div>
        <div className="max-w-lg">
          <p className="inline-flex items-center gap-2 rounded border border-white/15 px-2 py-1 font-mono text-[0.6875rem] uppercase tracking-[0.08em] text-[#93c5fd]">
            <Activity className="size-3.5" /> Autonomous IT support
          </p>
          <h1 className="mt-4 font-display text-4xl font-bold leading-tight tracking-[-0.025em] text-white">
            Fix IT issues in minutes, not tickets in queues.
          </h1>
          <div className="mt-8 space-y-5">
            {POINTS.map(({ icon: Icon, title: t, text }) => (
              <div key={t} className="flex gap-3">
                <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-white/15 bg-white/5"><Icon className="size-4 text-[#93c5fd]" /></span>
                <div><p className="font-semibold text-sm">{t}</p><p className="text-sm text-white/60 mt-0.5">{text}</p></div>
              </div>
            ))}
          </div>
        </div>
        <p className="font-mono text-[0.6875rem] text-white/40">Precision AI · Enterprise helpdesk</p>
      </section>
      <section className="flex items-center justify-center p-5 sm:p-10">
        <div className="w-full max-w-sm">
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <span className="flex size-9 items-center justify-center rounded-md bg-cobalt text-white"><Terminal className="size-4" strokeWidth={2.5} /></span>
            <span className="font-display text-lg font-extrabold tracking-tight">PRECISION<span className="text-cobalt">.AI</span></span>
          </div>
          <h2 className="text-[1.75rem] font-semibold tracking-[-0.02em]">{title}</h2>
          <p className="text-sm text-meta mt-1 mb-6">{subtitle}</p>
          {children}
        </div>
      </section>
    </div>
  );
}
