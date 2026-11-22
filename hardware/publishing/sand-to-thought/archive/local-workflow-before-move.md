# Learning and Blogging

> Historical reference. Paths and instructions in this document may be obsolete. The [collection guide](../README.md) describes the current workflow.

A working library for learning computer architecture and explaining the semiconductor stack clearly, accurately, and beautifully. The public audience starts with curious newcomers; deeper articles can extend to device physics, architecture, implementation, and quantitative comparisons of real chips.

## Start here

| I want to… | Open |
| --- | --- |
| Resume the blog review after compaction | [Current checkpoint and todo](../articles/sand/plan.md#resume-here--current-work-and-todo) |
| See the library, reading path, and coverage | [LIBRARY.md](../shared/library.md) |
| Understand the subjects and their connections | [TOPICS.md](../shared/topics.md) |
| Check writing, graphic, and animation conventions | [STYLE_GUIDE.md](../shared/style-guide.md) |
| Read or edit the first article | [Post 001 script](../articles/sand/script.md) |
| See its eleven chapters and discussion outlines | [Post 001 plan](../articles/sand/plan.md#chapter-plan) · [Chapters 5 and 6](../articles/sand/plan.md#chapters-5-and-6-discussion-outline) |
| Work on its illustrations | [Post 001 visuals](../articles/sand/visuals.md) |
| Find learning notes | [Chip architecture notebook](../../../learning/courses/chip-architecture-notebook.md) |
| Read the pasted lecture 6–7 recap | [Saved study recap](../../../learning/courses/eth-ddca-lectures-06-07-recap.md) |
| Find teaching preparation | [Standup lectures](../lectures/standup_lectures.md) and [lesson 1 script](../lectures/lecture-1/script.md) |
| See what was preserved during the move | [Archive](README.md) |

## Working roles

- **TUTOR:** learning, questions about other resources, and notes requested by Aidan.
- **BLOG DEVELOPER:** public explanations, article planning, website work, graphics, and animation.
- Both use the same project files. Read the latest version before editing; Aidan edits these files too. Do not send messages to another chat unless Aidan asks.
- Use the Codex in-app browser for website debugging and visual verification, as requested by Aidan.
- Discussion and planning do not by themselves authorise rewriting an article. The 2026-10-12 reorganisation preserves the current blog content.

The **Chip Architecture Notebook** is the main learning record. The [lecture 6–7 recap](../../../learning/courses/eth-ddca-lectures-06-07-recap.md) preserves Aidan's pasted text unchanged, saved on 2026-10-13. Detailed lecture notes and source references already live in the notebook. Blog decisions and proposed outlines belong in the post plan, with the collection structure in `LIBRARY.md` and subject definitions in `TOPICS.md`.

## Folder guide

```text
Learning and Blogging/
├── README.md                 # navigation and workflow
├── LIBRARY.md                # reading routes, posts, coverage
├── TOPICS.md                 # subject and topic definitions
├── STYLE_GUIDE.md            # shared editorial and visual conventions
├── lesson notes/             # existing learning and teaching files
├── blogs/
│   └── blog 001 - from sand to/
│       ├── script.md         # link to the canonical company article
│       ├── plan.md           # scope, chapters, coverage, sources, open questions
│       ├── visuals.md        # detailed scene direction and verification
│       ├── visual-cues.md    # private scene cues, separate from article prose
│       ├── assets/           # post-specific images and other media
│       └── web/              # current working HTML/CSS/JS site
├── shared/                   # reusable graphics and styles as they emerge
├── archive/                  # preserved earlier material; not active drafts
├── tools/                    # small maintenance helpers
└── preview.sh                # start Post 001 at localhost:8080
```

Post numbers are stable identifiers, not reading-order positions. One post can cover several subjects. Put each post in one folder and link to it from the relevant subjects. Add asset folders when useful; do not duplicate working files in `shared/`.

## Preview the website

From this folder:

```sh
./preview.sh
```

Open [http://localhost:8080](http://localhost:8080). Stop the preview with Ctrl-C in the terminal that started it. If the port is already in use, use the existing preview or stop that preview first.

The launcher uses `node` from PATH when available, otherwise the bundled Codex Node runtime on this Mac. With a normal Node installation you can also run:

```sh
cd 'blogs/blog 001 - from sand to/web'
node serve.js
```

No package installation is needed. The preview builds the article on startup and watches for saved edits. The Markdown parser is bundled in `tools/vendor/marked/`; Node 20 or later is required. GSAP, ScrollTrigger, and IBM Plex Sans currently load from external CDNs, so the illustrated preview needs internet access. The server listens only on this computer, on 127.0.0.1:8080. Existing footnote URLs remain valid.

## Editing the first post

The only editable article source is `hardware/publishing/sand-to-thought/articles/sand/script.md`. The [script in this folder](../articles/sand/script.md) is a symbolic link to that same file, not a second copy. Prefer opening the canonical path in your editor so an editor that replaces files cannot accidentally replace the link itself.

Save the canonical script to update localhost:5173. While `./preview.sh` is running, the standalone preview at localhost:8080 also rebuilds and refreshes automatically. No copy or synchronisation command is needed. Both paths follow the script in the company checkout's current branch. Saving is local; commit and push to update GitHub and trigger a Vercel preview.

Private [scene cues](../articles/sand/visual-cues.md) and [detailed visual directions](../articles/sand/visuals.md) remain in this learning folder and are never imported into the article. The generated `web/index.html` remains a standalone snapshot. The source link requires the company checkout at the path above; if moving to another computer, recreate the link to its checkout before building.
Keep the `<!-- scene: ... -->` markers in their existing order and retain `<!-- footer -->` before the closing text. Adding, removing, or reordering scenes requires a coordinated animation update. If a draft fails validation, the preview shows a message and keeps the last working page; correcting and saving it restores normal updates.

The HTML output is generated: edit article text in the script and page structure in `web/template.html`. Detailed [editing and build instructions](../articles/sand/implementation.md) explain the supported format. The generated website remains static HTML/CSS/JS; the refresh helper is only injected by the local preview server. This updates the local website, not a public deployment.

Alternative text drafts have been archived rather than merged. They include proposed wording that is not live. The latest applied prose and remaining work are recorded in the post plan.

## Maintaining the map

1. Define topics and their parent subject in `TOPICS.md`; add subtopics as a useful explanation requires them.
2. Record each post's actual treatment in the coverage table in its `plan.md`. Keep publication status separate from depth.
3. Run `python3 tools/update_library.py` to refresh the coverage summary in `LIBRARY.md`. It does not change scripts, website files, or the reading path.
4. Keep the curated post register and reading order in `LIBRARY.md` up to date when adding posts.

## Setup record

2026-10-12: created the agreed guides, extracted the current article into Markdown, and moved the unchanged website into its post folder. The previous `blogs and lectures/` directory is preserved as an archive snapshot. Learning and teaching notes were retained in place. No material has been published by this setup.

## Company website preview

The active company checkout is `the company checkout` on `feat/sand-to-thought-next`, saved to GitHub through `3ac77e39d`. PR #470 is merged and published; this branch contains the continuing memory and chapter 5 development, with no new PR or production deployment.

Review the new sequence at [localhost:5173/sand-to-thought/#sand-memory-width](http://localhost:5173/sand-to-thought/#sand-memory-width). It returns to the four-row array, widens locations to bytes and LC-3 words, adds MAR/MDR and clocked captures, then expands the address range and provides Read/Write buttons. The [Vercel preview](https://gradiated-5okmbo8el-gradiated.vercel.app/sand-to-thought/#sand-memory-width) is ready. Development and Vercel previews have 39 scenes. Publication remains through memory-buses with 25 scenes. Chapter 4, its interactions and the timing figure are retained. Website tests, standalone authoring checks and both build modes pass. See the post’s [current plan](../articles/sand/plan.md) for details and sources.

The website script is the single source of truth, linked from this folder as described above. Do not run the old `sync-sand-draft.mjs` draft-to-company workflow. Animation runtime files remain separate copies and still need coordinated updates when illustrations change.
