#!/usr/bin/env python3
"""WebGL2 proof for the MAARS skywave homepage canvas.

There is no GPU here, so Chromium runs on SwiftShader. The job of this file is to
refuse the two failure modes a naive smoke test waves through:

  1. a canvas that reports itself *ready* but is blank, and
  2. a canvas that renders one scene and then ignores the band buttons.

How it earns the right to say otherwise:

  * The page runs under prefers-reduced-motion, which the contract requires the
    module to honour by drawing one static frame. A still scene is what makes the
    rest of the measurement mean anything.
  * Each band is captured as a burst of frames and averaged, so any residual
    motion is damped rather than mistaken for a response to input.
  * 80 m is then measured a SECOND time at the end — same input, later in time,
    one more mount. That is the control. A band switch only counts if it moves
    the picture substantially further than the control does.
  * Blankness is measured on the pixels that were saved, not on a separate
    capture: grey-level standard deviation plus the count of distinct colours.

Every number behind every assertion is printed as a table, so a human can check
the claim instead of trusting it.

Runs two ways:
    pytest tests/test_webgl.py -s
    python3 tests/test_webgl.py

Environment overrides: MAARS_CHROME, MAARS_CHROME_ARGS, MAARS_HARNESS.
"""
from __future__ import annotations

import base64
import io
import os
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REPO = TESTS.parent
OUT = TESTS / "out"
HARNESS = Path(os.environ.get("MAARS_HARNESS") or (TESTS / "webgl_harness.html"))
CHROME = os.environ.get("MAARS_CHROME") or os.path.expanduser(
    "~/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome")
# Software GL. There is no GPU in this environment.
#
# The first set is the one this environment specifies. MEASURED, not assumed: in
# Chromium 1243 the deprecated --use-gl=swiftshader flag makes the GPU process drop
# the WebGL2 context a few hundred ms after creation (webglcontextlost fires, the
# canvas paints the broken-image icon, toDataURL returns a cleared buffer) unless the
# page happens to be running a continuous rAF loop. A correct module that honours
# prefers-reduced-motion by drawing ONE frame hits that bug every time. So if the
# context is lost, the run is retried on the flag set that Chromium still supports —
# and which config was used is printed with the results. A lost context is a browser
# fault; it must never be reported as a skywave.js fault.
ARG_SETS = [
    ["--no-sandbox", "--use-gl=swiftshader", "--enable-unsafe-swiftshader"],
    ["--no-sandbox", "--enable-unsafe-swiftshader"],
]
if os.environ.get("MAARS_CHROME_ARGS"):
    ARG_SETS = [os.environ["MAARS_CHROME_ARGS"].split()]
CHROME_ARGS = ARG_SETS[0]

# key, dataset band, what the band is for (contract's own words)
BANDS = [
    ("80", "80m", "3.920 MHz Kansas Sideband Net"),
    ("40", "40m", "7.260 MHz Kansas Weather Net"),
    ("20", "20m", "14.290 MHz daytime DX"),
    ("2",  "2m",  "147.255 MHz repeater - line of sight, no skip"),
]

# --- thresholds -----------------------------------------------------------
MIN_STDEV = 8.0        # grey-level contrast; a flat fill scores ~0
MIN_COLORS = 500       # a real shaded scene has thousands
MIN_MAD = 0.5          # mean absolute pixel difference, 0-255, for "these differ"
MIN_CHANGED = 0.002    # and at least 0.2% of pixels must move by >8 levels
MOTION_MARGIN = 2.0    # a band switch must out-move the same-band control this far
STATIC_MAD = 1.0       # under prefers-reduced-motion the scene must hold still
SETTLE_MS = 500
BURST = 4              # frames averaged per band (power of two)
BURST_GAP_MS = 150
READY_TIMEOUT_MS = 20000

