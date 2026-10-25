import { Fragment, type ReactNode } from "react";

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|https:\/\/[^\s)]+)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i} className="font-semibold text-ink">{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i} className="rounded-sm bg-muted px-1 font-mono text-xs">{part.slice(1, -1)}</code>;
    if (part.startsWith("https://")) return <span key={i} className="font-mono text-xs text-ink">{part}</span>;
    return <Fragment key={i}>{part}</Fragment>;
  });
}

/** Minimal markdown (headings, ordered/unordered lists, paragraphs). Output is React nodes only - no HTML injection.
 *  Level-1 headings are skipped: the page already shows the document title. */
export default function Markdown({ source }: { source: string }) {
  const blocks: ReactNode[] = [];
  const lines = source.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) {
      if (h[1].length > 1) blocks.push(<h3 key={i} className="mb-2 mt-6 text-base font-semibold text-ink first:mt-0">{inline(h[2])}</h3>);
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
        <ol key={i} className="my-2 space-y-2">
          {items.map((it, k) => (
            <li key={k} className="flex gap-2 text-sm text-body"><span className="mono w-4 shrink-0 text-right text-meta">{k + 1}.</span><span>{inline(it)}</span></li>
          ))}
        </ol>
      ) : (
        <ul key={i} className="my-2 list-disc space-y-1 pl-6 text-sm text-body">{items.map((it, k) => <li key={k}>{inline(it)}</li>)}</ul>
      ));
      continue;
    }
    if (line.trim()) {
      const para: string[] = [];
      while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*\d+[.)]\s|\s*[-*]\s)/.test(lines[i])) { para.push(lines[i]); i++; }
      blocks.push(<p key={i} className="my-2 text-sm text-body">{inline(para.join(" "))}</p>);
      continue;
    }
    i++;
  }
  return <div>{blocks}</div>;
}
