"""One on-chip KV260 comparison with verified original firmware and weight restoration."""
from contextlib import contextmanager
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

from measurement import (CASES, CONTROL_REPLAY, HOMOGENEOUS_REPLIES, MEASUREMENT_SECONDS, MODES,
                         REQUEST_NS, RESTORE_SECONDS, SESSIONS, mixed_order)

HERE = Path(__file__).resolve().parent
PROJECT_UIO = "gradiated-tiny-transformer-v1"
CLOCK = "gradiated-tiny-clock"
INTERFACE = "gradiated-tiny-interface"
STOCK_PROGRAM = "gradiated-tiny-program"
TAINT = "12288"
STATIC_STATE = ("boot_id", "kernel", "model", "ethernet_carrier", "manager", "dfx", "taint")
NOTICE = "OF: overlay: WARNING: memory leak will occur if overlay removed, property: "
EXPECTED_NOTICES = (
    NOTICE + "/fpga-region/firmware-name", NOTICE + "/fpga-region/resets",
    *(NOTICE + f"/{bus}/{key}" for bus in ("axi", "amba") for key in ("#address-cells", "#size-cells")),
)
ABSENT = tuple(map(Path, (
    "/sys/module/kv260_ddr4_weights", "/dev/kv260-ddr4-weights",
    "/sys/firmware/devicetree/base/axi/ddr4-weights@a0000060",
)))


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def interrupted(signum, _frame):
    raise InterruptedError(f"Lifecycle interrupted by {signal.Signals(signum).name}")


def temperatures():
    started = time.monotonic_ns()
    sources = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone[0-9]*")):
        sources.append((zone/"temp", zone/"type", zone.name))
    for hwmon in sorted(Path("/sys/class/hwmon").glob("hwmon[0-9]*")):
        try:
            name = (hwmon/"name").read_text().strip()
        except OSError:
            name = hwmon.name
        for temp in sorted(hwmon.glob("temp[0-9]*_input")):
            stem = temp.name.removesuffix("_input")
            sources.append((temp, hwmon/f"{stem}_label", f"{name}/{stem}"))

    rows = []
    for data, label, fallback in sources:
        begin = time.monotonic_ns()
        try:
            name = label.read_text().strip() or fallback
        except OSError:
            name = fallback
        row = {"path":str(data), "label":name, "unit":"millidegrees Celsius", "begin_ns":begin}
        try:
            row["value"] = int(data.read_text().strip())
        except (OSError, ValueError) as error:
            row["unavailable"] = str(error)
        row["end_ns"] = time.monotonic_ns()
        rows.append(row)
    return {"begin_ns":started, "end_ns":time.monotonic_ns(), "sensors":rows}


