# Task: 2026-07-31-inference-capacity-financing-model

## Outcome

The shared Google Sheet links OpenRouter inference demand through 2029 to model-specific GPU capacity, rack requirements, buy-versus-rent economics, price subsidy, and a scenario-based capital requirement. A repository decision brief records sources, assumptions, uncertainty, and the resume contract.

## Owner and coordination

- GitHub issue: https://github.com/Gradiated/gradiated/issues/30
- GitHub project:
- owner: js
- Codex thread:
- created: 2026-07-31T22:09:25+00:00
- started: 2026-07-31T22:09:25+00:00
- last updated: 2026-07-31T22:09:25+00:00
- scope: docs/decisions/2026-07-31-inference-capacity-financing-model.md
- excluded paths:
- dependencies: OpenRouter historical rankings API; Google Sheets MCP; repository GPU inventory

## Contract

- hypothesis or user value: A formula-driven demand-to-capacity model will let the company tune market capture, growth, hardware mix, and pricing strategy without embedding a single unverifiable forecast.
- acceptance checks: All scenario inputs are visibly editable; formulas project quarterly through 2029; capacity reconciles to demand; buy/rent and subsidy/funding outputs are linked; checks contain no formula errors; every externally sourced value has a URL and evidence label.
- quality gate: No fabricated OpenRouter history; no throughput transfer presented as measured; base-case assumptions are explicit; changes are batch-written and re-read; exported workbook is inspected when available.
- SLO or budget: One decision-ready workbook and one concise evidence brief; no paid API or cloud capacity spend.
- timeout: Complete in the current working session; leave history import explicitly blocked if no rotated key is available locally.
- artifact locations: Google Sheet 1Ix7kRD90UAdT9nWU_ykPr3KXe9SpW1Yak0SOzBumtOg; docs/decisions/2026-07-31-inference-capacity-financing-model.md
- resume command: python3 tools/devex/start.py && sed -n '1,240p' tasks/done/2026-07-31-inference-capacity-financing-model.md
- rollback or cleanup: Delete only the newly added capacity/economics tabs in the shared Sheet and revert this task's decision brief; preserve prior workbook tabs and unrelated repository work.

## Plan

1. Reuse repository GPU/cloud-price evidence and collect primary hardware/rack sources.
2. Add demand, capacity, hardware, subsidy, funding, scenarios, sources, and checks to the shared Sheet.
3. Re-read formulas/results, inspect an export if possible, record limitations, and hand off.

## Result

- status: done
- verification: Google Sheets readback found 0 formula errors; all extended structural checks PASS; history-dependent output is PASS after the 120-row import; editable inputs have light-cream fill and blue text; finance number formats are applied across model outputs.
- changed paths: docs/decisions/2026-07-31-inference-capacity-financing-model.md; tasks/done/2026-07-31-inference-capacity-financing-model.md; shared Google Sheet tabs Scenarios, Model Drivers, Demand Forecast, Hardware Economics, Capacity Detail, Capacity Plan, Pricing & Subsidy, Funding & Dashboard, Checks, Sources.
- limitations or blocked paths: current prices are a retrospective proxy, open-weight labels need license review, throughput is synthetic until per-model serving benchmarks exist, and no connected browser was available for visual inspection. A fresh OpenRouter refresh is temporarily unavailable while the 1Password desktop bridge is offline; GitHub Project metadata was unavailable because the current token lacks project scope.
- commit: this task's completion commit on main (see git history for this packet)
- next action: rotate the OpenRouter key, load four complete quarters of rankings/current prices, confirm open-source classification, benchmark per-model throughput, then replace planning prices with written hardware/cloud/colo quotes.
- released: 2026-07-31T22:27:18+00:00
