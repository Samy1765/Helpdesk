/**
 * Chart primitives. Categorical slots #1e5aa8 / #c05f12 pass the CVD, normal-vision and contrast checks on the
 * white surface (dataviz validator). 2px lines, bars with 4px data-ends, recessive grid, a legend whenever there
 * are two series, hover tooltips, and a table view on every chart so no value depends on colour or hover alone.
 * Status colours (met / breached) are reserved for status and always carry a text label.
 */
import { useState, type ReactNode } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, Area, AreaChart } from "recharts";
import { BarChart3, Table2 } from "lucide-react";
import { day } from "../lib/format";

export const SERIES = ["#1e5aa8", "#c05f12"];
const GRID = "#e2e5ea";
const AXIS = "#5b6474";

export function ChartCard({ title, description, children, table, legend }:
  { title: string; description?: string; children: ReactNode; table: { columns: string[]; rows: (string | number)[][] }; legend?: { label: string; color: string }[] }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className="card" aria-label={title}>
      <div className="card-header">
        <div className="min-w-0">
          <h2 className="card-title">{title}</h2>
          {description && <p className="text-xs text-meta">{description}</p>}
        </div>
        <button className="btn-ghost btn-sm" onClick={() => setAsTable((t) => !t)} aria-pressed={asTable}>
          {asTable ? <BarChart3 className="size-4" aria-hidden /> : <Table2 className="size-4" aria-hidden />} {asTable ? "Chart" : "Table"}
        </button>
      </div>
      <div className="p-4">
        {legend && legend.length > 1 && !asTable && (
          <ul className="mb-2 flex flex-wrap gap-4" aria-label="Legend">
            {legend.map((l) => (
              <li key={l.label} className="flex items-center gap-2 text-xs text-body">
                <span className="inline-block h-1 w-4 rounded-sm" style={{ background: l.color }} aria-hidden />{l.label}
              </li>
            ))}
          </ul>
        )}
        {asTable ? (
          <div className="max-h-72 overflow-auto scroll-thin" tabIndex={0} role="region" aria-label={`${title} data`}>
            <table className="w-full text-sm">
              <thead><tr>{table.columns.map((c, j) => <th key={c} className={`th border-b border-line px-0 pr-4 ${j ? "text-right" : ""}`}>{c}</th>)}</tr></thead>
              <tbody>{table.rows.map((r, i) => (
                <tr key={i} className="border-b border-line">{r.map((v, j) => <td key={j} className={`py-1 pr-4 ${j ? "text-right tabular-nums" : ""}`}>{v}</td>)}</tr>
              ))}</tbody>
            </table>
          </div>
        ) : children}
      </div>
    </section>
  );
}

function TooltipBox({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="card px-3 py-2 text-xs shadow-pop">
      <p className="mb-1 font-medium text-ink">{label ? day(String(label)) : ""}</p>
      {payload.map((p) => (
        <p key={p.name} className="flex items-center gap-2 text-body">
          <span className="inline-block h-1 w-3 rounded-sm" style={{ background: p.color }} aria-hidden />{p.name}
          <span className="ml-auto pl-4 font-medium text-ink tabular-nums">{p.value}</span>
        </p>
      ))}
    </div>
  );
}

const axisProps = { tick: { fill: AXIS, fontSize: 12 }, tickLine: false } as const;

export function TrendLines({ data, series }: { data: Record<string, string | number>[]; series: { key: string; label: string }[] }) {
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" tickFormatter={day} {...axisProps} axisLine={{ stroke: GRID }} minTickGap={32} />
          <YAxis allowDecimals={false} {...axisProps} axisLine={false} width={40} />
          <Tooltip content={<TooltipBox />} cursor={{ stroke: "#cdd2da", strokeWidth: 1 }} />
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
        <AreaChart data={data} margin={{ top: 8, right: 16, left: -16, bottom: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="date" tickFormatter={day} {...axisProps} axisLine={{ stroke: GRID }} minTickGap={32} />
          <YAxis allowDecimals={false} {...axisProps} axisLine={false} width={40} />
          <Tooltip content={<TooltipBox />} cursor={{ stroke: "#cdd2da", strokeWidth: 1 }} />
          <Area type="monotone" dataKey={dataKey} name={label} stroke={SERIES[0]} strokeWidth={2} fill={SERIES[0]} fillOpacity={0.08}
            activeDot={{ r: 4, stroke: "#ffffff", strokeWidth: 2 }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Horizontal single-series bars (one colour for every bar; nominal categories are never value-ramped). */
export function BarList({ items, total, suffix }: { items: { name: string; count: number; label?: string }[]; total?: number; suffix?: string }) {
  const max = Math.max(1, ...items.map((i) => i.count));
  if (!items.length) return <p className="py-8 text-center text-sm text-meta">No data for this period.</p>;
  return (
    <ul className="space-y-2">
      {items.map((i) => (
        <li key={i.name} title={`${i.label || i.name}: ${i.count}${total ? ` (${Math.round((i.count / total) * 100)}%)` : ""}`}>
          <div className="mb-1 flex justify-between gap-2 text-sm">
            <span className="truncate text-body">{i.label || i.name}</span>
            <span className="font-medium text-ink tabular-nums">{i.count}{suffix}{total ? <span className="font-normal text-meta"> · {Math.round((i.count / total) * 100)}%</span> : null}</span>
          </div>
          <div className="h-2 w-full">
            <div className="h-full rounded-r-sm" style={{ width: `${(i.count / max) * 100}%`, background: SERIES[0], minWidth: 4 }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Met / breached split for one SLA row: status colours with a text label, 2px gap between the segments. */
export function SplitBar({ met, breached, label }: { met: number; breached: number; label: string }) {
  const total = met + breached;
  const pct = total ? (met / total) * 100 : 0;
  return (
    <div>
      <div className="mb-1 flex justify-between gap-2 text-sm">
        <span className="text-body">{label}</span>
        <span className="font-medium text-ink tabular-nums">{total ? `${Math.round(pct)}%` : "-"}<span className="font-normal text-meta"> · {met} met, {breached} breached</span></span>
      </div>
      <div className="flex h-2 w-full gap-0.5" aria-hidden>
        {met > 0 && <div className="h-full rounded-l-sm bg-ok-dot" style={{ width: `${pct}%` }} />}
        {breached > 0 && <div className="h-full rounded-r-sm bg-crit" style={{ width: `${100 - pct}%` }} />}
        {!total && <div className="h-full w-full rounded-sm bg-muted" />}
      </div>
    </div>
  );
}

/** Share of a whole on a lighter step of the same ramp. */
export function Meter({ value, label }: { value: number; label: string }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm"><span className="text-body">{label}</span><span className="font-medium text-ink tabular-nums">{value}%</span></div>
      <div className="h-2 overflow-hidden rounded-sm bg-brand-soft"><div className="h-full rounded-r-sm" style={{ width: `${Math.min(100, value)}%`, background: SERIES[0] }} /></div>
    </div>
  );
}
