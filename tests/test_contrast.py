"""Contrast gate: render the theme's own block templates and measure every
text node against WCAG AA.

Why this file exists
--------------------
The site this project replaces had a link colour of #FFFFFF sitting on a white
background: 76 of 114 homepage links were invisible, for years, with nothing to
catch it. This rebuild shipped the same class of bug in its first deployment,
inverted:

    theme.json sets elements.heading.text = navy, which WordPress emits as
    `:root :where(h1..h6){color:navy}`. That element rule beats the colour a
    heading inherits from its section, so the hero h1 rendered navy #00008C on
    ink #14142B -- a measured 1.18:1 where large text needs 3.0.

Measured on the live site, not inferred. The fix lives in maars.css and makes
headings on dark surfaces follow the surface. This gate exists so neither
direction of the mistake can come back.

Run:  python3 tests/test_contrast.py
Needs: playwright, Pillow, the bundled Chromium.
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "out")
CHROME = os.path.expanduser(
    "~/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"
)

TEMPLATES = [
    "wp/themes/maars/templates/front-page.html",
    "wp/themes/maars/templates/archive-maars_publication.html",
    "wp/themes/maars/templates/single-maars_publication.html",
    "wp/themes/maars/parts/header.html",
    "wp/themes/maars/parts/footer.html",
]

BLOCK_COMMENT = re.compile(r"<!--\s*/?wp:[^>]*?-->", re.S)
PLAIN_COMMENT = re.compile(r"<!--(?!\s*/?wp:).*?-->", re.S)


def strip_blocks(html: str) -> str:
    """Block delimiters are comments; the HTML between them is what renders."""
    html = BLOCK_COMMENT.sub("", html)
    return PLAIN_COMMENT.sub("", html)


def theme_css_vars() -> str:
    """theme.json presets become CSS custom properties at runtime; recreate the
    handful the templates reference so the standalone render is faithful."""
    import json

    d = json.load(open(os.path.join(ROOT, "wp/themes/maars/theme.json")))
    palette = d["settings"]["color"]["palette"]
    lines = [
        f"  --wp--preset--color--{p['slug']}: {p['color']};" for p in palette
    ]
    # WordPress also emits the element rules from styles.elements. Reproducing
    # them is the whole point: the bug lived in exactly this rule.
    el = d.get("styles", {}).get("elements", {})

    def resolve(v):
        m = re.match(r"var:preset\|color\|(.+)", v or "")
        return f"var(--wp--preset--color--{m.group(1)})" if m else v

    rules = [":root {\n" + "\n".join(lines) + "\n}"]
    for tag, spec in (("h1, h2, h3, h4, h5, h6", el.get("heading")),
                      ("a", el.get("link"))):
        if spec and "color" in spec and "text" in spec["color"]:
            rules.append(
                f":root :where({tag}) {{ color: {resolve(spec['color']['text'])}; }}"
            )
    # The preset colour utility classes the templates actually use.
    for p in palette:
        rules.append(
            f".has-{p['slug']}-color {{ color: var(--wp--preset--color--{p['slug']}); }}"
        )
        rules.append(
            f".has-{p['slug']}-background-color {{ background-color: "
            f"var(--wp--preset--color--{p['slug']}); }}"
        )
    return "\n".join(rules)


def build_page() -> str:
    parts = []
    for t in TEMPLATES:
        p = os.path.join(ROOT, t)
        if os.path.exists(p):
            parts.append(f"<!-- SOURCE {t} -->\n" + strip_blocks(open(p).read()))
    css = open(os.path.join(ROOT, "wp/themes/maars/assets/css/maars.css")).read()
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        "<title>contrast harness</title>"
        f"<style>{theme_css_vars()}</style><style>{css}</style>"
        "</head><body>" + "\n".join(parts) + "</body></html>"
    )
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "contrast_harness.html")
    open(path, "w").write(page)
    return path


def _lum(rgb):
    def f(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = [f(x) for x in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def parse(s):
    m = re.findall(r"[\d.]+", s or "")
    return tuple(int(float(x)) for x in m[:3]) if len(m) >= 3 else None


def measure(path: str):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=CHROME,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page()
        pg.goto("file://" + path, wait_until="load")
        pg.wait_for_timeout(400)
        rows = pg.evaluate(
            """()=>{
            const sel='h1,h2,h3,h4,h5,h6,p,a,li,figcaption,button,strong,em,span';
            const out=[];
            for (const el of document.querySelectorAll(sel)) {
              const txt=(el.innerText||'').trim();
              if(!txt||txt.length<3) continue;
              if(el.querySelector(sel)) continue;
              const cs=getComputedStyle(el);
              if(cs.visibility==='hidden'||cs.display==='none'||cs.opacity==='0') continue;
              let e=el,bg='rgb(255, 255, 255)';
              while(e){const c=getComputedStyle(e).backgroundColor;
                if(c&&c!=='rgba(0, 0, 0, 0)'&&c!=='transparent'){bg=c;break;} e=e.parentElement;}
              out.push({t:txt.slice(0,50),fg:cs.color,bg,
                        size:parseFloat(cs.fontSize),weight:cs.fontWeight,tag:el.tagName});
            }
            return out;}"""
        )
        b.close()
    return rows


def main() -> int:
    path = build_page()
    rows = measure(path)
    print("ks0man-site contrast gate — the theme's own templates, measured\n")
    if len(rows) < 15:
        print(f"FAIL  only {len(rows)} text nodes rendered; the harness is not "
              "exercising the templates")
        return 1

    failures = []
    for r in rows:
        fg, bg = parse(r["fg"]), parse(r["bg"])
        if not fg or not bg:
            continue
        cr = ratio(fg, bg)
        large = r["size"] >= 24 or (r["size"] >= 18.66 and int(r["weight"]) >= 700)
        need = 3.0 if large else 4.5
        if cr < need:
            failures.append((cr, need, r))

    print(f"  text nodes measured : {len(rows)}")
    print(f"  WCAG AA failures    : {len(failures)}\n")
    for cr, need, r in sorted(failures)[:12]:
        print(
            f"  FAIL {cr:5.2f}:1 (need {need}) {r['tag']:3} {r['size']:.0f}px "
            f"fg={r['fg']} bg={r['bg']}  {r['t']!r}"
        )

    checks = [
        ("every text node meets WCAG AA", not failures),
        ("the harness actually rendered the templates", len(rows) >= 15),
    ]
    # The specific regression, asserted by name so it cannot silently return.
    css = open(os.path.join(ROOT, "wp/themes/maars/assets/css/maars.css")).read()
    checks.append(
        ("dark surfaces override the theme.json heading colour",
         ".maars-hero :is(h1" in css or ".has-ink-background-color :is(h1" in css)
    )

    failed = 0
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            failed += 1
    print(f"\n{len(checks) - failed}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
