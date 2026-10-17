"""Turn the 125 converted HTML newsletters into importable archive records.

POLICY, SET BY THE SOCIETY ON 17 SEPTEMBER 2026: publish the record in full.
This is the club's own account of itself, and every line of it was already
public on ks0man.com for twenty-seven years -- the migration is not new
exposure, it is continuity. Redaction is therefore OFF by default.

Third-party material is a different question and stays excluded: a 1951 QST
article, an ARRL band chart and a 1943 Harvard paper are not the Society's to
republish, which is the same principle stated the other way round.

Pass --redact to produce the stripped version instead; the unredacted text is
always recoverable from the mirror either way.

WHY THIS EXISTS
The Society published continuously from April 1998, but the first fifteen years
exist only as hand-written HTML. The media pipeline ships FILES; an HTML
newsletter is not a file to upload, it is a document to convert. So the whole
1998-2015 era was absent from the site while the PDF era imported fine, and the
archive began in 2013.

WHY REDACT RATHER THAN EXCLUDE
67% of these issues (84 of 125) carry an e-mail address, a telephone number or a
street address. Excluding them would drop two thirds of the club's own record to
protect a handful of lines. Names and callsigns stay: a callsign is public FCC
data and the minutes are the Society's own account of itself. Contact details go.

Run:  python3 tools/prepare_html_archive.py            # writes content/html_archive.json
      python3 tools/prepare_html_archive.py --check    # verify the output carries no PII
"""

import argparse
import html as _html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BLOCKS = os.path.expanduser("~/ks0man-migration/extract/blocks")
TEXT = os.path.expanduser("~/ks0man-migration/extract/pdftext")
OUT = os.path.join(ROOT, "content", "html_archive.json")

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")
PHONE = re.compile(r"\(?\b\d{3}\)?[ .\-]\d{3}[ .\-]\d{4}\b")
ADDR = re.compile(
    r"\b\d{2,5}\s+[NSEW]?\.?\s?[A-Z][A-Za-z]+\s+"
    r"(?:St|Ave|Rd|Hwy|Street|Avenue|Road|Lane|Ln|Dr|Drive|Ct|Blvd)\b"
)
MAILTO = re.compile(r'<a[^>]+href="mailto:[^"]*"[^>]*>(.*?)</a>', re.I | re.S)

MONTH = {1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
         7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"}


# Footer navigation the old site repeated on every page. It is not content, and
# it also contains the word "Newsletters", which defeated the kind classifier
# below: every 2015 issue is headed "MAARS Meeting Minutes" and was still filed
# as a newsletter because this boilerplate sat a few characters further down.
NAV_BOILERPLATE = [
    # Whole paragraph blocks whose only content is the old footer navigation,
    # in any of the shapes 27 years of hand-editing produced: bare text, wrapped
    # in <strong>, and as links back to newsletters.html / index.html.
    re.compile(r"<!-- wp:paragraph[^>]*-->\s*<p[^>]*>(?:(?!</p>).)*?"
               r"Back to (?:Newsletters?|Main Page)"
               r"(?:(?!</p>).)*?</p>\s*<!-- /wp:paragraph -->", re.I | re.S),
    # and any leftover anchor pointing at the old site's own pages
    re.compile(r'<a href="(?:newsletters|index)\.html"[^>]*>.*?</a>', re.I | re.S),
    re.compile(r"Back to Newsletters?\s*/?\s*Minutes", re.I),
    re.compile(r"Back to Main Page", re.I),
]


def strip_boilerplate(blocks: str) -> str:
    for pat in NAV_BOILERPLATE:
        blocks = pat.sub("", blocks)
    # tidy any paragraph left empty by the removal
    blocks = re.sub(r"<!-- wp:paragraph[^>]*-->\s*<p[^>]*>\s*</p>\s*<!-- /wp:paragraph -->", "", blocks)
    return re.sub(r"\n{3,}", "\n\n", blocks).strip()


def redact(blocks: str):
    """Remove contact details, keep the words around them."""
    counts = {"email": 0, "phone": 0, "address": 0, "mailto": 0}

    def _mailto(m):
        counts["mailto"] += 1
        inner = m.group(1)
        # keep whatever the link said, unless the link text was itself the address
        return "[e-mail removed]" if EMAIL.search(inner) else inner

    blocks = MAILTO.sub(_mailto, blocks)

    def _sub(pat, token, key):
        nonlocal blocks
        found = pat.findall(blocks)
        counts[key] += len(found)
        blocks = pat.sub(token, blocks)

    _sub(EMAIL, "[e-mail removed]", "email")
    _sub(PHONE, "[telephone removed]", "phone")
    _sub(ADDR, "[address removed]", "address")
    return blocks, counts


def classify(name: str):
    """Date and kind from the filename, with the kind confirmed from the text."""
    m = re.match(r"newsletter_(\d\d)-(\d\d)\.blocks\.html$", name)
    if not m:
        return None
    mm, yy = int(m.group(1)), int(m.group(2))
    year = 1900 + yy if yy >= 90 else 2000 + yy

    src = os.path.join(BLOCKS, name)
    try:
        raw = strip_boilerplate(open(src, errors="ignore").read())
    except OSError:
        raw = ""
    head = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw[:600])).strip().lower()
    # The filename says "newsletter" for every issue, including the years the
    # Society published only minutes. The opening line of the document decides.
    kind = "minutes" if re.search(r"^\W*maars meeting minutes|^\W*meeting minutes|^\W*minutes[,:]", head) else "newsletter"
    label = "Meeting minutes" if kind == "minutes" else "Newsletter"
    return dict(
        doc_type=kind,
        year=year,
        date=f"{year}-{mm:02d}-01",
        title=f"{label}, {MONTH[mm]} {year}",
        src=name.replace(".blocks.html", ".html"),
    )


