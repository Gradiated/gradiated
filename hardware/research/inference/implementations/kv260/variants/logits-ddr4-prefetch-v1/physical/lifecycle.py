"""Board owner for one Experiment 17 DDR4 comparison and restoration."""
from contextlib import contextmanager
import argparse
import errno
import fcntl
import json
import mmap
import os
from pathlib import Path
import re
import signal
import stat
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
MODULE = "kv260_ddr4_weights"
MODULE_SYS = Path("/sys/module") / MODULE
DRIVER_SYS = Path("/sys/bus/platform/drivers/kv260-ddr4-weights")
WEIGHTS = Path("/dev/kv260-ddr4-weights")
PROJECT_UIO = "gradiated-tiny-transformer-v1"
CLOCK, ORIGINAL_PROGRAM, ORIGINAL_INTERFACE = (
    "gradiated-tiny-clock", "gradiated-tiny-program", "gradiated-tiny-interface")
FIXTURE_PROGRAM, FIXTURE_INTERFACE, FIXTURE_DMA, AFI_RESTORE = (
    "gradiated-tiny-ddr4-program", "gradiated-tiny-ddr4-interface", "gradiated-tiny-ddr4-dma",
    "gradiated-tiny-ddr4-afi-restore")
from measurement import MODES, SESSIONS

RETAINED_TAINT = "12288"
OF_NOTICE = "OF: overlay: WARNING: memory leak will occur if overlay removed, property: "
PROGRAM_WARNINGS = (OF_NOTICE + "/fpga-region/firmware-name", OF_NOTICE + "/fpga-region/resets")
AMBA_WARNINGS = (OF_NOTICE + "/axi/#address-cells", OF_NOTICE + "/axi/#size-cells",
                 OF_NOTICE + "/amba/#address-cells", OF_NOTICE + "/amba/#size-cells")
MODULE_WARNINGS = (
    MODULE + ": loading out-of-tree module taints kernel.",
    MODULE + ": module verification failed: signature and/or required key missing - tainting kernel",
)
STATIC_STATE = ("boot_id", "kernel", "model", "ethernet_carrier", "manager", "dfx")


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


def no_references(device):
    """The shared setup snapshot checks UIO; also check the temporary misc device."""
    if not device.exists():
        return
    for process in Path("/proc").iterdir():
        if not process.name.isdecimal():
            continue
        try:
            for handle in (process / "fd").iterdir():
                try:
                    target = os.readlink(handle)
                except FileNotFoundError:
                    continue
                require(target not in (str(device), str(device) + " (deleted)"),
                        f"PID {process.name} retains the DDR device")
        except (FileNotFoundError, ProcessLookupError):
            continue


def direct_dma_state(candidate):
    root = Path("/sys/firmware/devicetree/base")
    axi = root/"axi"
    device = axi/"ddr4-weights@a0000060"
    require((root/"__symbols__/amba").read_bytes() == b"/axi\0" and
            (root/"__symbols__/smmu").read_bytes() == b"/axi/iommu@fd800000\0" and
            (axi/"iommu@fd800000/status").read_bytes() == b"disabled\0",
            "The reviewed nonsecure direct route's live DT identity differs")
    require((axi/"ranges").read_bytes() == b"" and not (axi/"dma-ranges").exists() and
            not (root/"dma-ranges").exists(), "A DMA ancestor changes the reviewed identity mapping")
    if candidate:
        require((device/"compatible").read_bytes() == b"gradiated,kv260-ddr4-logits-v1\0" and
                (device/"reg").read_bytes() == struct.pack(">4I",0,0xa0000060,0,0x30) and
                (device/"gradiated,verified-direct-dma").read_bytes() == b"" and
                not (device/"iommus").exists() and not (device/"dma-coherent").exists(),
                "Direct DMA companion device differs from the reviewed interface")
    else:
        require(not device.exists(), "Temporary DMA companion node already exists")
    return {"smmu":"/axi/iommu@fd800000", "smmu_status":"disabled", "axi_ranges":[],
            "dma_ranges_present":False, "direct_device":str(device) if candidate else None,
            "device_reg": [0xa0000060,0x30] if candidate else None}


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


def quiesced(data):
    return (data["magic"] == 0x44445233 and data["mode"] == "bram" and data["safe_release"] and
            not data["transport_busy"] and data["dma_bytes"] == 0 and int(data["hardware_base"], 16) == 0)


