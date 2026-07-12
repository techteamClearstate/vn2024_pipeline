#!/usr/bin/env python3
"""Execute the self-contained funnel dashboard in Chromium and exercise its UI.

The authority verifier covers numeric reconciliation.  This companion catches
JavaScript/render regressions by visiting every tab in every scope and every
combination of the seven simulator gates at desktop and mobile widths.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True)
    args = ap.parse_args()
    html = Path(args.html).resolve()
    if not html.exists():
        print(f"FAIL: dashboard not found: {html}")
        return 1

    errors: list[str] = []
    renders = 0
    with sync_playwright() as pw:
        driver_pid = pw._impl_obj._connection._transport._proc.pid  # Playwright exposes no public cleanup PID.
        browser = pw.chromium.launch(headless=True)
        for name, viewport in (("desktop", {"width": 1440, "height": 1000}),
                               ("mobile", {"width": 390, "height": 844})):
            print(f"  checking {name} viewport...", flush=True)
            probe = browser.new_page(viewport=viewport)
            probe.goto(html.as_uri(), wait_until="load")
            shape = probe.evaluate("() => ({tabs:TABS.map(x=>x[0]),scopes:scopes().map(x=>x.id),gates:DATA.simulator.gates.length})")
            probe.close()
            if shape["gates"] != 7:
                errors.append(f"[{name}] expected 7 toggleable gates, found {shape['gates']}")

            # A fresh page per scope prevents the synthetic 128-toggle burst
            # from accumulating detached responsive DOM nodes in Chromium.
            for scope in shape["scopes"]:
                print(f"    {scope}", flush=True)
                context = browser.new_context(viewport=viewport)
                page = context.new_page()
                page.set_default_timeout(30_000)
                page.set_default_navigation_timeout(60_000)
                page.on("pageerror", lambda exc, n=name, s=scope: errors.append(f"[{n}/{s}] pageerror: {exc}"))
                page.on("console", lambda msg, n=name, s=scope: errors.append(f"[{n}/{s}] console error: {msg.text}") if msg.type == "error" else None)
                page.goto(html.as_uri(), wait_until="domcontentloaded")

                # Every ordinary tab renders in every file/combined scope.
                for tab in shape["tabs"]:
                    page.evaluate("([scope,tab]) => {state.scope=scope;state.tab=tab;render();}", [scope, tab])
                    renders += 1
                    active = page.locator(f"#tab-{tab}.active").count()
                    if active != 1:
                        errors.append(f"[{name}] {scope}/{tab}: active tab not rendered")

                # All 2^7 simulator states render per scope.  Metrics are
                # computed from the embedded exact aggregate, so no network or
                # server round-trip is involved.
                failures = page.evaluate("""(scope) => {
                    const bad=[];
                    state.scope=scope;state.tab='simulator';render();
                    for(let mask=0;mask<(1<<DATA.simulator.gates.length);mask++){
                      DATA.simulator.gates.forEach((g,i)=>state.enabledGates[g.key]=!!(mask&(1<<i)));
                      renderSimulator();
                      if(!document.querySelector('#tab-simulator.active .simresult'))bad.push(mask);
                    }
                    return bad;
                }""", scope)
                renders += 1 << shape["gates"]
                for mask in failures:
                    errors.append(f"[{name}] {scope}/simulator mask {mask}: result card missing")
                context.close()
        if sys.platform == "win32":
            # After this intentionally abusive 1,904-render burst, Chromium's
            # graceful close can wait indefinitely on detached renderers.
            # Terminate only this harness's Playwright driver process tree.
            subprocess.run(
                ["taskkill", "/PID", str(driver_pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            browser.close()

    if errors:
        print(f"FAIL: {len(errors)} browser errors across {renders} render states")
        for error in errors[:30]:
            print("  -", error)
        return 1
    print(f"PASS headless render: {renders} states across all tabs, scopes, 128 gate masks, desktop + mobile; 0 JS errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
