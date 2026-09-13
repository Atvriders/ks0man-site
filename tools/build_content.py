#!/usr/bin/env python3
"""Build the full MAARS content bundle from the Society's own site mirror.

RUN THIS LOCALLY. Never in CI, never inside the Docker image.

The public image ships ``content/seed.json`` — a small, hand-curated, public-safe
seed with no personal data in it at all. This script is the other half: the
Society points it at its own mirror of ks0man.com and gets back the whole
archive — every newsletter, every set of minutes, every treasurer's report and
year-end report, plus the standing pages — in exactly the shape ``tools/seed.php``
already knows how to load::

    python3 tools/build_content.py --mirror ./mirror/ks0man.com --out content/bundle.json
    wp eval-file tools/seed.php content/bundle.json

The archive contains members' e-mail addresses, telephone numbers, home and
observer-post addresses. Redaction is therefore ON by default and has to be
switched off deliberately, with two flags, by somebody who has read what they
say. Even redacted, the output of this script is *not* safe to publish
unreviewed and must never be committed to a public repository.

HTML conversion follows the approach proven in the migration study's
``extract/convert_probe.py``: walk the top-level tables of the 1997-era HTML,
take the largest cell of each as the section body, lift the first bold run out
as the heading, and emit Gutenberg block markup. Measured on all 125 HTML
newsletters that recovers 98.5% of the words.

Dependencies: the Python standard library plus BeautifulSoup (``bs4``).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html as _html
import json
import os
import re
import sys
from collections import Counter, OrderedDict

try:
    from bs4 import BeautifulSoup, Comment, NavigableString
except ImportError:  # pragma: no cover - dependency check
    sys.stderr.write(
        "build_content.py needs BeautifulSoup.\n"
        "  Debian/Ubuntu:  sudo apt install python3-bs4\n"
        "  pip:            python3 -m pip install --user beautifulsoup4\n"
    )
    raise SystemExit(2)


SCHEMA = "maars-content-bundle/1"

#: Layout furniture from the 1997 stylesheet — spacers, rules, mail icons.
CHROME_IMAGES = {
    "spacebar.gif", "blueline_6px.gif", "maroon_line.gif", "top.gif", "home.gif",
    "goback.gif", "acrobat.gif", "email.gif", "e-mail.png", "lefthand.gif",
    "mac-blk.gif", "FDpulsarani.gif", "favicon.ico",
}

#: Decorative masthead art, matched by name.
CHROME_PATTERN = re.compile(r"^news[a-z0-9]*\.gif$|^maarslogo|^newscollage", re.I)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif"}
BINARY_EXTENSIONS = {".zip", ".mp4", ".ico", ".css", ".docx", ".doc", ".rtf"}

#: Old standing pages, and what each becomes. ``restricted`` marks a page whose
#: subject matter is people: it is still converted, but flagged private so a
#: human decides before any of it goes near a public server.
#:
#: Slugs here must not collide with the curated pages in content/seed.json, or
#: loading this bundle would overwrite them. The two whose subject the curated
#: seed also covers are dated instead — they are preserved artefacts of the old
#: site rather than replacements for the new page.
STANDING_PAGES = OrderedDict([
    ("index.html", ("homepage-1997", "The old homepage, preserved", False)),
    ("repeater.html", ("repeater-guidelines", "Using the repeater", False)),
    ("warn.html", ("warn", "Weather Amateur Radio Network", False)),
    ("links-maars.html", ("links-1997", "The old links page, preserved", False)),
    ("downloads.html", ("downloads", "File downloads", False)),
    ("events.html", ("events-index", "Events", False)),
    ("members.html", ("members", "Members", True)),
    ("silentkey.html", ("silent-keys", "Silent Keys", True)),
])

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

DOC_TYPE_LABELS = {
    "newsletter": "Newsletter",
    "minutes": "Meeting Minutes",
    "treasurer-report": "Treasurer's Report",
    "year-end-report": "Year-End Report",
}


# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #

class Redactor:
    """Strip personal data out of converted text, and count what it stripped.

    The counters are the point. A migration that quietly removes things is as
    untrustworthy as one that quietly keeps them, so every substitution is
    counted, per category and per file, and reported at the end. The matched
    values themselves are never stored, printed or written to the report — only
    how many there were.
    """

    #: Order matters: mailto links are consumed before bare addresses, and
    #: post-office boxes before the general street pattern.
    RULES = (
        (
            "e-mail addresses",
            re.compile(
                r'<a\s+[^>]*href\s*=\s*"mailto:[^"]*"[^>]*>(?P<text>.*?)</a>',
                re.I | re.S,
            ),
            "[e-mail removed]",
        ),
        (
            "e-mail addresses",
            re.compile(r"mailto:[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.I),
            "[e-mail removed]",
        ),
        (
            "e-mail addresses",
            re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
            "[e-mail removed]",
        ),
        (
            "e-mail addresses",
            re.compile(
                r"\b[A-Za-z0-9._%+\-]+\s+at\s+[A-Za-z0-9.\-]+\s+dot\s+[A-Za-z]{2,}\b",
                re.I,
            ),
            "[e-mail removed]",
        ),
        (
            "telephone numbers",
            re.compile(
                r"(?<!\d)(?:\+?1[\s.\-])?(?:\(\d{3}\)\s*|\d{3}[\s.\-])\d{3}[\s.\-]\d{4}(?!\d)"
            ),
            "[phone removed]",
        ),
        (
            "post-office boxes",
            re.compile(r"P\.?\s*O\.?\s*Box\s*#?\s*\d+", re.I),
            "[post-office box removed]",
        ),
        (
            "street addresses",
            re.compile(
                r"\b\d{1,6}\s+(?:[NSEW]\.?\s+|North\s+|South\s+|East\s+|West\s+)?"
                r"[A-Z][\w'.\-]*(?:\s+[A-Z][\w'.\-]*){0,3}\s+"
                r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Circle|Cir|"
                r"Boulevard|Blvd|Way|Terrace|Ter|Place|Pl|Trail|Trl|Highway|Hwy|Parkway|Pkwy)"
                r"\b\.?"
            ),
            "[address removed]",
        ),
        (
            "postal codes",
            re.compile(r"\b(?:KS|Kansas|MO|NE|OK|CO)\.?,?\s+\d{5}(?:-\d{4})?\b"),
            "[postal code removed]",
        ),
    )

    def __init__(self, enabled=True):
        """Create a redactor.

        Args:
            enabled: When False the redactor is a no-op that still counts
                nothing. Reaching that state requires two command-line flags.
        """
        self.enabled = enabled
        self.totals = Counter()
        self.per_file = {}
        self.files_touched = 0

    def scrub(self, text, source):
        """Redact one string.

        Args:
            text: The text to clean.
            source: Filename the text came from, for the per-file report.

        Returns:
            The redacted text (or the original, when redaction is off).
        """
        if not self.enabled or not text:
            return text

        hits = Counter()

        for label, pattern, replacement in self.RULES:
            text, count = pattern.subn(replacement, text)
            if count:
                hits[label] += count

        if hits:
            self.totals.update(hits)
            bucket = self.per_file.setdefault(source, Counter())
            if not bucket:
                self.files_touched += 1
            bucket.update(hits)

        return text

    @property
    def total_replacements(self):
        """int: Every substitution made, across all categories."""
        return sum(self.totals.values())

    def report(self):
        """dict: A JSON-serialisable summary. Counts only — never values."""
        return {
            "enabled": self.enabled,
            "total_replacements": self.total_replacements,
            "by_category": dict(self.totals),
            "files_affected": len(self.per_file),
            "by_file": {name: dict(counts) for name, counts in sorted(self.per_file.items())},
        }


# --------------------------------------------------------------------------- #
# HTML -> Gutenberg blocks
# --------------------------------------------------------------------------- #

def read_text(path):
    """Read a file that may be UTF-8, cp1252 or Latin-1.

    Five pages in the mirror are cp1252, which is why this exists.

    Args:
        path: File to read.

    Returns:
        tuple[str, str]: Decoded text and the encoding that worked.
    """
    with open(path, "rb") as handle:
        raw = handle.read()

    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue

    return raw.decode("latin-1", "replace"), "latin-1"


def _escape(text):
    """Escape text for HTML output, leaving quotes alone."""
    return _html.escape(text, quote=False)


def _inline(node):
    """Render inline content, keeping strong/em/a and dropping <font>."""
    out = []

    for child in node.children:
        if isinstance(child, Comment):
            continue

        if isinstance(child, NavigableString):
            out.append(_escape(str(child)))
            continue

        name = child.name.lower()

        if name in ("b", "strong"):
            out.append("<strong>" + _inline(child) + "</strong>")
        elif name in ("i", "em"):
            out.append("<em>" + _inline(child) + "</em>")
        elif name == "a" and child.get("href"):
            href = _html.escape(child["href"], quote=True)
            out.append('<a href="%s">%s</a>' % (href, _inline(child)))
        elif name == "br":
            out.append("<br>")
        elif name == "img":
            continue
        else:
            out.append(_inline(child))

    return re.sub(r"[ \t]+", " ", "".join(out))


def _table_block(table):
    """Render a genuine data table as a core/table block."""
    rows = []

    for row in table.find_all("tr"):
        cells = [_inline(cell) for cell in row.find_all(["td", "th"])]
        if any(re.sub(r"<[^>]+>", "", cell).strip() for cell in cells):
            rows.append(cells)

    if not rows:
        return None

    body = "".join(
        "<tr>" + "".join("<td>%s</td>" % cell for cell in row) + "</tr>" for row in rows
    )

    return (
        "<!-- wp:table --><figure class=\"wp-block-table\"><table><tbody>"
        + body
        + "</tbody></table></figure><!-- /wp:table -->"
    )


def _paragraphs(cell):
    """Split a table cell into paragraphs on <p> and doubled <br>."""
    text = _inline(cell)
    text = re.sub(r"(<br>\s*){2,}", "\n\n", text)
    chunks = [chunk.strip() for chunk in re.split(r"\n\n+", text) if chunk.strip()]
    return [chunk for chunk in chunks if re.sub(r"<[^>]+>", "", chunk).strip()]


def html_to_blocks(path):
    """Convert one 1997-era HTML page to Gutenberg block markup.

    Adapted from the migration study's ``extract/convert_probe.py``, which
    measured 98.5% mean word retention across all 125 HTML newsletters.

    Args:
        path: HTML file to convert.

    Returns:
        dict with ``blocks``, ``title``, ``headings``, ``images``, ``encoding``,
        ``words_in``, ``words_out``, ``retention`` and ``problems``.
    """
    text, encoding = read_text(path)
    soup = BeautifulSoup(text, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""
    blocks = []
    headings = []
    images = []
    problems = []

    for table in soup.find_all("table"):
        if table.find_parent("table"):
            continue

        cells = [cell for cell in table.find_all("td") if cell.find_parent("table") is table]

        if not cells:
            continue

        substantive = [cell for cell in cells if len(cell.get_text(strip=True)) >= 25]

        if len(substantive) >= 3 and len(table.find_all("tr")) >= 2:
            rendered = _table_block(table)
            if rendered:
                blocks.append(rendered)
                headings.append("(data table)")
                continue

        content = max(cells, key=lambda cell: len(cell.get_text(strip=True)))

        if len(content.get_text(strip=True)) < 40:
            images.extend(_collect_images(table))
            continue

        heading = None
        byline = None

        font = content.find("font")
        bold = (font.find("b") if font else None) or content.find("b")

        if bold:
            lines = [line.strip() for line in bold.get_text("\n", strip=True).split("\n") if line.strip()]
            if lines:
                heading = lines[0]
                if len(lines) > 1:
                    byline = " ".join(lines[1:])
                bold.decompose()
                if font and not font.get_text(strip=True):
                    font.decompose()

        images.extend(_collect_images(content))

        nested_blocks = []
        for nested in content.find_all("table"):
            rendered = _table_block(nested)
            if rendered:
                nested_blocks.append(rendered)
            nested.decompose()

        body = _paragraphs(content)

        if heading:
            headings.append(heading)
            blocks.append(
                '<!-- wp:heading {"level":2} --><h2 class="wp-block-heading">%s</h2>'
                "<!-- /wp:heading -->" % _escape(heading)
            )
            if byline:
                blocks.append(
                    '<!-- wp:paragraph {"className":"byline"} --><p class="byline"><em>%s</em></p>'
                    "<!-- /wp:paragraph -->" % _escape(byline)
                )
        else:
            problems.append("section with body text but no heading")

        for paragraph in body:
            blocks.append("<!-- wp:paragraph --><p>%s</p><!-- /wp:paragraph -->" % paragraph)

        blocks.extend(nested_blocks)

    markup = "\n\n".join(blocks)
    plain = re.sub(r"<[^>]+>", "", markup)
    original = soup.get_text(" ", strip=True)
    retention = len(plain.split()) / max(1, len(original.split()))

    return {
        "blocks": markup,
        "title": title,
        "headings": headings,
        "images": sorted(set(images)),
        "encoding": encoding,
        "words_in": len(original.split()),
        "words_out": len(plain.split()),
        "retention": round(retention, 3),
        "problems": problems,
    }


def _collect_images(node):
    """Return the non-chrome image filenames referenced under a node."""
    found = []

    for image in node.find_all("img"):
        src = (image.get("src") or "").strip()
        if not src or src in CHROME_IMAGES or CHROME_PATTERN.match(src):
            continue
        found.append(src)

    return found


def text_to_blocks(text):
    """Turn extracted PDF text into paragraph blocks.

    Args:
        text: Plain text, as produced by pdftotext or by OCR.

    Returns:
        str: Gutenberg block markup.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)

    blocks = []

    for chunk in text.split("\n\n"):
        chunk = " ".join(line.strip() for line in chunk.split("\n") if line.strip())
        if not chunk:
            continue
        blocks.append("<!-- wp:paragraph --><p>%s</p><!-- /wp:paragraph -->" % _escape(chunk))

    return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #

