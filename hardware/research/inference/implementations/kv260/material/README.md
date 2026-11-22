# Jokes, dialogue scripts and desired behaviour

This folder preserves the creative work. None of it loads into inference as an
answer bank or changes weights automatically.

## Start here

- [character.md](character.md): current identity, voice, approvals and exclusions.
- [one-liners-review-v2.txt](one-liners-review-v2.txt): editable 48-joke review,
  including the latest untrained J39/photoresist wording. User edits stay exact.
- [intern-review-v1.txt](intern-review-v1.txt): original reviewed 29 scenes / 49
  replies, including the user's five edits.
- [joke-library.txt](joke-library.txt): readable collection of all 106 explicitly
  banked joke versions. Includes historical and withdrawn drafts, labelled as such.
- [chip-jokes.txt](chip-jokes.txt): earlier chip themes, approved flavour examples,
  feedback and excluded proposals.
- jokes.txt / questions.txt: original plain-text material.
- chip-benchmark.json: earlier visible cases and reference answers, not heldouts.
- intern-generative-role-v1.txt: earlier personality prompt, historical material.

The exact current trained corpus is [../model/jokes.json](../model/jokes.json).
It remains separate from future drafts. Training needs explicit authorisation.

## Complete preserved source library

library.jsonl contains unique complete source records: dialogues, joke targets,
prompts, situations, knowledge cards, desired behaviour, earlier source notes and
inert snippets formerly embedded in Python. library-index.json maps original file
names and record positions to content hashes, with pre-cleanup file hashes.
Identical JSON/text content is stored once; roles, context, provenance, status and
wording remain. JSON formatting may differ; the authored strings do not.

Search an old filename or a phrase in library.jsonl in VS Code. Each row's
`content` is the source value and `sources` lists where it appeared. The index
records both tracked input documents and previously ignored authoring drafts.
The preservation pass compared every record of the original 190 input documents
before retirement and additionally retained all 33 earlier README/style notes plus four readable dialogue/preview sources.

Older material includes superseded names, withdrawn jokes and fictional-intern
prompts. It is preservation material, not current instructions, approval or an
untouched evaluation set. character.md governs new content. Generated trial
transcripts and failed experiment machinery are available at the Git recovery
checkpoint described in ../history.md.
