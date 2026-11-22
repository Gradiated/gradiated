# KV260 conditioned-model physical acceptance

**ID:** `kv260-conditioned-physical-acceptance-v1`

**Status:** Preregistered. Offline preparation reviewed. Physical testing awaits live preflight and review of the live state.

## Question and controls

Will the sealed `conditioned-hex-balanced-v1` package on our KV260 reproduce the pinned Mac W16A16 integer reference? The original model with the same FPGA image is a setup control. This is an equivalence check. Model quality and performance are separate questions.

Use one identified KV260, the existing Ubuntu SD and QSPI boot firmware, the sealed native host and overlays, and PL0 at the historical 50 MHz. Require reset 119, an operating manager with flags zero, clock and AFI bindings, and one dedicated transformer UIO mapping at `0xA0000000`. Record kernel and boot ID, active overlays, taint, existing kernel messages, DFX state and device ownership before and after.

The candidate and original rollback manifests are pinned below. The bitstream, three overlays and native library are byte-identical across them. The candidate has a separate weight image, references and text profile. Keep both sealed packages untouched. Verify the manifest from its external pin and every staged payload again before launching. The sealed on-board runner is the execution input. Historical server receipts use absolute Linux paths and the Mac copy of `board_prepare.py` has migrated path discovery. Neither re-sealing nor rebuilding is needed.

| Package | Manifest SHA-256 |
| --- | --- |
| `conditioned-6wbein7j` | `b0394ba256d877fb62d6eb6e74942d5ff0c649cf751d53481e827c8bae5e9167` |
| `text-bgjxdjep` (original) | `bf40e0c470fd3af974f021c1e6f57583c7c8098b9cd35889513fe1a136984d9f` |

Frozen completion reference: `.agents/runtime/hardware/inference/outputs/kv260-conditioned-physical-acceptance-v1-preparation/completion-references.json`, SHA-256 `33d290aed332af9e8b100a708222796d53f82529bb9c55d5d9ed13606cb0d367`. The three Mac software references produce 122, 90 and 104 output bytes respectively, all ending in EOS.

## Live preflight and ownership

Use the authenticated USB console. Inspect live device-tree and overlay metadata, boot identity and kernel logs. Check the installed firmware file against the sealed package. Its SHA-256 identifies the file on disk. Use the active firmware-name property, boot and overlay history, driver bindings and, after the write gate opens, the original BOS result to establish confidence in the running setup. The BOS result is a functional check. Neither it nor the on-disk checksum reads the loaded bitstream back. Record gaps in that evidence and stop if the configuration cannot be established.

Coordinate a board window with one named owner and attempt ID, with no in-flight request or needed context. Once writes are in scope, the owner holds one non-blocking advisory lock at `/run/lock/gradiated-kv260-acceptance.lock` through the entire sequence, including comparison and any authorised restoration. Every cooperating runner uses that same lock. This is separate from the sealed runner’s per-process UIO lock. Before every write gate, recheck for other operators, open or mapped device access and concurrent DFX or programming work. Check Linux process and device state with sufficient privileges. Mac serial-port availability only concerns the transport. An uncertain or conflicting owner stops the run.

## Protocol after review

1. Capture the read-only baseline through the established Mac USB/UART console. If the verified circuit is already live, leave the FPGA image, clock, overlays and services alone. If the board is stock, unknown, tainted or busy, stop and review. A fresh stock boot historically leaves the manager in flags `0x20` with PL0 near 100 MHz. A separate reviewed setup would need the verified firmware-file mode and enabled 50 MHz before applying the programming overlay. Never reuse the failed historical programming route or remove an overlay to guess at recovery.
2. Once the original setup is confirmed and the board is exclusively owned, run the original package’s BOS check once. Compare all 320 returned signed integer scores directly with its sealed `bos-logits.json`. Require API result zero, counters `[0, 29281, 320, 1, 0]` and an empty mismatch list. A failure stops the run before loading candidate weights.
3. Run the candidate’s `--validate all --watchdog-seconds 180` once, with one fresh reset/full load and six context clears between cases. Require every frame’s 320 signed integer scores to equal its pinned Mac vector. On the Mac, check the returned case names and order, per-case position and score counts, context counts and six explicit clears. Compare every returned `logits_sha256` with the corresponding `case_checks[].logits_sha256` in `.agents/runtime/hardware/inference/outputs/kv260-conditioned-physical-acceptance-v1-preparation/package-verification.json` (SHA-256 `245aecdea12af19ae8a60b0aaa9bee932d9a976ecaef91c74b797fdc623ea603`). Independently recompute each expected digest from the frozen score rows packed as `<320i`, in order. The sealed runner compares each actual score directly and emits digests on success. The cases are:

   | Case | Input positions |
   | --- | ---: |
   | BOS | 1 |
   | J01-first16 | 16 |
   | authored128 | 128 |
   | repeated-J01-256 | 256 |
   | encoded-fu2p2q | 13 |
   | encoded-hello | 11 |
   | encoded-max48 | 97 |
   | **Total** | **522** |

   The physical gate covers 167,040 exact score comparisons. The earlier RTL receipt includes seven additional BOS replays, so its comparison count is higher.