@contextmanager
def owner_lock(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        ss = os.fstat(fd)
        require(stat.S_ISREG(ss.st_mode) and ss.st_uid == 0 and ss.st_mode & 0o022 == 0,
                "Unexpected board ownership lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def node_mode(path):
    metadata = path.lstat()
    require(stat.S_ISCHR(metadata.st_mode), f"{path} is not a device node")
    return (metadata.st_uid, metadata.st_gid, stat.S_IMODE(metadata.st_mode))


def project_uio(state):
    nodes = [name for name, label in state["uio"].items() if label == PROJECT_UIO]
    require(len(nodes) == 1 and re.fullmatch(r"uio\d+", nodes[0]), "Project UIO identity is ambiguous")
    node = Path("/dev") / nodes[0]
    maps = Path("/sys/class/uio") / nodes[0] / "maps/map0"
    require(int((maps/"addr").read_text(), 0) == 0xa0000000 and
            int((maps/"size").read_text(), 0) == 4096, "Project UIO geometry differs")
    return node


class Lifecycle:
    def __init__(self, config, output, setup, prior, verify, overlays):
        self.config, self.output = config, output
        self.setup, self.prior, self.verify, self.overlays = setup, prior, verify, overlays
        self.live = setup.live
        self.mode = "stock"
        self.installed = {}
        self.deadline = time.monotonic() + MEASUREMENT_SECONDS
        self.armed = False
        self.original_verified = False

    def command(self, label, argv, seconds, directory=None):
        directory = directory or self.output
        with (directory / f"{label}.stdout").open("xb") as stdout, (directory / f"{label}.stderr").open("xb") as stderr:
            save(directory / f"{label}.argv.json", argv)
            process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, cwd=HERE, start_new_session=True)
            try:
                status = process.wait(timeout=min(seconds, self.deadline-time.monotonic()))
            except BaseException:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=3)
                raise
        require(status == 0, f"{label} exited {status}. See captured stdout/stderr")
        return (directory / f"{label}.stdout").read_text()

    def snapshot(self, label, mode, strict=True, full=True):
        state = self.live.snapshot()
        captured = state if full else {k: v for k, v in state.items() if k != "dmesg"}
        save(self.output / f"{label}.state.json", captured)
        for key in STATIC_STATE:
            require(state[key] == self.baseline[key], f"{label}: board {key} changed")
        require(not any(state["ownership"].values()), f"{label}: existing UIO ownership")
        require(not any(path.exists() for path in ABSENT), f"{label}: DDR fixture present")
        self.setup.check_clock(state)
        if mode is not None:
            for key, value in self.overlays.state_spec(self.baseline, mode, True).items():
                require(state[key] == value, f"{label}: unexpected {key}")
            filename, _ = self.overlays.image_spec(mode)
            if mode == "stock":
                require(self.live.digest(self.setup.FIRMWARE) == self.setup.FIRMWARE_SHA,
                        "Original firmware identity differs")
            else:
                self.overlays.pinned(self.setup.FIRMWARE.parent / filename, self.config["pins"][filename])
                require(node_mode(project_uio(state)) == (0, 0, 0o600), "Comparison UIO must be root-only")
        if strict:
            self.check_notices(self.last, state)
        self.last = state
        return state

    def check_notices(self, before, after):
        result = after["warnings"]
        old = before["warnings"]
        require(result.startswith(old), "Lost kernel warning continuity")
        additions = [line.split("]", 1)[-1].lstrip() for line in result[len(old):].splitlines()]
        require(set(additions) <= set(EXPECTED_NOTICES), f"Unexpected kernel notices: {additions}")

    def apply(self, name, data, label, seconds):
        pin = self.overlays.file_pin(data)["sha256"]
        self.command(f"{label}-apply-{name}", [sys.executable, "-I", "-B", "-c", self.setup.WRITE_OVERLAY,
                     str(self.live.MANAGER / "flags"), str(self.live.OVERLAYS / name), data.hex(), pin], seconds)

    def remove(self, name, label):
        self.command(f"{label}-remove-{name}", ["/usr/bin/rmdir", str(self.live.OVERLAYS / name)], 15)

    def asset(self, name):
        return self.overlays.pinned(HERE / name, self.config["pins"][name])

    def bos(self, label, run):
        original = self.prior.ORIGINAL
        argv = [sys.executable, "-I", "-B", str(original / "board_bos.py"), "--bundle", str(original)]
        if run:
            argv.append("--run-bos")
        values = json.loads(self.command(label, argv, 45 if run else 15))
        if run:
            checked = self.verify.check_bos(values, self.models[0])
            require(checked["scores"] == 320, "Unexpected original BOS verification coverage")
        else:
            require(self.prior.inspect_ok(values), "Sealed original inspection failed")
            checked = {"ready": True}
        save(self.output / f"{label}.checks.json", checked)

    def preflight(self):
        import board_resident as resident
        import energy_validation as energy
        import observer_validation as validation

        for name in self.config["pins"]:
            require(Path(name).name == name, "Staged asset escaped the sealed directory")
            self.asset(name)
        self.baseline = self.last = self.live.snapshot()
        save(self.output / "admission.state.json", self.baseline)
        anchor = self.config["restoration_anchor"]
        restored = json.loads(self.asset(anchor["state"]))
        outcome = json.loads(self.asset(anchor["outcome"]))
        require(outcome == {"experiment_passed": True, "restored": True} and
                self.baseline["boot_id"] == self.config["boot"] and
                self.baseline["taint"] == TAINT and
                self.baseline["model"] == "ZynqMP KV260 revB" and
                self.baseline["ethernet_carrier"] == "0" and
                self.baseline["manager"] == {"flags": "0", "state": "operating", "status": ""} and
                "ActiveState=inactive" in self.baseline["dfx"]["stdout"],
                "Expected same restored boot, known taint, board and manager state")
        for key in (*STATIC_STATE, "overlays", "firmware_name", "uio", "bindings"):
            require(self.baseline[key] == restored[key], f"Original {key} differs from Experiment 17 restoration")
        self.overlays.notices(restored, self.baseline)
        for mode in MODES:
            firmware = self.setup.FIRMWARE.parent / self.overlays.image_spec(mode)[0]
            require(not firmware.exists() and not firmware.is_symlink(), f"Temporary firmware already exists: {firmware}")
        self.original_modes = node_mode(project_uio(self.baseline))
        self.stock_data = {}
        for name in ("program", "interface"):
            size, digest = self.setup.OVERLAY_PINS[name]
            self.stock_data[name] = self.overlays.pinned(self.live.ORIGINAL / f"kv260-{name}.dtbo",
                                                        {"bytes": size, "sha256": digest})
        self.models = self.verify.load_inputs(self.prior.ORIGINAL, self.prior.CANDIDATE, self.prior.ACCEPTANCE)
        path = HERE / "stock_sampler.py"
        sampler = energy.source(path, self.config["pins"][path.name]["sha256"])
        sensor = sampler.state()
        require(sensor["health"][2] == TAINT, "Original INA260 boot taint marker differs")
        normalized = {**sensor, "health": [*sensor["health"]]}
        normalized["health"][2] = "0"
        validation.check_stock_sensor(normalized, sampler, self.baseline, self.overlays)
        save(self.output / "original-sensor.json", sensor)
        save(self.output / "spi-identity.json", energy.check_spi_identity())
        self.bos("original-inspection", False)
        self.bos("original-before", True)
        self.snapshot("original-ready", "stock")
        self.config["bundle_pins"] = {
            mode: self.overlays.prepare_bundle(self.prior.CANDIDATE, HERE, HERE / f"fixture-bundle-{mode}",
                                               resident, self.config["pins"], mode)
            for mode in MODES
        }

    def remove_installed(self):
        for firmware, identity in self.installed.items():
            self.overlays.pinned(firmware, self.config["pins"][firmware.name])
            info = firmware.lstat()
            require((info.st_dev, info.st_ino) == identity, "Temporary firmware identity changed")
            firmware.unlink()

    def replace_program(self, label, destination, state, recovering=False):
        filename, program = self.overlays.image_spec(destination)
        programs = {self.overlays.image_spec(mode)[1] for mode in (*MODES, "stock")}
        names = set(state["overlays"])
        require(CLOCK in names and names <= {CLOCK, INTERFACE, *programs} and len(names & programs) <= 1,
                f"{label}: unexpected overlay geometry")
        if INTERFACE in names:
            self.remove(INTERFACE, label)
            state = self.snapshot(f"{label}-interface-removed", None, strict=not recovering)
            require(INTERFACE not in state["overlays"], f"{label}: original interface survived removal")
        for current in names & programs:
            self.remove(current, label)
        bare = self.snapshot(f"{label}-before-program", None, strict=not recovering)
        require(bare["overlays"] == {CLOCK: "applied"} and bare["firmware_name"] is None and
                PROJECT_UIO not in bare["uio"].values(), f"{label}: previous program not fully removed")
        if destination == "stock":
            require(self.live.digest(self.setup.FIRMWARE) == self.setup.FIRMWARE_SHA,
                    "Stock firmware digest differs before reapply")
            program_data = self.stock_data["program"]
        else:
            fw = self.setup.FIRMWARE.parent / filename
            self.overlays.pinned(fw, self.config["pins"][filename])
            info = fw.lstat()
            require((info.st_dev, info.st_ino) == self.installed[fw], "Installed firmware identity changed")
            program_data = self.asset(self.overlays.image_overlay(destination))
        self.apply(program, program_data, label, 60)
        programmed = self.snapshot(f"{label}-programmed", None, strict=not recovering)
        require(programmed["overlays"] == dict.fromkeys((CLOCK, program), "applied") and
                programmed["firmware_name"] == filename and PROJECT_UIO not in programmed["uio"].values(),
                f"{label}: image or interface state after programming differs")
        self.apply(INTERFACE, self.stock_data["interface"], label, 20)
        self.command(f"{label}-settle-uio", ["/usr/bin/udevadm", "settle", "--timeout=5"], 6)
        attached = self.snapshot(f"{label}-attached", None, strict=not recovering)
        uio = project_uio(attached)
        uid, gid, mode = self.original_modes if destination == "stock" else (0, 0, 0o600)
        if node_mode(uio) != (uid, gid, mode):
            os.chown(uio, uid, gid)
            os.chmod(uio, mode)
        require(node_mode(uio) == (uid, gid, mode), f"{label}: UIO permissions differ")
        self.mode = destination
        self.snapshot(f"{label}-ready", destination, strict=not recovering)
        return filename

    def arm(self, label, mode, index, smoke=False, homogeneous=None):
        require(mode == self.mode, "Arm firmware role differs")
        self.snapshot(f"{label}-before", mode, full=False)
        save(self.output / f"{label}-before.temperatures.json", temperatures())
        arm_timeout_s = 30 + 5 * (HOMOGENEOUS_REPLIES[homogeneous] + 1) if homogeneous else 120
        cfg = self.output / f"{label}.config.json"
        save(cfg, {**self.config, "arm_timeout_s": arm_timeout_s})
        directory = self.output / label
        argv = [sys.executable, "-B", str(HERE / "bench_fixture.py"), str(cfg), str(directory), mode, str(index)]
        if smoke:
            argv.append("--smoke")
        if homogeneous:
            argv.extend(("--homogeneous", homogeneous))
        try:
            self.command(label, argv, arm_timeout_s + 4)
        finally:
            save(self.output / f"{label}-after.temperatures.json", temperatures())
        self.snapshot(f"{label}-after", mode, full=False)
        if smoke:
            rows = json.loads((directory / "smoke.json").read_text())["requests"]
            replies = [row["observed"]["header"] for row in rows]
            require(len(replies) == 3 and all(0 < r["done_ns"] - r["admitted_ns"] <= REQUEST_NS // 3
                                              for r in replies), "Smoke reply exceeds frozen margin")
        print(label, "passed", flush=True)

    def measure(self):
        save(self.output / "watchdog.json",
             {"request_timeout_ns": REQUEST_NS, "run_timeout_s": MEASUREMENT_SECONDS, "restore_timeout_s": RESTORE_SECONDS})
        save(self.output / "entry.temperatures.json", temperatures())
        for mode in MODES:
            filename, _ = self.overlays.image_spec(mode)
            fw = self.setup.FIRMWARE.parent / filename
            self.overlays.install_observer(HERE / filename, self.config["pins"][filename], fw)
            info = fw.lstat()
            self.installed[fw] = (info.st_dev, info.st_ino)
        for session, mode, rounds, series, cases, smoke in SESSIONS:
            if mode != self.mode:
                state = self.snapshot(f"{session}-switch-entry", self.mode)
                self.armed = True
                self.replace_program(session, mode, state)
            if smoke:
                self.arm(f"smoke-{session}-{mode}", mode, rounds[0], smoke=True)
            for index in rounds:
                self.arm(f"p{index}-{mode}", mode, index)
            for case in cases:
                self.arm(f"homogeneous-p{series}-{case}-{mode}", mode, series, homogeneous=case)

    def restore(self):
        self.deadline = time.monotonic() + RESTORE_SECONDS
        entry = self.snapshot("restore-entry", None, strict=False)
        self.replace_program("restore", "stock", entry, recovering=True)
        self.bos("original-after", True)
        save(self.output / "exit.temperatures.json", temperatures())
        restored = self.snapshot("restored", "stock", strict=False)
        self.original_verified = True
        self.remove_installed()
        self.check_notices(entry, restored)


