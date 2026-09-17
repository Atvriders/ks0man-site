#!/usr/bin/env python3
"""Upload the screened media set to a live WordPress over the REST API.

Idempotent, paced, and safe to run twice -- which took three duplicate uploads
of the same five photographs on the production site to get right.

WHY IDENTITY IS THE SLUG AND NOT THE FILE NAME
----------------------------------------------
WordPress renames what it stores. An image wider than the "big image" threshold
(2560px by default) is resized on upload and the ORIGINAL is kept aside, so the
attachment's source_url comes back as

    .../fd18-tower-scaled.jpg        uploaded as fd18-tower.jpg

Keying "is this already there?" on the source_url's file name therefore misses
every large photograph, and the uploader posts it again. WordPress does not
refuse the duplicate: it stores fd18-tower-1.jpg, then fd18-tower-2.jpg, and the
media library quietly grows a copy per run. Fifteen duplicate attachments on
ks0man.org before it was noticed.

Two other names survive the rename, and this checks all three, because no single
one of them is enough:

    slug                        "fd18-tower" -- derived from the uploaded name,
                                EXCEPT when a post already owns that slug, and
                                then the attachment gets "constitution-2"
    media_details.original_image
                                "fd18-tower.jpg" -- what a scaled image was
                                uploaded as, kept by WordPress beside the scaled
                                copy. Absent for PDFs, which are never scaled.
    source_url basename         "constitution.pdf" -- right for everything that
                                was not scaled, wrong for everything that was

An item counts as present if the manifest name matches ANY of the three. The
alternative, stripping "-scaled" and a trailing "-2" off the stored name, turns
newsletter-12-15.pdf into newsletter-12 and silently skips a real upload -- a
worse failure than the duplicate it is trying to avoid.

Usage:
    WP_USER=… WP_APP_PASSWORD='xxxx xxxx …' python3 tools/push_media.py --site https://ks0man.org
    …                                       python3 tools/push_media.py --site … --check

--check uploads nothing and prints what a run would do.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "media")
UA = "maars-push-media/1.0"


def slug_of(filename: str) -> str:
    """The slug WordPress will give an attachment uploaded under this name."""
    stem = os.path.splitext(os.path.basename(filename))[0].lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    return stem


def api(site: str, auth: str, method: str, path: str, data=None, headers=None,
        pace: float = 1.2, tries: int = 4):
    url = site.rstrip("/") + "/wp-json/wp/v2" + path
    for attempt in range(tries):
        req = urllib.request.Request(url, method=method)
        req.add_header("Authorization", "Basic " + auth)
        req.add_header("User-Agent", UA)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, data, timeout=180) as resp:
                body = resp.read().decode(errors="replace")
                time.sleep(pace)
                return json.loads(body) if body.strip().startswith(("{", "[")) else body
        except urllib.error.HTTPError as exc:
            text = exc.read().decode(errors="replace")[:200]
            # A host that throttles says so with 429/503, or with a JavaScript
            # challenge page. Both mean "slow down", not "this failed".
            if exc.code in (429, 503) or "reload" in text:
                wait = 25 * (attempt + 1)
                print(f"    throttled, waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            return {"__error": exc.code, "__body": text}
        except Exception as exc:  # noqa: BLE001
            wait = 12 * (attempt + 1)
            print(f"    {type(exc).__name__}, retry in {wait}s", flush=True)
            time.sleep(wait)
    return {"__error": "gave up"}


def existing_names(site: str, auth: str, pace: float) -> set[str]:
    """Every name by which something already on the site can be recognised."""
    names: set[str] = set()
    page = 1
    while True:
        rows = api(site, auth, "GET",
                   f"/media?per_page=100&page={page}"
                   "&_fields=id,slug,source_url,media_details",
                   pace=pace)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            names.add(row.get("slug", ""))
            names.add(os.path.basename(row.get("source_url", "")))
            original = (row.get("media_details") or {}).get("original_image")
            if original:
                names.add(original)
                names.add(slug_of(original))
        if len(rows) < 100:
            break
        page += 1
    names.discard("")
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", required=True)
    ap.add_argument("--check", action="store_true", help="report, upload nothing")
    ap.add_argument("--pace", type=float, default=1.2, help="seconds between requests")
    args = ap.parse_args()

    user = os.environ.get("WP_USER")
    password = os.environ.get("WP_APP_PASSWORD")
    if not user or not password:
        print("set WP_USER and WP_APP_PASSWORD (an application password)")
        return 2
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    manifest = json.load(open(os.path.join(MEDIA, "manifest.json")))
    present = existing_names(args.site, auth, args.pace)
    print(f"  manifest: {len(manifest)} items   names known to the site: {len(present)}")

    todo = []
    missing_locally = []
    for item in manifest:
        sub = "images" if item["kind"] == "image" else "documents"
        path = os.path.join(MEDIA, sub, item["file"])
        if not os.path.exists(path):
            missing_locally.append(item["file"])
            continue
        if item["file"] in present or slug_of(item["file"]) in present:
            continue
        todo.append((item, path))

    if missing_locally:
        print(f"  NOT ON DISK: {len(missing_locally)} manifest items — " +
              ", ".join(missing_locally[:5]))

    print(f"  to upload: {len(todo)}")
    if args.check:
        for item, _ in todo[:20]:
            print(f"    would upload {item['file']}")
        return 1 if (todo or missing_locally) else 0

    uploaded = failed = 0
    for item, path in todo:
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            blob = fh.read()
        got = api(args.site, auth, "POST", "/media", blob,
                  {"Content-Disposition": f'attachment; filename="{item["file"]}"',
                   "Content-Type": ctype},
                  pace=args.pace)
        if isinstance(got, dict) and got.get("id"):
            uploaded += 1
            present.add(item["file"])
            present.add(slug_of(item["file"]))
        else:
            failed += 1
            print(f"    FAILED {item['file']}: {str(got)[:120]}")

    print(f"  uploaded {uploaded}, already present {len(manifest) - len(todo)}, "
          f"failed {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
