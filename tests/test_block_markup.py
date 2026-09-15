"""Gate: every block comment in this theme is well formed, balanced and nested.

WHY THIS FILE EXISTS
--------------------
A block template is HTML with HTML comments load-bearing in it. Two silent
failure modes live in that arrangement and neither one raises an error
anywhere:

  1. A DELIMITER THAT WORDPRESS DOES NOT MATCH. The block parser's grammar is
     stricter than it looks. It wants `<!-- wp:name -->`, with a space after
     `wp:name` before the attribute object and a space before the closing
     `-->`. Write `<!--wp:paragraph-->` and WordPress does not see a block at
     all: it sees an HTML comment, the markup inside it renders as raw HTML,
     and everything a render_callback would have produced is gone. Nothing
     warns. The page just quietly does less.

  2. AN UNCLOSED OR MIS-NESTED DELIMITER. `<!-- wp:group -->` with no
     `<!-- /wp:group -->` swallows the rest of the template into one block.
     A closer that names a different block than the opener it meets nests the
     tree wrong. Both render *something*, which is what makes them expensive:
     the page looks broken in a way that reads as a CSS bug.

  3. A COMMENT THAT ENDS EARLY. `--!>` closes an HTML comment in the HTML5
     parser exactly as `-->` does, so one of those inside a prose comment
     truncates it and dumps the rest of the comment onto the page as text. A
     bare `--` inside a comment body is a parse error in the spec but is NOT
     a terminator in any shipping parser; test_comment_double_hyphen_is_not_a
     _terminator below measures that claim in Chromium rather than repeating
     it, so the difference between the fatal case and the tolerated one is a
     measurement in this repo and not a belief.

It also holds the revision-2 and revision-3 typographic rules that are easy to
undo by accident: no interpuncts in rendered text, no tracked-out capitalised
eyebrow labels, and the data face reserved for figures rather than prose.

Run:  python3 tests/test_block_markup.py
Needs: nothing. Pure python. The optional Chromium probe is skipped when
       playwright or the bundled browser is absent.
"""

import html.parser
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHROME = os.path.expanduser(
    "~/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"
)

TEMPLATE_DIRS = (
    "wp/themes/maars/templates",
    "wp/themes/maars/parts",
)

# WordPress's own block grammar, transcribed from WP_Block_Parser::next_token()
# in wp-includes/class-wp-block-parser.php. Every piece of whitespace in it is
# load-bearing: `\s+` after the name and before the terminator are required,
# and the attribute object is matched with a negative lookahead for the
# terminator rather than by brace counting, which is why a `--` inside the JSON
# is harmless to WordPress and a `}` before `-->` is not.
BLOCK_DELIM = re.compile(
    r"<!--\s+(?P<closer>/)?wp:"
    r"(?P<namespace>[a-z][a-z0-9_-]*/)?(?P<name>[a-z][a-z0-9_-]*)"
    r"\s+(?P<attrs>\{(?:(?!\}\s+/?-->).)*?\}\s+)?"
    r"(?P<void>/)?-->",
    re.S,
)

# Anything that opens an HTML comment, so a delimiter that WordPress will not
# match can be told apart from prose.
ANY_COMMENT = re.compile(r"<!--(.*?)(-->|--!>)", re.S)

# A comment that *looks* like a block delimiter to a human.
LOOKS_LIKE_BLOCK = re.compile(r"<!--\s*/?\s*wp:", re.S)

# The HTML5 early terminator. This one really does end a comment.
EARLY_TERMINATOR = re.compile(r"--!>")

VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}

INTERPUNCT = "·"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def template_files():
    out = []
    for d in TEMPLATE_DIRS:
        full = os.path.join(ROOT, d)
        if not os.path.isdir(full):
            continue
        for fn in sorted(os.listdir(full)):
            if fn.endswith(".html"):
                out.append(os.path.join(d, fn))
    return out


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def line_of(text, index):
    return text.count("\n", 0, index) + 1


def strip_comments(text):
    """What the browser is left with once every comment is removed."""
    return ANY_COMMENT.sub("", text)