def supervise(config, output):
    import kv260_accept as accept
    import observer_lifecycle as overlays
    import resident_validation as prior

    require(sys.platform == "linux" and os.geteuid() == 0, "Root on the admitted board required")
    require(config["arm_kind"] == "on-chip" and set(config["replay"]) == set(MODES),
            "Expected matched on-chip comparison")
    require(config["boot"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip(), "Board boot differs")
    require(all(set(config["replay"][mode]) == set(CASES) for mode in MODES), "Replay cases differ")
    require({case: value["cycles"] for case, value in config["replay"]["control"].items()} == CONTROL_REPLAY,
            "Exact historical control cycle constants differ")
    stage = HERE.lstat()
    require(stage.st_uid == 0 and stat.S_ISDIR(stage.st_mode) and stat.S_IMODE(stage.st_mode) & 0o077 == 0,
            "Unsafe board staging directory")
    setup = accept.pinned_module(prior.SETUP_HELPER, prior.SETUP_PIN)
    verify = prior.load_pinned(prior.ACCEPTANCE / "kv260_accept_checks.py", prior.CHECKS_PIN)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    with owner_lock(setup.LOCK):
        output.mkdir(mode=0o700)
        owner = Lifecycle(config, output, setup, prior, verify, overlays)
        result = {"experiment_passed": False, "restored": False}
        try:
            save(output / "intent.json", {"sessions": SESSIONS, "homogeneous_timed_replies": HOMOGENEOUS_REPLIES,
                                         "mixed_rounds": {i: mixed_order(i) for i in range(1, 5)},
                                         "configuration": config})
            owner.preflight()
            owner.measure()
            result["experiment_passed"] = True
        except BaseException as error:
            result["experiment_error"] = f"{type(error).__name__}: {error}"
        finally:
            try:
                if owner.armed:
                    owner.restore()
                    result["restored"] = True
                else:
                    owner.remove_installed()
                    result["original_untouched"] = True
            except BaseException as error:
                result["restored"] = owner.original_verified
                result["restore_error"] = f"{type(error).__name__}: {error}"
                try:
                    save(output / "restore-failure.state.json", setup.live.snapshot())
                except Exception as diagnostic:
                    result["diagnostic_error"] = str(diagnostic)
            save(output / "outcome.json", result)
        print(json.dumps(result), flush=True)
        return 0 if result == {"experiment_passed": True, "restored": True} else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    raise SystemExit(supervise(json.loads(args.config.read_text()), args.output.resolve()))
