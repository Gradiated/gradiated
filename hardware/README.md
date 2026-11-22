# Hardware

Aidan’s home for chip research, model development, experiments, learning and publishing inside the Gradiated repository.

## Start here

- Improve a model: read the [inference project](research/inference/README.md) and its selected [model baselines](research/inference/models/README.md).
- Run a chip experiment: follow the [experiment and measurement contract](research/inference/experiments/README.md). Define the question and comparison before collecting results.
- Write from results: use the [publishing guide](publishing/README.md). Article and lecture sources are here, with website entry points under `product/website`.
- Continue learning: open [learning](learning/README.md) or the [Sand to Thought collection](publishing/sand-to-thought/README.md).

## Structure

| Directory | Contents |
| --- | --- |
| `research/inference/models/` | Selected model identities, recipes and evidence status |
| `research/inference/devices/` | Hardware identities and configuration requirements |
| `research/inference/workloads/` | Versioned inputs, decoding and quality protocols |
| `research/inference/implementations/` | Software and device-specific circuit implementations |
| `research/inference/experiments/` | Questions, fixed controls, variants and concise findings |
| `research/inference/results/` | Compact, immutable run records referencing raw artifacts |
| `research/inference/schemas/` | Machine-readable record contracts |
| `research/inference/tools/` | Validate, compare and verify artifacts |
| `learning/` | Course notes, tutoring and references |
| `publishing/sand-to-thought/` | Articles, figures, lecture scripts, presentation code and editorial history |

Company-wide services, shared research tooling and product documentation remain outside this area. The website owns routes, navigation, common design components and deployment. It imports hardware publishing source using the website’s dependencies. Do not create duplicate article drafts or copied measurement tables.

## Current checkpoint — 15 November 2026

Both the original 26,720-parameter joke transformer and the newer text-input model have run on a physical KV260. The text-input model matched all 167,040 integer reference scores and three frozen completions. [Physical acceptance record](research/inference/results/physical-acceptance-20261114T232418Z-c39918/run.json)

The [KV260 speed baseline](research/inference/results/speed-20261115T125210Z-f3c38c/run.json) measures request latency and output generation rates on the board, with a fresh model load for each request. The [resident-speed benchmark](research/inference/results/resident-speed-20261115T150400Z-f42f45/run.json) adds latency and verified back-to-back rates with the weights kept loaded. Three [repeated resident blocks](research/inference/results/resident-diagnosis-20261115T165522Z-5cfeb0/findings.md) add about a minute of continuous throughput and VCC_SOM energy measurements per block. Whole-board energy and longer thermal behaviour remain open.

The article and lecture charts remain illustrative.

The [migration record](research/inference/migration.json) identifies the Mac and server source revisions. The existing implementation is kept together under `implementations/kv260/`, including its model manifests, reference arithmetic, RTL and host tools. This preserves the relative source identities used by older evidence. New shared benchmark records live above it.

The [storage record](research/inference/storage.json) describes recovered local artifacts. Shared durable backup is **pending**, by Aidan’s instruction. A verified second folder on the same Mac is not an independent backup. The temporary Linux server must not be retired on the strength of this reorganisation alone.

## Pending automation review

Revisit this checklist before opening the first PR from `hardware/research-and-articles-wip`, or when adding the first real experiment result, whichever comes first. Future hardware work should read this README and surface outstanding items at those points. Saving a work-in-progress branch does not require adding shared automation.

- [x] Remove the broad hardware-validation addition and both new push-path triggers from `.github/workflows/tests.yml` on this branch. The file matches the branch base. The original proposal is preserved in consolidation commit `21377c594` on `FPGA-deep-dive`.
- [ ] Before merging, review the missing push trigger for `hardware/publishing/**` on `main`. The retained website selector and its test select existing website checks when the workflow runs, including on PRs. They do not start the workflow for a publishing-only push to `main`.
- [ ] Propose hardware record validation as a separate, narrowly scoped change for a shared-workflow maintainer to review. Use the repository’s existing change-selection conventions. Trigger it for relevant experiment records, model/device/workload definitions, artifact manifests, publication selections, schemas and validator code. Include shared inputs where they affect validation. Ordinary unrelated changes should not gain a hardware-validation requirement.
- [ ] Verify both cases: relevant changes select the checks and unrelated changes skip them, while required-check reporting still completes correctly. Run `records.py check` and its tests from the commands below. Add the automation only after maintainer review and approval.

