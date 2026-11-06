"""Capture every built console story as an informative, committed PNG."""

from __future__ import annotations

import argparse
import functools
import json
import tempfile
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
CONSOLE = ROOT / "product/services/console"
DIST = CONSOLE / "storybook-static"
SCREENSHOTS = CONSOLE / "screenshots"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--story-prefix", default="", help="Capture only story IDs starting with this prefix"
    )
    parser.add_argument(
        "--output", type=Path, default=SCREENSHOTS, help="PNG output directory"
    )
    args = parser.parse_args()

    entries = json.loads((DIST / "index.json").read_text())["entries"]
    stories = [
        entry for entry in entries.values()
        if entry["type"] == "story" and entry["id"].startswith(args.story_prefix)
    ]
    if not stories:
        raise RuntimeError("No stories found in the Storybook build")

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(DIST))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"

    try:
        with (
            tempfile.TemporaryDirectory() as staging,
            sync_playwright() as playwright,
        ):
            browser = playwright.chromium.launch()
            for story in stories:
                tags = story.get("tags", [])
                mobile = "mobile" in tags
                context = browser.new_context(
                    viewport=(
                        {"width": 390, "height": 844}
                        if mobile
                        else {"width": 1440, "height": 1000}
                    ),
                    device_scale_factor=2 if mobile else 1,
                    is_mobile=mobile,
                    locale="en-US",
                    timezone_id="UTC",
                    color_scheme="light",
                    reduced_motion="reduce",
                )
                context.route(
                    "**/*",
                    lambda route: route.continue_()
                    if route.request.url.startswith(origin + "/")
                    else route.abort(),
                )
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "console",
                    lambda message: errors.append(message.text)
                    if message.type == "error" else None,
                )
                page.clock.set_fixed_time(datetime(2026, 10, 2, 12, tzinfo=timezone.utc))
                page.goto(f"{origin}/iframe.html?id={story['id']}&viewMode=story")
                page.wait_for_function(
                    "document.querySelector('[data-story-played=true]')"
                )
                page.evaluate("document.fonts.ready")
                page.evaluate("document.activeElement?.blur()")
                # Recharts animates through JS; let its entry animation finish.
                page.wait_for_timeout(2000)
                if "request-failure" in tags:
                    errors = [
                        error
                        for error in errors
                        if not error.startswith("Failed to load resource")
                    ]
                if errors:
                    raise RuntimeError(f"{story['id']}: {errors}")

                page.screenshot(
                    path=str(Path(staging) / f"{story['id']}.png"),
                    full_page=True,
                    animations="disabled",
                )
                print(f"Captured {story['id']}")
                context.close()
            browser.close()

            args.output.mkdir(parents=True, exist_ok=True)
            for old in args.output.glob(f"{args.story_prefix}*.png"):
                old.unlink()
            for captured in Path(staging).glob("*.png"):
                (args.output / captured.name).write_bytes(captured.read_bytes())
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