# The whole run happens under prefers-reduced-motion, which the contract requires the
# module to honour by drawing ONE static frame. That is what makes the band comparison
# meaningful: with the animation held still, any pixel that moves moved because the
# band changed. If the module animates anyway, the static check below says so by name
# instead of letting animation noise masquerade as a response to input.

READY_JS = "() => { const c = document.getElementById('skywave'); return !!c && c.dataset.maarsReady === '1'; }"

_CACHE: dict = {}


# --------------------------------------------------------------------------
# imaging helpers (PIL only — no numpy dependency)
# --------------------------------------------------------------------------

def _pil():
    try:
        from PIL import Image, ImageChops, ImageStat  # noqa: F401
    except ImportError:  # pragma: no cover
        raise AssertionError("Pillow is required for the pixel assertions (pip install pillow)") from None
    from PIL import Image, ImageChops, ImageStat
    return Image, ImageChops, ImageStat


def _flatten(rgba):
    """Composite onto white so a transparent canvas reads as blank, not as noise."""
    Image, _, _ = _pil()
    bg = Image.new("RGB", rgba.size, (255, 255, 255))
    bg.paste(rgba, mask=rgba.split()[3])
    return bg


def _alpha_fraction(rgba) -> float:
    hist = rgba.split()[3].histogram()
    total = sum(hist) or 1
    return sum(hist[9:]) / float(total)


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


def _diff(a, b) -> tuple[float, float]:
    """(mean absolute difference 0-255, fraction of pixels moved by more than 8 levels)"""
    _, ImageChops, ImageStat = _pil()
    if a.size != b.size:
        b = b.resize(a.size)
    d = ImageChops.difference(a, b)
    st = ImageStat.Stat(d)
    mad = sum(st.mean) / float(len(st.mean))
    hist = d.convert("L").histogram()
    total = sum(hist) or 1
    changed = sum(hist[9:]) / float(total)
    return mad, changed


def _mean_of(a, b):
    _, ImageChops, _ = _pil()
    if a.size != b.size:
        b = b.resize(a.size)
    return ImageChops.add(a, b, scale=2.0)


def _mean_of_list(imgs):
    """Pairwise tree mean — exact for a power-of-two burst, and PIL-only."""
    layer = list(imgs)
    while len(layer) > 1:
        nxt = []
        for i in range(0, len(layer) - 1, 2):
            nxt.append(_mean_of(layer[i], layer[i + 1]))
        if len(layer) % 2:
            nxt.append(layer[-1])
        layer = nxt
    return layer[0]


def _looks_empty(rgb) -> bool:
    """Weak test, used only to decide whether toDataURL gave us a real frame."""
    s = _stats(rgb)
    return s["stdev"] < 0.5 or s["colors"] < 8


# --------------------------------------------------------------------------
# the one browser run, memoised so every check reuses it
# --------------------------------------------------------------------------

def _grab(page):
    """Canvas pixels, straight out of the drawing buffer.

    toDataURL is the primary source and only works because skywave.js asks for
    preserveDrawingBuffer; without it Chromium hands back a cleared buffer once the
    frame has been composited. If that ever happens the composited element
    screenshot is used instead, and which source was used is recorded per band and
    printed — a silent switch would quietly change what is being measured."""
    Image, _, _ = _pil()
    direct = None
    url = page.evaluate(
        "() => { const c = document.getElementById('skywave');"
        " try { return c.toDataURL('image/png'); } catch (e) { return 'ERR:' + e; } }")
    if isinstance(url, str) and url.startswith("data:image/png;base64,"):
        rgba = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA")
        rgb = _flatten(rgba)
        if not _looks_empty(rgb):
            return rgb, _alpha_fraction(rgba), "toDataURL"
        direct = (rgb, _alpha_fraction(rgba))

    png = page.locator("#skywave").first.screenshot()
    rgba = Image.open(io.BytesIO(png)).convert("RGBA")
    rgb = _flatten(rgba)
    if direct is not None and _looks_empty(rgb):
        # Both routes agree there is nothing there. That is a blank RENDER, not a
        # readback problem, so keep the direct pixels and let the blankness check
        # be the one that speaks.
        return direct[0], direct[1], "toDataURL"
    return rgb, _alpha_fraction(rgba), "element-screenshot"