NEWSLETTER_RE = re.compile(r"^newsletter_(\d{2})-(\d{2})\.(html|pdf|docx?|txt)$", re.I)
TREASURER_RE = re.compile(r"^treasurer_(\d{2})-(\d{2})\.(pdf|html)$", re.I)
YEAR_END_RE = re.compile(r"^Year-End-Report-(\d{4})\.pdf$", re.I)


def four_digit_year(two_digit):
    """Expand a two-digit year the way the mirror's filenames mean it.

    Args:
        two_digit: The ``YY`` from a ``MM-YY`` filename.

    Returns:
        int: 1990-1999 for 90-99, otherwise 2000-2089.
    """
    value = int(two_digit)
    return 1900 + value if value >= 90 else 2000 + value


def parse_doc_date(title, year, month):
    """Find the document's own date, falling back to its filename.

    Args:
        title: Document title or first line.
        year: Year from the filename.
        month: Month from the filename, or None.

    Returns:
        str: ``YYYY-MM-DD``.
    """
    if title:
        month_names = r"(?P<mon>[A-Za-z]{3,9})"
        patterns = (
            re.compile(month_names + r"\.?\s+(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<year>\d{4})"),
            re.compile(r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+" + month_names + r"\.?,?\s+(?P<year>\d{4})"),
        )

        for pattern in patterns:
            match = pattern.search(title)
            if not match:
                continue

            name = match.group("mon").lower().rstrip(".")
            index = next((i for i, full in enumerate(MONTHS) if full.startswith(name[:3])), None)

            if index is None:
                continue

            day = int(match.group("day"))
            found = int(match.group("year"))

            if 1 <= day <= 31 and 1900 <= found <= 2100:
                return "%04d-%02d-%02d" % (found, index + 1, day)

    return "%04d-%02d-01" % (year, month or 1)


def classify_document(filename, title, year):
    """Decide a document's archive type.

    The document says what it is; the filename does not. From 2015 the monthly
    document is usually the meeting minutes but keeps the ``newsletter_`` name,
    and filing by filename is exactly the mistake the unified archive exists to
    avoid.

    Args:
        filename: Basename in the mirror.
        title: Document title or first line of text.
        year: Four-digit year.

    Returns:
        str: One of the ``maars_doc_type`` slugs.
    """
    if TREASURER_RE.match(filename):
        return "treasurer-report"

    if YEAR_END_RE.match(filename):
        return "year-end-report"

    haystack = (title or "").lower()

    if "minute" in haystack:
        return "minutes"

    if "newsletter" in haystack or "smoke signal" in haystack:
        return "newsletter"

    return "minutes" if year >= 2015 else "newsletter"


def find_pdf_text(pdftext_dir, stem):
    """Locate the text extracted from a PDF.

    Fourteen of the scanned PDFs had no text layer and were OCR'd into a
    ``.ocr.txt`` sibling. OCR output is good but not perfect, so anything that
    comes back from one is graded ``unverified``.

    Args:
        pdftext_dir: Directory holding the extracts.
        stem: Filename without its extension.

    Returns:
        tuple[str, str]: Text and its provenance (``"pdftext"``, ``"ocr"`` or
        ``"missing"``).
    """
    if not pdftext_dir:
        return "", "missing"

    plain = os.path.join(pdftext_dir, stem + ".txt")
    ocr = os.path.join(pdftext_dir, stem + ".ocr.txt")

    if os.path.isfile(plain):
        text, _ = read_text(plain)
        if text.strip():
            return text, "pdftext"

    if os.path.isfile(ocr):
        text, _ = read_text(ocr)
        if text.strip():
            return text, "ocr"

    return "", "missing"


def normalise_title(text):
    """Collapse the whitespace a PDF extractor leaves behind.

    pdftotext returns headings padded with tabs and runs of spaces, which makes
    two copies of the same title look different in a list.
    """
    text = (text or "").replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t-\u2013\u2014:")[:160]


def ensure_dated_title(title, doc_date):
    """Put the document's date in its title when the document did not.

    Sixty files called "The Treasurer's Report" are useless in an archive
    listing. Sixty files called "The Treasurer's Report - November 2023" are an
    archive.
    """
    if not title:
        return title

    if re.search(r"\b(?:19|20)\d{2}\b", title):
        return title

    year, month, _day = doc_date.split("-")

    return "%s \u2014 %s %s" % (title, MONTHS[int(month) - 1].title(), year)


def slugify(value):
    """Make a lowercase, hyphenated, ASCII slug.

    The slashed zero renders in titles and never in a slug: KSØMAN becomes
    ``ks0man``.
    """
    value = value.replace("Ø", "0").replace("ø", "0")
    value = _html.unescape(value)
    value = re.sub(r"[^A-Za-z0-9]+", "-", value.lower()).strip("-")
    return value[:180] or "untitled"


# --------------------------------------------------------------------------- #
# Bundle assembly
# --------------------------------------------------------------------------- #

def build(args):
    """Walk the mirror and assemble the bundle.

    Args:
        args: Parsed command-line arguments.

    Returns:
        tuple[dict, dict]: The bundle and a statistics dictionary.
    """
    redactor = Redactor(enabled=args.redact)

    publications = []
    pages = []
    posts = []
    media = []
    restricted = []
    problems = []

    doc_types = Counter()
    years = set()
    scanned = 0
    skipped = []
    images_without_alt = 0

    entries = sorted(os.listdir(args.mirror))

    for name in entries:
        path = os.path.join(args.mirror, name)

        if not os.path.isfile(path):
            continue

        scanned += 1
        stem, extension = os.path.splitext(name)
        extension = extension.lower()

        if extension in IMAGE_EXTENSIONS:
            if name in CHROME_IMAGES or CHROME_PATTERN.match(name):
                continue
            media.append({
                "file": name,
                "alt": "",
                "needs_alt": True,
                "_maars_source_file": posixish(args.mirror_label, name),
            })
            images_without_alt += 1
            continue

        if extension in BINARY_EXTENSIONS and extension not in (".docx", ".doc"):
            skipped.append(name)
            continue

        record = None

        if extension in (".html", ".htm"):
            record = build_html_record(args, name, path, redactor, problems)
        elif extension == ".pdf":
            record = build_pdf_record(args, name, path, redactor, problems)
        elif extension in (".docx", ".doc"):
            record = build_stub_record(args, name, problems)
        else:
            skipped.append(name)
            continue

        if record is None:
            skipped.append(name)
            continue

        kind = record.pop("_kind")

        if kind == "publication":
            publications.append(record)
            doc_type = record["terms"]["maars_doc_type"][0]
            doc_types[doc_type] += 1
            years.update(record["terms"].get("maars_year", []))
        elif kind == "page":
            pages.append(record)
            if record.get("restricted"):
                restricted.append(record["slug"])
        else:
            posts.append(record)

        if args.limit and (len(publications) + len(pages) + len(posts)) >= args.limit:
            break

    for group in (pages, posts, publications):
        deduplicate_slugs(group, problems)

    terms = build_terms(doc_types, years)
    site = load_site_block(args)

    bundle = OrderedDict()
    bundle["schema"] = SCHEMA
    bundle["kind"] = "local-full"
    bundle["generated"] = _dt.date.today().isoformat()
    bundle["generator"] = "tools/build_content.py"
    bundle["redacted"] = bool(args.redact)
    bundle["personal_data"] = "redacted" if args.redact else "PRESENT — DO NOT PUBLISH"
    bundle["notes"] = [
        "Generated locally from the Society's own mirror. This file is NOT the "
        "public seed and must never be committed to a public repository or baked "
        "into the image.",
        "Facility records (the repeater and the nets) are deliberately not "
        "generated. Every technical field on them has to be confirmed by a "
        "licensed member before it can carry a grade, so they stay hand-curated "
        "in content/seed.json.",
        "Person records are deliberately not generated. maars_person is a "
        "non-public post type and the roster and memorials need a human decision "
        "before any of them are loaded.",
    ]
    bundle["site"] = site
    bundle["terms"] = terms
    bundle["pages"] = pages
    bundle["facilities"] = []
    bundle["publications"] = publications
    bundle["posts"] = posts
    bundle["people"] = []
    bundle["media"] = media
    bundle["redaction"] = redactor.report()
    bundle["problems"] = problems

    stats = {
        "scanned": scanned,
        "publications": len(publications),
        "pages": len(pages),
        "posts": len(posts),
        "media": len(media),
        "needs_alt": images_without_alt,
        "skipped": skipped,
        "doc_types": doc_types,
        "restricted": restricted,
        "years": sorted(years),
        "problems": len(problems),
    }

    return bundle, stats, redactor


def deduplicate_slugs(records, problems):
    """Make every slug in a group unique, and say so when one had to change.

    Two documents can legitimately carry the same type and date — a treasurer's
    report filed twice in one month, say. Silently overwriting one with the
    other is how an archive loses a document, so the collision is renamed and
    recorded.

    Args:
        records: Bundle records, modified in place.
        problems: Problem list, appended to.
    """
    seen = {}

    for record in records:
        slug = record.get("slug", "")

        if slug not in seen:
            seen[slug] = 1
            continue

        seen[slug] += 1
        record["slug"] = "%s-%d" % (slug, seen[slug])

        problems.append({
            "file": record.get("meta", {}).get("_maars_source_file", slug),
            "problem": 'slug "%s" was already taken; filed as "%s"' % (slug, record["slug"]),
        })


def posixish(label, name):
    """Join a display label and a filename with a forward slash."""
    label = (label or "").rstrip("/")
    return "%s/%s" % (label, name) if label else name


def build_html_record(args, name, path, redactor, problems):
    """Convert one HTML file into a bundle record."""
    converted = html_to_blocks(path)
    source = posixish(args.mirror_label, name)

    for problem in converted["problems"]:
        problems.append({"file": name, "problem": problem})

    if converted["retention"] < 0.90:
        problems.append({
            "file": name,
            "problem": "low text retention (%.0f%%) — check this one by hand"
                       % (converted["retention"] * 100),
        })

    blocks = redactor.scrub(converted["blocks"], name)
    title = redactor.scrub(converted["title"], name).strip()

    match = NEWSLETTER_RE.match(name) or TREASURER_RE.match(name)

    if match:
        month = int(match.group(1))
        year = four_digit_year(match.group(2))
        heading = converted["headings"][0] if converted["headings"] else ""

        if is_generic_title(title):
            title = redactor.scrub(heading, name).strip() or default_title(name, year, month)

        doc_type = classify_document(name, title + " " + heading, year)
        doc_date = parse_doc_date(title + " " + heading, year, month)

        return publication_record(
            title=title,
            doc_type=doc_type,
            doc_date=doc_date,
            year=year,
            blocks=blocks,
            source=source,
            grade="sourced",
        )

    if name in STANDING_PAGES:
        slug, label, is_restricted = STANDING_PAGES[name]
        record = {
            "_kind": "page",
            "slug": slug,
            "title": title if title and not is_generic_title(title) else label,
            "blocks": blocks,
            "menu_order": 50,
            "meta": {
                "_maars_grade": "sourced",
                "_maars_verified_on": "",
                "_maars_source_file": source,
            },
        }

        if is_restricted:
            record["restricted"] = True
            record["_maars_visibility"] = "private"
            record["meta"]["_maars_grade"] = "unverified"

        return record

    return {
        "_kind": "post",
        "slug": slugify(stem_of(name)),
        "title": title if title and not is_generic_title(title) else prettify(stem_of(name)),
        "blocks": blocks,
        "meta": {
            "_maars_grade": "sourced",
            "_maars_verified_on": "",
            "_maars_source_file": source,
        },
        "terms": {},
    }


def build_pdf_record(args, name, path, redactor, problems):
    """Convert one PDF into a bundle record, using its text extract."""
    stem = stem_of(name)
    source = posixish(args.mirror_label, name)
    text, provenance = find_pdf_text(args.pdftext, stem)

    if provenance == "missing":
        problems.append({
            "file": name,
            "problem": "no text extract found — run pdftotext (and OCR if the "
                       "PDF is a scan) into the --pdftext directory",
        })

    header = [line.strip() for line in text.split("\n") if line.strip()][:3]
    first_line = header[0] if header else ""

    # The date is usually on the second or third line of the header block, not
    # in the title. Looking further than that starts picking up dates out of the
    # body — "BALANCE AS OF January 1" is not the date of the report.
    date_hint = " ".join(header)

    title = redactor.scrub(first_line, name).strip()
    blocks = redactor.scrub(text_to_blocks(text), name) if text else ""

    grade = "unverified" if provenance in ("ocr", "missing") else "sourced"

    if provenance == "ocr":
        problems.append({
            "file": name,
            "problem": "text came from OCR — verify callsigns, dollar figures and "
                       "proper names against the paper before publishing",
        })

    match = NEWSLETTER_RE.match(name) or TREASURER_RE.match(name)

    if match:
        month = int(match.group(1))
        year = four_digit_year(match.group(2))

        if is_generic_title(title) or not title:
            title = default_title(name, year, month)

        return publication_record(
            title=title,
            doc_type=classify_document(name, date_hint or title, year),
            doc_date=parse_doc_date(date_hint or title, year, month),
            year=year,
            blocks=blocks,
            source=source,
            grade=grade,
        )

    year_end = YEAR_END_RE.match(name)

    if year_end:
        year = int(year_end.group(1))

        if not title or "report" not in title.lower():
            title = "MAARS Year-End Report %d" % year

        return publication_record(
            title=title,
            doc_type="year-end-report",
            doc_date="%04d-12-31" % year,
            year=year,
            blocks=blocks,
            source=source,
            grade=grade,
        )

    return {
        "_kind": "post",
        "slug": slugify(stem),
        "title": title or prettify(stem),
        "blocks": blocks,
        "meta": {
            "_maars_grade": grade,
            "_maars_verified_on": "",
            "_maars_source_file": source,
        },
        "terms": {},
    }


def build_stub_record(args, name, problems):
    """Record a file this tool cannot read, rather than dropping it silently."""
    stem = stem_of(name)

    problems.append({
        "file": name,
        "problem": "no text extractor for this format — convert it to PDF or "
                   "paste the text in by hand; the record is a title-only stub",
    })

    match = NEWSLETTER_RE.match(name)

    if match:
        month = int(match.group(1))
        year = four_digit_year(match.group(2))

        return publication_record(
            title=default_title(name, year, month),
            doc_type=classify_document(name, "", year),
            doc_date="%04d-%02d-01" % (year, month),
            year=year,
            blocks="",
            source=posixish(args.mirror_label, name),
            grade="unverified",
        )

    return {
        "_kind": "post",
        "slug": slugify(stem),
        "title": prettify(stem),
        "blocks": "",
        "meta": {
            "_maars_grade": "unverified",
            "_maars_verified_on": "",
            "_maars_source_file": posixish(args.mirror_label, name),
        },
        "terms": {},
    }


def publication_record(title, doc_type, doc_date, year, blocks, source, grade):
    """Assemble one maars_publication record."""
    title = ensure_dated_title(normalise_title(title), doc_date)

    return {
        "_kind": "publication",
        "slug": "%s-%s" % (doc_type.replace("-report", ""), doc_date),
        "title": title,
        "date": doc_date,
        "blocks": blocks,
        "terms": {
            "maars_doc_type": [doc_type],
            "maars_year": [str(year)],
        },
        "meta": {
            "_maars_doc_date": doc_date,
            "_maars_grade": grade,
            "_maars_verified_on": "",
            "_maars_source_file": source,
        },
    }


def build_terms(doc_types, years):
    """Build the taxonomy term list the bundle needs."""
    terms = []

    for slug in ("newsletter", "minutes", "treasurer-report", "year-end-report"):
        if doc_types.get(slug):
            terms.append({
                "taxonomy": "maars_doc_type",
                "slug": slug,
                "name": DOC_TYPE_LABELS[slug],
            })

    for year in sorted(years):
        terms.append({"taxonomy": "maars_year", "slug": str(year), "name": str(year)})

    return terms


def load_site_block(args):
    """Reuse the site configuration from the public seed, if it is available.

    Site title, front page, permalinks and the primary menu belong to the
    curated seed. Copying the block through means one bundle can be loaded on
    its own without losing the navigation.
    """
    if not args.site_from:
        return {}

    try:
        with open(args.site_from, "r", encoding="utf-8") as handle:
            seed = json.load(handle)
    except (OSError, ValueError):
        return {}

    return seed.get("site", {})


def is_generic_title(title):
    """True for the boilerplate <title> shared by most of the old pages."""
    if not title:
        return True

    normalised = re.sub(r"[^a-z ]", "", title.lower()).strip()

    return normalised in (
        "manhattan area amateur radio society",
        "maars",
        "untitled document",
        "untitled normalpage",
        "new page",
    )


def stem_of(name):
    """Filename without its extension."""
    return os.path.splitext(name)[0]


def prettify(stem):
    """Turn a filename stem into a readable title."""
    return re.sub(r"[_\-]+", " ", stem).strip().title()


def default_title(name, year, month):
    """A title for a document that did not supply one."""
    kind = "Treasurer's Report" if TREASURER_RE.match(name) else "MAARS Newsletter"
    return "%s — %s %d" % (kind, MONTHS[(month - 1) % 12].title(), year)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_args(argv=None):
    """Define and parse the command line."""
    parser = argparse.ArgumentParser(
        prog="build_content.py",
        description=(
            "Build the full MAARS content bundle from the Society's own mirror of "
            "ks0man.com. Run this locally, never in CI and never in the image."
        ),
        epilog=(
            "The output is not the public seed. content/seed.json is hand-curated "
            "and contains no personal data; this bundle contains whatever survived "
            "redaction and must be reviewed before it goes anywhere public."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--mirror",
        default=os.path.join("mirror", "ks0man.com"),
        help="directory holding the site mirror (default: %(default)s)",
    )
    parser.add_argument(
        "--pdftext",
        default=os.path.join("extract", "pdftext"),
        help="directory of PDF text extracts, <stem>.txt and <stem>.ocr.txt "
             "(default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        default=os.path.join("content", "bundle.json"),
        help="where to write the bundle (default: %(default)s)",
    )
    parser.add_argument(
        "--site-from",
        default=os.path.join("content", "seed.json"),
        help="copy the site/menu configuration out of this bundle "
             "(default: %(default)s; pass an empty string to omit it)",
    )
    parser.add_argument(
        "--mirror-label",
        default="mirror/ks0man.com",
        help="prefix recorded in _maars_source_file, so provenance does not leak "
             "a local filesystem path (default: %(default)s)",
    )
    parser.add_argument(
        "--redaction-report",
        default="",
        help="also write the per-file redaction counts to this JSON file "
             "(counts only — never the matched values)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="stop after N records; useful for a quick look at the output shape",
    )
    parser.add_argument("--dry-run", action="store_true", help="convert but write nothing")
    parser.add_argument("--quiet", action="store_true", help="only print the summary")

    redaction = parser.add_argument_group("redaction")
    redaction.add_argument(
        "--redact",
        dest="redact",
        action="store_true",
        default=True,
        help="strip e-mail addresses, telephone numbers and street addresses (the default)",
    )
    redaction.add_argument(
        "--no-redact",
        dest="redact",
        action="store_false",
        help="keep personal data in the output; requires "
             "--i-understand-this-contains-personal-data",
    )
    redaction.add_argument(
        "--i-understand-this-contains-personal-data",
        dest="acknowledged",
        action="store_true",
        help="acknowledge that the unredacted bundle holds members' e-mail "
             "addresses, telephone numbers and home addresses, and must never be "
             "committed, uploaded or built into an image",
    )

    args = parser.parse_args(argv)

    if not args.redact and not args.acknowledged:
        parser.error(
            "--no-redact produces a file containing members' e-mail addresses, "
            "telephone numbers and home addresses. If you genuinely need it, pass "
            "--i-understand-this-contains-personal-data as well, and do not commit "
            "the result."
        )

    if args.acknowledged and args.redact:
        parser.error(
            "--i-understand-this-contains-personal-data only means something "
            "together with --no-redact. Drop it, or add --no-redact."
        )

    if os.path.basename(args.out) == "seed.json":
        parser.error(
            "refusing to write to seed.json. content/seed.json is the public-safe "
            "seed baked into the image and is maintained by hand. Write to "
            "content/bundle.json instead."
        )

    if not os.path.isdir(args.mirror):
        parser.error("--mirror %s is not a directory" % args.mirror)

    if args.pdftext and not os.path.isdir(args.pdftext):
        sys.stderr.write(
            "warning: --pdftext %s is not a directory; PDFs will become "
            "title-only stubs\n" % args.pdftext
        )
        args.pdftext = ""

    return args


def print_summary(args, stats, redactor, size):
    """Print what was built and what was removed."""
    out = sys.stdout.write

    out("\n")
    out("MAARS content bundle\n")
    out("--------------------\n")
    out("mirror        %s\n" % args.mirror)
    out("files scanned %d\n" % stats["scanned"])
    out("publications  %d\n" % stats["publications"])

    for doc_type, count in sorted(stats["doc_types"].items()):
        out("                %-18s %4d\n" % (DOC_TYPE_LABELS.get(doc_type, doc_type), count))

    if stats["years"]:
        span = "%s-%s" % (stats["years"][0], stats["years"][-1])
        missing = [
            str(year)
            for year in range(int(stats["years"][0]), int(stats["years"][-1]) + 1)
            if str(year) not in stats["years"]
        ]
        out("                years %s\n" % span)
        if missing:
            out("                years with nothing at all: %s\n" % ", ".join(missing))

    out("pages         %d\n" % stats["pages"])
    out("posts         %d\n" % stats["posts"])
    out("images        %d  (%d still need alt text)\n" % (stats["media"], stats["needs_alt"]))
    out("problems      %d  (listed in the bundle under \"problems\")\n" % stats["problems"])

    if stats["skipped"]:
        out("skipped       %d  (%s%s)\n" % (
            len(stats["skipped"]),
            ", ".join(stats["skipped"][:4]),
            ", ..." if len(stats["skipped"]) > 4 else "",
        ))

    if stats["restricted"]:
        out("restricted    %s  (flagged private: these pages are about people)\n"
            % ", ".join(stats["restricted"]))

    out("\n")

    if redactor.enabled:
        out("Redaction: ON\n")

        if redactor.total_replacements:
            for label, count in sorted(redactor.totals.items()):
                out("  %-22s %4d\n" % (label, count))
            out("  %-22s %4s\n" % ("", "----"))
            out("  %-22s %4d replacement(s) across %d file(s)\n" % (
                "total", redactor.total_replacements, len(redactor.per_file)))
        else:
            out("  nothing matched — check that --mirror points at the real mirror\n")
    else:
        out("!! Redaction: OFF\n")
        out("!! This bundle contains members' e-mail addresses, telephone numbers\n")
        out("!! and home addresses. Do not commit it. Do not upload it. Do not\n")
        out("!! build it into an image.\n")

    out("\n")

    if args.dry_run:
        out("Dry run — nothing written.\n")
    else:
        out("Wrote %s (%.1f KB)\n" % (args.out, size / 1024.0))
        out("Load it with:  wp eval-file tools/seed.php %s\n" % args.out)

    out("\n")


def main(argv=None):
    """Entry point.

    Returns:
        int: Process exit status.
    """
    args = parse_args(argv)

    if not args.quiet:
        sys.stdout.write("Reading %s ...\n" % args.mirror)

    bundle, stats, redactor = build(args)

    payload = json.dumps(bundle, indent=1, ensure_ascii=False) + "\n"
    size = len(payload.encode("utf-8"))

    if not args.dry_run:
        directory = os.path.dirname(os.path.abspath(args.out))

        if directory and not os.path.isdir(directory):
            os.makedirs(directory)

        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(payload)

        if args.redaction_report:
            with open(args.redaction_report, "w", encoding="utf-8") as handle:
                json.dump(redactor.report(), handle, indent=1)
                handle.write("\n")

    print_summary(args, stats, redactor, size)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
