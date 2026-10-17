#!/usr/bin/env python3
"""Build the redirects for every old ks0man.com address, from what the new site holds.

The map that came out of the study was written against an information
architecture that was never built: it sent /newsletter_03-22.pdf to
/archive/minutes-2022-03-11/ (the real permalink carries the year),
/repeater.html to /repeater/operating-guidelines/ and a dozen documents to
/governance/… . Every one of those 404s. A redirect map nobody checked against
the live site is a list of broken links with an HTTP status in front of it.

This one decides from the repository what each old address IS, then asks the
live site where that thing lives:

    a newsletter or minutes  ->  the archive record made from that file
    a byte-for-byte copy     ->  the record of the document it copies (the old
                                 site's "Jan. 2017" was the February minutes)
    a photograph or document ->  the file in the media library, at the size
                                 ks0man.com served it: where the migration made
                                 a smaller copy, the original that shipped beside
                                 it, and never WordPress's -scaled derivative
    a page                   ->  the page that replaced it
    a file that never existed->  /archive/gaps/, which names it
    a stylesheet             ->  410 Gone

The old addresses are every file in the mirror, AND every file the old pages
link to that the mirror does not hold: newsletters.html linked "Apr. 2010" and
"Mar. 2021" to files ks0man.com answered with 404, and the webmaster's folder
has both.

Three outputs from one set of decisions:
    migrate/url_map.csv, and an Apache .htaccess for the old host, with the
        live site's URLs (written to --out, and copied into the repository);
    wp/plugins/maars-core/inc/legacy-map.php: the decisions themselves, which
        the plugin uses to answer an old address that reaches the NEW site.
        The webmaster's pages linked www.ks0man.org/<file>, and ks0man.org is
        this site now. The plugin resolves each decision against its own
        database, so the map holds no upload paths and works on any install.

Usage:
    python3 tools/build_redirects.py --plugin-only          (no site needed)
    WP_USER=… WP_APP_PASSWORD=… python3 tools/build_redirects.py --site https://ks0man.org [--verify]
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from push_media import shipped_key, site_media_maps, site_publications  # noqa: E402
from prepare_pages import LINK_ALIASES, PAGE_LINKS, intended_urls, is_chrome  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.expanduser("~/ks0man-migration/mirror/ks0man.com")
FOLDER = os.path.expanduser("~/ks0man-migration/webmaster-folder")
OUTDIR = os.path.expanduser("~/ks0man-migration/migrate")
PLUGIN_MAP = os.path.join(ROOT, "wp", "plugins", "maars-core", "inc", "legacy-map.php")
GAPS = "/archive/gaps/"

# Linked from the old site and never on it: dead before the migration began.
NEVER_THERE = {
    "Sale_Barn_Cafe.jpg", "FD97index.html",
    # the GeoCities home page's own pictures, which stayed on GeoCities
    "bkrnd.jpg", "devil.gif", "emailed.gif", "ghost.gif", "hrace.jpg", "smlogo.gif",
}

OWN_HOST = re.compile(r"^(https?:)?//(www\.)?ks0man\.(com|org)(/|$)", re.I)
REF = re.compile(r"""(?:href|src|background)\s*=\s*["']?([^"'\s>]+)""", re.I)


def mirror_names() -> list[str]:
    """Every file the mirror of ks0man.com holds. wget saved query strings into
    file names ("serv-1?s=<id>&t=<timestamp>"); those were never paths, and a
    RewriteRule matches the path only, so a rule for one could never fire."""
    if not os.path.isdir(MIRROR):
        return []
    return sorted(n for n in os.listdir(MIRROR)
                  if os.path.isfile(os.path.join(MIRROR, n)) and "?" not in n)


def linked_names(held: set[str]) -> list[str]:
    """Files the old pages link to, at the site root, that the mirror does not hold."""
    out: set[str] = set()
    for base in (MIRROR, FOLDER):
        if not os.path.isdir(base):
            continue
        for page in os.listdir(base):
            if not page.lower().endswith((".html", ".htm")):
                continue
            text = open(os.path.join(base, page), "rb").read().decode("latin-1")
            for ref in REF.findall(text):
                ref = ref.strip()
                if ref.lower().startswith(("mailto:", "javascript:", "#")):
                    continue
                if re.match(r"^[a-z]+:", ref, re.I) or ref.startswith("//"):
                    if not OWN_HOST.match(ref):
                        continue
                    ref = urllib.parse.urlparse(ref if ":" in ref else "http:" + ref).path
                path = urllib.parse.unquote(ref.split("#")[0].split("?")[0]).lstrip("./")
                if not path:
                    continue
                if "/" in path.strip("/"):
                    # The old site was flat, so a deeper path was a link that lost
                    # its site's name; it is an old address only if the webmaster's
                    # copy says where it was meant to go.
                    if path.strip("/") in intended_urls():
                        out.add(path.strip("/"))
                    continue
                name = path.strip("/")
                if (not name or name in held or "." not in name or "@" in name
                        or name.lower().startswith("www.") or is_chrome(name)):
                    continue              # an address, a host, or 1997 furniture: not a file
                out.add(name)
    return sorted(out)


def sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def decide_all() -> list[dict]:
    """What every old address is. No network: the repository decides."""
    manifest = json.load(open(os.path.join(ROOT, "media", "manifest.json")))
    issues = json.load(open(os.path.join(ROOT, "content", "html_archive.json")))
    shipped = {i["src"]: i["file"] for i in manifest}
    folded = {k.lower(): v for k, v in shipped.items()}
    dups = {i["src"]: i["duplicate_of"] for i in manifest if i.get("duplicate_of")}
    records = {i["src"].lower(): i["src"] for i in manifest if i.get("title") and i.get("date")}
    records.update({i["src"].lower(): i["src"] for i in issues})

    # The shipped file that IS the served file, byte for byte. For nine
    # photographs the migration shipped a 1600px copy under the plain name and
    # the bytes ks0man.com served beside it as "<name>-original.jpg"; an old
    # address goes to the bytes it used to return, whatever they shipped as.
    by_hash: dict[str, list[str]] = {}
    for item in manifest:
        sub = "images" if item["kind"] == "image" else "documents"
        path = os.path.join(ROOT, "media", sub, item["file"])
        if os.path.exists(path):
            by_hash.setdefault(sha(path), []).append(item["file"])

    def served_as(name: str) -> str | None:
        path = os.path.join(MIRROR, name)
        if not os.path.exists(path):
            return None
        same = by_hash.get(sha(path)) or []
        if shipped.get(name) in same:
            return shipped[name]
        return same[0] if same else None

    held = set(mirror_names())
    names = sorted(held | set(linked_names(held)), key=str.lower)

    def decide(name: str, hops: int = 0) -> tuple[str, str, str]:
        if "/" in name:
            return "away", intended_urls()[name], "another site's document; the link had lost the site's name"
        lower = name.lower()
        stem = os.path.splitext(lower)[0]
        if lower.startswith("index.htm"):
            return "page", "/", "the front page"
        if name in dups:
            return "record", dups[name], f"archive record ({name} is a copy of {dups[name]})"
        if lower in records:
            return "record", records[lower], "archive record"
        for ext in (".pdf", ".html"):
            if stem + ext in records:
                return "record", records[stem + ext], "archive record (same issue)"
        if name in PAGE_LINKS:
            return "page", PAGE_LINKS[name], "page"
        if name in LINK_ALIASES and hops == 0:
            kind, key, _ = decide(LINK_ALIASES[name], 1)
            return kind, key, f"{LINK_ALIASES[name]}, the same document under the name the folder kept"
        exact = served_as(name)
        if exact and exact != shipped.get(name):
            return "file", exact, "the file as ks0man.com served it"
        if exact:
            return "file", exact, "file in the media library"
        if name in shipped:
            return "file", shipped[name], "file in the media library"
        if lower in folded:
            return "file", folded[lower], "file in the media library (name in another case)"
        if name in NEVER_THERE:
            return "gaps", "", "linked from the old site, never on it"
        if lower.endswith((".css", ".js")):
            return "gone", "", "stylesheet"
        if lower.startswith("login.php"):
            return "gone", "", "a Facebook link that lost its site's name"
        if lower.startswith(("serv", "visit.")):
            return "gone", "", "hit counter"
        if lower.endswith((".html", ".htm")):
            return "page", "/history/", "page kept under History"
        return "gaps", "", "not carried over"

    out, seen = [], set()
    for name in names:
        if name.lower() in seen:
            continue                      # "Email.gif" and "email.gif": one address to a server that folds case
        seen.add(name.lower())
        kind, key, why = decide(name)
        out.append({"name": name, "kind": kind, "key": key, "why": why,
                    "linked_only": name not in held})
    return out


# Addresses the new site answers before the plugin can: the web server serves
# /favicon.ico itself (LiteSpeed answers 404 for it without ever starting
# WordPress), and WordPress core sends /login.php to its own login form. A row
# for either in the plugin's map could never fire; the old host's rules keep them.
ANSWERED_ELSEWHERE = {"favicon.ico", "login.php"}


def write_plugin_map(decisions: list[dict]) -> None:
    def php(s: str) -> str:
        return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"

    lines = [
        "<?php",
        "/**",
        " * Old ks0man.com addresses -> what they are now. GENERATED by",
        " * tools/build_redirects.py from the repository; do not edit by hand.",
        " *",
        " * Keyed by the old file name in lower case. Each value is a kind and a key:",
        " *   record  the archive record made from that source file",
        " *   file    the attachment shipped under that name (served at full size)",
        " *   page    a path on this site",
        " *   gaps    the page naming files the old site linked to and never held",
        " *   gone    a stylesheet or hit counter: 410",
        " *   away    another site's document, at the address the webmaster wrote",
        " * inc/legacy.php resolves record and file against this site's database,",
        " * so nothing here depends on where an install put its uploads.",
        " *",
        " * @package MAARS",
        " */",
        "",
        "defined( 'ABSPATH' ) || exit;",
        "",
        "return array(",
    ]
    for d in sorted(decisions, key=lambda d: d["name"].lower()):
        if d["name"].lower() in ANSWERED_ELSEWHERE:
            continue
        lines.append(f"\t{php(d['name'].lower())} => array( {php(d['kind'])}, {php(d['key'])} ),")
    lines += [");", ""]
    with open(PLUGIN_MAP, "w") as fh:
        fh.write("\n".join(lines))
    kept = sum(1 for d in decisions if d["name"].lower() not in ANSWERED_ELSEWHERE)
    print(f"  wrote {os.path.relpath(PLUGIN_MAP, ROOT)} ({kept} old addresses)")


def live_rows(decisions: list[dict], site: str, auth: str, pace: float) -> tuple[list[dict], int]:
    urls, full = site_media_maps(site, auth, pace)
    # The host converted favicon.ico to favicon.jpg on upload; the manifest says so.
    for item in json.load(open(os.path.join(ROOT, "media", "manifest.json"))):
        if item.get("stored_as") and item["stored_as"] in full:
            full.setdefault(item["file"], full[item["stored_as"]])
    pubs = site_publications(site, auth, pace)
    print(f"  the site has {len(pubs)} archive records and {len(full)} media names")

    rows, unresolved = [], 0
    for d in decisions:
        kind, key = d["kind"], d["key"]
        target, code = "", 301
        if kind == "page":
            target = key
        elif kind == "gaps":
            target = GAPS
        elif kind == "gone":
            code = 410
        elif kind == "away":
            target = key
        elif kind == "record":
            link = pubs.get(key.lower())
            target = urllib.parse.urlparse(link).path if link else ""
        elif kind == "file":
            link = full.get(key) or full.get(shipped_key(key))
            target = urllib.parse.urlparse(link).path if link else ""
        if code == 301 and not target:
            unresolved += 1
            print(f"  NOT ON THE SITE: /{d['name']} ({kind} {key})")
            continue
        rows.append({"old_path": "/" + d["name"], "new_url": target, "code": code, "why": d["why"]})
    return rows, unresolved


def verify(site: str, rows: list[dict], pace: float) -> int:
    bad = 0
    checked = 0
    seen: dict[str, int] = {}
    for row in rows:
        if row["code"] == 410 or not row["new_url"] or row["new_url"].startswith("http"):
            continue                      # another site's document is not this site's to check
        url = row["new_url"]
        if url in seen:
            status = seen[url]
        else:
            try:
                req = urllib.request.Request(site.rstrip("/") + urllib.parse.quote(url, safe="/%-._~"),
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
            elif row["new_url"].startswith("http"):
                fh.write(f"RewriteRule ^{old}$ {row['new_url']} [R=301,L,NE]\n")
            else:
                fh.write(f"RewriteRule ^{old}$ https://ks0man.org{row['new_url']} [R=301,L,NE]\n")
        fh.write("\n# Anything not named above goes to the front page rather than a 404.\n"
                 "RewriteRule ^(.*)$ https://ks0man.org/ [R=301,L]\n")

    for src, dest in ((csv_path, os.path.join(ROOT, "migrate", "url_map.csv")),
                      (ht_path, os.path.join(ROOT, "migrate", "ks0man_com.htaccess"))):
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copyfile(src, dest)
    print(f"  wrote {csv_path} and {ht_path} ({len(rows)} rules), and their copies in migrate/")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site")
    ap.add_argument("--out", default=OUTDIR)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--plugin-only", action="store_true", help="write only the plugin's map")
    ap.add_argument("--pace", type=float, default=1.2)
    args = ap.parse_args()

    decisions = decide_all()
    if not decisions:
        print("  no mirror to read; nothing written")
        return 2
    write_plugin_map(decisions)

    from collections import Counter
    for why, n in Counter(d["why"].split(" (")[0] for d in decisions).most_common():
        print(f"    {n:4}  {why}")
    print(f"    ({sum(d['linked_only'] for d in decisions)} of them linked from the old pages "
          "but not held by the mirror)")

    if args.plugin_only:
        return 0
    if not args.site:
        print("  --site is needed for the .htaccess and url_map.csv")
        return 2
    user, password = os.environ.get("WP_USER"), os.environ.get("WP_APP_PASSWORD")
    if not user or not password:
        print("set WP_USER and WP_APP_PASSWORD")
        return 2
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    rows, unresolved = live_rows(decisions, args.site, auth, max(args.pace, 1.0))
    bad = verify(args.site, rows, max(args.pace, 0.35)) if args.verify else 0
    write(rows, args.out)
    return 1 if (bad or unresolved) else 0


if __name__ == "__main__":
    sys.exit(main())