class TagBalance(html.parser.HTMLParser):
    """Stack check over the HTML that survives comment stripping."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_ELEMENTS:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in VOID_ELEMENTS:
            return
        if not self.stack:
            self.errors.append(
                f"line {self.getpos()[0]}: </{tag}> with nothing open"
            )
            return
        open_tag, open_line = self.stack.pop()
        if open_tag != tag:
            self.errors.append(
                f"line {self.getpos()[0]}: </{tag}> closes <{open_tag}> "
                f"opened on line {open_line}"
            )


# ---------------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------------

def check_delimiters_parse(rel, text):
    """Every comment that mentions wp: must match WordPress's grammar."""
    errors = []
    matched = {m.start() for m in BLOCK_DELIM.finditer(text)}
    for m in ANY_COMMENT.finditer(text):
        whole = text[m.start():m.end()]
        if not LOOKS_LIKE_BLOCK.match(whole):
            continue
        if m.start() in matched:
            continue
        errors.append(
            f"{rel}:{line_of(text, m.start())}: this reads as a block "
            f"delimiter but WordPress will not match it (it needs a space "
            f"after `wp:name` and a space before `-->`): "
            f"{whole[:88]!r}"
        )
    return errors


def check_attribute_json(rel, text):
    errors = []
    for m in BLOCK_DELIM.finditer(text):
        blob = m.group("attrs")
        if not blob:
            continue
        try:
            value = json.loads(blob.strip())
        except json.JSONDecodeError as exc:
            errors.append(
                f"{rel}:{line_of(text, m.start())}: attributes of "
                f"wp:{m.group('name')} are not valid JSON ({exc})"
            )
            continue
        if not isinstance(value, dict):
            errors.append(
                f"{rel}:{line_of(text, m.start())}: attributes of "
                f"wp:{m.group('name')} are not an object"
            )
    return errors


def check_balance_and_nesting(rel, text):
    """The stack check. A closer must meet the opener it belongs to."""
    errors = []
    stack = []
    for m in BLOCK_DELIM.finditer(text):
        name = (m.group("namespace") or "") + m.group("name")
        line = line_of(text, m.start())
        if m.group("void"):
            if m.group("closer"):
                errors.append(
                    f"{rel}:{line}: `<!-- /wp:{name} /-->` is both a closer "
                    f"and a void block"
                )
            continue
        if m.group("closer"):
            if not stack:
                errors.append(
                    f"{rel}:{line}: `/wp:{name}` closes a block that was "
                    f"never opened"
                )
                continue
            open_name, open_line = stack.pop()
            if open_name != name:
                errors.append(
                    f"{rel}:{line}: `/wp:{name}` meets `wp:{open_name}` "
                    f"opened on line {open_line}"
                )
        else:
            stack.append((name, line))
    for name, line in stack:
        errors.append(f"{rel}:{line}: `wp:{name}` is never closed")
    return errors


def check_comments_terminate(rel, text):
    """No comment may end early, and every comment must end."""
    errors = []
    for m in EARLY_TERMINATOR.finditer(text):
        errors.append(
            f"{rel}:{line_of(text, m.start())}: `--!>` ends an HTML comment "
            f"in the HTML5 parser; everything after it inside that comment "
            f"renders as text"
        )
    depth = 0
    idx = 0
    while True:
        start = text.find("<!--", idx)
        if start < 0:
            break
        end = ANY_COMMENT.match(text, start)
        if not end:
            errors.append(
                f"{rel}:{line_of(text, start)}: comment opened here is never "
                f"closed"
            )
            break
        idx = end.end()
        depth += 1
    return errors


def check_double_hyphen_in_delimiters(rel, text):
    """Report `--` inside a block delimiter. A warning, not an error, and the
    Chromium probe below is what decides which it is."""
    warnings = []
    for m in BLOCK_DELIM.finditer(text):
        body = text[m.start() + 4:m.end() - 3]
        if "--" in body:
            warnings.append(
                f"{rel}:{line_of(text, m.start())}: `--` inside the "
                f"wp:{m.group('name')} delimiter (a spec parse error; no "
                f"shipping parser treats it as a terminator)"
            )
    return warnings


