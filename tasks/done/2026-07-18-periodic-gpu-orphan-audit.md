# Task: periodic GPU orphan audit

## Outcome

The existing periodic research supervisor now checks provider reality against the shared GPU pool even while the director is deferred, fences objectively unsafe registered benches, and wakes the director for provider cleanup.

## Contract

- GitHub issue: https://github.com/joshsny/gradiated/issues/16
- Scope: supervisor skill and prompt, harness cadence and director observation, focused tests, factory README, Sol instructions, and the Gemma supervisor handoff.
- Safety: one grouped listing per already-authenticated provider; no repeated polling, provider setup, automatic provider deletion, retirement, or additional experiment gate.
- Reproduce: `PYTHONPATH=research/factory/src:research/factory/tests python3 -m unittest discover -s research/factory/tests -p 'test_*.py' -v`

## Verification

- 107 factory tests passed.
- `research-supervisor` skill validation passed.
- Python compilation, repository DevEx, and scoped diff checks passed.
- The live harness reloaded the implementation at a cycle boundary. Its configured audit cadence is every four one-minute cycles.
- The current Nebius H200 is not orphaned: its provider instance and disk exist, owner and watchdog processes are active, claim is fresh, and the resource IDs match the pool inventory.