def release_weights(uio):
    from weights import Fixture

    with Fixture() as fixture:
        initial = fixture.state()
        if quiesced(initial):
            return {"initial": initial, "final":initial, "soft_reset":False}
        try:
            fixture.clear()
            reset = False
        except OSError as error:
            if error.errno != errno.EBUSY:
                raise
            # This is the fixture's model reset. The FPGA reader preserves
            # ARVALID and drains RLAST independently of the neural controller.
            require(node_mode(uio) == (0, 0, 0o600), "Recovery UIO permissions changed")
            require(initial["magic"] == 0x44445233, "Unexpected FPGA register contract")
            with uio.open("r+b", buffering=0) as device:
                with mmap.mmap(device.fileno(), 4096, access=mmap.ACCESS_WRITE) as registers:
                    registers[0x1c:0x20] = struct.pack("<I", 2)
                    require(struct.unpack_from("<I", registers, 0)[0] & 3 == 0,
                            "Soft reset did not clear the model and controller")
            reset = True
            deadline = time.monotonic() + 3
            while True:
                state = fixture.state()
                if state["safe_release"] and not state["transport_busy"]:
                    fixture.clear()
                    break
                require(time.monotonic() < deadline, f"Outstanding DMA did not drain: {state}")
                time.sleep(.01)
        final = fixture.state()
        require(quiesced(final), f"DMA buffer remains owned: {final}")
        return {"initial":initial, "final":final, "soft_reset":reset}


