#!/usr/bin/env python3
"""Publish content/mirror_pages.json to a live WordPress, resolving its tokens.

The converted pages carry references as tokens rather than URLs, because the
converter cannot know either:

    {{media:silentkey-nadine-stueve.jpg}}  ->  https://…/uploads/2026/09/silentkey-nadine-stueve.jpg
    {{pub:newsletter_01-24.pdf}}           ->  https://…/archive/2024/meeting-minutes-january-2024/

This resolves them against the site being published to, and REFUSES to publish a
page with a token it could not resolve -- a page that goes out with
"{{media:...}}" in it is worse than one that is late.

Idempotent: a page that is already there is updated in place, by slug, so the
permalink and any links to it survive a second run.

Usage:
    WP_USER=… WP_APP_PASSWORD='xxxx …' python3 tools/push_pages.py --site https://ks0man.org
    …                                  python3 tools/push_pages.py --site … --check
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from push_media import api, slug_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_JSON = os.path.join(ROOT, "content", "mirror_pages.json")
TOKEN = re.compile(r"\{\{(media|pub):([^}]+)\}\}")


def media_urls(site: str, auth: str, pace: float) -> dict[str, str]:
    """Every name an attachment answers to -> its URL. See push_media.py."""
    out: dict[str, str] = {}
    page = 1
    while True:
        rows = api(site, auth, "GET",
                   f"/media?per_page=100&page={page}"
                   "&_fields=id,slug,source_url,media_details", pace=pace)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            url = row.get("source_url", "")
            if not url:
                continue
            out.setdefault(row.get("slug", ""), url)
            out.setdefault(os.path.basename(url), url)
            original = (row.get("media_details") or {}).get("original_image")
            if original:
                out.setdefault(original, url)
                out.setdefault(slug_of(original), url)
        if len(rows) < 100:
            break
        page += 1
    out.pop("", None)
    return out


def publication_urls(site: str, auth: str, pace: float) -> dict[str, str]:
    """Source file on ks0man.com -> the permalink of the record made from it."""
    out: dict[str, str] = {}
    page = 1
    while True:
        rows = api(site, auth, "GET",
                   f"/maars_publication?per_page=100&page={page}"
                   "&status=publish&_fields=id,link,meta", pace=pace)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            source = ((row.get("meta") or {}).get("_maars_source_file") or "")
            if source:
                out[os.path.basename(source).lower()] = row["link"]
        if len(rows) < 100:
            break
        page += 1
    return out


def resolve(blocks: str, media: dict[str, str], pubs: dict[str, str]) -> tuple[str, list[str]]:
    missing: list[str] = []

    def swap(match: re.Match) -> str:
        kind, name = match.group(1), match.group(2)
        if kind == "media":
            url = media.get(name) or media.get(slug_of(name))
        else:
            url = pubs.get(name.lower())
            if not url:
                # newsletter_06-09.html and newsletter_06-09.pdf are the same
                # issue in two formats; the record was made from one of them.
                stem = os.path.splitext(name.lower())[0]
                for ext in (".pdf", ".html", ".htm", ".doc", ".docx"):
                    url = pubs.get(stem + ext)
                    if url:
                        break
        if not url:
            missing.append(match.group(0))
            return match.group(0)
        return url

    return TOKEN.sub(swap, blocks), missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--pace", type=float, default=1.2)
    args = ap.parse_args()

    user = os.environ.get("WP_USER")
    password = os.environ.get("WP_APP_PASSWORD")
    if not user or not password:
        print("set WP_USER and WP_APP_PASSWORD")
        return 2
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    data = json.load(open(PAGES_JSON))
    media = media_urls(args.site, auth, args.pace)
    pubs = publication_urls(args.site, auth, args.pace)
    print(f"  {len(media)} media names, {len(pubs)} archive records known to the site")

    existing = {}
    page = 1
    while True:
        rows = api(args.site, auth, "GET",
                   f"/pages?per_page=100&page={page}&status=publish,draft,private"
                   "&_fields=id,slug,link", pace=args.pace)
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            existing[row["slug"]] = row
        if len(rows) < 100:
            break
        page += 1

    blocked = []
    ready = []
    for spec in data["pages"]:
        resolved, missing = resolve(spec["blocks"], media, pubs)
        if missing:
            blocked.append((spec["slug"], sorted(set(missing))))
            continue
        ready.append((spec, resolved))

    for slug, missing in blocked:
        print(f"  NOT PUBLISHING {slug}: unresolved {', '.join(missing[:6])}")

    if args.check:
        for spec, resolved in ready:
            state = "update" if spec["slug"] in existing else "create"
            print(f"  would {state} /{spec['slug']}/  ({len(resolved)//1024} KB)")
        return 1 if blocked else 0

    done = failed = 0
    for spec, resolved in ready:
        parent_id = 0
        if spec.get("parent"):
            parent = existing.get(spec["parent"])
            if not parent:
                print(f"  {spec['slug']}: parent page '{spec['parent']}' is not there")
                failed += 1
                continue
            parent_id = parent["id"]
        payload = {
            "title": spec["title"],
            "slug": spec["slug"],
            "status": "publish",
            "content": resolved,
            "parent": parent_id,
            "meta": {
                "_maars_grade": "measured",
                "_maars_verified_on": data.get("generated", ""),
                "_maars_source_file": "mirror/ks0man.com/" + spec["sources"][0],
            },
        }
        path = f"/pages/{existing[spec['slug']]['id']}" if spec["slug"] in existing else "/pages"
        got = api(args.site, auth, "POST", path, json.dumps(payload).encode(),
                  {"Content-Type": "application/json"}, pace=args.pace)
        if isinstance(got, dict) and got.get("id"):
            done += 1
            existing[spec["slug"]] = {"id": got["id"], "slug": spec["slug"], "link": got["link"]}
            print(f"  {got['link']}")
        else:
            failed += 1
            print(f"  FAILED {spec['slug']}: {str(got)[:160]}")

    print(f"  pages: {done} published, {failed} failed, {len(blocked)} withheld")
    return 1 if (failed or blocked) else 0


if __name__ == "__main__":
    sys.exit(main())