def _capture() -> dict:
    if "result" in _CACHE:
        return _CACHE["result"]
    if "error" in _CACHE:
        raise AssertionError(_CACHE["error"])
    try:
        res = _run()
    except AssertionError as exc:
        _CACHE["error"] = str(exc)
        raise
    _CACHE["result"] = res
    _print_table(res)
    return res


LOST_JS = """() => {
  const c = document.getElementById('skywave');
  if (!c) { return { lost: true, flagged: true }; }
  let g = null;
  try { g = c.getContext('webgl2'); } catch (e) { g = null; }
  return { lost: (!g) || g.isContextLost(), flagged: !!(window.__maarsHarness || {}).lost };
}"""


def _preflight():
    if not HARNESS.is_file():
        raise AssertionError(f"missing harness page {HARNESS}")
    if not Path(CHROME).is_file():
        raise AssertionError(
            f"Chromium not found at {CHROME}. Set $MAARS_CHROME or run "
            "`python3 -m playwright install chromium`.")
    skywave = REPO / "wp/themes/maars/assets/js/skywave.js"
    if not skywave.is_file():
        raise AssertionError(f"missing {skywave} — nothing to render")
    OUT.mkdir(parents=True, exist_ok=True)


def _run() -> dict:
    try:
        import playwright  # noqa: F401
    except ImportError:  # pragma: no cover
        raise AssertionError(
            "playwright is required (pip install playwright). No browser check ran.") from None
    _preflight()
    for i, args in enumerate(ARG_SETS):
        res = _attempt(args)
        if not res.get("context_lost"):
            res["args_used"] = args
            res["args_attempt"] = i + 1
            return res
    raise AssertionError(
        "Chromium dropped the WebGL2 context under every launch configuration tried:\n  "
        + "\n  ".join(" ".join(a) for a in ARG_SETS)
        + "\nThis is a browser/SwiftShader fault, not a skywave.js fault — the context was "
          "lost before a frame could be read back. No rendering claim can be made from this run.")


