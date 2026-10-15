const { Marked } = require("marked");
const HTML_ENTITIES = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};
const escapeHtml = (value) =>
  String(value).replace(/[&<>"']/g, (character) => HTML_ENTITIES[character]);

function createMarkdown() {
  const definitions = new Map();
  const references = new Map();
  const markdown = new Marked({ gfm: true });

  markdown.use({
    extensions: [
      {
        name: "footnoteDefinition",
        level: "block",
        start: (src) => src.search(/^\[\^[a-zA-Z0-9_-]+\]:/m),
        tokenizer(src) {
          const match =
            /^\[\^([a-zA-Z0-9_-]+)\]:[ \t]*(.*)(?:\n|$)((?:(?: {4}|\t)[^\n]*(?:\n|$))*)/.exec(
              src,
            );
          if (!match) return;

          const id = match[1];
          if (definitions.has(id))
            throw Error(`Footnote ${id} is defined twice.`);
          definitions.set(
            id,
            (match[2] + "\n" + match[3].replace(/^(?: {4}|\t)/gm, "")).trim(),
          );
          return { type: "footnoteDefinition", raw: match[0] };
        },
        renderer: () => "",
      },
      {
        name: "footnoteReference",
        level: "inline",
        start: (src) => src.indexOf("[^"),
        tokenizer(src) {
          const match = /^\[\^([a-zA-Z0-9_-]+)\]/.exec(src);
          if (match)
            return { type: "footnoteReference", raw: match[0], id: match[1] };
        },
        renderer(token) {
          if (!definitions.has(token.id))
            throw Error(`Footnote ${token.id} has no definition.`);
          const refs = references.get(token.id) || [];
          const ref = `fn-${token.id}-ref${refs.length ? "-" + (refs.length + 1) : ""}`;
          refs.push(ref);
          references.set(token.id, refs);
          return `<sup class="fn"><a href="#fn-${token.id}" id="${ref}" aria-label="Footnote ${token.id}">${token.id}</a></sup>`;
        },
      },
    ],
    renderer: {
      html() {
        throw Error(
          "Use Markdown for article content; raw HTML is not supported.",
        );
      },
      link(token) {
        if (
          /^(?:javascript|data|vbscript):/i.test(token.href.replace(/\s/g, ""))
        )
          throw Error("Unsupported link protocol.");
        return false;
      },
    },
  });

  return { markdown, definitions, references };
}

function parseScript(tokens) {
  const intro = [];
  const scenes = [];
  const footer = [];
  let title;
  let current = intro;
  let pendingHeading;
  let inFooter = false;

  for (const token of tokens) {
    if (token.type === "space" || token.type === "footnoteDefinition") continue;
    // Only explicitly labelled visual-direction blocks are editorial.
    if (
      token.type === "blockquote" &&
      /^>\s*\*\*Visual cue(?:\s|:|\*\*)/.test(token.raw)
    )
      continue;
    if (token.type === "html") {
      const raw = token.raw.trim();
      const marker = /^<!--\s*scene:\s*([a-z0-9-]+)\s*-->$/.exec(raw);
      if (marker) {
        if (inFooter)
          throw Error("Scene markers must appear before the footer.");
        current = [];
        if (pendingHeading) {
          current.push(pendingHeading);
          pendingHeading = undefined;
        }
        scenes.push({ key: marker[1], tokens: current });
      } else if (raw === "<!-- footer -->") {
        if (inFooter || pendingHeading)
          throw Error("Use one footer marker after the final scene.");
        inFooter = true;
        current = footer;
      } else if (
        /^<!--[\s\S]*-->$/.test(raw) &&
        !/<!--\s*(?:scene\b|footer\b)/.test(raw)
      ) {
        // Editorial comments are not published.
      } else
        throw Error(
          "Unrecognised marker or HTML. Use <!-- scene: key --> or <!-- footer --> on separate lines.",
        );
      continue;
    }
    if (token.type === "heading" && token.depth === 1) {
      if (title || intro.length || scenes.length || inFooter)
        throw Error("Start the script with exactly one # title.");
      title = token;
      continue;
    }
    if (token.type === "heading" && token.depth === 2 && !inFooter) {
      if (pendingHeading)
        throw Error("Place a scene marker after each ## heading.");
      pendingHeading = token;
      continue;
    }
    if (pendingHeading)
      throw Error(
        "Place a scene marker immediately after a ## heading (editorial notes may go between).",
      );
    current.push(token);
  }
  if (!title || intro.length !== 1 || intro[0].type !== "paragraph")
    throw Error("Use one # title followed by one introductory paragraph.");
  if (!inFooter || pendingHeading)
    throw Error(
      "Keep <!-- footer --> after the last scene and before the closing text.",
    );

  return { title, intro, scenes, footer };
}

function validateScenes(scenes, expectedScenes) {
  if (
    !Array.isArray(expectedScenes) ||
    !expectedScenes.length ||
    expectedScenes.some((key) => !/^[a-z0-9-]+$/.test(key)) ||
    new Set(expectedScenes).size !== expectedScenes.length
  )
    throw Error("Invalid scene manifest.");
  if (
    JSON.stringify(scenes.map((scene) => scene.key)) !==
    JSON.stringify(expectedScenes)
  ) {
    throw Error(
      `Scene order changed. Keep these markers in order: ${expectedScenes.join(", ")}. Adding, removing or reordering scenes needs a coordinated animation update.`,
    );
  }
}

function selectPublishedScenes(scenes, expectedScenes, publication) {
  if (!publication) return scenes;

  const last = expectedScenes.indexOf(publication.publishedThrough);
  if (
    last < 0 ||
    typeof publication.footer !== "string" ||
    !publication.footer.trim()
  ) {
    throw Error(
      "Use a known publishedThrough scene and a non-empty publication footer.",
    );
  }

  if (scenes[last + 1] && scenes[last + 1].tokens[0]?.type !== "heading") {
    throw Error(
      "The publication boundary must end immediately before a chapter heading.",
    );
  }

  return scenes.slice(0, last + 1);
}

function renderFootnotes(markdown, definitions, references, publication) {
  const notes = [];
  for (const [id, definition] of definitions) {
    const refs = references.get(id);
    if (!refs) {
      if (publication) continue;
      throw Error(`Footnote ${id} is defined but never referenced.`);
    }
    if (/\[\^/.test(definition))
      throw Error("Nested footnotes are not supported.");
    const note = markdown.parseInline(definition);
    const back = refs
      .map(
        (ref, i) =>
          `<a href="#${ref}" class="fn-back" aria-label="Back to text${i ? " " + (i + 1) : ""}">&#8617;</a>`,
      )
      .join(" ");
    notes.push(
      `<p class="footnote" id="fn-${id}"><sup>${id}</sup> ${note} ${back}</p>`,
    );
  }

  return notes;
}

function renderPost(source, template, expectedScenes, publication) {
  const { markdown, definitions, references } = createMarkdown();
  const tokens = markdown.lexer(source);
  const { title, intro, scenes, footer } = parseScript(tokens);

  validateScenes(scenes, expectedScenes);

  const visibleScenes = selectPublishedScenes(
    scenes,
    expectedScenes,
    publication,
  );
  const links = tokens.links;
  const render = (list) =>
    markdown.parser(Object.assign([...list], { links })).trim();
  const titleHTML = markdown.parser([title]).trim();
  const lede = render(intro).replace(/^<p>/, '<p class="lede">');
  const sections = visibleScenes.map((scene) => {
    if (!scene.tokens.some((token) => token.type !== "heading"))
      throw Error(`Scene ${scene.key} needs some article text.`);
    return `<section class="scene-text" data-scene="${scene.key}" id="sand-${scene.key}">\n${render(scene.tokens)}\n</section>`;
  });
  const footerHTML = render(
    publication ? markdown.lexer(publication.footer) : footer,
  );
  const notes = renderFootnotes(markdown, definitions, references, publication);
  const article = [
    `<header class="post-header" id="sand-introduction">`,
    titleHTML,
    lede,
    "</header>",
    ...sections,
    '<footer class="post-footer">',
    footerHTML,
    ...notes,
    "</footer>",
  ].join("\n");
  for (const placeholder of ["{{TITLE}}", "{{ARTICLE}}"]) {
    if (template.split(placeholder).length !== 2)
      throw Error(`Template must contain exactly one ${placeholder}.`);
  }
  // Replacement callbacks preserve literal $ characters in the author's prose.
  return template
    .replace("{{TITLE}}", () => escapeHtml(title.text))
    .replace("{{ARTICLE}}", () => article);
}

module.exports = { renderPost };
