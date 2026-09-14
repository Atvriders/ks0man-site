"""End-to-end: render the maars/skywave block through its REAL PHP callback,
then boot that exact markup in Chromium and prove the WebGL scene mounts.

This exists because test_webgl.py passing does NOT prove WordPress serves a
working scene. test_webgl.py loads a hand-written harness; this loads the
markup the plugin actually emits.

It earned its place immediately: it caught a defect nothing else would have.
The block routed its data-* attributes through get_block_wrapper_attributes(),
which is documented around class/style. data-maars-autostart never reached the
markup, so the bootstrap's selector matched nothing and the canvas stayed blank
with no console error and no failing unit test.

Run:  python3 tests/test_block_boot.py
Needs: php on PATH (or $MAARS_PHP), playwright, Pillow, and the bundled Chromium.
"""

import os
import shutil
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out")
CHROME = os.path.expanduser(
    "~/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"
)
PHP = os.environ.get("MAARS_PHP", "php")

# A blank canvas is the failure this whole file exists to catch, so the
# thresholds are deliberately far above anything a cleared buffer produces.
MIN_COLORS = 500
MIN_STDEV = 8.0


def render_block() -> None:
    """Run the real render_callback via the PHP harness."""
    r = subprocess.run(
        [PHP, os.path.join(HERE, "wp_render_harness.php")],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise AssertionError(f"PHP harness failed:\n{r.stdout}\n{r.stderr}")
    print("  php:", (r.stderr or r.stdout).strip())


def build_page() -> str:
    """Assemble the page the way WordPress would: block markup, the theme's
    stylesheet, the deferred script and the inline bootstrap after it."""
    block = open(os.path.join(OUT, "block.html")).read()
    inline = open(os.path.join(OUT, "inline.js")).read()
    css = open(
        os.path.join(ROOT, "wp/themes/maars/assets/css/maars.css")
    ).read()
    shutil.copy(
        os.path.join(ROOT, "wp/themes/maars/assets/js/skywave.js"),
        os.path.join(OUT, "skywave.js"),
    )
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>WP output boot test</title>"
        f"<style>{css}</style></head><body>"
        f'<main class="wp-site-blocks">{block}</main>'
        '<script src="skywave.js" defer></script>'
        f"<script>{inline}</script></body></html>"
    )
    path = os.path.join(OUT, "wp_page.html")
    open(path, "w").write(page)
    return path


def boot(path: str):
    from playwright.sync_api import sync_playwright

    errs = []
    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=CHROME,
            args=[
                "--no-sandbox",
                "--use-gl=swiftshader",
                "--enable-unsafe-swiftshader",
                "--disable-dev-shm-usage",
            ],
        )
        pg = b.new_context(viewport={"width": 1100, "height": 760}).new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on(
            "console",
            lambda m: errs.append(f"console.{m.type}: {m.text}")
            if m.type == "error"
            else None,
        )
        pg.goto("file://" + path, wait_until="load")
        ready = True
        try:
            pg.wait_for_function(
                "()=>{const c=document.querySelector('canvas.maars-skywave__canvas');"
                "return c && c.dataset.maarsReady==='1';}",
                timeout=25000,
            )
        except Exception as ex:
            ready = False
            errs.append("ready timeout: " + str(ex)[:160])
        state = pg.evaluate(
            """()=>{const c=document.querySelector('canvas.maars-skywave__canvas');
            if(!c) return null;
            return {ready:c.dataset.maarsReady||null,
                    fallback:c.dataset.maarsFallback||null,
                    parentFallback:c.parentElement.classList.contains('maars-skywave--fallback'),
                    autostart:c.parentElement.getAttribute('data-maars-autostart'),
                    aria:(c.getAttribute('aria-label')||'').slice(0,70)};}"""
        )
        shot = os.path.join(OUT, "wp_boot.png")
        pg.locator("canvas.maars-skywave__canvas").screenshot(path=shot)
        b.close()
    return ready, state, errs, shot


def pixels(shot: str):
    from PIL import Image

    im = Image.open(shot).convert("RGB")
    px = list(im.getdata())
    grey = [(r + g + b) // 3 for r, g, b in px]
    return im.size, len(set(px)), statistics.pstdev(grey)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    print("ks0man-site block-boot gate — the plugin's real markup, in a browser\n")
    render_block()

    block = open(os.path.join(OUT, "block.html")).read()
    checks = []

    # The exact defect this file was written to catch.
    checks.append(
        (
            'block markup carries data-maars-autostart="1"',
            'data-maars-autostart="1"' in block,
        )
    )
    checks.append(
        ("block markup carries the canvas class", "maars-skywave__canvas" in block)
    )
    checks.append(("block markup carries a noscript fallback", "<noscript" in block))
    for mhz in ("3.920", "7.260", "14.290", "147.255"):
        checks.append((f"band {mhz} MHz embedded in the markup", mhz in block))

    path = build_page()
    ready, state, errs, shot = boot(path)
    size, colors, stdev = pixels(shot)
    print(f"  canvas state: {state}")
    print(f"  page errors : {errs if errs else 'none'}")
    print(f"  rendered    : {size}  distinct colours={colors}  stdev={stdev:.2f}\n")

    checks.append(("canvas reports ready", bool(state) and state["ready"] == "1"))
    checks.append(("canvas did not fall back", bool(state) and not state["fallback"]))
    checks.append(
        ("wrapper did not fall back", bool(state) and not state["parentFallback"])
    )
    checks.append(("no page or console errors", not errs))
    checks.append((f"canvas is not blank (>{MIN_COLORS} colours)", colors > MIN_COLORS))
    checks.append((f"canvas is not blank (stdev >{MIN_STDEV})", stdev > MIN_STDEV))

    failed = 0
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            failed += 1
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    print(f"screenshot: {shot}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
