#!/usr/bin/env python3
"""Keep every web page ks0man.com served, as it served it, in one file.

From 1998 to 2015 the newsletter WAS a web page. Those 125 issues are archive
records whose text is the page, carried over -- but the page itself, the file a
reader of ks0man.com actually downloaded, was on the new site nowhere. The
webmaster's folder bundle (ks0man-com-web-pages-as-the-webmaster-kept-them.zip)
is not a substitute: the webmaster's copies are working copies, with classic-Mac
line endings, and some are other documents under the same name. The folder's
newsletter_07-09.html is a draft of the March 2010 issue; the page ks0man.com
served under that name is July 2009.

This builds ks0man-com-pages-as-served.zip from the wget mirror of
11 September 2026. wget ran without --convert-links, so the mirror files are
the bytes the server sent. Every .html, .htm and .css file goes in, except the
query-string copies wget saved beside a page (index.html?refid=9 is index.html
byte for byte). Each HTML-era record links this bundle and names its own page
inside it (wp/plugins/maars-core/inc/original.php).

Deterministic: entries are sorted and stamped with the mirror's own file
times, so a rebuild from the same mirror produces the same bytes.

    python3 tools/bundle_served_pages.py [--mirror ~/ks0man-migration/mirror/ks0man.com]
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "media", "manifest.json")
BUNDLE = "ks0man-com-pages-as-served.zip"
KEEP = (".html", ".htm", ".css")


def served_pages(mirror: str) -> list[str]:
    return sorted(
        name for name in os.listdir(mirror)
        if "?" not in name and name.lower().endswith(KEEP)
        and os.path.isfile(os.path.join(mirror, name))
    )


def build(mirror: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name in served_pages(mirror):
            path = os.path.join(mirror, name)
            stamp = time.localtime(os.path.getmtime(path))[:6]
            info = zipfile.ZipInfo(name, date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            with open(path, "rb") as fh:
                out.writestr(info, fh.read())
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mirror", default=os.path.expanduser("~/ks0man-migration/mirror/ks0man.com"))
    args = ap.parse_args()

    if not os.path.isdir(args.mirror):
        print(f"no mirror at {args.mirror}")
        return 2

    names = served_pages(args.mirror)
    data = build(args.mirror)
    with open(os.path.join(ROOT, "media", "documents", BUNDLE), "wb") as fh:
        fh.write(data)

    manifest = json.load(open(MANIFEST))
    manifest = [i for i in manifest if i["file"] != BUNDLE]
    manifest.append({
        "kind": "document",
        "src": "(every web page and stylesheet as ks0man.com served it)",
        "file": BUNDLE,
        "bytes": len(data),
        "category": "site",
        "contains": names,
        "origin": "mirror",
    })
    manifest.sort(key=lambda i: (i["kind"], i["file"]))
    with open(MANIFEST, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    print(f"{BUNDLE}: {len(names)} files, {len(data):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
