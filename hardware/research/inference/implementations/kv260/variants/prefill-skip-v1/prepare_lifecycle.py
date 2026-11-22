"""Extend the preserved two-image lifecycle to the named prefill comparison arms."""
import argparse
from hashlib import sha256
from pathlib import Path

SOURCE_PIN = "cb9674b187d22727a20ca3f9980d3adbca2c6c43c70eb3f2b13a2d6887659e8a"


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Unexpected lifecycle source around {old!r}")
    return text.replace(old, new)


def derive(data):
    if sha256(data).hexdigest() != SOURCE_PIN:
        raise ValueError("Preserved autonomous lifecycle differs")
    text = data.decode()
    text = once(text, '"""Verified runtime overlay transitions for the KV260 autonomous comparison image."""',
                '"""Verified transitions between original, autonomous control and prefill-skip images."""')
    text = once(text, "OBSERVER_FILE = 'gradiated-tiny-autonomous-v1-50mhz.bit.bin'",
                "CONTROL_FILE = 'gradiated-tiny-autonomous-v1-50mhz.bit.bin'\n"
                "CONTROL_OVERLAY = 'gradiated-tiny-autonomous-v1-program'\n"
                "CONTROL_DTBO = 'kv260-autonomous-program.dtbo'\n"
                "OBSERVER_FILE = 'gradiated-tiny-prefill-skip-v1-50mhz.bit.bin'")
    text = once(text, "OBSERVER_OVERLAY = 'gradiated-tiny-autonomous-v1-program'",
                "OBSERVER_OVERLAY = 'gradiated-tiny-prefill-skip-v1-program'")
    text = once(text, "OBS_DTBO = 'kv260-autonomous-program.dtbo'",
                "OBS_DTBO = 'kv260-prefill-skip-program.dtbo'")
    text = once(text, "    require(mode=='candidate', 'Unknown firmware mode')",
                "    if mode=='control':\n        return CONTROL_FILE, CONTROL_OVERLAY\n"
                "    require(mode=='candidate', 'Unknown firmware mode')")
    text = once(text, "def state_spec(baseline, mode, interface):",
                "def image_overlay(mode):\n"
                "    require(mode in ('control','candidate'), 'Unknown staged image mode')\n"
                "    return CONTROL_DTBO if mode=='control' else OBS_DTBO\n\n\n"
                "def state_spec(baseline, mode, interface):")
    text = once(text, "def prepare_bundle(stock_bundle, staged, destination, resident, pins):",
                "def prepare_bundle(stock_bundle, staged, destination, resident, pins, mode='candidate'):")
    text = once(text, '    """Derive a local observer package from verified, unmodified stock members."""',
                '    """Derive one named arm package from verified, unmodified stock members."""\n'
                "    overlay_name = image_overlay(mode)\n    firmware_name, _ = image_spec(mode)")
    text = once(text, "f\"FIRMWARE = '{OBSERVER_FILE}'\".encode()", "f\"FIRMWARE = '{firmware_name}'\".encode()")
    text = once(text, "'kv260-program.dtbo':pinned(staged/OBS_DTBO,pins[OBS_DTBO]),\n                    OBSERVER_FILE:pinned(staged/OBSERVER_FILE,pins[OBSERVER_FILE])",
                "'kv260-program.dtbo':pinned(staged/overlay_name,pins[overlay_name]),\n"
                "                    firmware_name:pinned(staged/firmware_name,pins[firmware_name])")
    text = once(text, "    require(mode=='candidate', 'Invalid runner mode')",
                "    require(mode in ('control','candidate'), 'Invalid runner mode')")
    text = once(text, "def derive_logger(source, mode, loader):\n    if mode=='candidate':\n        source = rewritten(source, f'\"{STOCK_FILE}\"'.encode(), f'\"{OBSERVER_FILE}\"'.encode())",
                "def derive_logger(source, mode, loader):\n    firmware_name, _ = image_spec(mode)\n"
                "    if mode!='stock':\n        source = rewritten(source, f'\"{STOCK_FILE}\"'.encode(), f'\"{firmware_name}\"'.encode())")
    text = once(text, "    observer_path = setup.FIRMWARE.parent/OBSERVER_FILE\n    pinned(observer_path,pins[OBSERVER_FILE])",
                "    # Check both installed arm files before taking down any interface.\n"
                "    for staged_firmware in (CONTROL_FILE, OBSERVER_FILE):\n"
                "        pinned(setup.FIRMWARE.parent/staged_firmware,pins[staged_firmware])")
    text = once(text, "else staged/OBS_DTBO", "else staged/image_overlay(after_mode)")
    text = once(text, "else pins[OBS_DTBO]", "else pins[image_overlay(after_mode)]")
    text = once(text, "        pinned(observer_path,pins[OBSERVER_FILE])",
                "        pinned(setup.FIRMWARE.parent/target_firmware,pins[target_firmware])")
    return text.encode()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('output', type=Path)
    a = p.parse_args()
    data = derive(a.source.read_bytes())
    with a.output.open('xb') as f:
        f.write(data)
