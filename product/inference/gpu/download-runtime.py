import concurrent.futures
import subprocess
import sys
import threading
import time
import json
import urllib.request
import urllib.parse
from pathlib import Path


def download(url: str, destination: Path) -> None:
    deadline = time.monotonic() + 1200
    retryable = (6, 7, 18, 28, 56)
    digest = Path(urllib.parse.urlsplit(url).path).name.removesuffix('.tar.gz')
    with urllib.request.urlopen(f'http://127.0.0.1:3004/api/internal/v1/runtime-bundles/{digest}', timeout=10) as response:
        grant = json.load(response)
    target = urllib.parse.urlsplit(grant['url'])
    if target.scheme != 'https' or not target.hostname or not target.hostname.endswith('.amazonaws.com') or target.username or target.password:
        raise ValueError('Invalid private runtime download grant')
    curl_config = 'url = ' + json.dumps(grant['url']) + '\n'

    def curl(
        options: list[str], output: object, maximum: int = 30
    ) -> subprocess.CompletedProcess[bytes]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Runtime download deadline exceeded")
        return subprocess.run(
            [
                "curl",
                "--disable",
                "--config",
                "-",
                "--silent",
                "--show-error",
                "--fail",
                "--connect-timeout",
                "5",
                "--max-time",
                str(min(maximum, remaining)),
                *options,
            ],
            input=curl_config.encode(),
            stdout=output,
            timeout=min(maximum + 5, remaining),
            check=False,
        )

    while True:
        head = curl(
            [
                "--range",
                "0-0",
                "--output",
                "/dev/null",
                "--write-out",
                "%header{content-range}",
            ],
            subprocess.PIPE,
            maximum=10,
        )
        if head.returncode not in retryable:
            break
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    length = head.stdout.strip().rsplit(b"/", 1)[-1]
    if head.returncode or not length.isdigit() or int(length) <= 0:
        raise RuntimeError("Cannot read runtime bundle size")
    size = int(length)
    with destination.open("wb") as archive:
        archive.truncate(size)

    stop = threading.Event()
    part_size = (size + 7) // 8

    def part(start: int) -> None:
        end = min(start + part_size, size)
        try:
            with destination.open("r+b", buffering=0) as archive:
                archive.seek(start)
                while archive.tell() < end:
                    if stop.is_set():
                        return
                    offset = archive.tell()
                    code = curl(
                        [
                            "--range",
                            f"{offset}-{end - 1}",
                            "--max-filesize",
                            str(end - offset),
                        ],
                        archive,
                    ).returncode
                    if archive.tell() > end or code not in (0, *retryable):
                        raise RuntimeError(
                            f"Runtime bundle transfer failed (curl {code})"
                        )
                    if code == 0 and archive.tell() != end:
                        raise RuntimeError("Runtime bundle range was truncated")
                    if code:
                        stop.wait(min(1, max(0, deadline - time.monotonic())))
        except Exception:
            stop.set()
            raise

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(part, range(0, size, part_size)))


if __name__ == "__main__":
    download(sys.argv[1], Path(sys.argv[2]))