The intended benefit is to catch incorrect hashes, broken result references and invalid publication selections before merging. Until the automation is reviewed, run the checks locally. This checklist records pending work, not an instruction to change shared workflows automatically.

## Saving this work-in-progress branch

Both Vercel configurations (`product/website/vercel.json` and `product/services/console/vercel.json`) disable automatic Git deployments for the exact branch `hardware/research-and-articles-wip`. Other branches retain their existing behaviour. Keep both exclusions while this branch is for source backup only. Recheck the exclusions before pushing from a renamed or newly created branch. Manual deployments and deploy hooks are separate mechanisms and are not authorised by a push request.

The FPGA article remains `status: draft`. Its page is omitted from the public build, but the shared article loader can still bundle its prose into public JavaScript. Draft status and `noindex` do not provide privacy. Review and fix this before deploying if unpublished text must stay private.

Archive-sharing decisions agreed with Aidan. Preserve the local originals.

- [x] Include the historical [model source library](research/inference/implementations/kv260/material/README.md#complete-preserved-source-library) in the shared private repository, including previously ignored authoring drafts and withdrawn material. These are historical research inputs, not approved public copy or current model instructions.
- [x] Keep the 40 ETH course-slide images local and out of the outgoing commit. Their bytes are preserved, with scoped ignore rules. Notes and the Lecture 2 script retain links to the official decks and their slide labels. See [learning references](learning/references/README.md) for the local locations.

## Working rules

Use short-lived branches for changes, not permanent machine-specific versions. Current work continues on `hardware/research-and-articles-wip` in `/Users/aidanmcconnell/dev/gradiated-hardware-wip`. The original `FPGA-deep-dive` branch, checkouts and recovery refs remain intact. The FPGA article remains a draft, with no PR or merge required to save work on the remote branch. Agree file ownership before concurrent edits. Only one runner may own a board during configuration or measurement. Record the source commit and any uncommitted patch for a run. Never silently change a selected model, baseline or frozen evaluation set.

Run relevant checks before promoting a candidate. Preserve failures and limitations. A faster implementation must meet the declared quality requirement, and any precision change must be explicit. Keep software, RTL simulation, implementation reports, analytical estimates and physical measurements distinct.

A result has a unique ID, exact model/implementation/device/workload identities, conditions, correctness evidence, repeated samples and artifact hashes. Compare only matching protocols and measurement boundaries. Record measured observations separately from derived cost assumptions. Correct a result with a new record referring to the old one, rather than overwriting history.

Large payloads and raw logs stay outside Git. Git holds code, recipes, schemas, compact findings and artifact manifests. Protect selected weights, deployable bitstreams, baseline evidence and anything supporting a published claim. Caches and reproducible build intermediates are disposable only after confirming their role.

Use the Mac for development and local recovery copies. Temporary Linux machines build and execute work. Recover unique commits and artifacts, verify their hashes and test restoration before retiring a machine. Do not copy credentials, authentication state or private operational prompts into project records.

Respect the scope authorised for each task. New spending, publication, deployments, destructive cleanup or board changes outside that scope require explicit authorisation. No such actions are implied by this migration. A failed or inconclusive experiment is a result, not a reason to erase its history.

## Checks

From the repository root:

```sh
python3 hardware/research/inference/tools/records.py check
python3 -m unittest discover -s hardware/research/inference/tools -p 'test_*.py'
hardware/research/inference/implementations/kv260/check.sh
mise exec -- pnpm --dir product/website test
mise exec -- pnpm --dir product/website exec tsc --noEmit
```

The KV260 check uses the preserved, pinned Mac runtime. It does not install dependencies or access the board. See the implementation README for software inference and separate Linux requirements. The migration has not retrained a model or performed a new physical experiment.
