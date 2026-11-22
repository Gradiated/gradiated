const { existsSync, readFileSync } = require("node:fs");
const { Marked } = require("marked");

const marker =
  /\[@([a-zA-Z0-9][a-zA-Z0-9_-]*(?:\s*;\s*@[a-zA-Z0-9][a-zA-Z0-9_-]*)*)\]/g;
const text = (value) => ({ type: "text", value: String(value) });
const element = (tag, children, properties = {}) => ({
  type: "citationElement",
  data: { hName: tag, hProperties: properties },
  children,
});
const escapeHtml = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ],
  );
const html = (node) => {
  if (node.type === "text") return escapeHtml(node.value);

  const { hName, hProperties } = node.data;
  const attributes = Object.entries(hProperties)
    .map(
      ([key, value]) =>
        ` ${key === "className" ? "class" : key}="${escapeHtml(value)}"`,
    )
    .join("");
  return `<${hName}${attributes}>${node.children.map(html).join("")}</${hName}>`;
};

const referenceFileFor = (path) =>
  path.replace(/\.(?:md|mdx)$/, ".references.json");
const readReferences = (path) => {
  const file = referenceFileFor(path);
  try {
    const sources = JSON.parse(readFileSync(file, "utf8"));
    if (!sources || typeof sources !== "object" || Array.isArray(sources))
      throw new Error("Expected an object keyed by source name");
    return sources;
  } catch (error) {
    if (error.code === "ENOENT") return {};
    throw new Error(`Cannot read references in ${file}: ${error.message}`);
  }
};

const validateReference = (key, source) => {
  const fail = (message) => {
    throw new Error(`Reference ${key}: ${message}`);
  };
  if (!source || typeof source !== "object" || Array.isArray(source))
    fail("expected source details");
  if (
    !Array.isArray(source.authors) ||
    !source.authors.length ||
    source.authors.some(
      (author) => typeof author !== "string" || !author.trim(),
    )
  )
    fail("authors must be a non-empty list of names");
  if (typeof source.title !== "string" || !source.title.trim())
    fail("title is required");
  if (typeof source.url !== "string" || !source.url.trim())
    fail("url must be an absolute http or https URL");
  let url;
  try {
    url = new URL(source.url);
  } catch {
    fail("url must be an absolute http or https URL");
  }
  if (
    !["https:", "http:"].includes(url.protocol) ||
    url.username ||
    url.password
  )
    fail("url must use http or https without credentials");
  for (const field of [
    "publication",
    "volume",
    "pages",
    "publisher",
    "accessed",
  ]) {
    if (
      source[field] !== undefined &&
      (typeof source[field] !== "string" || !source[field].trim())
    )
      fail(`${field} must be a non-empty string`);
  }
  if (
    source.year !== undefined &&
    (!Number.isInteger(source.year) || source.year < 1 || source.year > 9999)
  )
    fail("year must be a four-digit year");
};

const referenceText = (source) => {
  const authors =
    source.authors.length > 5
      ? `${source.authors[0]} et al.`
      : source.authors.length === 1
        ? source.authors[0]
        : `${source.authors.slice(0, -1).join(", ")} & ${source.authors.at(-1)}`;
  const children = [
    text(`${authors}${/[.!?]$/.test(authors) ? "" : "."} `),
    element("a", [text(source.title)], {
      href: source.url,
      target: "_blank",
      rel: "noopener noreferrer",
    }),
    text(/[.!?]$/.test(source.title) ? "" : "."),
  ];
  if (source.publication)
    children.push(text(" "), element("em", [text(source.publication)]));
  if (source.volume)
    children.push(text(" "), element("strong", [text(source.volume)]));
  if (source.pages)
    children.push(text(`${source.volume ? "," : ""} ${source.pages}`));
  const imprint = [source.publisher, source.year]
    .filter((value) => value !== undefined)
    .join(", ");
  if (imprint) children.push(text(` (${imprint})`));
  if (source.publication || source.volume || source.pages || imprint)
    children.push(text("."));
  if (source.accessed) children.push(text(` Accessed ${source.accessed}.`));
  return children;
};