def _attempt(args: list) -> dict:
    from playwright.sync_api import sync_playwright
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import TimeoutError as PWTimeout

    res: dict = {"bands": {}, "console": [], "pageerrors": [], "chrome": CHROME, "args": args}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, args=args)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900},
                                  device_scale_factor=1, reduced_motion="reduce")
        page = ctx.new_page()
        page.on("console", lambda m: res["console"].append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: res["pageerrors"].append(str(e)))
        page.goto(HARNESS.as_uri())

        try:
            page.wait_for_function(READY_JS, timeout=READY_TIMEOUT_MS)
        except (PWTimeout, PWError):
            lost = page.evaluate(LOST_JS)
            if lost["lost"] or lost["flagged"]:
                browser.close()
                return {"context_lost": True, "args": args}
            diag = page.evaluate(
                "() => ({ err: document.body.dataset.harnessError || '',"
                " api: typeof (window.MAARSSkywave || {}).mount,"
                " ctx: (window.__maarsHarness || {}).contextRequests || [],"
                " fb: document.getElementById('skywave-wrap').className })")
            browser.close()
            raise AssertionError(
                f"canvas never set dataset.maarsReady='1' within {READY_TIMEOUT_MS} ms.\n"
                f"  harness error : {diag['err'] or '(none)'}\n"
                f"  MAARSSkywave.mount typeof: {diag['api']}\n"
                f"  webgl2 context requests  : {diag['ctx']}\n"
                f"  wrapper class            : {diag['fb']}\n"
                f"  page errors  : {res['pageerrors']}\n"
                f"  console      : {res['console'][-12:]}")

        info = page.evaluate(
            "() => { const c = document.getElementById('skywave');"
            " return { ready: c.dataset.maarsReady || '',"
            "          fallback: (c.dataset.maarsFallback === undefined) ? null : c.dataset.maarsFallback,"
            "          fallbackClass: c.parentElement.classList.contains('maars-skywave--fallback'),"
            "          ctxRequests: (window.__maarsHarness || {}).contextRequests || [],"
            "          w: c.width, h: c.height }; }")
        res.update(info)

        def burst(key):
            """Click a band, let it settle, then average BURST frames of it."""
            page.locator(f"#band-{key}").first.click()
            try:
                page.wait_for_function(READY_JS, timeout=5000)
                ready_again = True
            except (PWTimeout, PWError):
                ready_again = False
            page.wait_for_timeout(SETTLE_MS)
            frames, source, alpha = [], None, 0.0
            for i in range(BURST):
                if i:
                    page.wait_for_timeout(BURST_GAP_MS)
                img, alpha, source = _grab(page)
                frames.append(img)
            drift, _ = _diff(frames[0], frames[-1])
            return {
                "frames": frames, "avg": _mean_of_list(frames), "first": frames[0],
                "source": source, "alpha": alpha, "ready_again": ready_again,
                "drift": drift,
                "harness_band": page.evaluate("() => document.body.dataset.harnessBand || ''"),
                "harness_via": page.evaluate("() => document.body.dataset.harnessVia || ''"),
            }

        for key, band, blurb in BANDS:
            rec = burst(key)
            if page.evaluate(LOST_JS)["lost"]:
                browser.close()
                return {"context_lost": True, "args": args}
            path = OUT / f"skywave_{band}.png"
            rec["first"].save(path)
            rec.update({"key": key, "blurb": blurb, "path": path}, **_stats(rec["first"]))
            res["bands"][band] = rec

        # Control: go back to 80 m and take the same measurement again. Same input,
        # later in time, one more mount. Whatever this moves is NOT the band.
        control_rec = burst("80")
        control_rec["first"].save(OUT / "skywave_80m_control.png")
        res["control_mad"], res["control_changed"] = _diff(res["bands"]["80m"]["avg"], control_rec["avg"])
        res["control_path"] = OUT / "skywave_80m_control.png"

        final = page.evaluate(LOST_JS)
        if final["lost"] or final["flagged"]:
            browser.close()
            return {"context_lost": True, "args": args}
        res["context_lost"] = False
        res["harness_error"] = page.evaluate("() => document.body.dataset.harnessError || ''")
        browser.close()

    base = res["bands"]["80m"]["avg"]
    for band, rec in res["bands"].items():
        rec["mad_vs_80m"], rec["changed_vs_80m"] = _diff(base, rec["avg"])
    res["drift_mad"] = max(r["drift"] for r in res["bands"].values())
    res["gate"] = max(MIN_MAD, MOTION_MARGIN * res["control_mad"])
    return res


