/* Code fence meta for the docs: ```python title="train.py" {3,5-7}
   puts the title on <pre data-title> and wraps each source line in a span,
   marking the listed lines with data-highlight. Runs after rehype-highlight,
   whose token spans can cross a newline, so lines are rebuilt from a flat list
   of (text, classes) runs. */

const parseMeta = (meta) => {
  const title = /title="([^"]+)"/.exec(meta)?.[1];
  const ranges = /\{([\d,\s-]+)\}/.exec(meta)?.[1];
  const lines = new Set();

  for (const part of (ranges ?? "").split(",")) {
    const [from, to] = part.trim().split("-").map(Number);
    if (!from) continue;
    for (let line = from; line <= (to || from); line += 1) lines.add(line);
  }

  return { title, lines };
};

const flatten = (nodes, classes, out) => {
  for (const node of nodes) {
    if (node.type === "text") out.push({ text: node.value, classes });
    else if (node.type === "element") {
      const own = node.properties?.className ?? [];
      flatten(node.children ?? [], [...classes, ...own], out);
    }
  }
  return out;
};

const toLines = (runs) => {
  const lines = [[]];
  for (const run of runs) {
    const parts = run.text.split("\n");
    parts.forEach((part, index) => {
      if (index > 0) lines.push([]);
      if (part)
        lines[lines.length - 1].push({ text: part, classes: run.classes });
    });
  }
  if (lines.length > 1 && lines[lines.length - 1].length === 0) lines.pop();
  return lines;
};

const visit = (node, fn) => {
  fn(node);
  for (const child of node.children ?? []) visit(child, fn);
};

const rehypeDocsCodeMeta = () => (tree) => {
  visit(tree, (pre) => {
    if (pre.type !== "element" || pre.tagName !== "pre") return;

    const code = pre.children?.find(
      (child) => child.type === "element" && child.tagName === "code",
    );
    const meta = code?.data?.meta ?? code?.properties?.metastring;
    if (!code || !meta) return;

    const { title, lines } = parseMeta(meta);
    if (title) pre.properties = { ...pre.properties, dataTitle: title };
    if (lines.size === 0) return;

    pre.properties = { ...pre.properties, dataHighlights: "" };
    code.children = toLines(flatten(code.children, [], [])).map(
      (runs, index) => ({
        type: "element",
        tagName: "span",
        properties: {
          className: ["gr-line"],
          ...(lines.has(index + 1) ? { dataHighlight: "" } : {}),
        },
        children: [
          ...runs.map((run) =>
            run.classes.length
              ? {
                  type: "element",
                  tagName: "span",
                  properties: { className: run.classes },
                  children: [{ type: "text", value: run.text }],
                }
              : { type: "text", value: run.text },
          ),
          { type: "text", value: "\n" },
        ],
      }),
    );
  });
};

module.exports = { parseMeta, rehypeDocsCodeMeta };
