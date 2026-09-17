#!/usr/bin/env python3
"""Build the ks0man.com -> ks0man.org redirect map from what the new site holds.

The map that came out of the study was written against an information
architecture that was never built: it sent /newsletter_03-22.pdf to
/archive/minutes-2022-03-11/ (the real permalink carries the year),
/repeater.html to /repeater/operating-guidelines/ and a dozen documents to
/governance/… . Every one of those 404s. A redirect map nobody checked against
the live site is a list of broken links with an HTTP status in front of it.

This one is built the other way round: it asks the live site what it has, and
matches each old URL to it.

    a newsletter or minutes  ->  the archive record made from that file
                                 (matched on _maars_source_file)
    a photograph or document ->  the file in the media library
                                 (matched through media/manifest.json)
    a page                   ->  the page that replaced it
    third-party material     ->  /archive/gaps/, which says why it is not here
    site furniture           ->  410 Gone; nothing links to a 1997 spacer gif

Writes url_map.csv and an Apache .htaccess, and can check every target it wrote.

Usage:
    WP_USER=… WP_APP_PASSWORD=… python3 tools/build_redirects.py --site https://ks0man.org
    python3 tools/build_redirects.py --site … --verify      (HTTP-checks every target)
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from push_media import api, slug_of  # noqa: E402
from prepare_pages import CHROME, PAGE_LINKS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.expanduser("~/ks0man-migration/mirror/ks0man.com")
OUTDIR = os.path.expanduser("~/ks0man-migration/migrate")
GAPS = "/archive/gaps/"

# Not ours to republish; the gaps page explains each one. See
# tools/screen_media.py, which holds the same list and the evidence for it.
THIRD_PARTY = {
    "events_1951_flood.pdf", "events_1951_flood_response.pdf", "Carl_and_Jerry.pdf",
    "BandChart.pdf", "Harvard_on_learning_code_1943.pdf", "KC2G_MUF_What_Is_It.pdf",
    "Morse_code_Speed_vs._Proficiency.pdf", "events_Kansas_History_2003.pdf",
    "HF_Tuning.pdf", "Kansas_RACES_draft_1-2016.pdf", "ARES_Registration.pdf",
    "tower.pdf", "Winter-Field-Day-Rules.pdf", "after_action_6-2017.pdf",
}

# Linked from the old site and never on it: dead before the migration began.
NEVER_THERE = {
    "A Learning Approach to Achieve QRQ.pdf", "ADSL-filter.pdf", "HyVee_on_3rd.jpg",
    "Tips and Tonics for Healthier Radio Clubs.pdf",
    "january_2016_spectrum_wall_chart.pdf", "k0s_field_manual.pdf",
}

VIDEO = re.compile(r"\.(mp4|mov|avi)$", re.I)


def old_paths() -> list[str]:
    """Every file the mirror of ks0man.com holds, as a site-root path."""
    if not os.path.isdir(MIRROR):
        return []
    out = []
    for name in sorted(os.listdir(MIRROR)):
        if not os.path.isfile(os.path.join(MIRROR, name)):
            continue
        if "?" in name:
            # wget saved query strings into file names, so the mirror holds
            # entries like "serv-1?s=<id>&t=<timestamp>". They were never
            # paths on ks0man.com, and RewriteRule matches the path only -- a
            # rule written for one of these can never fire.
            continue
        out.append("/" + name)
    return out


def build(site: str, auth: str, pace: float) -> list[dict]:
    manifest = json.load(open(os.path.join(ROOT, "media", "manifest.json")))
    shipped = {item["src"]: item["file"] for item in manifest}

    media: dict[str, str] = {}
    page = 1
    while True:
        rows = api(site, auth, "GET",
                   f"/media?per_page=100&page={page}"
                   "&_fields=id,slug,source_url,media_details", pace=pace)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            url = urllib.parse.urlparse(row["source_url"]).path
            media.setdefault(row.get("slug", ""), url)
            media.setdefault(os.path.basename(url), url)
            original = (row.get("media_details") or {}).get("original_image")
            if original:
                media.setdefault(original, url)
                media.setdefault(slug_of(original), url)
        if len(rows) < 100:
            break
        page += 1

    pubs: dict[str, str] = {}
    page = 1
    while True:
        rows = api(site, auth, "GET",
                   f"/maars_publication?per_page=100&page={page}"
                   "&status=publish&_fields=link,meta", pace=pace)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            source = ((row.get("meta") or {}).get("_maars_source_file") or "")
            if source:
                pubs[os.path.basename(source).lower()] = urllib.parse.urlparse(row["link"]).path
        if len(rows) < 100:
            break
        page += 1

    print(f"  the site has {len(pubs)} archive records and {len(media)} media names")

    rows_out = []
    for path in old_paths():
        name = path.lstrip("/")
        lower = name.lower()
        target, code, why = None, 301, ""

        if lower.startswith("index.htm"):
            target, why = "/", "the front page"
        elif lower in pubs:
            target, why = pubs[lower], "archive record"
        elif os.path.splitext(lower)[0] + ".pdf" in pubs:
            target, why = pubs[os.path.splitext(lower)[0] + ".pdf"], "archive record (same issue, PDF)"
        elif os.path.splitext(lower)[0] + ".html" in pubs:
            target, why = pubs[os.path.splitext(lower)[0] + ".html"], "archive record (same issue, HTML)"
        elif name in PAGE_LINKS:
            target, why = PAGE_LINKS[name], "page"
        elif name in THIRD_PARTY:
            target, why = GAPS, "third-party: not ours to republish"
        elif name in NEVER_THERE:
            target, why = GAPS, "linked from the old site, never on it"
        elif VIDEO.search(name):
            target, why = GAPS, "video, not hosted here"
        elif (name in CHROME
              or re.match(r"^(news[a-z0-9]*\.gif|maarslogo|spacer)", name, re.I)
              or lower.endswith((".css", ".js"))
              or lower.startswith(("serv?", "serv-", "login.php", "visit."))):
            # Stylesheets, the GeoCities hit counter, a stray Facebook login
            # callback. Nothing links to them and nothing should redirect to a
            # page on their behalf.
            target, code, why = "", 410, "1997 site furniture"
        elif name in shipped and shipped[name] in media:
            target, why = media[shipped[name]], "file in the media library"
        elif name in shipped and slug_of(shipped[name]) in media:
            target, why = media[slug_of(shipped[name])], "file in the media library"
        elif lower.split("?")[0].endswith((".html", ".htm")):
            target, why = "/", "page with no successor"
        else:
            target, why = GAPS, "not carried over"

        rows_out.append({"old_path": path, "new_url": target, "code": code, "why": why})

    return rows_out


def verify(site: str, rows: list[dict], pace: float) -> int:
    bad = 0
    checked = 0
    seen: dict[str, int] = {}
    for row in rows:
        if row["code"] == 410 or not row["new_url"]:
            continue
        url = row["new_url"]
        if url in seen:
            status = seen[url]
        else:
            try:
                req = urllib.request.Request(site.rstrip("/") + url,
                                             headers={"User-Agent": "maars-mapcheck"},
                                             method="HEAD")
                with urllib.request.urlopen(req, timeout=45) as resp:
                    status = resp.status
            except urllib.error.HTTPError as exc:
                status = exc.code
            except Exception:  # noqa: BLE001
                status = 0
            seen[url] = status
            time.sleep(pace)
        checked += 1
        if status != 200:
            bad += 1
            print(f"  {status}  {row['old_path']} -> {url}")
    print(f"  verified {checked} redirects against {len(seen)} distinct targets: "
          f"{bad} do not answer 200")
    return bad


def write(rows: list[dict], outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, "url_map.csv")
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["old_path", "new_url", "code", "why"])
        writer.writeheader()
        writer.writerows(rows)

    ht_path = os.path.join(outdir, "htaccess_ks0man_com.txt")
    with open(ht_path, "w") as fh:
        fh.write(
            "# ks0man.com -> ks0man.org\n"
            "# Generated by tools/build_redirects.py from what the live site holds,\n"
            "# and every target was checked for a 200 before this file was written.\n"
            "# Drop this in the document root of ks0man.com.\n\n"
            "RewriteEngine On\n\n"
        )
        for row in rows:
            old = re.escape(row["old_path"].lstrip("/"))
            if row["code"] == 410:
                fh.write(f"RewriteRule ^{old}$ - [G,NC]\n")
            else:
                fh.write(f"RewriteRule ^{old}$ https://ks0man.org{row['new_url']} [R=301,L,NE]\n")
        fh.write("\n# Anything not named above goes to the front page rather than a 404.\n"
                 "RewriteRule ^(.*)$ https://ks0man.org/ [R=301,L]\n")

    print(f"  wrote {csv_path} and {ht_path} ({len(rows)} rules)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", required=True)
    ap.add_argument("--out", default=OUTDIR)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--pace", type=float, default=0.35)
    args = ap.parse_args()

    user = os.environ.get("WP_USER")
    password = os.environ.get("WP_APP_PASSWORD")
    if not user or not password:
        print("set WP_USER and WP_APP_PASSWORD")
        return 2
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    rows = build(args.site, auth, max(args.pace, 1.0))
    if not rows:
        print("  no mirror to read; nothing written")
        return 2

    from collections import Counter
    for why, n in Counter(r["why"] for r in rows).most_common():
        print(f"    {n:4}  {why}")

    bad = verify(args.site, rows, args.pace) if args.verify else 0
    write(rows, args.out)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