def _print_table(res: dict) -> None:
    print("\n  MAARS skywave — SwiftShader pixel evidence")
    print(f"  chrome  : {res['chrome']}")
    print(f"  args    : {' '.join(res.get('args_used', []))}"
          + ("" if res.get("args_attempt", 1) == 1
             else f"   (attempt {res['args_attempt']} — an earlier flag set lost the GL context)"))
    print(f"  harness : {HARNESS}")
    print(f"  canvas  : {res.get('w')}x{res.get('h')}  ready={res.get('ready')!r} "
          f"fallback={res.get('fallback')!r} fallbackClass={res.get('fallbackClass')}")
    print(f"  webgl2 context requests: {res.get('ctxRequests')}   "
          f"prefers-reduced-motion: reduce   frames averaged per band: {BURST}")
    print()
    head = ("  band  what                                          source              "
            "mean   stdev  colors  alpha%  drift  MAD vs 80m  moved%  via")
    print(head)
    print("  " + "-" * (len(head) - 2))
    for _, band, _ in BANDS:
        r = res["bands"][band]
        print(f"  {band:<5} {r['blurb'][:44]:<44}  {r['source']:<18} "
              f"{r['mean']:6.1f} {r['stdev']:7.2f} {r['colors']:7d} "
              f"{100*r['alpha']:6.1f} {r['drift']:6.3f} {r['mad_vs_80m']:11.3f} "
              f"{100*r['changed_vs_80m']:7.2f}  {r['harness_via']}")
    print()
    print(f"  control  80m measured twice (same input, later, one more mount): "
          f"MAD {res['control_mad']:.3f}, {100*res['control_changed']:.2f}% of pixels moved")
    print(f"  drift    worst first-to-last frame movement inside one band: {res['drift_mad']:.3f} "
          f"(must stay under {STATIC_MAD} — reduced motion means one static frame)")
    print(f"  gate     a band switch must beat max({MIN_MAD}, {MOTION_MARGIN} x control) "
          f"= {res['gate']:.3f} MAD and move {100*MIN_CHANGED:.1f}% of pixels")
    print(f"  blank    every band needs stdev >= {MIN_STDEV} and >= {MIN_COLORS} distinct colours")
    print(f"  screenshots: {OUT}")
    if res.get("pageerrors"):
        print(f"  page errors: {res['pageerrors']}")
    print()


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------

def test_canvas_reports_ready_without_falling_back():
    res = _capture()
    assert res["ready"] == "1", f"dataset.maarsReady is {res['ready']!r}, not '1'"
    assert res["fallback"] is None, (
        f"canvas.dataset.maarsFallback is set ({res['fallback']!r}) — WebGL2 did not come up")
    assert res["fallbackClass"] is False, \
        "parent carries maars-skywave--fallback — the module took the no-WebGL2 path"
    assert res["ctxRequests"], "skywave.js never asked for a webgl2 context"
    assert "webgl2" in res["ctxRequests"], \
        f"expected a 'webgl2' context request, got {res['ctxRequests']}"


def test_the_webgl_context_survived_the_whole_run():
    res = _capture()
    assert res.get("context_lost") is False, "the WebGL2 context was lost during the run"


def test_no_page_errors_or_harness_errors():
    res = _capture()
    assert not res["pageerrors"], "uncaught JS errors:\n  " + "\n  ".join(res["pageerrors"])
    assert not res["harness_error"], f"harness reported: {res['harness_error']}"


def test_every_band_screenshot_is_written():
    res = _capture()
    for _, band, _ in BANDS:
        p = res["bands"][band]["path"]
        assert p.is_file(), f"missing screenshot {p}"
        assert p.stat().st_size > 2000, f"{p} is suspiciously small ({p.stat().st_size} bytes)"


def test_every_band_renders_a_non_blank_canvas():
    res = _capture()
    bad = []
    for _, band, _ in BANDS:
        r = res["bands"][band]
        if r["stdev"] < MIN_STDEV:
            bad.append(f"{band}: grey stdev {r['stdev']:.2f} < {MIN_STDEV} — the canvas is flat")
        if r["colors"] < MIN_COLORS:
            bad.append(f"{band}: only {r['colors']} distinct colours (< {MIN_COLORS}) — nothing was shaded")
        if r["w"] < 200 or r["h"] < 150:
            bad.append(f"{band}: canvas is {r['w']}x{r['h']} — too small to be the scene")
    assert not bad, "BLANK / DEGENERATE CANVAS:\n  " + "\n  ".join(bad)


