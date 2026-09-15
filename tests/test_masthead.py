#!/usr/bin/env python3
"""The masthead is a receiver: prove it draws one, and prove it is legible.

This is the maars/masthead twin of tests/test_block_boot.py. It renders the
block through its REAL PHP render callback, assembles the page the way
WordPress would — theme stylesheet, deferred script, inline bootstrap after it
— and then boots that exact markup in Chromium and measures the pixels.

WHAT IT REFUSES TO WAVE THROUGH, in the order the failures actually happen:

  1. A FLAT RECTANGLE. A canvas that mounts, reports itself ready and paints
     one colour is the single likeliest way this feature fails, and it does not
     announce itself: `maarsReady` is "1", no error is logged, and the band
     looks deliberate. So blankness is measured three ways on the saved pixels
     — grey-level standard deviation, distinct colours, and the structure of
     the picture itself (columns must differ from each other AND rows must
     differ from each other, which a vertical gradient would pass on one and
     fail on the other).

  2. A WATERFALL WITH NO CARRIER IN IT. The whole point of this band is that
     it is tuned to the Society's own machine. The column at 147.255 MHz is
     compared against control columns either side of it: it has to be brighter
     AND more magenta than the noise floor, because magenta is the one colour
     this site reserves and spending it on nothing would be worse than not
     drawing a marker at all.

  3. TEXT ON A HOT PIXEL. The identity sits over a heat map whose brightest
     value is near-white. The scrim behind it is measured, not assumed: the
     composited background is sampled at the glyph baselines and every text
     colour on the band is checked against the WORST pixel found there.

  4. MOTION THE READER ASKED NOT TO HAVE. Under prefers-reduced-motion the
     module must draw ONE frame. That is asserted twice — the frame counter,
     and two captures a second apart that must be identical.

  5. A BAND THAT BREAKS A PHONE. 390px, no horizontal scroll, and the canvas
     still painted.

  6. A LEAK. destroy() must cancel its timer and its frame, disconnect the
     observer and take its dataset flag back off.

Every number behind every assertion is printed, so a human can check the claim
instead of trusting it.

Run:  python3 tests/test_masthead.py
      pytest tests/test_masthead.py -s
Needs: php on PATH (or $MAARS_PHP), playwright, Pillow, the bundled Chromium.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
OUT = TESTS / "out"
PHP = os.environ.get("MAARS_PHP", "php")
CHROME = os.environ.get("MAARS_CHROME") or os.path.expanduser(
    "~/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome")
CHROME_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

CSS = REPO / "wp/themes/maars/assets/css/maars.css"
JS = REPO / "wp/themes/maars/assets/js/waterfall.js"
THEME_JSON = REPO / "wp/themes/maars/theme.json"
HARNESS_PHP = TESTS / "wp_masthead_harness.php"

# --- thresholds ------------------------------------------------------------
MIN_STDEV = 6.0          # grey-level spread across the band; a flat fill is ~0
MIN_COLORS = 400         # a real heat map has thousands
MIN_COL_SPREAD = 3.0     # columns must differ from each other
MIN_ROW_SPREAD = 2.0     # and rows from each other, or it is a gradient
CARRIER_GAIN = 1.25      # the marked column against the noise floor
STATIC_MAD = 0.35        # under reduced motion, two captures must match
AA_NORMAL = 4.5
READY_MS = 20000

_CACHE: dict = {}


# --------------------------------------------------------------------------
# imaging helpers (Pillow only, no numpy)
# --------------------------------------------------------------------------

def _pil():
    try:
        from PIL import Image, ImageChops, ImageStat  # noqa: F401
    except ImportError:  # pragma: no cover
        raise AssertionError(
            "Pillow is required for the pixel assertions (pip install pillow)") from None
    from PIL import Image, ImageChops, ImageStat
    return Image, ImageChops, ImageStat


def _stats(rgb) -> dict:
    _, _, ImageStat = _pil()
    grey = rgb.convert("L")
    st = ImageStat.Stat(grey)
    colors = rgb.getcolors(maxcolors=2_000_000)
    return {
        "w": rgb.size[0], "h": rgb.size[1],
        "mean": st.mean[0], "stdev": st.stddev[0],
        "colors": len(colors) if colors else 2_000_000,
    }


def _structure(rgb) -> tuple[float, float]:
    """(spread of column means, spread of row means) in grey levels.

    A flat fill scores (0, 0). A vertical gradient scores (0, high) and a
    horizontal one (high, 0); a waterfall has to score on both, because it is
    a picture in two dimensions and nothing else here is."""
    grey = rgb.convert("L")
    w, h = grey.size
    px = grey.load()
    cols = []
    for x in range(0, w, max(1, w // 160)):
        s = 0
        n = 0
        for y in range(0, h, max(1, h // 40)):
            s += px[x, y]
            n += 1
        cols.append(s / n)
    rows = []
    for y in range(0, h, max(1, h // 60)):
        s = 0
        n = 0
        for x in range(0, w, max(1, w // 80)):
            s += px[x, y]
            n += 1
        rows.append(s / n)

    def sd(v):
        m = sum(v) / len(v)
        return (sum((x - m) ** 2 for x in v) / len(v)) ** 0.5

    return sd(cols), sd(rows)


def _column(rgb, frac: float, half: int = 4) -> tuple[float, float]:
    """(mean grey, mean magenta-ness) of a narrow vertical strip.

    Magenta-ness is red plus blue minus twice green: it is positive for
    everything on the carrier ramp and at most zero for the navy noise ramp,
    so it separates 'a bright bit of noise' from 'the club's own carrier'."""
    w, h = rgb.size
    px = rgb.load()
    x0 = max(0, min(w - 1, int(w * frac) - half))
    x1 = max(1, min(w, int(w * frac) + half))
    g = 0.0
    m = 0.0
    n = 0
    for x in range(x0, x1):
        for y in range(0, h, 2):
            r, gg, b = px[x, y][:3]
            g += 0.2126 * r + 0.7152 * gg + 0.0722 * b
            m += (r + b) - 2 * gg
            n += 1
    return g / n, m / n


