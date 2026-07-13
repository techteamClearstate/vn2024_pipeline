"""Exercise every results-navigation page at desktop and mobile widths."""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE = ROOT / "outputs/20260713_llm_adjudication/dashboard/site"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE)
    args = parser.parse_args()
    site = args.site.resolve()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        errors = []
        for width, height in ((1440, 1000), (390, 844)):
            for name in ("index.html", "quality.html", "simulator.html", "comparison.html",
                         "outputs.html", "schemas.html"):
                page = browser.new_page(viewport={"width": width, "height": height})
                page.on("pageerror", lambda exc, n=name, w=width: errors.append(f"{w}/{n}: {exc}"))
                page.goto((site / name).as_uri(), wait_until="load")
                if name == "comparison.html":
                    page.select_option("#tier", "Review")
                    page.select_option("#dimension", "manufacturer")
                    page.fill("#search", "johnson")
                    assert page.locator("#comparison-body tr").count() >= 1
                if name == "schemas.html":
                    assert page.locator("#schemas details").count() >= 6
                if name == "simulator.html":
                    first_gate = page.locator('#sim-gates input[type="checkbox"]').first
                    first_gate.uncheck()
                    assert page.locator("#sim-results .card").count() >= 3
                assert page.locator("header nav").is_visible()
                page.close()
        browser.close()
        assert not errors, errors
    print("PASS: 6 pages × desktop/mobile; filters and gate toggle exercised; 0 JavaScript errors")


if __name__ == "__main__":
    main()