class Lifecycle:
    def __init__(self, config, output, setup, prior, verify, overlays):
        self.config, self.output = config, output
        self.setup, self.prior, self.verify, self.overlays = setup, prior, verify, overlays
        self.live = setup.live
        self.firmware = None
        self.installed = {}
        self.deadline = time.monotonic() + 1800
        self.armed = False
        self.driver_admitted = False
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

    def snapshot(self, label, names=None, warnings=(), strict=True):
        state = self.live.snapshot()
        save(self.output / f"{label}.state.json", state)
        for key in STATIC_STATE:
            require(state[key] == self.baseline[key], f"{label}: board {key} changed")
        require(not any(state["ownership"].values()), f"{label}: existing UIO ownership")
        no_references(WEIGHTS)
        require(state["taint"] == RETAINED_TAINT, f"{label}: kernel taint differs from admitted Experiment 16 restoration")
        self.setup.check_clock(state)
        if names is not None:
            require(state["overlays"] == dict.fromkeys(names, "applied"), f"{label}: overlays differ")
        if strict:
            self.overlays.notices(self.last, state, warnings)
        self.last = state
        return state

    def original(self, state):
        for key in ("firmware_name", "overlays", "uio", "bindings"):
            require(state[key] == self.baseline[key], f"Original {key} did not restore")
        require(self.live.digest(self.setup.FIRMWARE) == self.setup.FIRMWARE_SHA, "Original firmware digest drifted")

    def fixture(self, label):
        state = self.snapshot(label, (CLOCK, FIXTURE_PROGRAM, FIXTURE_INTERFACE, FIXTURE_DMA))
        require(state["firmware_name"] == self.firmware.name and self.live.digest(self.firmware) ==
                self.config["pins"][self.firmware.name]["sha256"], "Fixture firmware differs")
        require(state["bindings"] == self.baseline["bindings"] and state["uio"] == self.baseline["uio"],
                "Fixture bindings or UIO identity differ")
        require(node_mode(project_uio(state)) == (0, 0, 0o600), "UIO requires root-only access")
        require(DRIVER_SYS.joinpath("a0000060.ddr4-weights").is_symlink() and
                node_mode(WEIGHTS) == (0, 0, 0o600), "DMA driver binding or permissions differ")
        misc = Path("/sys/class/misc") / WEIGHTS.name
        dev = WEIGHTS.stat()
        require((misc/"dev").read_text().strip() == f"{os.major(dev.st_rdev)}:{os.minor(dev.st_rdev)}"
                and int(state["taint"]) == self.config["fixture_taint"],
                "DDR misc device number or approved kernel taint differs")
        self.readback(label, "candidate")

    def asset(self, name):
        return self.overlays.pinned(HERE / name, self.config["pins"][name])

    def apply(self, name, data, seconds=20, label=None):
        checksum = self.overlays.file_pin(data)["sha256"]
        prefix = label + "-" if label else ""
        self.command(prefix + "apply-" + name, [sys.executable, "-I", "-B", "-c", self.setup.WRITE_OVERLAY,
                     str(self.live.MANAGER/"flags"), str(self.live.OVERLAYS/name), data.hex(), checksum], seconds)

    def remove(self, name, label=None):
        self.command("remove-"+(label or name), ["/usr/bin/rmdir", str(self.live.OVERLAYS/name)], 15)

    def readback(self, label, stage):
        argv = [sys.executable, "-I", "-B", str(HERE/"readback.py"), stage]
        baseline = self.output/"hp0-baseline.json"
        if stage != "baseline":
            argv += ["--baseline", str(baseline)]
        data = json.loads(self.command("hp0-"+label, argv, 5))
        require(data["fpd_reset"] == 0xe0032, "Live FPD reset register differs")
        if stage == "baseline":
            save(baseline, data)
        return data

    def bos(self, label, flags, timeout):
        original = self.prior.ORIGINAL
        values = json.loads(self.command(label, [sys.executable, "-I", "-B", str(original/"board_bos.py"),
                            "--bundle", str(original), *flags], timeout))
        if flags:
            checked = self.verify.check_bos(values, self.models[0])
        else:
            require(self.prior.inspect_ok(values), "Sealed original inspection failed")
            checked = {"ready": True}
        save(self.output / f"{label}.checks.json", checked)
        return checked

    def preflight(self):
        from bench_fixture import prepare_bundle
        import energy_validation as energy
        import observer_validation as validation

        for name, pin in self.config["pins"].items():
            require(Path(name).name == name, "Staged asset escaped the sealed directory")
            self.overlays.pinned(HERE/name, pin)
        self.afi_restore = self.asset(self.config["afi_restore_overlay"])
        self.baseline = self.last = self.live.snapshot()
        save(self.output/"admission.state.json", self.baseline)
        require(self.baseline["boot_id"] == self.config["boot"] and
                self.baseline["manager"] == {"flags":"0", "state":"operating", "status":""},
                "Original boot or FPGA manager does not match admission")
        project = self.config["project_state"]
        admission = self.verify.read_json(validation.validate_board_config_path(project["board_path"]),project["sha256"])
        anchor = self.config["restoration_anchor"]
        restored = json.loads(self.overlays.pinned(HERE / anchor["state"], self.config["pins"][anchor["state"]]))
        outcome = json.loads(self.overlays.pinned(HERE / anchor["outcome"], self.config["pins"][anchor["outcome"]]))
        require(outcome == {"experiment_passed": True, "restored": True} and
                restored["taint"] == self.baseline["taint"] == RETAINED_TAINT,
                "Verified Experiment 16 restoration and same-boot module taint required")
        for key in (*STATIC_STATE, "overlays", "firmware_name", "uio", "bindings"):
            require(self.baseline[key] == restored[key], f"Original {key} differs from Experiment 16 restoration")
        self.overlays.notices(restored, self.baseline, ())
        self.overlays.check_state({**self.baseline, "taint": "0"}, admission, "stock")
        require("ActiveState=inactive" in self.baseline["dfx"]["stdout"] and
                self.baseline["model"] == "ZynqMP KV260 revB", "Board application ownership differs")
        require(not MODULE_SYS.exists() and not WEIGHTS.exists(), "Temporary module or device already exists")
        for arm in self.config["arms"].values():
            firmware = self.setup.FIRMWARE.parent / arm["firmware"]
            require(not firmware.exists() and not firmware.is_symlink(), "Temporary firmware already exists")
        require(not self.setup.FIRMWARE.is_symlink() and
                self.live.digest(self.setup.FIRMWARE) == self.setup.FIRMWARE_SHA, "Original firmware is not pinned")
        self.original_modes = node_mode(project_uio(self.baseline))
        self.stock_data = {}
        for name in ("program", "interface"):
            size, checksum = self.setup.OVERLAY_PINS[name]
            self.stock_data[name] = self.overlays.pinned(self.live.ORIGINAL/f"kv260-{name}.dtbo",
                                                       {"bytes":size,"sha256":checksum})
        self.models = self.verify.load_inputs(self.prior.ORIGINAL, self.prior.CANDIDATE, self.prior.ACCEPTANCE)
        expected_hp0 = json.loads(self.asset(anchor["hp0"]))
        require(self.readback("entry", "baseline") == expected_hp0,
                "Original HP0/FPD/SMMU words differ from Experiment 16 restoration")
        save(self.output/"original-direct-dma-dt.json",direct_dma_state(False))
        stock_path = HERE/"stock_sampler.py"
        stock_sampler = energy.source(stock_path,self.config["pins"][stock_path.name]["sha256"])
        sensor = stock_sampler.state()
        require(sensor["health"][2] == RETAINED_TAINT, "Original INA260 taint marker differs")
        normalized_sensor = {**sensor, "health": [*sensor["health"]]}
        normalized_sensor["health"][2] = "0"
        validation.check_stock_sensor(normalized_sensor, stock_sampler,
                                      {**self.baseline, "taint": "0"}, self.overlays)
        save(self.output/"original-sensor.json",sensor)
        save(self.output/"spi-identity.json",energy.check_spi_identity())
        self.bos("original-inspection", [], 15)
        self.setup.check_clock(self.baseline)
        self.bos("original-before", ["--run-bos"], 45)
        self.original(self.snapshot("original-ready", (CLOCK, ORIGINAL_PROGRAM, ORIGINAL_INTERFACE)))
        self.config["bundle_pins"] = {
            mode: prepare_bundle(self.config, HERE / f"fixture-bundle-{mode}", mode)
            for mode in MODES
        }

    def install(self, session, mode, state):
        arm = self.config["arms"][mode]
        self.firmware = self.setup.FIRMWARE.parent / arm["firmware"]
        if self.firmware not in self.installed:
            self.overlays.install_observer(HERE / self.firmware.name, self.config["pins"][self.firmware.name],
                                           self.firmware)
            info = self.firmware.stat()
            self.installed[self.firmware] = (info.st_dev, info.st_ino)
        self.armed = True
        if ORIGINAL_INTERFACE in state["overlays"]:
            self.remove(ORIGINAL_INTERFACE, session + "-original-interface")
            self.snapshot(session + "-original-interface-removed", (CLOCK, ORIGINAL_PROGRAM), AMBA_WARNINGS)
        if ORIGINAL_PROGRAM in state["overlays"]:
            self.remove(ORIGINAL_PROGRAM, session + "-original-program")
            self.snapshot(session + "-original-program-removed", (CLOCK,), PROGRAM_WARNINGS)
        self.snapshot(session + "-before-install", (CLOCK,))
        self.overlays.pinned(self.firmware, self.config["pins"][self.firmware.name])
        info = self.firmware.lstat()
        require((info.st_dev, info.st_ino) == self.installed[self.firmware] and stat.S_ISREG(info.st_mode),
                "Installed firmware identity changed before programming")
        self.apply(FIXTURE_PROGRAM, self.asset(arm["program_overlay"]), 60, session)
        self.snapshot(session + "-programmed", (CLOCK, FIXTURE_PROGRAM), PROGRAM_WARNINGS)
        self.apply(FIXTURE_INTERFACE, self.asset(self.config["interface_overlay"]), label=session)
        state = self.snapshot(session + "-interface-applied", (CLOCK, FIXTURE_PROGRAM, FIXTURE_INTERFACE), AMBA_WARNINGS)
        self.command(session + "-settle-uio", ["/usr/bin/udevadm", "settle", "--timeout=5"], 6)
        uio = project_uio(state)
        os.chown(uio, 0, 0)
        os.chmod(uio, 0o600)
        require(node_mode(uio) == (0, 0, 0o600), "Failed to constrain project UIO")
        self.readback(session + "-configured", "candidate")
        self.apply(FIXTURE_DMA, self.asset(self.config["dma_overlay"]), label=session)
        self.snapshot(session + "-dma-device-applied", (CLOCK, FIXTURE_PROGRAM, FIXTURE_INTERFACE, FIXTURE_DMA), AMBA_WARNINGS)
        save(self.output / (session + "-direct-dma-dt.json"), direct_dma_state(True))
        module = HERE / self.config["driver"]
        self.asset(module.name)
        self.command(session + "-insert-driver", ["/usr/sbin/insmod", str(module)], 10)
        self.snapshot(session + "-driver-inserted", (CLOCK, FIXTURE_PROGRAM, FIXTURE_INTERFACE, FIXTURE_DMA), MODULE_WARNINGS)
        self.fixture(session + "-ready")
        self.driver_admitted = True
        status = self.command(session + "-driver-status", [
            sys.executable, "-I", "-B", str(HERE / "weights.py"), "status"], 5)
        require(quiesced(json.loads(status)), "DDR device CLI did not return the idle fixture contract")
        self.command(session + "-verify-initial-release",
                     [sys.executable, "-B", str(Path(__file__)), "--release", str(uio)], 8)

    def measure(self):
        from measurement import HOMOGENEOUS_REPLIES
        deadline = {"request_timeout_ns": 5_000_000_000, "arm_timeout_s": 120}
        save(self.output / "watchdog.json", deadline)
        for session, mode, rounds, homogeneous_round, prompts, smoke in SESSIONS:
            if session != "B2":
                state = self.snapshot(session + "-switch-entry", strict=False)
                if session != "A1":
                    state = self.release_ddr(state, session + "-switch")
                self.install(session, mode, state)
            if smoke:
                block = self.arm(f"smoke-{session}-{mode}", mode, rounds[0], deadline, True)
                times = [r["observed"]["header"]["done_ns"] - r["observed"]["header"]["admitted_ns"]
                         for r in block["requests"]]
                require(len(times) == 3 and all(0 < delta <= 5_000_000_000 // 3 for delta in times),
                        "Smoke reply exceeds the frozen margin")
            for n in rounds:
                self.arm(f"p{n}-{mode}", mode, n, deadline, False)
            for case in prompts:
                requests = HOMOGENEOUS_REPLIES[case]+1
                policy = {**deadline, "arm_timeout_s": 30 + 5 * requests}
                self.arm(f"homogeneous-p{homogeneous_round}-{case}-{mode}", mode,
                         homogeneous_round, policy, False, homogeneous=case)

    def arm(self, label, mode, pair, watchdog, smoke, homogeneous=None):
        require(self.firmware.name == self.config["arms"][mode]["firmware"], "Arm firmware differs")
        self.fixture(label + "-before")
        save(self.output/(label+"-before.temperatures.json"),temperatures())
        cfg = self.output/(label+".config.json")
        save(cfg, {**self.config, **watchdog})
        directory = self.output/label
        argv = [sys.executable,"-B",str(HERE/"bench_fixture.py"),str(cfg),str(directory),mode,str(pair)]
        if smoke:
            argv.append("--smoke")
        if homogeneous is not None:
            argv.extend(("--homogeneous",homogeneous))
        try:
            self.command(label, argv, watchdog["arm_timeout_s"]+4)
        finally:
            save(self.output/(label+"-after.temperatures.json"),temperatures())
        require(quiesced(json.loads((directory / "quiesced.json").read_text())), "Arm did not release its buffer")
        self.fixture(label + "-after")
        print(label, "passed", flush=True)
        if smoke:
            return json.loads((directory/"smoke.json").read_text())

    def release_ddr(self, state, label, strict_warnings=True):
        original_warnings = state["warnings"]
        require(MODULE_SYS.exists() or not self.driver_admitted,
                "Admitted module disappeared before proving DMA release")
        if MODULE_SYS.exists():
            if WEIGHTS.exists():
                uio = project_uio(state)
                result = self.command(label + "-release-weights", [sys.executable,"-B",str(Path(__file__)),
                                      "--release", str(uio)], 8)
                require(quiesced(json.loads(result)["final"]), "No proved DMA quiesce; preserve fixture state")
            else:
                require(not DRIVER_SYS.joinpath("a0000060.ddr4-weights").exists() and
                        not self.driver_admitted,
                        "DMA device disappeared while the driver might own a buffer")
            self.driver_admitted = False
            self.command(label + "-unload-driver", ["/usr/sbin/rmmod",MODULE], 12)
            require(not MODULE_SYS.exists() and not WEIGHTS.exists(), "Temporary driver persists")
        require(not WEIGHTS.exists(), "DMA node survives without a known driver")
        self.driver_admitted = False
        for name in (FIXTURE_DMA,FIXTURE_INTERFACE,FIXTURE_PROGRAM,AFI_RESTORE):
            if name in state["overlays"]:
                self.remove(name, label + "-" + name)
                state = self.snapshot(label + "-removed-" + name, strict=False)
                require(name not in state["overlays"], f"{name} survived removal")
        hf = self.output/"hp0-baseline.json"
        if hf.exists():
            previous = json.loads(hf.read_text())
            argv = [sys.executable,"-I","-B",str(HERE/"readback.py"),"restored","--baseline",str(hf)]
            # The restored comparison may exit nonzero when width changes are
            # expected. The complete readback is still recorded before acting.
            try:
                self.command(label + "-hp0-before-restore",argv,5)
            except RuntimeError:
                actual = json.loads((self.output / (label + "-hp0-before-restore.stdout")).read_text())
                expect = {**previous, "hp0_read":(previous["hp0_read"] & ~3) | 1,
                          "hp0_write":(previous["hp0_write"] & ~3) | 1}
                require(actual == expect, "HP0 changed beyond the two planned width fields")
                self.command(label + "-apply-afi-restore",
                             [sys.executable, "-I", "-B", "-c", self.setup.WRITE_OVERLAY,
                              str(self.live.MANAGER / "flags"), str(self.live.OVERLAYS / AFI_RESTORE),
                              self.afi_restore.hex(), self.config["pins"][self.config["afi_restore_overlay"]]["sha256"]], 20)
                self.readback(label + "-width-restored", "restored")
                self.remove(AFI_RESTORE, label + "-completed-afi-restore")
                state = self.snapshot(label + "-afi-restored", strict=False)

        current_warnings = state["warnings"]
        continuous = current_warnings.startswith(original_warnings)
        known = set(PROGRAM_WARNINGS + AMBA_WARNINGS)
        suffix = current_warnings[len(original_warnings):] if continuous else current_warnings
        messages = [line.split("]", 1)[-1].lstrip() for line in suffix.splitlines()]
        unexpected = [m for m in messages if m not in known]
        save(self.output / (label + "-ddr-teardown-warnings.json"),
             {"continuous": continuous, "known": [m for m in messages if m in known], "unexpected": unexpected})
        if strict_warnings:
            require(continuous, "DDR teardown lost kernel warning continuity")
            require(not unexpected, "Unexpected kernel warning during DDR teardown")
        return state

    def restore(self):
        self.deadline = time.monotonic() + 180
        restore_start = self.snapshot("restore-entry", strict=False)
        state = restore_start
        allowed = {CLOCK, ORIGINAL_PROGRAM, ORIGINAL_INTERFACE, FIXTURE_PROGRAM,
                   FIXTURE_INTERFACE, FIXTURE_DMA, AFI_RESTORE}
        require(set(state["overlays"]) <= allowed and state["overlays"].get(CLOCK) == "applied",
                "Unexpected overlays during restoration")
        state = self.release_ddr(state, "restore", strict_warnings=False)
        for key,name in (("program",ORIGINAL_PROGRAM),("interface",ORIGINAL_INTERFACE)):
            if state["overlays"].get(name) != "applied":
                if name in state["overlays"]:
                    self.remove(name)
                self.apply(name,self.stock_data[key],60 if key=="program" else 20)
                state = self.snapshot("original-"+key+"-restored", strict=False)
                require(state["overlays"].get(name) == "applied", f"Original {key} did not apply")
        self.original(state)
        self.command("settle-original-uio", ["/usr/bin/udevadm", "settle", "--timeout=5"], 6)
        uio = project_uio(state)
        uid,gid,mode = self.original_modes
        if node_mode(uio) != self.original_modes:
            os.chown(uio, uid, gid)
            os.chmod(uio, mode)
        require(node_mode(uio) == self.original_modes, "Original UIO permissions were not restored")
        self.bos("original-after", ["--run-bos"], 45)
        self.readback("exit","restored")
        save(self.output/"restored-direct-dma-dt.json",direct_dma_state(False))
        restored = self.snapshot("restored", (CLOCK, ORIGINAL_PROGRAM, ORIGINAL_INTERFACE), strict=False)
        self.original(restored)
        self.remove_staged_firmware()
        self.original_verified = True
        old, current = restore_start["warnings"], restored["warnings"]
        require(current.startswith(old), "Restoration kernel-warning anchor was lost")
        expected = set(PROGRAM_WARNINGS + AMBA_WARNINGS)
        additions = [line.split("]",1)[-1].lstrip() for line in current[len(old):].splitlines()]
        save(self.output/"restore-warnings.json", {"known": [m for m in additions if m in expected],
                                                  "unexpected": [m for m in additions if m not in expected]})
        require(set(additions) <= expected, "Original restored with an unexpected kernel warning")

    def remove_staged_firmware(self):
        for firmware, identity in self.installed.items():
            self.overlays.pinned(firmware, self.config["pins"][firmware.name])
            info = firmware.stat()
            require((info.st_dev, info.st_ino) == identity, "Temporary firmware identity changed")
            firmware.unlink()
            require(not firmware.exists(), "Temporary firmware remains")


def supervise(config, output):
    import kv260_accept as accept
    import observer_lifecycle as overlays
    import resident_validation as prior

    require(sys.platform == "linux" and os.geteuid() == 0, "Root on the admitted board required")
    require(config["allow_module_load"] is True and config["fixture_taint"] == 12288,
            "The exact temporary module load and taint were not authorized")
    essentials = {"lifecycle.py","bench_fixture.py","measurement.py","weights.py","sequential_sampler.py", "prefetch_sampler.py",
                  "stock_sampler.py","readback.py","matrix.bin","autonomous_mmio.so"}
    require(essentials <= set(config["pins"]), "Missing mandatory staged payload")
    for name, pin in config["pins"].items():
        require(Path(name).name == name and isinstance(pin.get("bytes"),int) and pin["bytes"]>0 and
                re.fullmatch(r"[0-9a-f]{64}",pin.get("sha256","")), "Invalid staged payload pin")
    require(re.fullmatch(r"[0-9a-f-]{36}", config["boot"]) and
            Path("/proc/sys/kernel/random/boot_id").read_text().strip() == config["boot"], "Board boot differs")
    common_assets = ("interface_overlay", "dma_overlay", "afi_restore_overlay", "driver")
    require(set(config["arms"]) == set(MODES), "Unexpected comparison arms")
    assets = [config[key] for key in common_assets]
    for mode, stem in (("sequential", "burst"), ("prefetch", "prefetch")):
        arm = config["arms"][mode]
        require(arm == {
            "firmware": f"gradiated-tiny-logits-ddr4-{stem}-v1-50mhz.bit.bin",
            "program_overlay": f"kv260-logits-ddr4-{stem}-program.dtbo",
            "interface_overlay": config["interface_overlay"],
        }, "Unexpected fixture asset names")
        assets.extend((arm["firmware"], arm["program_overlay"]))
    require(len(assets) == len(set(assets)), "Stage each fixture asset independently")
    require(all(Path(name).name == name and name in config["pins"] for name in assets),
            "Unpinned fixture asset")
    stage = HERE.stat()
    require(stage.st_uid == 0 and stat.S_IMODE(stage.st_mode) & 0o022 == 0, "Unsafe staging directory")
    setup = accept.pinned_module(prior.SETUP_HELPER, prior.SETUP_PIN)
    verify = prior.load_pinned(prior.ACCEPTANCE/"kv260_accept_checks.py",prior.CHECKS_PIN)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    with owner_lock(setup.LOCK):
        output.mkdir(mode=0o700)
        owner = Lifecycle(config,output,setup,prior,verify,overlays)
        result = {"experiment_passed":False, "restored":False}
        try:
            from measurement import HOMOGENEOUS_REPLIES

            save(output / "intent.json", {"boot": config["boot"], "sessions": SESSIONS,
                                         "homogeneous_timed_replies": HOMOGENEOUS_REPLIES,
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
                    owner.remove_staged_firmware()
                    result["original_untouched"] = True
            except BaseException as error:
                result["restored"] = owner.original_verified
                result["restore_error"] = f"{type(error).__name__}: {error}"
                try:
                    save(output/"restore-failure.state.json",setup.live.snapshot())
                except Exception as diagnostic:
                    result["diagnostic_error"] = str(diagnostic)
            save(output/"outcome.json", result)
        print(json.dumps(result), flush=True)
        return 0 if result == {"experiment_passed": True, "restored": True} else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--release", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.release:
        require(os.geteuid() == 0 and re.fullmatch(r"/dev/uio\d+",str(args.release)), "Unexpected release target")
        print(json.dumps(release_weights(args.release)), flush=True)
        return 0
    require(args.config is not None and args.output is not None, "Specify the pinned config and fresh output")
    return supervise(json.loads(args.config.read_text()),args.output.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
