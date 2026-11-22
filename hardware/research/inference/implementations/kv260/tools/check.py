"""Run bounded project checks without installing packages or loading models."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
REPO = next(p for p in PROJECT.parents if (p / "product").is_dir() and (p / ".git").exists())
RUNTIME = REPO / ".agents/runtime/hardware/inference"


def main():
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Use the pinned Python 3.12 environment; no packages will be installed.")
    tmp = RUNTIME / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(tmp))
    commands = [
        ([sys.executable, "-I", "-B", str(REPO / "tools/gradctl/gradctl"), "devex", "check"], 30),
        *[(["/bin/bash", "-n", str(path)], 10) for path in sorted(PROJECT.glob("*.sh"))],
        ([sys.executable, "-I", "-B", "-m", "unittest", "discover", "-s", str(PROJECT / "tools"), "-p", "test_*.py", "-v"], 120),
    ]
    try:
        # Compile in memory: never create bytecode beside project source.
        for path in PROJECT.rglob("*.py"):
            compile(path.read_bytes(), str(path), "exec")
        print("Python syntax passed.", flush=True)
        with tempfile.TemporaryDirectory(prefix="project-check-", dir=tmp) as directory:
            for number, (command, timeout) in enumerate(commands, 1):
                print(f"Check {number}/{len(commands)}: {Path(command[0]).name} {command[1:]}", flush=True)
                with (Path(directory) / f"check-{number}.log").open("w+") as log:
                    child = subprocess.Popen(command, cwd=REPO, env=env, stdout=log,
                                             stderr=subprocess.STDOUT, start_new_session=True)
                    try:
                        code = child.wait(timeout=timeout)
                    except (subprocess.TimeoutExpired, KeyboardInterrupt):
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                        log.seek(0)
                        print(log.read(), end="", flush=True)
                        raise
                    log.seek(0)
                    print(log.read(), end="", flush=True)
                if code:
                    raise SystemExit(code)
    except subprocess.TimeoutExpired as error:
        raise SystemExit(f"Project check exceeded its {error.timeout}s timeout.") from error
    print("All project checks passed.")


if __name__ == "__main__":
    main()
