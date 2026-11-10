---
name: gpu-model-rollout
description: Roll a risky change to a production GPU model pool (new runtime bundle, engine flags, caching, kernels, SGLang patches) out one replica at a time, hold at the first replica to compare it against the rest, then finish or roll back. Use for any change to a serving pool's runtime that live tests have not already proven at production load.
---

# GPU model rollout

A runtime pin change rolls a pool's Rollout (`gpu-inference/<pool>`) one replica
at a time: `maxUnavailable 1, maxSurge 0`, then `setWeight 50`, an SDK
qualification analysis, and `setWeight 100`. For a bigger change, hold it at
the first new replica, compare, then decide.

## Before

1. Test the change on a leased host first (`$gpu-host-lease`), with the same
   profile and flags as production. Record what you measured in the PR.
2. Ship it as one PR, so the pool never runs half of a change (for example
   engine flags without the patches they need). Merge it; the release workflow
   publishes the bundle.
3. Roll out at a quiet hour. Each replaced replica drains, and its sessions
   lose their GPU prefix cache.

## Roll out and hold

1. Open the pin PR that moves the pool to the new runtime
   (`product/inference/gpu/runtimes.json` / `models.json`, then
   `python3 tools/gpu/render-config.py`). Merge it.
2. Watch the Rollout. As soon as the first new pod is Ready, pause it:
   `kubectl -n gpu-inference patch rollout <pool> --type merge -p '{"spec":{"paused":true}}'`.
   Argo CD ignores `/spec/paused`, so the pause survives syncs.
3. Compare the new replica with the old ones for at least an hour of real
   traffic: errors and restarts, time to first token, cache hit rate
   (`sglang:cache_hit_rate` and the gateway cache panels), memory headroom,
   and any metric the change should move. Say what you saw in the PR.

## Then

- **Good:** resume with
  `kubectl -n gpu-inference patch rollout <pool> --type merge -p '{"spec":{"paused":false}}'`
  and watch it finish, including the qualification analysis.
- **Bad:** abort, which returns every replica to the stable ReplicaSet:
  `kubectl argo rollouts -n gpu-inference abort <pool>`, or without the plugin
  `kubectl -n gpu-inference patch rollout <pool> --subresource status --type merge -p '{"status":{"abort":true}}'`.
  Then revert the pin PR so Argo does not roll forward again.

Leave Kimi and any pool under a freeze alone unless the user says otherwise.