def _mad(a, b) -> float:
    _, ImageChops, ImageStat = _pil()
    if a.size != b.size:
        b = b.resize(a.size)
    d = ImageChops.difference(a, b)
    st = ImageStat.Stat(d)
    return sum(st.mean) / float(len(st.mean))


def _lum(rgb) -> float:
    def f(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (f(x) for x in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ratio(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _parse_rgb(s: str):
    m = re.findall(r"[\d.]+", s or "")
    return tuple(int(float(x)) for x in m[:3]) if len(m) >= 3 else None


# --------------------------------------------------------------------------
# build the page WordPress would serve
# --------------------------------------------------------------------------

def render_block() -> None:
    r = subprocess.run([PHP, str(HARNESS_PHP)], capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(f"PHP harness failed:\n{r.stdout}\n{r.stderr}")
    print("  php:", (r.stderr or r.stdout).strip())


def preset_vars() -> str:
    """theme.json's palette becomes CSS custom properties at runtime; recreate
    the ones the stylesheet reads so the standalone render is faithful."""
    d = json.loads(THEME_JSON.read_text())
    lines = []
    for p in d["settings"]["color"]["palette"]:
        lines.append(f"  --wp--preset--color--{p['slug']}: {p['color']};")
    for f in d["settings"]["typography"]["fontFamilies"]:
        lines.append(f"  --wp--preset--font-family--{f['slug']}: {f['fontFamily']};")
    return ":root {\n" + "\n".join(lines) + "\n}"


NAV = """
<div class="wp-block-group maars-navbar is-layout-flow">
  <nav class="wp-block-navigation maars-nav is-layout-flex" aria-label="Primary">
    <ul class="wp-block-navigation__container">
      <li class="wp-block-navigation-item"><a class="wp-block-navigation-item__content" href="/about/">About</a></li>
      <li class="wp-block-navigation-item"><a class="wp-block-navigation-item__content" href="/events/">Meetings &amp; Events</a></li>
      <li class="wp-block-navigation-item"><a class="wp-block-navigation-item__content" href="/on-the-air/">On the Air</a></li>
      <li class="wp-block-navigation-item"><a class="wp-block-navigation-item__content" href="/storm-spotting/">Storm Spotting</a></li>
      <li class="wp-block-navigation-item"><a class="wp-block-navigation-item__content" href="/news/">News</a></li>
      <li class="wp-block-navigation-item"><a class="wp-block-navigation-item__content" href="/archive/">Archive</a></li>
      <li class="wp-block-navigation-item"><a class="wp-block-navigation-item__content" href="/join/">Join</a></li>
    </ul>
  </nav>
</div>
"""

BELOW = """
<main class="maars-main is-layout-flow">
  <section class="maars-lede">
    <h1 class="maars-lede__title">Next meeting</h1>
    <p>Friday, October 9, 2026 at 6:30 P.M. The Society meets on the second Friday
       of the month, which is the rule its own constitution sets.</p>
  </section>
</main>
"""


def build_page(*, fallback: bool = False) -> str:
    block = (OUT / "masthead.html").read_text()
    inline = (OUT / "masthead_inline.js").read_text()
    shutil.copy(JS, OUT / "waterfall.js")

    # Break the 2D context on purpose, to exercise the CSS fallback path.
    sabotage = """
<script>
(function(){
  var orig = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type) {
    if (String(type).indexOf('2d') === 0 && this.classList.contains('maars-masthead__canvas')) {
      return null;
    }
    return orig.apply(this, arguments);
  };
}());
</script>
""" if fallback else ""

    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>MAARS masthead &mdash; WordPress output</title>"
        f"<style>{preset_vars()}</style>"
        f"<style>{CSS.read_text()}</style>"
        "</head><body class='wp-site-blocks'>"
        f"{sabotage}"
        '<header class="maars-site-header">'
        '<div class="wp-block-group maars-header has-ink-color has-paper-background-color '
        'has-text-color has-background is-layout-flow" '
        'style="padding-top:0rem;padding-right:0rem;padding-bottom:0rem;padding-left:0rem">'
        f"{block}{NAV}"
        "</div></header>"
        f"{BELOW}"
        '<script src="waterfall.js" defer></script>'
        f"<script>{inline}</script>"
        "</body></html>"
    )
    name = "masthead_fallback.html" if fallback else "masthead_page.html"
    path = OUT / name
    path.write_text(page)
    return str(path)


# --------------------------------------------------------------------------
# the browser run, memoised
# --------------------------------------------------------------------------

READY_JS = ("()=>{const c=document.querySelector('canvas.maars-masthead__canvas');"
            "return !!c && c.dataset.maarsReady==='1';}")

MEASURE_JS = r"""
() => {
  const band = document.querySelector('.maars-masthead');
  const cv   = document.querySelector('canvas.maars-masthead__canvas');
  const rows = [];
  for (const el of document.querySelectorAll('.maars-masthead__identity p, .maars-masthead__identity a, .maars-masthead__identity span')) {
    const txt = (el.innerText || '').trim();
    if (!txt) { continue; }
    const cs = getComputedStyle(el);
    const r  = el.getBoundingClientRect();
    rows.push({ text: txt.slice(0, 40), color: cs.color, size: parseFloat(cs.fontSize),
                weight: cs.fontWeight, family: cs.fontFamily.split(',')[0],
                top: r.top, bottom: r.bottom, left: r.left, right: r.right });
  }
  const b = band ? band.getBoundingClientRect() : null;
  const c = cv ? cv.getBoundingClientRect() : null;
  return {
    bandRect: b ? { x: b.x, y: b.y, w: b.width, h: b.height } : null,
    canvasRect: c ? { x: c.x, y: c.y, w: c.width, h: c.height } : null,
    canvasBacking: cv ? { w: cv.width, h: cv.height } : null,
    ariaHidden: cv ? cv.getAttribute('aria-hidden') : null,
    fallbackClass: band ? band.classList.contains('maars-masthead--fallback') : null,
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    identityLeft: (document.querySelector('.maars-masthead__call a') || {}).getBoundingClientRect
      ? document.querySelector('.maars-masthead__call a').getBoundingClientRect().left : null,
    mainLeft: (document.querySelector('.maars-lede__title') || {}).getBoundingClientRect
      ? document.querySelector('.maars-lede__title').getBoundingClientRect().left : null,
    state: (window.__maarsHandle && window.__maarsHandle.getState) ? window.__maarsHandle.getState() : null,
    text: rows
  };
}
"""

HANDLE_JS = """
() => {
  const band = document.querySelector('.maars-masthead');
  window.__maarsHandle = band ? band.maarsWaterfall : null;
  return !!window.__maarsHandle;
}
"""


def _shot(page, selector: str):
    Image, _, _ = _pil()
    png = page.locator(selector).first.screenshot()
    return Image.open(io.BytesIO(png)).convert("RGB")


def _run() -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover
        raise AssertionError("playwright is required (pip install playwright)") from None

    OUT.mkdir(parents=True, exist_ok=True)
    if not Path(CHROME).is_file():
        raise AssertionError(f"Chromium not found at {CHROME}. Set $MAARS_CHROME.")
    render_block()
    page_path = build_page()
    fallback_path = build_page(fallback=True)

    res: dict = {"errors": [], "font_misses": []}
    PARENT_FONTS = "twentytwentyfive/assets/fonts/"

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=CHROME_ARGS)

        def wire(pg):
            def on_console(m):
                if m.type != "error":
                    return
                loc = ""
                try:
                    loc = (m.location or {}).get("url", "") or ""
                except Exception:
                    loc = ""
                if "ERR_FILE_NOT_FOUND" in m.text and PARENT_FONTS in loc:
                    res["font_misses"].append(loc)
                    return
                res["errors"].append(f"console.{m.type}: {m.text}")
            pg.on("console", on_console)
            pg.on("pageerror", lambda e: res["errors"].append(f"pageerror: {e}"))

        # --- 1. desktop, motion allowed -----------------------------------
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        pg = ctx.new_page()
        wire(pg)
        pg.goto("file://" + page_path, wait_until="load")
        pg.wait_for_function(READY_JS, timeout=READY_MS)
        pg.wait_for_timeout(1400)
        pg.evaluate(HANDLE_JS)
        res["desktop"] = pg.evaluate(MEASURE_JS)
        band = _shot(pg, ".maars-masthead")
        band.save(OUT / "masthead_band_1440.png")
        res["band"] = band
        pg.screenshot(path=str(OUT / "masthead_page_1440.png"))

        # the picture must keep moving while motion is allowed
        first = _shot(pg, ".maars-masthead")
        pg.wait_for_timeout(700)
        second = _shot(pg, ".maars-masthead")
        res["moving_mad"] = _mad(first, second)

        # the composited background behind the identity, measured not assumed
        res["worst_bg"] = _worst_background(pg, band, res["desktop"])

        # destroy() must leave nothing behind
        res["after_destroy"] = pg.evaluate(
            """() => {
                 const band = document.querySelector('.maars-masthead');
                 const cv = document.querySelector('canvas.maars-masthead__canvas');
                 if (band && band.maarsWaterfall) { band.maarsWaterfall.destroy(); }
                 return { ready: cv ? (cv.dataset.maarsReady || '') : 'no-canvas',
                          mounted: cv ? (cv.dataset.maarsMounted || '') : 'no-canvas' };
               }""")
        ctx.close()

        # --- 2. prefers-reduced-motion ------------------------------------
        ctx = b.new_context(viewport={"width": 1440, "height": 900},
                            device_scale_factor=2, reduced_motion="reduce")
        pg = ctx.new_page()
        wire(pg)
        pg.goto("file://" + page_path, wait_until="load")
        pg.wait_for_function(READY_JS, timeout=READY_MS)
        pg.wait_for_timeout(300)
        pg.evaluate(HANDLE_JS)
        a = _shot(pg, ".maars-masthead")
        pg.wait_for_timeout(1200)
        c = _shot(pg, ".maars-masthead")
        res["static_mad"] = _mad(a, c)
        res["static_state"] = pg.evaluate(
            "()=>window.__maarsHandle ? window.__maarsHandle.getState() : null")
        a.save(OUT / "masthead_band_reduced.png")
        ctx.close()

        # --- 3. a phone ----------------------------------------------------
        ctx = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3)
        pg = ctx.new_page()
        wire(pg)
        pg.goto("file://" + page_path, wait_until="load")
        pg.wait_for_function(READY_JS, timeout=READY_MS)
        pg.wait_for_timeout(1000)
        pg.evaluate(HANDLE_JS)
        res["phone"] = pg.evaluate(MEASURE_JS)
        phone = _shot(pg, ".maars-masthead")
        phone.save(OUT / "masthead_band_390.png")
        res["phone_band"] = phone
        pg.screenshot(path=str(OUT / "masthead_page_390.png"))
        ctx.close()

        # --- 4. no 2D context ---------------------------------------------
        ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        pg = ctx.new_page()
        wire(pg)
        pg.goto("file://" + fallback_path, wait_until="load")
        pg.wait_for_timeout(900)
        res["fallback"] = pg.evaluate(
            """() => {
                 const band = document.querySelector('.maars-masthead');
                 const cv = document.querySelector('canvas.maars-masthead__canvas');
                 return { klass: band ? band.classList.contains('maars-masthead--fallback') : null,
                          reason: cv ? (cv.dataset.maarsFallbackReason || '') : '',
                          hidden: cv ? getComputedStyle(cv).display : '',
                          identity: !!document.querySelector('.maars-masthead__call a') };
               }""")
        fb = _shot(pg, ".maars-masthead")
        fb.save(OUT / "masthead_band_fallback.png")
        res["fallback_band"] = fb
        ctx.close()
        b.close()

    return res


def _worst_background(pg, band_img, measured) -> dict:
    """Sample the COMPOSITED band pixels directly under each line of the
    identity and report the brightest one found. The text has to clear AA
    against that, not against an average."""
    br = measured["bandRect"]
    if not br:
        return {}
    w, h = band_img.size
    sx = w / br["w"]
    sy = h / br["h"]
    px = band_img.load()
    worst = None
    for row in measured["text"]:
        y0 = max(0, int((row["top"] - br["y"]) * sy))
        y1 = min(h - 1, int((row["bottom"] - br["y"]) * sy))
        x0 = max(0, int((row["left"] - br["x"]) * sx))
        x1 = min(w - 1, int((row["right"] - br["x"]) * sx))
        if y1 <= y0 or x1 <= x0:
            continue
        for y in range(y0, y1, 2):
            for x in range(x0, x1, 3):
                p = px[x, y][:3]
                if worst is None or _lum(p) > _lum(worst):
                    worst = p
    return {"pixel": worst, "lum": _lum(worst) if worst else None}


def capture() -> dict:
    if "result" in _CACHE:
        return _CACHE["result"]
    if "error" in _CACHE:
        raise AssertionError(_CACHE["error"])
    try:
        r = _run()
    except AssertionError as exc:
        _CACHE["error"] = str(exc)
        raise
    _CACHE["result"] = r
    _report(r)
    return r


def _report(r: dict) -> None:
    band = r["band"]
    s = _stats(band)
    cs, rs = _structure(band)
    print("\nMAARS masthead — the band, measured at 1440px\n")
    print(f"  band                 {s['w']}x{s['h']} px")
    print(f"  grey mean / stdev    {s['mean']:.1f} / {s['stdev']:.2f}   (need stdev > {MIN_STDEV})")
    print(f"  distinct colours     {s['colors']}            (need > {MIN_COLORS})")
    print(f"  column spread        {cs:.2f}                 (need > {MIN_COL_SPREAD})")
    print(f"  row spread           {rs:.2f}                 (need > {MIN_ROW_SPREAD})")
    for name, frac in (("147.10", 0.20), ("147.255", 0.51), ("147.40", 0.80)):
        g, m = _column(band, frac)
        print(f"  column {name:>8}      luma {g:6.2f}   magenta-ness {m:7.2f}")
    print(f"  moving (MAD/700ms)   {r['moving_mad']:.3f}")
    print(f"  reduced motion MAD   {r['static_mad']:.3f}        (need < {STATIC_MAD})")
    st = r.get("static_state") or {}
    print(f"  reduced motion frames {st.get('frames')}          (need 1)")
    wb = r.get("worst_bg") or {}
    print(f"  worst pixel under text {wb.get('pixel')}  L={wb.get('lum'):.4f}"
          if wb.get("pixel") else "  worst pixel under text: none sampled")
    d = r["desktop"]
    print(f"  canvas css / backing {d['canvasRect']['w']:.0f}x{d['canvasRect']['h']:.0f}"
          f" / {d['canvasBacking']['w']}x{d['canvasBacking']['h']}")
    print(f"  aria-hidden          {d['ariaHidden']}")
    print(f"  identity left edge   {d['identityLeft']:.1f}   main heading left {d['mainLeft']:.1f}")
    p = r["phone"]
    print(f"  390px overflow       {p['overflow']}  ({p['scrollWidth']} vs {p['clientWidth']})")
    print(f"  fallback             {r['fallback']}")
    print(f"  after destroy()      {r['after_destroy']}")
    if r["font_misses"]:
        print(f"  (parent-theme webfonts unavailable over file://: {len(r['font_misses'])} — "
              "expected in this harness)")
    print()


# --------------------------------------------------------------------------
# the assertions
# --------------------------------------------------------------------------

def test_block_renders_the_markup_contract():
    render_block()
    html = (OUT / "masthead.html").read_text()
    for needle in (
        'class="wp-block-maars-masthead maars-masthead"',
        'class="maars-masthead__canvas"',
        'aria-hidden="true"',
        'class="maars-masthead__identity"',
        'class="maars-masthead__call"',
        'class="maars-masthead__long"',
        'class="maars-masthead__tuned"',
        'class="maars-fig"',
        "147.255",
        "KSØMAN",
    ):
        assert needle in html, f"maars/masthead no longer emits {needle!r}\n{html}"
    assert "role=" not in html.split("</canvas>")[0], \
        "the canvas is decorative; it must not carry a role"
    # The identity is real text, not something drawn into the canvas.
    assert "Manhattan Area Amateur Radio Society" in html


def test_the_band_is_not_a_flat_rectangle():
    r = capture()
    s = _stats(r["band"])
    cs, rs = _structure(r["band"])
    assert s["stdev"] > MIN_STDEV, (
        f"the band is flat: grey stdev {s['stdev']:.2f} (need > {MIN_STDEV}). "
        "That is the failure this file exists to catch.")
    assert s["colors"] > MIN_COLORS, f"only {s['colors']} distinct colours in the band"
    assert cs > MIN_COL_SPREAD, (
        f"columns do not differ ({cs:.2f}); the band has no spectrum in it")
    assert rs > MIN_ROW_SPREAD, (
        f"rows do not differ ({rs:.2f}); the band is a gradient, not a waterfall")


def test_the_carrier_is_marked_and_it_is_magenta():
    r = capture()
    lo_g, lo_m = _column(r["band"], 0.20)
    hi_g, hi_m = _column(r["band"], 0.80)
    c_g, c_m = _column(r["band"], 0.51)
    floor_g = (lo_g + hi_g) / 2
    floor_m = (lo_m + hi_m) / 2
    assert c_g > floor_g * CARRIER_GAIN, (
        f"nothing is marked at 147.255: carrier column luma {c_g:.2f} against a "
        f"noise floor of {floor_g:.2f}")
    assert c_m > floor_m + 6.0, (
        f"the carrier is not magenta: {c_m:.2f} against {floor_m:.2f}. Magenta is "
        "the one colour this site reserves; the carrier is what it is reserved for.")


def test_it_moves_slowly_and_stops_for_reduced_motion():
    r = capture()
    assert r["moving_mad"] > 0.05, (
        "the waterfall is not scrolling: two captures 700ms apart are identical")
    assert r["static_mad"] < STATIC_MAD, (
        f"prefers-reduced-motion is not honoured: the band moved {r['static_mad']:.3f} "
        "between two captures a second apart")
    st = r.get("static_state") or {}
    assert st.get("frames") == 1, (
        f"under prefers-reduced-motion the module must draw ONE frame; it drew "
        f"{st.get('frames')}")


def test_the_identity_clears_wcag_against_the_worst_pixel_on_the_band():
    r = capture()
    worst = (r.get("worst_bg") or {}).get("pixel")
    assert worst, "no band pixels were sampled under the identity"
    failures = []
    for row in r["desktop"]["text"]:
        fg = _parse_rgb(row["color"])
        if not fg:
            continue
        cr = _ratio(fg, worst)
        large = row["size"] >= 24 or (row["size"] >= 18.66 and int(row["weight"]) >= 700)
        need = 3.0 if large else AA_NORMAL
        if cr < need:
            failures.append((cr, need, row))
    for cr, need, row in failures:
        print(f"  FAIL {cr:5.2f}:1 (need {need}) {row['size']:.0f}px "
              f"{row['color']} on {worst}  {row['text']!r}")
    assert not failures, (
        f"text on the band fails WCAG AA against the brightest pixel behind it {worst}")
    # and no text under the floor the brief sets
    for row in r["desktop"]["text"]:
        assert row["size"] >= 17.5, f"{row['text']!r} is {row['size']}px; the floor is 18px"
        assert int(row["weight"]) >= 400, f"{row['text']!r} is weight {row['weight']}"


def test_the_band_is_full_bleed_and_the_identity_keeps_the_page_left_edge():
    r = capture()
    d = r["desktop"]
    assert d["canvasRect"]["x"] <= 0.5, (
        f"the band does not reach the left edge (x={d['canvasRect']['x']})")
    assert d["canvasRect"]["w"] >= d["clientWidth"] - 1, (
        f"the band is {d['canvasRect']['w']}px wide in a {d['clientWidth']}px window")
    assert 150 <= round(d["canvasRect"]["h"]) <= 190, (
        f"the band is {d['canvasRect']['h']}px tall; the brief fixes it at 150-190")
    assert abs(d["identityLeft"] - d["mainLeft"]) < 2.0, (
        f"the callsign starts at {d['identityLeft']:.1f} and the page's heading at "
        f"{d['mainLeft']:.1f}; the site has one left edge")


def test_it_survives_a_phone():
    r = capture()
    p = r["phone"]
    assert not p["overflow"], (
        f"horizontal scroll at 390px: {p['scrollWidth']} > {p['clientWidth']}")
    s = _stats(r["phone_band"])
    assert s["stdev"] > MIN_STDEV, f"the band is flat at 390px (stdev {s['stdev']:.2f})"
    assert 150 <= round(p["canvasRect"]["h"]) <= 190


def test_no_canvas_means_a_soft_gradient_and_never_an_error():
    r = capture()
    f = r["fallback"]
    assert f["klass"], "with no 2D context the band must take maars-masthead--fallback"
    assert f["reason"] == "no-2d-context", f"fallback reason was {f['reason']!r}"
    assert f["hidden"] == "none", "the fallback hides the canvas and shows the CSS gradient"
    assert f["identity"], "the identity must still be there with no canvas"
    s = _stats(r["fallback_band"])
    assert s["stdev"] > 2.0, "the fallback band is a flat fill, not a soft gradient"
    assert not r["errors"], "the page logged errors:\n  " + "\n  ".join(r["errors"][:8])


def test_destroy_takes_everything_back():
    r = capture()
    a = r["after_destroy"]
    assert a["ready"] == "", f"destroy() left dataset.maarsReady = {a['ready']!r}"
    assert a["mounted"] == "", f"destroy() left dataset.maarsMounted = {a['mounted']!r}"


def main() -> int:
    checks = [
        ("the block emits the markup contract", test_block_renders_the_markup_contract),
        ("the band is not a flat rectangle", test_the_band_is_not_a_flat_rectangle),
        ("147.255 is marked, in magenta", test_the_carrier_is_marked_and_it_is_magenta),
        ("it scrolls, and it stops for reduced motion", test_it_moves_slowly_and_stops_for_reduced_motion),
        ("the identity clears AA on the worst pixel", test_the_identity_clears_wcag_against_the_worst_pixel_on_the_band),
        ("full bleed, one left edge", test_the_band_is_full_bleed_and_the_identity_keeps_the_page_left_edge),
        ("390px holds", test_it_survives_a_phone),
        ("no canvas is a gradient, not an error", test_no_canvas_means_a_soft_gradient_and_never_an_error),
        ("destroy() takes everything back", test_destroy_takes_everything_back),
    ]
    failed = 0
    for name, fn in checks:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL  {name}\n        {exc}")
    print(f"\n  screenshots in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