def test_band_switch_80m_to_20m_changes_the_image():
    res = _capture()
    r = res["bands"]["20m"]
    assert r["mad_vs_80m"] >= res["gate"], (
        f"80m -> 20m moved the image by MAD {r['mad_vs_80m']:.3f}, which does not beat "
        f"{res['gate']:.3f} (same-band control {res['control_mad']:.3f}). "
        "The canvas is ignoring the band selector.")
    assert r["changed_vs_80m"] >= MIN_CHANGED, (
        f"only {100*r['changed_vs_80m']:.3f}% of pixels moved between 80m and 20m "
        f"(need {100*MIN_CHANGED:.1f}%)")


def test_two_metres_looks_different_from_eighty_metres():
    """The teaching point: at 2 m the ray escapes to space instead of refracting."""
    res = _capture()
    r = res["bands"]["2m"]
    assert r["mad_vs_80m"] >= res["gate"], (
        f"2m vs 80m MAD {r['mad_vs_80m']:.3f} does not beat {res['gate']:.3f} "
        f"(same-band control {res['control_mad']:.3f}) — the escaping ray is not being drawn")
    assert r["changed_vs_80m"] >= MIN_CHANGED, (
        f"2m vs 80m moved only {100*r['changed_vs_80m']:.3f}% of pixels")


def test_forty_metres_is_also_its_own_scene():
    res = _capture()
    r = res["bands"]["40m"]
    assert r["mad_vs_80m"] >= res["gate"], (
        f"40m vs 80m MAD {r['mad_vs_80m']:.3f} does not beat {res['gate']:.3f} — "
        "adjacent HF bands should still hop differently")


def test_the_difference_is_the_band_and_not_the_clock():
    """Control. Measuring 80 m twice — same input, later in time, one more mount —
    must move far less than measuring 80 m against another band. Without this, an
    animation that ignores the buttons would sail through."""
    res = _capture()
    swings = {b: res["bands"][b]["mad_vs_80m"] for _, b, _ in BANDS if b != "80m"}
    best = max(swings.values())
    assert best >= res["gate"], (
        f"largest band swing {best:.3f} vs same-band control {res['control_mad']:.3f} — "
        f"needs to clear {res['gate']:.3f} (max of the {MIN_MAD} floor and {MOTION_MARGIN}x the "
        "control). The scene is changing with the clock, or not at all — but not with the band.")
    assert res["bands"]["80m"]["mad_vs_80m"] < 0.001, "80m is not identical to itself"


def test_reduced_motion_holds_the_scene_still():
    """The contract: prefers-reduced-motion renders one static frame. This is also
    what licenses every band comparison above — a still scene means a pixel that
    moved, moved because the band changed."""
    res = _capture()
    assert res["drift_mad"] < STATIC_MAD, (
        f"the canvas kept moving under prefers-reduced-motion (worst within-band drift "
        f"{res['drift_mad']:.3f} MAD, limit {STATIC_MAD}). The contract requires one static "
        "frame, and while the scene animates the band comparison cannot be trusted.")


def test_every_band_actually_reached_the_module():
    res = _capture()
    for _, band, _ in BANDS:
        r = res["bands"][band]
        assert r["harness_band"] == band, \
            f"harness thinks the band is {r['harness_band']!r} after clicking #band-{r['key']}"
        assert r["source"] == "toDataURL", (
            f"{band}: canvas.toDataURL() came back blank so the composited screenshot was used "
            "instead — the drawing buffer was not preserved")


# --------------------------------------------------------------------------
# standalone runner
# --------------------------------------------------------------------------

def _all_checks():
    g = globals()
    return [(n, g[n]) for n in list(g) if n.startswith("test_") and callable(g[n])]


def main() -> int:
    print(f"ks0man-site WebGL gate — harness {HARNESS}")
    failures = []
    for name, fn in _all_checks():
        try:
            fn()
        except AssertionError as exc:
            failures.append(name)
            print(f"FAIL  {name}")
            for line in str(exc).splitlines():
                print(f"      {line}")
        except Exception as exc:  # noqa: BLE001
            failures.append(name)
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS  {name}")
    total = len(_all_checks())
    print(f"\n{total - len(failures)}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
