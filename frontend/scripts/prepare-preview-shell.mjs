// Keep Vite's development HTML ordinary. The production shell is assembled by
// nginx SSI, using the same built scripts/styles and a backend metadata fragment.
import { readFile, writeFile } from "node:fs/promises";
import { URL } from "node:url";

const file = new URL("../dist/index.html", import.meta.url);
const html = await readFile(file, "utf8");
const marker = /<!-- preview:start -->([\s\S]*?)<!-- preview:end -->/;
if (!marker.test(html)) throw new Error("Missing preview metadata block");
await writeFile(
  file,
  html.replace(
    marker,
    (_, fallback) =>
      `<!--# block name="preview_fallback" -->${fallback}<!--# endblock -->\n` +
      '<!--# include virtual="/__preview/$preview_id/head" stub="preview_fallback" -->',
  ),
);
