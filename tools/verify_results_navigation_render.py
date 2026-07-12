"""Exercise every results-navigation page at desktop and mobile widths."""
from pathlib import Path
from playwright.sync_api import sync_playwright

SITE = Path(__file__).resolve().parents[1] / "outputs/results_navigation"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    errors = []
    for width, height in ((1440, 1000), (390, 844)):
        for name in ("index.html", "quality.html", "comparison.html", "outputs.html", "schemas.html"):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("pageerror", lambda exc, n=name, w=width: errors.append(f"{w}/{n}: {exc}"))
            page.goto((SITE / name).resolve().as_uri(), wait_until="load")
            if name == "comparison.html":
                page.select_option("#tier", "Review")
                page.select_option("#dimension", "manufacturer")
                page.fill("#search", "johnson")
                assert page.locator("#comparison-body tr").count() >= 1
            if name == "schemas.html":
                assert page.locator("#schemas details").count() >= 6
            assert page.locator("header nav").is_visible()
            page.close()
    browser.close()
    assert not errors, errors
print("PASS: 5 pages × desktop/mobile; filters exercised; 0 JavaScript errors")
