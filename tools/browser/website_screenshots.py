"""Capture built website pages and interactions for informative PR image diffs."""

from __future__ import annotations

import functools
import tempfile
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from storybook_screenshots import QuietHandler

ROOT = Path(__file__).resolve().parents[2]
WEBSITE = ROOT / "product/website"
DIST = WEBSITE / "dist"
SCREENSHOTS = WEBSITE / "screenshots"
CAPTURES = (
    ("home-desktop", "/", 1440, 1000, None, False),
    ("home-mobile-menu", "/", 390, 844, "menu", False),
    ("docs-desktop", "/docs/quickstart/", 1440, 1000, None, False),
    ("inference-desktop", "/inference/", 1440, 1000, None, True),
    ("training-desktop", "/training/", 1440, 1000, None, True),
    ("training-waitlist-desktop", "/training/", 1440, 1000, "waitlist", False),
    ("training-waitlist-mobile", "/training/", 390, 844, "waitlist", False),
)


def main() -> None:
    if not (DIST / "index.html").is_file():
        raise RuntimeError("Build the website before capturing screenshots")

    runtime = ROOT / ".agents/runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(DIST))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"

    try:
        with (
            tempfile.TemporaryDirectory(dir=runtime) as temporary,
            sync_playwright() as playwright,
        ):
            staging = Path(temporary)
            for name, path, width, height, interaction, full_page in CAPTURES:
                context = playwright.chromium.launch_persistent_context(
                    str(staging / f"profile-{name}"),
                    headless=True,
                    viewport={"width": width, "height": height},
                    device_scale_factor=1,
                    locale="en-US",
                    timezone_id="UTC",
                    color_scheme="light",
                    reduced_motion="reduce",
                )
                try:

                    def route_request(route):
                        url = urlparse(route.request.url)
                        if url.path == "/api/v1/models" and url.hostname in {
                            "api.gradiated.com",
                            "127.0.0.1",
                        }:
                            route.fulfill(
                                json={"data": []},
                                headers={"Access-Control-Allow-Origin": "*"},
                            )
                        elif route.request.url.startswith(origin + "/"):
                            route.continue_()
                        else:
                            route.abort()

                    context.route("**/*", route_request)
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.clock.set_fixed_time(
                        datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
                    )
                    page.goto(origin + path, wait_until="networkidle")
                    page.evaluate("document.fonts.ready")
                    if path == "/training/":
                        for button in page.get_by_role(
                            "button", name="Join post-training waitlist"
                        ).all():
                            visible_text = button.evaluate(
                                "element => { const style = getComputedStyle(element); return style.color !== style.backgroundColor; }"
                            )
                            if not visible_text:
                                raise RuntimeError(
                                    f"{name}: waitlist button text blends into its background"
                                )
                    if interaction == "menu":
                        page.get_by_role("button", name="Open menu", exact=True).click()
                        expect(page.locator(".gr-nav-sheet-actions")).to_be_visible()
                    elif interaction == "waitlist":
                        page.get_by_role(
                            "button", name="Join post-training waitlist"
                        ).first.click()
                        expect(page.get_by_role("dialog")).to_be_visible()
                    else:
                        # Scroll through the page so lazy media loads before the full-page capture.
                        page.evaluate("""async () => {
                            for (let y = 0; y < document.body.scrollHeight; y += 800) {
                                window.scrollTo(0, y);
                                await new Promise(resolve => setTimeout(resolve, 50));
                            }
                            window.scrollTo(0, 0);
                        }""")
                    page.evaluate("document.activeElement?.blur()")
                    page.wait_for_timeout(2000)
                    if errors:
                        raise RuntimeError(f"{name}: {errors}")
                    page.screenshot(
                        path=str(staging / f"{name}.png"),
                        full_page=full_page,
                        animations="disabled",
                    )
                    print(f"Captured {name}")
                finally:
                    context.close()

            SCREENSHOTS.mkdir(exist_ok=True)
            for old in SCREENSHOTS.glob("*.png"):
                old.unlink()
            for captured in staging.glob("*.png"):
                (SCREENSHOTS / captured.name).write_bytes(captured.read_bytes())
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
