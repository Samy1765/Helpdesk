/**
 * Chart primitives (dataviz method): validated categorical slots (#2a78d6 / #eb6834 pass CVD + contrast
 * on white), 2px lines, <=24px bars with 4px rounded data-ends, solid hairline grid, legend only for >=2
 * series, hover tooltips, and a table view for every chart so no value is color- or hover-gated.
 */
import { useState, type ReactNode } from "react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Table2, BarChart3 } from "lucide-react";

export const SERIES = ["#2a78d6", "#eb6834"];
const GRID = "#e2e8f0";
const AXIS = "#64748b";

export function ChartCard({ title, subtitle, children, table, legend }:
  { title: string; subtitle?: string; children: ReactNode; table: { columns: string[]; rows: (string | number)[][] }; legend?: { label: string; color: string }[] }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className="card">
      <div className="card-header">
        <div className="min-w-0">
          <p className="label-caps !text-ink">{title}</p>
          {subtitle && <p className="text-xs text-meta mt-0.5">{subtitle}</p>}
        </div>
        <button className="btn-ghost btn-sm" onClick={() => setAsTable((t) => !t)} aria-pressed={asTable}>
          {asTable ? <BarChart3 className="size-3.5" /> : <Table2 className="size-3.5" />} {asTable ? "Chart" : "Table"}
        </button>
      </div>
      <div className="p-4">
        {legend && legend.length > 1 && !asTable && (
          <div className="flex flex-wrap gap-4 mb-3">
            {legend.map((l) => (
              <span key={l.label} className="flex items-center gap-1.5 text-xs text-body">
                <span className="inline-block h-0.5 w-4 rounded" style={{ background: l.color }} />{l.label}
              </span>
            ))}
          </div>
        )}
        {asTable ? (
          <div className="max-h-72 overflow-auto scroll-thin">
            <table className="w-full text-sm">
              <thead><tr>{table.columns.map((c) => <th key={c} className="label-caps text-left py-1.5 pr-3 border-b border-line">{c}</th>)}</tr></thead>
              <tbody>{table.rows.map((r, i) => (
                <tr key={i} className="border-b border-muted">{r.map((v, j) => <td key={j} className={`py-1.5 pr-3 ${j ? "tabular-nums" : ""}`}>{v}</td>)}</tr>
              ))}</tbody>
            </table>
          </div>
        ) : children}
      </div>
    </section>
  );
}

function TooltipBox({ active, payload, label, fmt }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string; fmt?: (l: string) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 shadow-pop text-xs">
      <p className="font-medium text-ink mb-1">{fmt ? fmt(String(label)) : label}</p>
      {payload.map((p) => (
        <p key={p.name} className="flex items-center gap-2 text-body">
          <span className="inline-block h-0.5 w-3 rounded" style={{ background: p.color }} />{p.name}
          <span className="ml-auto pl-3 font-semibold text-ink tabular-nums">{p.value}</span>
        </p>
      ))}
    </div>
  );
}

const dayLabel = (d: string) => new Date(d + "T00:00:00").toLocaleDateString([], { month: "short", day: "numeric" });

export function TrendLines({ data, series }: { data: Record<string, string | number>[]; series: { key: string; label: string }[] }) {
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" tickFormatter={dayLabel} tick={{ fill: AXIS, fontSize: 11 }} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={24} />
          <YAxis allowDecimals={false} tick={{ fill: AXIS, fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
          <Tooltip content={<TooltipBox fmt={dayLabel} />} cursor={{ stroke: "#cbd5e1", strokeWidth: 1 }} />
          {series.map((s, i) => (
            <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={SERIES[i]} strokeWidth={2}
              dot={false} activeDot={{ r: 4, stroke: "#ffffff", strokeWidth: 2 }} strokeLinecap="round" strokeLinejoin="round" />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function GrowthArea({ data, dataKey, label }: { data: Record<string, string | number>[]; dataKey: string; label: string }) {
  return (
    <div className="h-56">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" tickFormatter={dayLabel} tick={{ fill: AXIS, fontSize: 11 }} tickLine={false} axisLine={{ stroke: GRID }} minTickGap={24} />
          <YAxis allowDecimals={false} tick={{ fill: AXIS, fontSize: 11 }} tickLine={false} axisLine={false} width={40} />
          <Tooltip content={<TooltipBox fmt={dayLabel} />} cursor={{ stroke: "#cbd5e1", strokeWidth: 1 }} />
          <Area type="monotone" dataKey={dataKey} name={label} stroke={SERIES[0]} strokeWidth={2} fill={SERIES[0]} fillOpacity={0.1}
            activeDot={{ r: 4, stroke: "#ffffff", strokeWidth: 2 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Horizontal single-series bars (one color for every bar; nominal categories are never value-ramped). */
export function BarList({ items, total, suffix }: { items: { name: string; count: number; label?: string }[]; total?: number; suffix?: string }) {
  const max = Math.max(1, ...items.map((i) => i.count));
  if (!items.length) return <p className="text-sm text-meta py-6 text-center">No data in this window.</p>;
  return (
    <ul className="space-y-2.5">
      {items.map((i) => (
        <li key={i.name} className="group" title={`${i.label || i.name}: ${i.count}${total ? ` (${Math.round((i.count / total) * 100)}%)` : ""}`}>
          <div className="flex justify-between gap-2 text-[0.8125rem] mb-1">
            <span className="text-body truncate">{i.label || i.name}</span>
            <span className="font-semibold text-ink tabular-nums">{i.count}{suffix}{total ? <span className="text-meta font-normal"> · {Math.round((i.count / total) * 100)}%</span> : null}</span>
          </div>
          <div className="h-3 w-full">
            <div className="h-full rounded-r-[4px] transition-opacity group-hover:opacity-80" style={{ width: `${(i.count / max) * 100}%`, background: SERIES[0], minWidth: 4 }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Meter: share of a whole, fill on a lighter step of the same ramp. */
export function Meter({ value, label }: { value: number; label: string }) {
  return (
    <div>
      <div className="flex justify-between text-[0.8125rem] mb-1"><span className="text-body">{label}</span><span className="font-semibold text-ink">{value}%</span></div>
      <div className="h-2 rounded-sm bg-[#cde2fb] overflow-hidden"><div className="h-full rounded-r-[4px]" style={{ width: `${Math.min(100, value)}%`, background: SERIES[0] }} /></div>
    </div>
  );
}