MIRROR = os.path.expanduser("~/ks0man-migration/mirror/ks0man.com")


def build(do_redact=False):
    """Convert every HTML-era issue AS KS0MAN.COM SERVED IT.

    The first version took its text from ~/ks0man-migration/extract/blocks,
    the output of an early feasibility probe that read only table cells, skipped
    any table whose longest cell was under forty characters, never read text
    outside a table and dropped every picture. The audit of 17 October 2026
    found what that cost: the 1998 hamfest calendars, the January 1999
    time-zone quiz table its own puzzle asks readers to fill in, a webmaster's
    note, two illustrations, and 107 relative links that 404 on the new site --
    "Print a PDF file copy of the above form" on 101 issues among them.

    The issues now go through tools/prepare_pages.py's converter, which walks
    the whole page, keeps tables, pictures and jump targets, and rewrites every
    link to where the thing now lives. Titles, dates and kinds are unchanged:
    they are taken from the previous build, so a record's identity does not
    move under it.
    """
    sys.path.insert(0, HERE)
    import prepare_pages as pp

    previous = {}
    if os.path.exists(OUT):
        for item in json.load(open(OUT)):
            previous[item["src"]] = item
    media = pp.media_map()

    items = []
    totals = {"email": 0, "phone": 0, "address": 0, "mailto": 0}
    for name in sorted(os.listdir(MIRROR)):
        if not re.match(r"newsletter_\d\d-\d\d\.html$", name):
            continue
        meta = dict(previous.get(name) or classify(name.replace(".html", ".blocks.html")) or {})
        if not meta:
            continue
        blocks, unresolved, stats = pp.convert_page([os.path.join(MIRROR, name)], media, "issue")
        blocks = pp.drop_navigation(blocks)
        raw = strip_boilerplate("\n\n".join(blocks))
        ids = set(re.findall(r'id="([^"]+)"', raw))
        raw = re.sub(r'href="#([^"]+)"',
                     lambda m: m.group(0) if m.group(1) in ids else 'href="#"', raw)
        if do_redact:
            raw, c = redact(raw)
            for k in totals:
                totals[k] += c[k]
        meta.update({k: v for k, v in (classify(name.replace(".html", ".blocks.html")) or {}).items()
                     if k not in meta})
        meta["src"] = name
        meta["blocks"] = raw
        meta["words"] = len(re.sub(r"<[^>]+>", " ", raw).split())
        meta["retention"] = round(stats["words_out"] / max(1, stats["words_in"]), 3)
        if unresolved:
            meta["unresolved"] = sorted(set(unresolved))
        items.append(meta)

    items.sort(key=lambda i: (i["date"], i["src"]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(items, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(f"  {len(items)} issues prepared -> {os.path.relpath(OUT, ROOT)}")
    if do_redact:
        print(f"  redacted: {totals['email']} e-mail, {totals['phone']} telephone, "
              f"{totals['address']} address, {totals['mailto']} mailto link(s)")
    else:
        print("  published in full, as the Society published it (no redaction)")
    rets = sorted(i["retention"] for i in items)
    print(f"  retention against the served page: min {rets[0]:.0%}, median {rets[len(rets)//2]:.0%}")
    low = [(i["src"], i["retention"]) for i in items if i["retention"] < 0.85]
    if low:
        print("  below 85%:", low[:10])
    yrs = sorted({i["year"] for i in items})
    print(f"  span: {min(yrs)}-{max(yrs)}")
    from collections import Counter
    print("  kinds:", dict(Counter(i["doc_type"] for i in items)))
    gone = sorted({u for i in items for u in i.get("unresolved", [])})
    if gone:
        print("  references to nothing (dropped):", gone[:12])
    return 0


def check():
    if not os.path.exists(OUT):
        print("  no prepared file; run without --check first")
        return 1
    items = json.load(open(OUT))
    bad = []
    for i in items:
        b = i["blocks"]
        hits = {"email": EMAIL.findall(b), "phone": PHONE.findall(b), "address": ADDR.findall(b)}
        if any(hits.values()):
            bad.append((i["src"], {k: v[:2] for k, v in hits.items() if v}))
    print(f"  re-screened {len(items)} prepared issues")
    if bad:
        print(f"  FAIL: {len(bad)} still carry contact details")
        for s, h in bad[:8]:
            print("   ", s, h)
        return 1
    print("  0 carry an e-mail address, telephone number or street address")

    # the screener has to be able to fail, or it proves nothing
    planted = " ".join(["a.person@" + "example.org", "(" + "785" + ") " + "555" + "-" + "0142",
                        "123" + " N. Elm " + "Street"])
    if not (EMAIL.search(planted) and PHONE.search(planted) and ADDR.search(planted)):
        print("  FAIL: the screener does not detect planted contact details")
        return 1
    print("  meta-check: the screener does detect planted contact details")
    empty = [i["src"] for i in items if i["words"] < 40]
    if empty:
        print(f"  note: {len(empty)} issue(s) under 40 words: {empty[:5]}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--redact", action="store_true",
                    help="strip contact details (not the Society's chosen policy)")
    a = ap.parse_args()
    sys.exit(check() if a.check else build(a.redact))
