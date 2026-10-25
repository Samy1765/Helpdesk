// Design guard: fails when source code steps outside the design system (run in CI with `npm run lint:design`).
//   - one type scale: no arbitrary font sizes (text-[...])
//   - 4/8 px spacing: no half-step spacing classes (p-1.5, gap-2.5, ...)
//   - restrained surfaces: no gradients, blur/glow, large radii, heavy weights or pulsing decoration
//   - plain copy: no emoji and no marketing slogans in the interface
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = fileURLToPath(new URL("../src/", import.meta.url));
const RULES = [
  [/text-\[[^\]]*\]/, "arbitrary font size; use text-xs/sm/base/lg/xl/2xl"],
  [/\b-?(?:p[xytblr]?|m[xytblr]?|gap(?:-[xy])?|space-[xy]|top|left|right|bottom|inset|size|[wh]|min-[wh])-\d+\.5\b/, "half-step spacing; use the 4/8 px scale"],
  [/gradient/, "gradient"],
  [/\bblur\b|backdrop-blur|drop-shadow|glow/, "blur or glow effect"],
  [/rounded-(?:lg|xl|2xl|3xl)\b/, "radius above 6 px"],
  [/font-(?:bold|extrabold|black)\b/, "weight above 600"],
  [/animate-(?:pulse|bounce|ping)\b/, "decorative animation"],
  [/\p{Extended_Pictographic}/u, "emoji"],
  [/\b(?:AI-powered|revolutioni[sz]e|seamless|cutting-edge|next-gen|supercharge|magic)\b/i, "marketing copy"],
];
// The dataviz spec asks for a 2 px surface gap between adjacent fills
const ALLOW = [{ file: "components/charts.tsx", pattern: /\bgap-0\.5\b/ }];

function* files(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* files(p);
    else if (/\.(tsx?|css)$/.test(name)) yield p;
  }
}

const problems = [];
for (const file of files(ROOT)) {
  const rel = relative(ROOT, file).replace(/\\/g, "/");
  readFileSync(file, "utf8").split("\n").forEach((line, i) => {
    for (const [re, why] of RULES) {
      const m = line.match(re);
      if (m && !ALLOW.some((a) => a.file === rel && a.pattern.test(m[0]))) problems.push(`${rel}:${i + 1}  ${why}: ${m[0]}`);
    }
  });
}
if (problems.length) {
  console.error(`Design check failed (${problems.length}):\n` + problems.join("\n"));
  process.exit(1);
}
console.log("Design check passed.");