def check_html_balance(rel, text):
    parser = TagBalance()
    parser.feed(strip_comments(text))
    errors = [f"{rel}:{e}" for e in parser.errors]
    for tag, line in parser.stack:
        errors.append(f"{rel}:{line}: <{tag}> is never closed")
    return errors


def rendered_text(text):
    """Roughly what a reader sees: comments gone, tags gone."""
    body = strip_comments(text)
    body = re.sub(r"<[^>]+>", " ", body)
    return body


def check_no_interpuncts(rel, text):
    errors = []
    body = rendered_text(text)
    if INTERPUNCT in body:
        where = body.index(INTERPUNCT)
        errors.append(
            f"{rel}: an interpunct is in rendered text: "
            f"{body[max(0, where - 40):where + 40].strip()!r}"
        )
    return errors


def check_no_eyebrows(rel, text):
    """Revision 2 deleted every tracked-out capitalised label. They come back
    as `textTransform: uppercase` plus a letterSpacing, so both are refused."""
    errors = []
    for m in re.finditer(r"uppercase", text, re.I):
        line = line_of(text, m.start())
        if "text-transform" in text[max(0, m.start() - 60):m.start()].lower():
            errors.append(
                f"{rel}:{line}: text-transform:uppercase — revision 2 deleted "
                f"every capitalised eyebrow label"
            )
    for m in re.finditer(r'letterSpacing"\s*:\s*"([^"]+)"', text):
        value = m.group(1).strip()
        if value in ("0", "0em", "0px", "normal"):
            continue
        if value.startswith("-"):
            continue
        try:
            number = float(re.sub(r"[a-z%]+$", "", value))
        except ValueError:
            continue
        if number > 0.03:
            errors.append(
                f"{rel}:{line_of(text, m.start())}: letter-spacing {value} is "
                f"tracking-out; the eyebrow rule forbids it"
            )
    return errors


def check_data_face_is_for_figures(rel, text):
    """Fira Code is for callsigns, frequencies, tones, offsets, counts and
    money. A sentence in it is the defect revision 2 fixed."""
    errors = []
    for m in re.finditer(
        r'class="[^"]*has-data-font-family[^"]*"[^>]*>(.*?)</', text, re.S
    ):
        inner = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if len(inner) > 24 or len(inner.split()) > 3:
            errors.append(
                f"{rel}:{line_of(text, m.start())}: the data face is on prose: "
                f"{inner[:60]!r}"
            )
    return errors


def check_header_shape(rel, text):
    """Revision 3's header: the masthead block, then seven navigation items,
    and no trace of the text wordmark it replaced."""
    errors = []
    if "wp:maars/masthead" not in text:
        errors.append(f"{rel}: the masthead block is missing")
    links = len(re.findall(r"<!--\s+wp:navigation-link\s", text))
    if links != 7:
        errors.append(f"{rel}: {links} navigation items, expected 7")
    for dead in ("maars-wordmark", "maars-wordmark__call", "maars-wordmark__where"):
        if dead in text:
            errors.append(
                f"{rel}: `{dead}` is the revision-2 text masthead and should "
                f"be gone"
            )
    return errors


def check_front_page_order(rel, text):
    """The order revision 2 settled on, asserted by class so a reshuffle has
    to be deliberate."""
    wanted = [
        "maars-lede",
        "maars-onair",
        "maars-hero",
        "maars-about",
        "maars-news",
        "maars-archive-teaser",
    ]
    errors = []
    seen = []
    for cls in wanted:
        idx = text.find(f'class="wp-block-group {cls}')
        if idx < 0:
            errors.append(f"{rel}: section .{cls} is missing")
        else:
            seen.append((idx, cls))
    order = [c for _, c in sorted(seen)]
    expected = [c for c in wanted if c in order]
    if order != expected:
        errors.append(
            f"{rel}: sections are in the order {order}, expected {expected}"
        )
    return errors


def check_footer_keeps_the_constitution(rel, text):
    errors = []
    if "official organ" not in text:
        errors.append(
            f"{rel}: the constitutional note is gone. Article III makes the "
            f"e-mail reflector the official organ and the footer has to say so"
        )
    if "This website is not the official organ" not in text:
        errors.append(f"{rel}: the footer no longer disclaims being the organ")
    return errors


