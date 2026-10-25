import { Fragment, type ReactNode } from "react";

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i} className="font-semibold text-ink">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i} className="code-chip">{part.slice(1, -1)}</code>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

const cells = (row: string) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

/** Minimal markdown (headings, lists, tables, paragraphs). Output is React nodes only - no HTML injection. */
export default function Markdown({ source }: { source: string }) {
  const blocks: ReactNode[] = [];
  const lines = source.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) {
      const level = h[1].length;
      blocks.push(level <= 1
        ? <h2 key={i} className="text-xl font-semibold mt-2 mb-2">{inline(h[2])}</h2>
        : <h3 key={i} className="text-base font-semibold mt-5 mb-2">{inline(h[2])}</h3>);
      i++;
      continue;
    }
    if (/^\s*\|/.test(line) && i + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1])) {
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(cells(lines[i])); i++; }
      blocks.push(
        <div key={i} className="my-3 overflow-x-auto">
          <table className="w-full text-sm border border-line">
            <thead><tr>{head.map((h, k) => <th key={k} className="th">{inline(h)}</th>)}</tr></thead>
            <tbody className="divide-y divide-muted">
              {rows.map((r, k) => <tr key={k}>{r.map((c, j) => <td key={j} className="px-3 py-2 text-body align-top">{inline(c)}</td>)}</tr>)}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line) || /^\s*[-*]\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const items: string[] = [];
      while (i < lines.length && (ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*]\s+/).test(lines[i])) {
        items.push(lines[i].replace(/^\s*(\d+[.)]|[-*])\s+/, ""));
        i++;
      }
      blocks.push(ordered ? (
        <ol key={i} className="list-decimal pl-5 space-y-1.5 my-2 text-sm text-body marker:text-meta">
          {items.map((it, k) => <li key={k} className="pl-1">{inline(it)}</li>)}
        </ol>
      ) : (
        <ul key={i} className="list-disc pl-5 space-y-1 my-2 text-sm text-body">{items.map((it, k) => <li key={k}>{inline(it)}</li>)}</ul>
      ));
      continue;
    }
    if (line.trim()) {
      const para: string[] = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*\d+[.)]\s|\s*[-*]\s)/.test(lines[i])) { para.push(lines[i]); i++; }
      blocks.push(<p key={i} className="text-sm text-body leading-relaxed my-2">{inline(para.join(" "))}</p>);
      continue;
    }
    i++;
  }
  return <div>{blocks}</div>;
}
