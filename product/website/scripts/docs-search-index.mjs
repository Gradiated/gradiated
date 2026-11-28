/* The docs search index: one entry per page section (its h2 or h3), plus the
   entries the generated pages hand over (endpoints, error codes, releases).
   Written to /docs/search.json and fetched the first time a reader searches. */

const slugify = (value) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");

const plain = (markdown) =>
  markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[`*_|>#]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const MAX_TEXT = 1500;

const sectionsOf = (source) => {
  const sections = [];
  let current = { heading: null, lines: [] };
  let fenced = false;

  for (const line of source.split("\n")) {
    if (line.startsWith("```")) fenced = !fenced;
    const match =
      !fenced &&
      (/^(##|###) (.+)$/.exec(line) ??
        /^<(DocsStep) title="([^"]+)">/.exec(line));
    if (match) {
      sections.push(current);
      current = { heading: plain(match[2]), lines: [] };
    } else if (!line.startsWith("# ")) {
      current.lines.push(line);
    }
  }
  sections.push(current);
  return sections;
};

export const buildSearchIndex = (pages, generated) => {
  const generatedPages = new Set(
    generated.entries.map((entry) => entry.path.split("#")[0]),
  );
  const entries = [];

  for (const page of pages) {
    const group = generated.groups[page.path] ?? "Docs";
    const sections = sectionsOf(page.source);
    for (const [index, section] of sections.entries()) {
      if (generatedPages.has(page.path) && index > 0) break;
      const text = plain(section.lines.join("\n")).slice(0, MAX_TEXT);
      if (!section.heading && !text) continue;
      entries.push({
        group,
        path: section.heading
          ? `${page.path}#${slugify(section.heading)}`
          : page.path,
        title: page.title,
        ...(section.heading ? { heading: section.heading } : {}),
        text,
      });
    }
  }

  for (const entry of generated.entries) {
    entries.push({
      group: generated.groups[entry.path.split("#")[0]] ?? "Reference",
      ...entry,
      text: plain(entry.text),
    });
  }
  return { entries };
};