# ---------------------------------------------------------------------------
# the Chromium probe: measure the `--` claim instead of repeating it
# ---------------------------------------------------------------------------

def probe_comment_terminators():
    """Return (ran, findings). Loads three comments in the real HTML parser and
    reports which of them swallow the markup that follows."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False, []
    if not os.path.exists(CHROME):
        return False, []

    page_html = (
        "<!doctype html><meta charset=utf-8><body>"
        '<div id="a"><!-- wp:x {"className":"t--type"} /-->AFTER_A</div>'
        '<div id="b"><!-- wp:x {"className":"t"} /-->AFTER_B</div>'
        '<div id="c"><!-- wp:x --!>AFTER_C</div>'
        "</body>"
    )
    out = os.path.join(HERE, "out")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "comment_terminator_probe.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page_html)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROME,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page()
        page.goto("file://" + path, wait_until="load")
        seen = page.evaluate(
            "() => ['a','b','c'].map(id => "
            "document.getElementById(id).textContent.trim())"
        )
        browser.close()
    return True, seen


# ---------------------------------------------------------------------------

def main():
    files = template_files()
    if not files:
        print("FAIL  no block templates found")
        return 1

    errors = []
    warnings = []
    blocks = 0

    for rel in files:
        text = read(rel)
        blocks += len(list(BLOCK_DELIM.finditer(text)))
        errors += check_comments_terminate(rel, text)
        errors += check_delimiters_parse(rel, text)
        errors += check_attribute_json(rel, text)
        errors += check_balance_and_nesting(rel, text)
        errors += check_html_balance(rel, text)
        errors += check_no_interpuncts(rel, text)
        errors += check_no_eyebrows(rel, text)
        errors += check_data_face_is_for_figures(rel, text)
        warnings += check_double_hyphen_in_delimiters(rel, text)
        if rel.endswith("parts/header.html"):
            errors += check_header_shape(rel, text)
        if rel.endswith("templates/front-page.html"):
            errors += check_front_page_order(rel, text)
        if rel.endswith("parts/footer.html"):
            errors += check_footer_keeps_the_constitution(rel, text)

    print("ks0man-site block-markup gate\n")
    print(f"  templates checked   : {len(files)}")
    print(f"  block delimiters    : {blocks}")
    print(f"  errors              : {len(errors)}")
    print(f"  warnings            : {len(warnings)}\n")

    for w in warnings:
        print(f"  WARN  {w}")
    if warnings:
        print()
    for e in errors:
        print(f"  FAIL  {e}")
    if errors:
        print()

    ran, seen = probe_comment_terminators()
    if ran:
        # Each probe is one <div> holding a comment and then the literal text
        # AFTER_x. What the div's textContent turns out to be is the whole
        # measurement: exactly "AFTER_x" means the comment ended where it was
        # meant to, anything longer means it ended EARLY and spilled its own
        # body onto the page, and "" means it never ended and swallowed the
        # markup after it.
        probes = [
            ("`--` inside a block delimiter", "AFTER_A"),
            ("a delimiter with no `--` in it", "AFTER_B"),
            ("`--!>` inside a comment", "AFTER_C"),
        ]
        print("  Chromium comment-terminator probe (measured, not assumed):")
        for (label, want), got in zip(probes, seen):
            if got == want:
                verdict = "ended where it should"
            elif got == "":
                verdict = "NEVER ENDED, swallowed the page"
            else:
                verdict = f"ENDED EARLY, spilled {got[:28]!r}"
            print(f"    {label:32} -> {verdict}")
        if seen[0] != "AFTER_A":
            errors.append(
                "a `--` inside a block delimiter truncates it in this "
                "browser; every BEM `--` in a className has to go"
            )
        if seen[2] != "AFTER_C":
            errors.append(
                "the `--!>` probe behaved unexpectedly; this gate's premise "
                "needs rechecking"
            )
        print("    so: `--!>` really does end a comment early and is refused")
        print("        above; a bare `--` does not and is only warned about.\n")
    else:
        print("  Chromium probe skipped (no playwright or no browser)\n")

    print(f"{'PASS' if not errors else 'FAIL'}  block markup")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