4. Run one candidate text completion for each frozen encoded prompt above. Reconstruct the exact prompt bytes from the respective token fixture. Each independent request uses the sealed `--complete` mode with a cap of 255 output decisions and a 256-position context. The host encodes actual UTF-8 as BOS followed by two hexadecimal digit IDs per byte, with a 48-byte input maximum. It picks the first index with the highest score across all 320 signed logits. Check the prompt bytes, prefix tokens and every prefix score vector against the frozen fixture. Independently recompute each selection from the 320 raw scores in the recorded frame, using the lowest index on ties. Check the frame order, reported score hashes, token feedback and counters, then compare generated token IDs, EOS/stop and raw bytes with the pinned Mac integer completions. Preserve poor output verbatim in ignored evidence. A poor but matching completion is an observation about the model. A difference from the reference is a correctness failure.
5. If the hardware remains healthy and the pre-test state used the original package, restore the original weights with one original BOS check. Preserve the circuit configuration. Record that this leaves a fresh BOS context. If any session times out, a counter or score differs, a device operation fails, or new unexplained kernel errors or taint appear, stop immediately. Save the first mismatch and read-only state. Do not retry blindly or issue further MMIO on an uncertain session. If no safe model-only recovery is possible and stock restoration is needed, use the established human-supervised full power-cycle procedure after review. Preserve the unchanged SD and QSPI. Capture the stock baseline before declaring recovery. A userspace watchdog cannot guarantee recovery from a stalled hardware bus.

### Sealed commands

After both gates are cleared and local package checks pass, set the two directory variables to the verified bundle paths on the KV260. The controlling process supplies each `prompt` as a single argument decoded strictly from the pinned `input_utf8_hex`. Preserve whitespace and UTF-8 bytes. Call the completion command once per frozen encoded input and stop between invocations to verify the previous gate. For model-only restoration, repeat the original BOS command once when the recovery conditions above hold.

```sh
sudo -n python3 -I -B "$original_dir/board_bos.py" --bundle "$original_dir" --run-bos
sudo -n python3 -I -B "$candidate_dir/board_bos.py" --bundle "$candidate_dir" \
  --validate all --watchdog-seconds 180
sudo -n python3 -I -B "$candidate_dir/board_bos.py" --bundle "$candidate_dir" \
  --complete="$prompt" --max-new-tokens 255
```

For every invocation, retain the raw streams separately and the exit status. Require exit zero, stdout containing exactly one machine JSON object, and a Boolean true `accepted` for BOS and validation or `hardware_accepted` for completion. Also require the independent comparisons specified above before proceeding.

## Limits and evidence

One attempt per gate, two original BOS checks at most, three candidate completions, and no concurrent board work. The sealed runner bounds native calls at 30 seconds, original BOS at 40 seconds, and each validation or completion process at 180 seconds. Allow 20 minutes for the acceptance session after packages are staged and preflight is clear. Give the two separate UART transfers up to 10 minutes each. Stop at the first failed gate or budget expiry. Keep transfer quoting and framing separate from the Linux console and verify byte lengths and hashes at both ends.

Before the first physical step of an attempt, freeze the exact plan and source revision in a new attempt directory and record the plan SHA-256. Save and hash the binary Git patch relative to that revision for any uncommitted source changes, including any untracked experiment inputs used. Compare the working files with the frozen copy before starting. Preserve that snapshot if a later attempt needs a revised plan. Save package/reference and capture hashes, device configuration, attempt ID, preflight, stop/recovery records, raw stdout/stderr, exit statuses, counters and completion JSON under the new checkout’s ignored runtime. Recover evidence to the Mac before relying on results. Add a schema-valid immutable run record only after physical execution, recording any failed or aborted attempt. Wall time here includes setup and checking and cannot support latency, throughput or energy claims.
