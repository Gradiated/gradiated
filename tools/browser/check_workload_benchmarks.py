"""Check the workload benchmark display/editor against local Storybook fixtures."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ORIGIN = "http://127.0.0.1:6006"
OUTPUT = Path(".agents/runtime/workload-benchmarks")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(ORIGIN + "/") else route.abort())
        page = context.new_page()
        page.goto(ORIGIN + "/iframe.html?id=pages-training--manual-benchmarks-slow-list&viewMode=story")
        edit = page.get_by_role("button", name="Edit benchmarks", exact=True)
        edit.wait_for()
        assert edit.is_disabled()
        page.get_by_text("76.6% Task success", exact=True).wait_for()
        edit.click()
        assert page.get_by_role("dialog").get_by_label("This model (%)", exact=True).input_value() == "76.5625"
        page.get_by_role("dialog").get_by_role("button", name="Cancel", exact=True).click()
        page.goto(ORIGIN + "/iframe.html?id=pages-training--manual-benchmarks&viewMode=story")
        page.get_by_text("76.6% Task success", exact=True).wait_for()
        page.get_by_text("2.58 s median", exact=True).wait_for()
        page.get_by_text("$0.000266 / task est.", exact=True).wait_for()
        page.get_by_role("button", name="Edit benchmarks", exact=True).click()
        dialog = page.get_by_role("dialog")
        assert dialog.get_by_label("This model ($)", exact=True).input_value() == "0.000266433"
        assert dialog.get_by_label("This model (%)", exact=True).input_value() == "76.5625"
        dialog.get_by_label("Workload", exact=True).fill("")
        dialog.get_by_role("button", name="Save benchmarks", exact=True).click()
        dialog.get_by_role("alert").wait_for()
        assert dialog.is_visible()
        dialog.get_by_label("Workload", exact=True).fill("Support tool selection")
        page.screenshot(path=str(OUTPUT / "editor.png"))
        dialog.get_by_label("This model (%)", exact=True).fill("80")
        dialog.get_by_role("button", name="Save benchmarks", exact=True).click()
        dialog.wait_for(state="hidden")
        page.get_by_text("80.0% Task success", exact=True).wait_for()
        page.screenshot(path=str(OUTPUT / "stats.png"))
        file_requests = []
        page.on("request", lambda request: file_requests.append(request.url) if "/versions/" in request.url and "/files" in request.url else None)
        page.goto(ORIGIN + "/iframe.html?id=pages-training--manual-benchmarks-table&viewMode=story")
        page.get_by_text("76.6% Task success", exact=True).first.wait_for()
        assert not file_requests, file_requests
        page.screenshot(path=str(OUTPUT / "table.png"))
        page.goto(ORIGIN + "/iframe.html?id=pages-training--manual-benchmarks-list-retry&viewMode=story")
        page.get_by_text("Benchmarks could not be loaded.", exact=False).wait_for()
        page.get_by_role("button", name="Retry", exact=True).first.click()
        page.get_by_text("76.6% Task success", exact=True).wait_for()
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(ORIGIN + "/iframe.html?id=pages-training--manual-benchmarks&viewMode=story")
        page.get_by_role("button", name="Edit benchmarks", exact=True).click()
        page.get_by_role("dialog").get_by_role("button", name="Save benchmarks", exact=True).wait_for()
        page.screenshot(path=str(OUTPUT / "mobile-editor.png"))
        browser.close()
    print("Benchmark stats, save, validation, mobile, failed-list retry and table without per-row file requests passed.")


if __name__ == "__main__":
    main()
