# KV260 stock-to-project setup

**ID:** kv260-stock-to-project-setup-v1

**Status:** Proposed for technical review. Setup ends at read-only inspection of the loaded FPGA, before the [physical acceptance experiment](kv260-conditioned-physical-acceptance-v1.md).

## Starting point and evidence

The Mac USB inventory on boot 9089d6bb-bf7b-4ae4-b76e-ee37e4900519 found the stock K26 image and only its four axi-pmon UIO devices. The manager was operating with flags 0x20 and dfx-mgr was running. The custom firmware on disk matched its pin. The on-disk hash identifies that file. Applied overlay metadata and the kernel loading diagnostics are the evidence for what the board loaded.

The preserved live-preflight.json has SHA-256 84640a0a362dcb76a7ada1862017be1ef7ef7a2c4d92481572498ed6007ed979. It ran as UID 1000 after noninteractive sudo was denied. Its empty kernel-message sample and zero count accompany a failed dmesg call, so the kernel errors are unknown. Its empty process matches accompany 130 permission denials, so device ownership is unknown. The actual PL0 rate is also unknown.

This procedure follows the successful 9 November 2026 firmware-file load. The historical receipt manifest in board-bringup/mac-filemode-load-20261109 has SHA-256 33aa20fc99418b2b838a67ff40eb939f23657674be40449bce9ce0d75cb33da4. Its twelve receipts and the six retained Mac command sources were checked locally. The bitstream and three overlays below are byte-identical in the four relevant sealed packages. [Historical sequence and recovery](../implementations/kv260/history/server-record.md#physical-bos-comparison-passed)

## Files, ownership and pre-change capture

1. Use the existing detached Mac USB console. Assign one named operator and one setup attempt ID for the board window. Confirm that any stock application users have released the board. Use the same non-blocking advisory lock at /run/lock/gradiated-kv260-acceptance.lock as the acceptance experiment. Hold it from the final pre-change checks to the post-setup inspection and evidence export. Reviewers stay out of the board console while the owner is active. The lock coordinates cooperating runners. Privileged process and service checks cover other access.
2. Start with the original sealed bundle at /home/ubuntu/.agents/runtime/fpga-inference/board-packages/text-bgjxdjep. Recheck its manifest, exact member set and all hashes as regular files. This is the bundle whose manifest and runner were observed on this boot. Use its overlay files for setup. Check /lib/firmware/gradiated-tiny-50mhz.bit.bin against the listed pin and use it in place if it matches. Stop if the staged data is absent, altered or linked unexpectedly.
3. If staging is needed, transfer the sealed archive over the existing UART only in its reviewed staging window. Use a fresh private attempt directory on the Linux filesystem and immutable input copies on the Mac. Send bounded numbered frames, confirm frame count, and verify archive size/SHA-256 on both ends before extraction. Accept only the exact regular-file members declared by the pinned manifest, with no duplicate names or path traversal. Create files exclusively, then recheck the reconstructed package. The original archive is 1,563,353 bytes with SHA-256 494d9ac21f16fad78af3d877ce5665ac59a45354cb62734a142838f8d08b63cc. The conditioned archive is 1,664,210 bytes with SHA-256 567d0a1499c7bf1dbb45e3814d74a2f052989ac973a32cc5efabc2697e892509 and is needed only for the later acceptance stage. An absent firmware file needs a separately checked exclusive, no-follow copy of the sealed firmware under its unique filename. An existing mismatch stops the procedure. Keep stock firmware and packages in place.
4. As root in that UART console session, save the pre-change board ID and boot ID, kernel release and build, taint, applied overlay status, live firmware-name property, manager state/status and flags, full clk_summary, both FCLK and AFI driver registrations, UIO bindings, Ethernet carrier, DFX service state and managed apps. Record stock firmware file hashes and read-only xmutil bootfw_status output for comparison. Save dmesg with timestamps plus the warning/error subset and a privileged process/descriptor/mapping inventory. Check for other FPGA loaders, board runners, open or mapped UIO and /dev/mem access, and active programming/configfs operations. Require successful reads and no unexplained diagnostics or competing users. If a process disappears during enumeration, distinguish that from a permissions failure. Keep the full capture privately and compare it with the recorded stock baseline.
5. Expect a fresh stock boot with k26-starter-kits_image_1 applied, dfx-mgr.service active, flags 0x20, only the stock axi-pmon UIO devices, taint zero, Ethernet carrier zero, and PL0 near the historical 99,999,999 Hz. Compare actual runtime ABI, firmware, boot and overlay details with the saved successful route. An unexplained difference stops setup. Preserve the same boot between checks. Freeze this procedure, source revision and any uncommitted patch, and the input and capture hashes with the attempt.

| Sealed file | Bytes | SHA-256 |
| --- | ---: | --- |
| Original package.json | 7,573 | bf40e0c470fd3af974f021c1e6f57583c7c8098b9cd35889513fe1a136984d9f |
| Original board_bos.py | 35,279 | a177225e088afffdeff70b2f81162497f5891fc8b1b7466d85f2b216451734aa |
| gradiated-tiny-50mhz.bit.bin | 7,797,692 | 678aaab239203a9b235b44868b36dd8b1022a5480430c7a3a8f6f587e24ea0d0 |
| kv260-clock.dtbo | 510 | 2f01134458d9bfe640999959f82130cf79ef7244aed04017f1b6fa6e0eccfc76 |
| kv260-program.dtbo | 347 | 33e5b9643561728cd32a2c89d465a0f94dccc6bf4398498f7826fa7dfb914779 |
| kv260-interface.dtbo | 762 | 5aacc09abe63d4056d823497ef1230c5fa64370fd8a9919364cdd4d2f391b53f |

## Proposed execution after review

Run these stages in order under one root supervisor with the shared lock. In the supervisor, open the lock with O_CREAT, O_NOFOLLOW and O_CLOEXEC, mode 0600. Verify by fstat that it is a regular root-owned file. Take fcntl.flock(fd, LOCK_EX | LOCK_NB), fail closed if busy and keep the descriptor open until the final checks and evidence export finish. Run and capture one stage at a time. Before each write, require the same boot, taint zero, the expected preceding overlay state and continued exclusive ownership. After each stage, compare new kernel messages against the saved baseline. A deadline, state mismatch, unreadable baseline, ambiguous kernel-log delta or unexplained warning/error ends this attempt. The snippets describe the commands for each gate and are not a batch to paste into the console.

1. Release the stock overlay through DFX. Resolve the installed xmutil in the pre-change capture. Require unload exit zero, the stock slot reported unloaded by listapps, and an empty configfs overlay directory. Then stop DFX for this session by the same runtime command used in the successful run. Require inactive, MainPID=0, the original UnitFileState and no competing loaders. The setup uses the existing systemd unit and preserves its boot enablement.

~~~sh
timeout -k 2s 20s xmutil unloadapp
timeout -k 2s 10s xmutil listapps
timeout -k 2s 15s systemctl stop dfx-mgr.service
timeout -k 2s 5s systemctl show dfx-mgr.service \
  -p ActiveState -p SubState -p MainPID -p UnitFileState
~~~

2. Select firmware-file mode. Read the flags as hexadecimal before and after the write. Require zero before applying the clock overlay and recheck immediately before programming, with DFX inactive and no intervening loader. The stock unload alone left 0x20 on the historical board. The earlier load attempted in that mode triggered a kernel fault.

~~~sh
manager=/sys/class/fpga_manager/fpga0
cat "$manager/flags"
timeout -k 2s 5s /bin/sh -c 'printf "0\n" > /sys/class/fpga_manager/fpga0/flags'
cat "$manager/flags"
~~~

3. Apply kv260-clock.dtbo at gradiated-tiny-clock through configfs. The expected xlnx,fclk consumer requests PL clock 71. Require applied status, one xilinx_fclk binding for tiny_transformer_clock, set_rate 50000000, and one pl0_ref row at exactly 50000000 with enable/prepare counts at least one and hardware-enable Y. Compare the full clock inventory and investigate any change outside the PL0 divider chain. Keep the clock overlay in place.
4. Recheck the installed firmware hash, hexadecimal flags zero, PL0 exactly 50 MHz and enabled, DFX inactive with MainPID=0, and the clock as the sole overlay. Record a programming attempt before issuing one write of kv260-program.dtbo at gradiated-tiny-program. Require applied status, the live firmware-name property gradiated-tiny-50mhz.bit.bin, manager operating with flags zero, the same enabled 50 MHz clock and taint zero. Preserve the diagnostics. The successful historical load emitted the two exact lines below, each once after stripping its timestamp. Allow at most one of each at this stage. Any other new warning or error needs an explanation before proceeding.

~~~text
OF: overlay: WARNING: memory leak will occur if overlay removed, property: /fpga-region/firmware-name
OF: overlay: WARNING: memory leak will occur if overlay removed, property: /fpga-region/resets
~~~

5. With the previous stage accepted, apply kv260-interface.dtbo at gradiated-tiny-interface. Require applied status, the AFI binding for tiny_transformer_afi and one dedicated UIO named gradiated-tiny-transformer-v1, bound to uio_pdrv_genirq at /axi/tiny-transformer@a0000000 with address 0xA0000000, map size 4096 and offset zero. Identify it by name and live mapping. The historical device was uio4. Require live DT reset 119 in the programming and AFI nodes. This identifies the configured reset line. A functional reset remains part of later acceptance.
6. Run the sealed original runner with no mode flags and an external deadline. Require machine JSON, exit zero, ready true, empty errors, zero flags and clock.rate_hz equal to 50000000. Repeat the human and process ownership checks, compare the state and diagnostics with the baseline and copy the complete evidence to the Mac. Return this inspection for technical review before the BOS gate.

~~~sh
timeout -k 2s 15s /usr/bin/python3 -I -B \
  "$original_dir/board_bos.py" --bundle "$original_dir"
~~~

For steps 3, 4 and 5, use the historically successful single-write/close configfs operation. This function is for use inside the locked root supervisor after the corresponding preceding gate and hashes have passed. Supply the three overlay names in sequence, one invocation per stage. The wrapper limits command time. A blocked kernel operation may persist beyond the timeout.

~~~sh
apply_overlay() {
  timeout -k 3s "$1" /usr/bin/python3 -I -B - "$original_dir" "$2" <<'PY'
import hashlib
import os
from pathlib import Path
import sys

overlays = {
    "clock": (510, "2f01134458d9bfe640999959f82130cf79ef7244aed04017f1b6fa6e0eccfc76"),
    "program": (347, "33e5b9643561728cd32a2c89d465a0f94dccc6bf4398498f7826fa7dfb914779"),
    "interface": (762, "5aacc09abe63d4056d823497ef1230c5fa64370fd8a9919364cdd4d2f391b53f"),
}
bundle = Path(sys.argv[1])
stage = sys.argv[2]
size, digest = overlays[stage]
payload_path = bundle / f"kv260-{stage}.dtbo"
if payload_path.is_symlink() or not payload_path.is_file():
    raise SystemExit("Overlay must be a regular sealed file")
payload = payload_path.read_bytes()
if len(payload) != size or hashlib.sha256(payload).hexdigest() != digest:
    raise SystemExit("Overlay pin differs")
if int(Path("/sys/class/fpga_manager/fpga0/flags").read_text().strip(), 16) != 0:
    raise SystemExit("Manager is not in firmware-file mode")
overlay = Path("/sys/kernel/config/device-tree/overlays") / f"gradiated-tiny-{stage}"
overlay.mkdir()
fd = os.open(overlay / "dtbo", os.O_WRONLY | os.O_NOFOLLOW)
try:
    if os.write(fd, payload) != len(payload):
        raise SystemExit("Short overlay write")
finally:
    os.close(fd)
if (overlay / "status").read_text().strip() != "applied":
    raise SystemExit("Overlay is not applied")
PY
}

apply_overlay 20s clock
apply_overlay 60s program
apply_overlay 20s interface
~~~

## Time, evidence and recovery

Allow up to five minutes for the privileged baseline and setup after inputs are available, with the per-stage bounds above. Allow ten minutes each for inbound staging if needed and outbound evidence export, with a total limit of 30 minutes for one attempt. Record before/after snapshots, stdout, stderr, exit status, monotonic time, pins and hashes for each stage and any interrupted command. Export the full diagnostic archive by numbered UART frames with a byte count and SHA-256, verifying both sides. Keep it with the immutable attempt record on the Mac.

Stop at the first failed gate and preserve the board state and diagnostics. Leave the clock enabled while the custom image may be live. Removing the programming overlay cannot restore the bitstream or the earlier AFI and clock state. The historical route has no verified live inverse. If stock restoration is needed, have Aidan supervise a full power cycle after a controlled shutdown if the board responds. Disconnect both the 12 V supply and USB to avoid back-power, then boot normally with the preserved SD and QSPI and inspect the stock firmware, services, overlays, clocks, taint and device ownership. A failed UART capture is a reason to diagnose and recover the evidence before considering any subsequent write.

## Private sudo handoff

After review, run /usr/bin/screen -r 12728.ttys003.Aidans-MacBook-Pro in Mac Terminal if the session ID still matches screen -ls. At the authenticated Kria shell, run the commands below and enter the password privately if sudo requests it. This tests the same controlling terminal and the same timeout and noninteractive sudo path the agent will use. A successful probe prints UID 0. Detach the exact session from a separate Mac Terminal with /usr/bin/screen -d 12728.ttys003.Aidans-MacBook-Pro, provided the session ID still matches screen -ls. Tell the agent when the handoff is complete. The agent first confirms the detached session and repeats the bounded UID check on that same UART console. The sudo timestamp may expire or differ with TTY or session changes. A denial returns to private handoff before any privileged command. Credentials stay with the operator.

~~~sh
tty
sudo -v
/usr/bin/timeout -k 2s 5s /usr/bin/sudo -n /usr/bin/id -u
~~~

The first privileged command after that test is the read-only baseline capture. The stock-to-project commands above remain a separate reviewed stage.
