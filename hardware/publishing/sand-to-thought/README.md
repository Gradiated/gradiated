# Sand to Thought

Research, learning, teaching and article planning for the Sand to Thought collection. The overview connects the computing stack. Deep dives can explore any related question and may connect to several chapters or subjects without being confined to one.

## FPGA article: edit this version

The reconciled [FPGA script](articles/fpga/script.md), with all thirteen inference experiments, is the sole editing and future publication source. On this Mac, open it under `/Users/aidanmcconnell/dev/gradiated`, on `FPGA-deep-dive`. Its [local preview](http://127.0.0.1:5173/sand-to-thought/fpga/) imports that checkout. Other FPGA worktree copies are superseded recovery material and must not receive further article edits. See [the publishing instructions](AGENTS.md).

## Purpose and goals

Aidan works at Gradiated and is developing a deep understanding of the semiconductor stack, from transistor physics and manufacturing through circuits, memory, processors, compilers, GPUs and complete computing systems. The long-term ambition is to design and tape out a custom chip.

The aim is to learn as efficiently as possible while building understanding that can support engineering decisions. The project combines lectures, reading, discussion, worked examples and writing. Explaining ideas clearly to a newcomer is part of the learning process, exposing gaps that familiarity with terminology can hide.

Sand to Thought and its deep dives also make this learning visible to potential customers, investors and other readers. Published work should demonstrate careful reasoning, technical depth and intellectual honesty, showing how Gradiated develops understanding from the ground up. Distinguish what is understood, what is being investigated and what has actually been built.

## How the assistant should help

- **As tutor**, check Aidan's understanding, connect layers and identify useful prerequisites without continually derailing the chosen topic. Use questions and worked examples to expose gaps and support progress.
- **As writer**, help explain mechanisms clearly enough to reveal gaps in reasoning. Preserve Aidan's meaning and make explanations accessible to curious newcomers.
- **As reviewer**, challenge unsupported claims and distinguish a useful simplification from a misleading explanation. State uncertainty and separate evidence from assumptions.
- **As assistant**, preserve decisions, unresolved questions and learning progress so future work can resume without repeatedly rebuilding context.

These goals guide learning and editorial choices. Keep room for curiosity and exploration without requiring every deep dive to justify its immediate relevance to tape-out. Keep changing tasks and study checkpoints separate from this enduring purpose.

## Start here

| Work | Source |
| --- | --- |
| Collection and reading routes | [Library](shared/library.md) |
| Topics and relationships | [Topic map](shared/topics.md) |
| Writing and visual conventions | [Style guide](shared/style-guide.md) |
| Overview planning and history | [Plan](articles/sand/plan.md) |
| Illustration decisions | [Visuals](articles/sand/visuals.md) and [visual cues](articles/sand/visual-cues.md) |
| Published article source | [Company script](./articles/sand/script.md) |
| Website implementation and previews | [Implementation guide](articles/sand/implementation.md) |
| Deep-dive questions | [Ideas backlog](planning/ideas.md) |
| Deep-dive study and sources | [Research notebook](planning/notes.md) |
| Course study | [Learning guide](../../learning/README.md) |
| Tutor questions and worked examples | [Tutoring guide](../../learning/tutoring/README.md) |
| Stand-up lectures and delivery scripts | [Teaching guide](lectures/README.md) |
| Shared references and missing attachments | [Sources](shared/sources.md) |
| Earlier drafts and workflow history | [Archive](archive/README.md) |

## Current checkpoint — 14 November 2026

The canonical publishing source now lives under `hardware/publishing/sand-to-thought/`. Article scripts and references sit beside their figures and plans in `articles/`. Lecture scripts, presentation code and assets sit in `lectures/`. Learning notes live in `hardware/learning/`. The website imports these sources and retains routes, shared design and deployment.

This consolidation is local on `FPGA-deep-dive`. See [the hardware guide](../../README.md) for the current research and backup status. Earlier dated entries preserve the history of previous branches, publication limits and workflows. PR #715 and the first deep dive belong to that history.

Notes, private editorial cues and teaching preparation are not imported by the website build. Repository access and website publication are separate. Never add credentials, private chat prompts, customer information or sensitive personal material to this collection.

## How to work here

- Read the current file before editing. Aidan edits these notes too.
- Learning explanations and questions belong in the course notebook or relevant deep-dive notes. Teaching scripts change only when requested.
- Keep possible article questions in the backlog. Create `articles/<article-name>/` when work begins, with notes and a plan as needed. Use links to connect related articles and subjects. Do not force a publication order or a single parent chapter.
- Shared guidance has one home in `shared/`. Article-specific exceptions belong with the article. Article figures and collection-specific reusable code live here. Common website design components remain in the website source.
- Preserve source references, exact editions, uncertainty, corrections and the difference between studied material and proposed reading.
- Use repository-relative Markdown links. Do not introduce links to Downloads, temporary files or private chat folders.
- Update the overview coverage table in its plan, then run `python3 hardware/publishing/sand-to-thought/tools/update_library.py` from the repository root to refresh only the library coverage summary.
- Saving is local. A commit records a version locally. A push sends it to GitHub. Do not push, open a PR or change published article content without the authorisation for that work.

## Original local workspace

The existing Learning and Blogging folder retains small Markdown pointers to these canonical notes. Follow the link before editing. These are pointers rather than duplicate working notes. The company checkout's current branch determines the note version. On another computer, open the repository notes directly rather than relying on those Mac-specific pointers.

Before replacing any local note with a link, the original is preserved under `archive/local-notes-before-repository-2026-10-20/` in the original learning folder. The standalone preview runtime, tools, downloaded PDFs and historical snapshots remain local. They have not been deleted or changed as part of the repository notes move.
