# Historical standalone preview workflow

This is retained context for the local-only portable preview. Use the [current implementation guide](../articles/sand/implementation.md) for company website work. The local preview tools and runtime have not moved.

# Local website — Post 001

## Everyday editing

1. From the project root, run `./preview.sh` and open [localhost:8080](http://localhost:8080).
2. Edit and save the canonical script at `hardware/publishing/sand-to-thought/articles/sand/script.md`. The local [script.md](../articles/sand/script.md) is a symbolic link to that same file. The preview rebuilds the HTML and refreshes the browser automatically, usually within two seconds. It tries to keep you at the same place in the article.
3. Review the text and its illustration together. Later illustrations now hold through their associated text and transition in the gaps. Check normal scrolling as well as pinned scenes after text edits.

The preview is running only while its terminal process is alive; Ctrl-C stops it. `node serve.js` from this directory also starts the builder and watcher. Node 20 or later is required; `preview.sh` can use the bundled Codex Node on this Mac. No package installation is needed. GSAP, ScrollTrigger, and IBM Plex Sans still need internet access.

Both script paths read the same company file immediately, without a sync process. Save to update the local website; commit and push from the company repository for a Vercel preview. Switching its branch also changes the source visible here. The standalone HTML output remains portable, but rebuilding on another computer requires relinking script.md to that computer’s checkout. Animation runtime files remain separate and need coordinated changes.

## Script format

- Start with one `# Title` and one introductory paragraph.
- A `## Heading` goes immediately before the scene it introduces (with optional editorial notes between). Its text can be edited normally. Smaller headings can be used within a scene.
- Keep every `<!-- scene: key -->` on its own line, in the existing order. Text belongs to that scene until the next marker or section heading. Ordinary paragraphs, **bold**, *italics*, code, lists, blockquotes, and links are supported.
- Keep private editorial directions in [visual-cues.md](../articles/sand/visual-cues.md) and detailed decisions in [visuals.md](../articles/sand/visuals.md). These files are not imported into either build. The renderer still omits legacy Visual cue blocks and HTML comments.
- `<!-- footer -->` ends the final scene and starts the closing text. Retain this marker even when rewriting the ending.
- Use `[^1]` for a footnote reference and `[^1]: Text` for its definition. Additional labels can contain letters, digits, underscores, or hyphens; the label is what the reader sees. Indent continuation lines by four spaces. Repeated references get separate return links. Footnotes support inline formatting; nested footnotes and multi-paragraph notes are not supported.
- Use Markdown for article content; raw HTML is rejected. Code examples can use fenced code blocks.
- Relative URLs are relative to the generated `web/index.html`. For now, use absolute external links; local media needs to be served from `web/` or deliberately wired into the publishing setup. Automatic asset copying is not implemented.

Adding, removing, or reordering scenes is a separate animation change. The publisher checks the script against `scenes.json` and refuses mismatches. Changing this manifest alone does not update the JavaScript timeline. Scenes 0–2 remain fixed unless Aidan explicitly requests a change.

If a saved draft is invalid, the browser displays an explanation and continues showing the last valid build. Correct the script and save again. Errors are also printed in the server terminal. A static output is only current after a successful build.

## Website files

- `index.html`: generated article and page shell; **do not edit article text here**.
- `template.html`: the editable page shell, with one `{{TITLE}}` and one `{{ARTICLE}}` placeholder. It preserves the original SVG stage, controls, styles, and script imports.
- `scenes.json`: the ordered scene keys corresponding to the existing animation timeline.
- `style.css`: page and diagram styling.
- `main.js`: 3D renderer, scroll mapping, frame loop, and debug controls.
- `scenes2d.js`: two-dimensional scene timeline, resolving original numbered keys through the current scene manifest.
- `memory-model.js`, `memory-controls.js` and `memory-scenes.js`: addressed memory behaviour, latch-array growth, manual read/write buttons and digit transfers, the adder write followed by a read at address 01, replaying on each scene entry, and bus notation. The single latch and first register retain their loops.
- `computer-scenes.js`: chapter 5 diagrams and demonstrations, including the abstract timing grid.
- `instruction-cycle-scenes.js` and `instruction-cycle-model.js`: progressive stored-program, PC, MAR/MDR, IR, execution and sequencing views. Transfers preserve address selection and gate result captures; the final demonstration holds after two instructions.
- `memory-interface-scenes.js` and `memory-access-model.js`: chapter 5’s byte/word growth, MAR/MDR interface, independent address-width expansion and manual read/write transfers. They reuse `memory-controls.js`.
- `scroll-progress.js`: text-aware reading progress, preserving the opening artwork's choreography.
- `serve.js`: local preview, builder, watcher, and optional `SNAP_DIR` capture support. Binds only to 127.0.0.1:8080.

The watcher follows the script link and handles normal saves and editor saves that replace the canonical file atomically. Prefer editing the canonical path to avoid replacing the symbolic link itself. It watches the script, template, and manifest. Browser refresh also detects changes to the generated HTML, CSS, and animation scripts. Changes to server/build tooling require restarting the preview.

## Build and checks

With Node on PATH, from the project root:

```sh
node tools/build_post.cjs
node --test tools/build_post.test.cjs tools/scroll-progress.test.cjs
```

To build once using the same Node lookup as the preview launcher:

```sh
./preview.sh --build
```

A successful build writes `web/index.html` atomically. Failed builds never replace the last working output. Marked 17.0.5 and its licence live in `tools/vendor/marked/`. The resulting HTML is static: the server injects its refresh helper only when serving a local preview; no refresh code is included in the generated page.

Read the [plan](../articles/sand/plan.md) and [visual directions and pinned-scene verification recipe](../articles/sand/visuals.md) before changing illustrations. The planned chapter headings and pending editorial corrections have not been applied. The [original handover](before-reorganisation/HANDOVER.md) remains an archived reference; its obsolete paths and publishing instructions are superseded by these notes.
