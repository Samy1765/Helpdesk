import type { ReactNode } from "react";
import { CheckCircle2, LifeBuoy } from "lucide-react";

const POINTS = [
  { title: "Describe the problem in your own words", text: "The assistant asks a few questions, checks fixes that worked before and opens a ticket only when it has to." },
  { title: "One incident instead of fifty tickets", text: "When several people report the same outage, the reports are grouped so the right team fixes it once." },
  { title: "Nothing changes without your approval", text: "Restarting a service on your laptop or unlocking your account always asks you first." },
];

function Wordmark({ light }: { light?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className={`flex size-8 items-center justify-center rounded ${light ? "bg-white/10 text-white" : "bg-cobalt text-white"}`}>
        <LifeBuoy className="size-4" />
      </span>
      <span className="leading-tight">
        <span className="block font-semibold">Precision AI</span>
        <span className={`block text-xs ${light ? "text-white/60" : "text-meta"}`}>IT Helpdesk</span>
      </span>
    </div>
  );
}

export default function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="min-h-dvh grid lg:grid-cols-[1fr_28rem] xl:grid-cols-[1fr_32rem]">
      <section className="hidden lg:flex flex-col justify-between bg-cobalt-dark text-white p-10">
        <Wordmark light />
        <div className="max-w-md">
          <h1 className="text-2xl font-semibold leading-snug text-white">Get IT help without waiting in a queue.</h1>
          <ul className="mt-8 space-y-6">
            {POINTS.map(({ title: t, text }) => (
              <li key={t} className="flex gap-3">
                <CheckCircle2 className="size-5 shrink-0 text-white/70 mt-0.5" />
                <div><p className="font-medium">{t}</p><p className="text-sm text-white/70 mt-1 leading-relaxed">{text}</p></div>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-white/50">Precision AI helpdesk, version 1.0</p>
      </section>
      <section className="flex items-center justify-center p-5 sm:p-10 bg-surface">
        <div className="w-full max-w-sm">
          <div className="lg:hidden mb-8"><Wordmark /></div>
          <h2 className="text-2xl font-semibold">{title}</h2>
          <p className="text-sm text-meta mt-1 mb-6">{subtitle}</p>
          {children}
        </div>
      </section>
    </div>
  );
}
