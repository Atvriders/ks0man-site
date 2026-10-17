#!/usr/bin/env python3
"""Bring the webmaster's own working folder into the archive -- all of it.

On 16 October 2026 the Society's webmaster supplied "MAARS Page.zip": the folder
ks0man.com was built from, 561 files once the macOS metadata is stripped. The
mirror this migration started from was fetched over the wire and holds only what
the live site linked to; the folder holds everything the webmaster kept.

Compared, file by file, with what ks0man.org then held:

    271  identical to files already migrated
    151  same name, different bytes (148 are HTML drafts of pages)
    139  never seen before -- 74 MB

and, counting the mirror too, 186 files were not on the live site at all.

The Society's instruction was explicit: "anything we are missing needs to be
added. do not skip adding anything. everything needs to be there." So nothing in
this tool decides whether a file goes in. It decides only WHERE:

    a dated document            -> an archive record (title, date, kind, year)
    the same document, another  -> attached to the record the first one made
    format                         (_maars_alternates), never a second record
    a photograph, a flyer, a    -> the media library, listed by topic on
    spreadsheet, a video           /club-files/ so it can be found
    a page of the old site      -> converted to a page (tools/prepare_pages.py)
                                   AND kept, byte for byte, in a source bundle

Every addition is recorded in media/manifest.json with a `category`, so the
Club files page is generated from the manifest and a test can prove every file
is reachable from somewhere.

Run:  python3 tools/ingest_webmaster_files.py ~/Uploads/"MAARS Page.zip"
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "media")
MANIFEST = os.path.join(MEDIA, "manifest.json")
MIRROR = os.path.expanduser("~/ks0man-migration/mirror/ks0man.com")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico"}

# The archive records the folder (and the media library) can now make. Titles
# follow the convention every other record uses; the kind was read off each
# document's own first page, not guessed from its file name.
RECORDS = {
    # 21 issues that were uploaded on 17 September 2026 and never given a
    # record, so the archive list did not show them.
    "newsletter_11-09.pdf": ("newsletter", "Newsletter, November 2009"),
    "newsletter_02-10.pdf": ("newsletter", "Newsletter, February 2010"),
    "newsletter_05-10.pdf": ("newsletter", "Newsletter, May 2010"),
    "newsletter_07-10.pdf": ("newsletter", "Newsletter, July 2010"),
    "newsletter_08-10.pdf": ("newsletter", "Newsletter, August 2010"),
    "newsletter_10-10.pdf": ("newsletter", "Newsletter, October 2010"),
    "newsletter_12-10.pdf": ("newsletter", "Newsletter, December 2010"),
    "newsletter_09-13.pdf": ("minutes", "Meeting minutes, September 2013"),
    "newsletter_02-14.pdf": ("newsletter", "Newsletter, February 2014"),
    "newsletter_10-15.pdf": ("minutes", "Meeting minutes, October 2015"),
    "newsletter_11-15.pdf": ("minutes", "Meeting minutes, November 2015"),
    "newsletter_12-15.pdf": ("minutes", "Meeting minutes, December 2015"),
    "newsletter_01-16.pdf": ("minutes", "Meeting minutes, January 2016"),
    "newsletter_04-16.pdf": ("minutes", "Meeting minutes, April 2016"),
    "newsletter_07-17.pdf": ("minutes", "Meeting minutes, July 2017"),
    "newsletter_11-18.pdf": ("minutes", "Meeting minutes, November 2018"),
    "newsletter_07-19.pdf": ("minutes", "Meeting minutes, July 2019"),
    "newsletter_04-20.pdf": ("minutes", "Meeting minutes, April 2020 (chat transcript)"),
    "newsletter_09-22.pdf": ("minutes", "Meeting minutes, September 2022"),
    "newsletter_05-23.pdf": ("minutes", "Meeting minutes, May 2023"),
    "newsletter_11-23.pdf": ("minutes", "Meeting minutes, November 2023"),
    # From the webmaster's folder, never on the live site.
    "newsletter_04-10.pdf": ("newsletter", "Newsletter, April 2010"),
    # Headed "THE TREASURER'S REPORT March 1, 2012" and running to April 1: the
    # March report, presented at the April meeting -- hence the file name.
    "treasurer_4-12.pdf": ("treasurer-report", "Treasurer's report, March 2012"),
    "treasurer_03-21.pdf": ("treasurer-report", "Treasurer's report, March 2021"),
    "Dec 2018 Treasurer's Report.docx": ("treasurer-report", "Treasurer's report, December 2018"),
}

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], 1)}

# The same document in another format: joined to the record, not a new one.
ALTERNATES = {
    "newsletter_05-19.doc": "newsletter_05-19.pdf",
    "newsletter_04-20.rtf": "newsletter_04-20.pdf",
    "2018 Year End Report.docx": "Year-End-Report-2018.pdf",
}

# Pages of the old site and the webmaster's drafts of them. They are converted
# into pages where they carry content (see tools/prepare_pages.py), and every
# one of them is ALSO kept exactly as it was, in one bundle: raw HTML served
# out of the media library would run on this site's own origin, scripts and
# all, and a 1997 GeoCities page has scripts.
WEB_SOURCE = re.compile(r"\.(html?|css|webloc)$", re.I)
BUNDLE_NAME = "ks0man-com-web-pages-as-the-webmaster-kept-them.zip"

# Where each file belongs on /club-files/. Matched in order; first wins.
CATEGORY_RULES = [
    ("storm-spotting", r"^warn"),
    ("silent-keys", r"(thank-you-card|^silentkey_|^norm\.jpg)"),
    ("exams", r"(vec test session|exams)"),
    ("repeater", r"(download_repeaters|repeater\.webloc|^repeater_|^repeaterbanner)"),
    ("membership", r"(application|membership|^dues\.|members[ _]|members\.|email.*list|email current|shirts order|bumper sticker|ham_of_the_year)"),
    ("silent-keys", r"^(silentkey_|norm\.jpg)"),
    ("officers", r"^officer"),
    ("field-day", r"(^fd\d\d|field_day|field day|fdpulsar)"),
    ("winter-field-day", r"winter[-_ ]field[-_ ]day"),
    ("events", r"(fox-?hunt|fox_hunt|christmas|thomas\.jpg|picnic|casa|warrior|5k|hamfest|salina|santafe|party|pota|kids_day|public_service)"),
    ("breakfast", r"(breakfast|bluemont|chick-fil-a|donut_palace|four_points|hyvee)"),
    ("meetings", r"(meeting|groesbeck|library|events 2020|dave mills|fiedler|^program_)"),
    ("collections", r"^ddy_"),
    ("history", r"(1951_flood|kansas_history|constitution|^stats\.jpg)"),
    ("reading", r"(bandchart|hf_tuning|ionosphere|kc2g|morse|harvard|pathfinder|carl_and_jerry|parity|emergency_plan|ares_|races|after_action|tower\.pdf|echo link|nwsflyer|google\+|^set\.rtf|warrior)"),
    ("photographs", r"(^francis_|jason-johnson)"),
    ("reading", r"^after_action"),
    ("site", r"(photo_winter|logo|news[a-z0-9]*\.(gif|jpg)|newscollage|newsart|white-mist|arrlwww|links_arrl|ninja|ctswbb|wpa pass|css text|acrobat|blueline|email\.gif|e-mail|flashxp|goback|home\.gif|lefthand|mac-blk|maroon|rcbackbg|spacebar|top\.gif|favicon|corridors|\.psd$|\.bmp$|ks0man-com-web-pages)"),
]


def slug(name: str) -> str:
    stem, ext = os.path.splitext(name)
    stem = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return stem + ext.lower()


def category_of(name: str) -> str:
    low = name.lower()
    for key, pattern in CATEGORY_RULES:
        if re.search(pattern, low):
            return key
    return "other"


def record_fields(src: str) -> dict:
    kind, title = RECORDS[src]
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{4})", title)
    year, month = int(m.group(2)), MONTHS[m.group(1)]
    return {"doc_type": kind, "year": year, "date": f"{year}-{month:02d}-01", "title": title}


def special_name(src: str) -> str:
    """Files with no usable extension get the one their contents prove."""
    if src == "MAARS application":
        return "maars-application.indd"     # Adobe InDesign document header
    if src == "corridors":
        return "corridors.ttf"               # TrueType font: 0x00010000 sfnt
    return slug(src)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    zpath = os.path.expanduser(sys.argv[1])
    zf = zipfile.ZipFile(zpath)

    # Every real file in the folder, by its name inside "MAARS Page/".
    folder = {}
    for info in zf.infolist():
        if info.filename.startswith("__MACOSX/") or info.is_dir():
            continue
        if os.path.basename(info.filename) == ".DS_Store":
            continue
        rel = info.filename.split("/", 1)[1]
        folder[rel] = info

    manifest = json.load(open(MANIFEST))
    by_src = {item["src"]: item for item in manifest}
    shipped = {item["file"] for item in manifest}

    added, records_made, alternates = [], 0, 0

    # 1. The 21 issues already in the library get the fields that make records.
    for src in RECORDS:
        if src in by_src and "title" not in by_src[src]:
            by_src[src].update(record_fields(src))
            records_made += 1

    # 2. The two .rtfd bundles (a Mac mail message with its pictures) become one
    #    zip each, so the message and the pictures it shows stay together.
    bundles = {}
    for rel in list(folder):
        if ".rtfd/" in rel:
            bundles.setdefault(rel.split(".rtfd/")[0] + ".rtfd", []).append(rel)

    # 3. Everything else from the folder, and from the mirror, that is not shipped.
    candidates = []
    for rel, info in folder.items():
        if ".rtfd/" in rel:
            continue
        candidates.append((rel, lambda info=info: zf.read(info)))
    for name in sorted(os.listdir(MIRROR)):
        path = os.path.join(MIRROR, name)
        if os.path.isfile(path) and "?" not in name and name not in folder:
            candidates.append((name, lambda path=path: open(path, "rb").read()))

    web_pages = []
    for rel, read in sorted(candidates):
        if rel in by_src:
            # Already shipped under this name -- unless the folder holds a
            # DIFFERENT file by it. The award photograph is 242 KB in the mirror
            # and 515 KB in the folder: the webmaster's copy is the original the
            # web copy was shrunk from. Both are kept.
            have = by_src[rel]
            sub = "images" if have["kind"] == "image" else "documents"
            path = os.path.join(MEDIA, sub, have["file"])
            if WEB_SOURCE.search(rel) or not os.path.exists(path):
                continue
            data = read()
            if data == open(path, "rb").read():
                continue
            stem, ext = os.path.splitext(have["file"])
            name = f"{stem}-original{ext}"
            if name in shipped:
                continue
            with open(os.path.join(MEDIA, sub, name), "wb") as fh:
                fh.write(data)
            item = {"kind": have["kind"], "src": rel + " (the webmaster's copy)", "file": name,
                    "bytes": len(data), "category": category_of(rel),
                    "note": f"larger original of {have['file']}"}
            manifest.append(item)
            shipped.add(name)
            added.append(item)
            continue
        if WEB_SOURCE.search(rel):
            web_pages.append((rel, read))
            continue
        name = special_name(rel)
        if name in shipped:
            # Same shipped name, different source: keep both, never overwrite.
            stem, ext = os.path.splitext(name)
            name = f"{stem}-from-folder{ext}"
        if name in shipped:
            continue
        data = read()
        kind = "image" if os.path.splitext(name)[1] in IMAGE_EXT else "document"
        sub = "images" if kind == "image" else "documents"
        with open(os.path.join(MEDIA, sub, name), "wb") as fh:
            fh.write(data)
        item = {"kind": kind, "src": rel, "file": name, "bytes": len(data)}
        if rel in RECORDS:
            item.update(record_fields(rel))
            records_made += 1
        elif rel in ALTERNATES:
            item["alternate_of"] = ALTERNATES[rel]
            alternates += 1
        else:
            item["category"] = category_of(rel)
        manifest.append(item)
        shipped.add(name)
        added.append(item)

    for bundle, members in sorted(bundles.items()):
        name = slug(bundle.replace(".rtfd", "")) + ".rtfd.zip"
        if name in shipped:
            continue
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for rel in sorted(members):
                out.writestr(rel, zf.read(folder[rel]))
        data = buf.getvalue()
        with open(os.path.join(MEDIA, "documents", name), "wb") as fh:
            fh.write(data)
        item = {"kind": "document", "src": bundle, "file": name, "bytes": len(data),
                "category": category_of(bundle)}
        manifest.append(item)
        shipped.add(name)
        added.append(item)

    if web_pages and BUNDLE_NAME not in shipped:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for rel, read in web_pages:
                out.writestr(rel, read())
        data = buf.getvalue()
        with open(os.path.join(MEDIA, "documents", BUNDLE_NAME), "wb") as fh:
            fh.write(data)
        item = {"kind": "document", "src": "(the HTML, CSS and bookmark files of the folder)",
                "file": BUNDLE_NAME, "bytes": len(data), "category": "site",
                "contains": [rel for rel, _ in web_pages]}
        manifest.append(item)
        added.append(item)

    manifest.sort(key=lambda i: (i["kind"], i["file"]))
    with open(MANIFEST, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    from collections import Counter
    print(f"  files added to media/: {len(added)} "
          f"({sum(i['bytes'] for i in added) / 1048576:.1f} MB)")
    print(f"  archive records the manifest now makes: +{records_made}")
    print(f"  other formats joined to existing records: {alternates}")
    print(f"  web pages kept in the source bundle: {len(web_pages)}")
    print("  by category:", dict(Counter(i.get("category", "(record)") for i in added).most_common()))
    print(f"  manifest: {len(manifest)} items")
    unplaced = [i["src"] for i in added if i.get("category") == "other"]
    if unplaced:
        print("  NOT YET PLACED (category 'other'):", unplaced)
    return 0


if __name__ == "__main__":
    sys.exit(main())
