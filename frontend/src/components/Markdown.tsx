import { Fragment, type ReactNode } from "react";

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i} className="font-semibold text-ink">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i} className="code-chip">{part.slice(1, -1)}</code>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

/** Minimal markdown (headings, ordered/unordered lists, paragraphs). Output is React nodes only - no HTML injection. */
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
        : <h3 key={i} className="text-[1.0625rem] font-semibold mt-5 mb-2">{inline(h[2])}</h3>);
      i++;
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
        <ol key={i} className="space-y-1.5 my-2">
          {items.map((it, k) => (
            <li key={k} className="flex gap-2.5 text-sm text-body"><span className="mono text-cobalt font-semibold">{String(k + 1).padStart(2, "0")}</span><span>{inline(it)}</span></li>
          ))}
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
