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


def wp_names(row: dict) -> set[str]:
    """Every name an attachment answers to, as WordPress stores it AND as it was shipped.

    EVERY name carries its extension. The first version also offered the bare
    slug, "field-day-2016", and that is how Field_Day_2016.jpg came to be
    "already on the site": the PDF of the same name answered for it. Seven files
    were never uploaded that way -- three photographs, a PageMaker file, an
    InDesign file, and the Word and RTF copies of two sets of minutes, whose
    "other format" then pointed at the PDF itself.

    WordPress renames in three ways, and each has already cost a duplicate:
      - a large image becomes <name>-scaled.jpg; media_details.original_image
        keeps the uploaded name;
      - an unrecognised double extension gets an underscore: "letter.rtfd.zip"
        is stored as "letter.rtfd_.zip", slug "letter-rtfd_";
      - a slug already taken gets "-2". That one is not undone: stripping a
        trailing "-2" would turn newsletter-12-15.pdf into newsletter-12-15.
    """
    names: set[str] = set()
    url_name = os.path.basename(row.get("source_url", "") or "")
    original = (row.get("media_details") or {}).get("original_image") or ""
    for name in (url_name, original):
        if not name:
            continue
        healed = re.sub(r"_(?=\.[^.]+$)", "", name)             # x.rtfd_.zip -> x.rtfd.zip
        for form in (name, healed):
            stem, ext = os.path.splitext(form)
            names.add(form)
            names.add(form.lower())
            names.add(slug_of(stem) + ext.lower())                 # shipped-name form, WITH extension
    slug = (row.get("slug", "") or "").rstrip("_")
    if slug and url_name:
        names.add(slug + os.path.splitext(url_name)[1].lower())    # constitution-2.pdf
    names.discard("")
    return names


def shipped_key(file_name: str) -> str:
    """The form wp_names() offers for a shipped file name."""
    stem, ext = os.path.splitext(file_name)
    return slug_of(stem) + ext.lower()


class ListingFailed(RuntimeError):
    """A page of a listing came back as an error, not as data."""


def list_all(site: str, auth: str, path: str, pace: float = 1.2) -> list[dict]:
    """Every row of a paged REST listing, or an exception -- never a short list.

    The first version of every inventory loop here treated a non-list reply as
    the end of the data. A proxy's 502 on page 3 then truncated the inventory
    silently, and each tool acted on what it had not seen: records created
    again, files uploaded again as -1 copies, pages created as members-2.
    """
    out: list[dict] = []
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        rows = api(site, auth, "GET", f"{path}{sep}per_page=100&page={page}", pace=pace)
        if isinstance(rows, dict) and rows.get("__error") == 400 and page > 1:
            break                     # WordPress answers 400 past the last page
        if not isinstance(rows, list):
            raise ListingFailed(f"{path} page {page}: {str(rows)[:160]}")
        out.extend(rows)
        if len(rows) < 100:
            break
        page += 1
    return out


def site_media_maps(site: str, auth: str, pace: float = 1.2) -> tuple[dict, dict]:
    """(name -> URL, name -> full-size URL) for everything in the media library."""
    urls: dict[str, str] = {}
    full: dict[str, str] = {}
    for row in list_all(site, auth, "/media?_fields=id,slug,source_url,media_details", pace):
        url = row.get("source_url", "")
        if not url:
            continue
        original = (row.get("media_details") or {}).get("original_image")
        big = (url.rsplit("/", 1)[0] + "/" + original) if original else url
        for name in wp_names(row):
            urls.setdefault(name, url)
            full.setdefault(name, big)
    return urls, full


def site_publications(site: str, auth: str, pace: float = 1.2) -> dict[str, str]:
    """Source file name (lower case) -> the permalink of the record made from it."""
    out: dict[str, str] = {}
    for row in list_all(site, auth, "/maars_publication?status=publish&_fields=id,link,meta", pace):
        source = ((row.get("meta") or {}).get("_maars_source_file") or "")
        if source:
            out[os.path.basename(source).lower()] = row["link"]
    return out


TOKEN = re.compile(r"\{\{(media-full|media|pub):([^}]+)\}\}")


def resolve_tokens(html: str, urls: dict, full: dict, pubs: dict) -> tuple[str, list[str]]:
    """Swap {{media:}}, {{media-full:}} and {{pub:}} for URLs; report the rest."""
    missing: list[str] = []

    def swap(match):
        kind, name = match.group(1), match.group(2)
        if kind == "pub":
            url = pubs.get(name.lower())
            if not url:
                stem = os.path.splitext(name.lower())[0]
                for ext in (".pdf", ".html", ".htm", ".doc", ".docx"):
                    url = pubs.get(stem + ext)
                    if url:
                        break
        else:
            table = full if kind == "media-full" else urls
            url = table.get(name) or table.get(shipped_key(name))
        if not url:
            missing.append(match.group(0))
            return match.group(0)
        return url

    return TOKEN.sub(swap, html), missing


def api(site: str, auth: str, method: str, path: str, data=None, headers=None,
        pace: float = 1.2, tries: int = 4):
    url = site.rstrip("/") + "/wp-json/wp/v2" + path
    # A fixed timeout is a bet on the line speed. 180 seconds carries a PDF at
    # any speed, and loses a 58 MB video at 175 KB/s -- which then restarts
    # from byte 0, four times, and fails. Allow 20 KB/s for whatever is sent.
    timeout = max(180, int(len(data) / 20000)) if isinstance(data, (bytes, bytearray)) else 180
    for attempt in range(tries):
        req = urllib.request.Request(url, method=method)
        req.add_header("Authorization", "Basic " + auth)
        req.add_header("User-Agent", UA)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, data, timeout=timeout) as resp:
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
    for row in list_all(site, auth, "/media?_fields=id,slug,source_url,media_details", pace):
        names |= wp_names(row)
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
        if item["file"] in present or shipped_key(item["file"]) in present:
            continue
        if item.get("stored_as") and item["stored_as"] in present:
            # WordPress converted it on upload (an .ico arrives as a .jpg); the
            # converted copy is what the site has, and uploading again would
            # only make a second one.
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
            present.add(shipped_key(item["file"]))
            print(f"    {uploaded}/{len(todo)} {item['file']} ({len(blob) // 1024} KB)", flush=True)
        else:
            failed += 1
            print(f"    FAILED {item['file']}: {str(got)[:120]}")

    print(f"  uploaded {uploaded}, already present {len(manifest) - len(todo)}, "
          f"failed {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