const createCitations = (sources = {}) => {
  const used = new Map();
  const cite = (keys) =>
    element(
      "sup",
      keys.flatMap((key, index) => {
        if (!Object.hasOwn(sources, key))
          throw new Error(
            `Citation ${key} is not defined in the article's references file.`,
          );
        validateReference(key, sources[key]);
        if (!used.has(key))
          used.set(key, { number: used.size + 1, occurrences: [] });
        const entry = used.get(key);
        const id = `cite-${key}-${entry.occurrences.length + 1}`;
        entry.occurrences.push(id);
        const link = element("a", [text(entry.number)], {
          href: `#ref-${key}`,
          id,
          role: "doc-biblioref",
          "aria-label": `Reference ${entry.number}`,
        });
        return index ? [text(","), link] : [link];
      }),
      { className: "article-citation" },
    );
  const keysFor = (value) => value.split(/\s*;\s*@/);
  const bibliography = () =>
    used.size
      ? element(
          "section",
          [
            element("h2", [text("References")], {
              id: "article-references-heading",
            }),
            element(
              "ol",
              [...used].map(([key, entry]) =>
                element(
                  "li",
                  [
                    element("p", referenceText(sources[key])),
                    element(
                      "span",
                      entry.occurrences.flatMap((id, index) => [
                        ...(index ? [text(" ")] : []),
                        element(
                          "a",
                          [
                            text(
                              entry.occurrences.length === 1
                                ? "↩"
                                : `↩${index + 1}`,
                            ),
                          ],
                          {
                            href: `#${id}`,
                            role: "doc-backlink",
                            "aria-label": `Return to citation ${entry.number}, occurrence ${index + 1}`,
                          },
                        ),
                      ]),
                      { className: "article-reference-backlinks" },
                    ),
                  ],
                  { id: `ref-${key}`, tabIndex: -1 },
                ),
              ),
            ),
          ],
          {
            className: "article-references",
            role: "doc-bibliography",
            "aria-labelledby": "article-references-heading",
          },
        )
      : undefined;

  return {
    cite,
    keysFor,
    bibliography,
    renderBibliography: () => {
      const node = bibliography();
      return node ? html(node) : "";
    },
    markedExtension: {
      extensions: [
        {
          name: "articleCitation",
          level: "inline",
          start: (source) => source.indexOf("[@"),
          tokenizer(source) {
            if (this.lexer.state.inLink) return;
            const match = new RegExp(`^${marker.source}`).exec(source);
            if (match)
              return {
                type: "articleCitation",
                raw: match[0],
                keys: keysFor(match[1]),
              };
          },
          renderer: (token) => html(cite(token.keys)),
        },
      ],
    },
  };
};

const renderCitedSections = (source, sources = {}) => {
  const citations = createCitations(sources);
  const markdown = new Marked(citations.markedExtension);
  const chunks = source.split(/<!-- scene: ([a-z-]+) -->/);
  const introduction = markdown.parse(chunks[0]);
  const scenes = [];
  for (let i = 1; i < chunks.length; i += 2)
    scenes.push({ key: chunks[i], html: markdown.parse(chunks[i + 1]) });
  return { introduction, scenes, bibliography: citations.renderBibliography() };
};

const remarkArticleCitations = () => (tree, file) => {
  if (!file.path?.replaceAll("\\", "/").includes("/content/articles/")) return;

  const citations = createCitations(readReferences(file.path));
  const skip = new Set([
    "code",
    "inlineCode",
    "link",
    "linkReference",
    "definition",
    "html",
    "mdxjsEsm",
  ]);
  const visit = (parent) => {
    if (skip.has(parent.type) || !parent.children) return;

    parent.children = parent.children.flatMap((node) => {
      if (node.type !== "text") {
        visit(node);
        return [node];
      }
      const children = [];
      let cursor = 0;
      for (const match of node.value.matchAll(marker)) {
        if (match.index > cursor)
          children.push(text(node.value.slice(cursor, match.index)));
        children.push(citations.cite(citations.keysFor(match[1])));
        cursor = match.index + match[0].length;
      }
      if (!cursor) return [node];
      if (cursor < node.value.length)
        children.push(text(node.value.slice(cursor)));
      return children;
    });
  };
  visit(tree);
  const references = citations.bibliography();
  if (references) tree.children.push(references);
};

const articleCitationsPlugin = () => ({
  name: "article-citations",
  enforce: "pre",
  configureServer(server) {
    const reload = (file) => {
      if (
        file.replaceAll("\\", "/").includes("/content/articles/") &&
        file.endsWith(".references.json")
      ) {
        server.ws.send({ type: "full-reload" });
      }
    };
    server.watcher.on("add", reload);
    server.watcher.on("unlink", reload);
    server.httpServer?.once("close", () => {
      server.watcher.off("add", reload);
      server.watcher.off("unlink", reload);
    });
  },
  transform(_code, id) {
    if (
      !id.includes("?") &&
      id.includes("/content/articles/") &&
      id.endsWith(".mdx")
    ) {
      const references = referenceFileFor(id);
      if (existsSync(references)) this.addWatchFile(references);
    }
  },
  load(id) {
    const suffix = ["?fabrication-article", "?cited-article"].find((query) =>
      id.endsWith(`.md${query}`),
    );
    if (!suffix) return;

    const file = id.slice(0, -suffix.length);
    this.addWatchFile(file);
    const references = referenceFileFor(file);
    if (existsSync(references)) this.addWatchFile(references);
    const article = renderCitedSections(
      readFileSync(file, "utf8"),
      readReferences(file),
    );
    return `export default ${JSON.stringify(article)};`;
  },
});

module.exports = {
  createCitations,
  readReferences,
  referenceFileFor,
  renderCitedSections,
  remarkArticleCitations,
  articleCitationsPlugin,
};
