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
from push_media import api, list_all, resolve_tokens, site_media_maps, site_publications  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES_JSON = os.path.join(ROOT, "content", "mirror_pages.json")


MIRROR = os.path.expanduser("~/ks0man-migration/mirror/ks0man.com")
FOLDER = os.path.expanduser("~/ks0man-migration/webmaster-folder")


def source_path(name: str) -> str:
    """Where a page's source really came from: the old site as served, or the
    webmaster's folder. Every page used to say mirror/ks0man.com, including
    nine built from files ks0man.com never served."""
    if name == "media/manifest.json":
        return "media/manifest.json"
    if os.path.exists(os.path.join(MIRROR, name)):
        return "mirror/ks0man.com/" + name
    if os.path.exists(os.path.join(FOLDER, name)):
        return "webmaster-folder/" + name
    return name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--pace", type=float, default=1.2)
    ap.add_argument("--seed", default="",
                    help="comma-separated slugs of content/seed.json pages to publish FIRST "
                         "(a parent such as 'history' must exist before its children)")
    ap.add_argument("--facilities", default="",
                    help="comma-separated slugs of content/seed.json facilities (repeaters and "
                         "nets) whose text to update")
    args = ap.parse_args()

    user = os.environ.get("WP_USER")
    password = os.environ.get("WP_APP_PASSWORD")
    if not user or not password:
        print("set WP_USER and WP_APP_PASSWORD")
        return 2
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()

    data = json.load(open(PAGES_JSON))
    if args.seed:
        wanted = [x.strip() for x in args.seed.split(",") if x.strip()]
        seed = json.load(open(os.path.join(ROOT, "content", "seed.json")))
        by_slug = {pg["slug"]: pg for pg in seed.get("pages", [])}
        missing = [w for w in wanted if w not in by_slug]
        if missing:
            print(f"  no such seed page: {', '.join(missing)}")
            return 2
        seeded = [{"slug": w, "title": by_slug[w]["title"], "parent": by_slug[w].get("parent"),
                   "sources": [], "blocks": by_slug[w]["blocks"],
                   "meta": by_slug[w].get("meta", {})} for w in wanted]
        data = dict(data, pages=seeded + list(data["pages"]))
    media, full = site_media_maps(args.site, auth, args.pace)
    for item in json.load(open(os.path.join(ROOT, "media", "manifest.json"))):
        if item.get("stored_as") and item["stored_as"] in media:
            media.setdefault(item["file"], media[item["stored_as"]])
            full.setdefault(item["file"], full[item["stored_as"]])
    pubs = site_publications(args.site, auth, args.pace)
    print(f"  {len(media)} media names, {len(pubs)} archive records known to the site")

    existing = {}
    for row in list_all(args.site, auth, "/pages?status=publish,draft,private&_fields=id,slug,link", args.pace):
        existing[row["slug"]] = row

    blocked = []
    ready = []
    for spec in data["pages"]:
        resolved, missing = resolve_tokens(spec["blocks"], media, full, pubs)
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
            "meta": spec.get("meta") or {
                "_maars_grade": "measured",
                "_maars_verified_on": data.get("generated", ""),
                "_maars_source_file": source_path(spec["sources"][0]) if spec["sources"] else "",
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

    # Repeaters and nets are maars_facility posts, made by the first seed and
    # never touched by this tool until a correction had to reach one.
    if args.facilities:
        seed = json.load(open(os.path.join(ROOT, "content", "seed.json")))
        by_slug = {f["slug"]: f for f in seed.get("facilities", [])}
        for slug in [x.strip() for x in args.facilities.split(",") if x.strip()]:
            spec = by_slug.get(slug)
            if not spec:
                print(f"  no such seed facility: {slug}")
                failed += 1
                continue
            resolved, missing = resolve_tokens(spec["blocks"], media, full, pubs)
            if missing:
                print(f"  NOT UPDATING facility {slug}: unresolved {', '.join(missing[:6])}")
                failed += 1
                continue
            rows = api(args.site, auth, "GET", f"/maars_facility?slug={slug}&status=publish&_fields=id,link",
                       pace=args.pace)
            if not (isinstance(rows, list) and rows):
                print(f"  facility {slug} is not on the site")
                failed += 1
                continue
            got = api(args.site, auth, "POST", f"/maars_facility/{rows[0]['id']}",
                      json.dumps({"content": resolved}).encode(),
                      {"Content-Type": "application/json"}, pace=args.pace)
            if isinstance(got, dict) and got.get("id"):
                print(f"  {got['link']}")
            else:
                failed += 1
                print(f"  FAILED facility {slug}: {str(got)[:160]}")

    return 1 if (failed or blocked) else 0


if __name__ == "__main__":
    sys.exit(main())
