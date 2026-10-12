import { readFileSync, writeFileSync, watch } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const input = process.argv.indexOf("--source");
if (input === -1 || !process.argv[input + 1]) {
  throw new Error("Provide --source with the path to the draft's script.md.");
}
const source = resolve(process.argv[input + 1]);
const destination = fileURLToPath(
  new URL("../content/articles/sand/script.md", import.meta.url),
);
const entry = fileURLToPath(
  new URL(
    "../content/articles/how-to-get-an-answer-out-of-sand.mdx",
    import.meta.url,
  ),
);
const sync = () => {
  const draftText = readFileSync(source, "utf8").replace(
    /^> \*\*Visual cue(?:\s|:|\*\*)[^\n]*(?:\n>[^\n]*)*(?:\n|$)/gm,
    "",
  );
  const text = draftText.replace(/\n{3,}/g, "\n\n");
  const title = text.match(/^# (.+)$/m)?.[1];
  if (!title) throw new Error("The working draft needs its article title.");
  const previousEntry = readFileSync(entry, "utf8");
  const nextEntry = previousEntry.replace(
    /^title: .*$/m,
    `title: ${JSON.stringify(title)}`,
  );
  if (previousEntry !== nextEntry) writeFileSync(entry, nextEntry);
  if (readFileSync(destination, "utf8") !== text) {
    writeFileSync(destination, text);
    console.log("Updated the website's sand article from the working draft.");
  }
};
sync();
if (process.argv.includes("--watch")) {
  let timer;
  watch(resolve(source, ".."), () => {
    clearTimeout(timer);
    timer = setTimeout(sync, 150);
  });
  console.log("Watching the working draft for changes.");
}
