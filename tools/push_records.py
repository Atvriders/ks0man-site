#!/usr/bin/env python3
"""Make the archive on a live site match the repository: every record, its
file, its other formats, its provenance, and its text.

The media import inside the Docker image does this as it imports
(tools/import_media.php, tools/import_html_archive.php). A live site that
received its files over REST needs it done from outside, and on 16 October 2026
ks0man.org showed why: twenty-one newsletters and minutes uploaded a month
earlier with no record, and not one of 243 records knowing which file was its
own.

What a run makes true, for every manifest item with a title and a date:
    - its record exists (keyed on the source file it was made from), and its
      title, date, kind and year are the manifest's -- so a correction in the
      manifest (three sets of minutes filed as newsletters, a March report
      filed as April) reaches the site;
    - _maars_attachment is the attachment that IS the document, parented to it;
    - _maars_source_file says where the file really came from: the old site
      as served (mirror/ks0man.com/) or the webmaster's own folder
      (webmaster-folder/), never the first when it was the second;
    - _maars_verified_on is set.
For every item with alternate_of: the record lists it in _maars_alternates,
REPLACED from the manifest rather than merged into.
For every item with duplicate_of: a record made from it is deleted, because it
describes a document that does not exist -- the old site linked "Jan. 2017" to
a byte-identical copy of the February 2017 minutes.
With --issues: the 125 records of the HTML years carry content/html_archive.json
as their text, with its links resolved.
With --text: the 142 records made from PDF and Word files carry their
machine-read text from content/record_text.json (tools/prepare_record_text.py).

Idempotent and paced; --check reports what a run would change and writes nothing.

    WP_USER=… WP_APP_PASSWORD='xxxx …' python3 tools/push_records.py --site https://ks0man.org [--issues] [--text] [--check]
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from push_media import (  # noqa: E402
    api, list_all, resolve_tokens, shipped_key, site_media_maps, site_publications, wp_names,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR = os.path.expanduser("~/ks0man-migration/mirror/ks0man.com")
FOLDER = os.path.expanduser("~/ks0man-migration/webmaster-folder")
VERIFIED_ON = "2026-10-17"


def source_path(src: str) -> str:
    if os.path.exists(os.path.join(MIRROR, src)):
        return "mirror/ks0man.com/" + src
    if os.path.exists(os.path.join(FOLDER, src)):
        return "webmaster-folder/" + src
    return "mirror/ks0man.com/" + src


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--site", required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--issues", action="store_true", help="also push the HTML-era issue texts")
    ap.add_argument("--text", action="store_true", help="also push the text of the PDF and Word records")
    ap.add_argument("--pace", type=float, default=1.2)
    args = ap.parse_args()

    user, password = os.environ.get("WP_USER"), os.environ.get("WP_APP_PASSWORD")
    if not user or not password:
        print("set WP_USER and WP_APP_PASSWORD")
        return 2
    auth = base64.b64encode(f"{user}:{password}".encode()).decode()
    site, pace, check = args.site, args.pace, args.check
    json_hdr = {"Content-Type": "application/json"}

    def post(path, payload):
        if check:
            return {"id": -1}
        return api(site, auth, "POST", path, json.dumps(payload).encode(), json_hdr, pace=pace)

    manifest = json.load(open(os.path.join(ROOT, "media", "manifest.json")))

    att_by_name: dict[str, dict] = {}
    for row in list_all(site, auth, "/media?_fields=id,slug,source_url,media_details,post", pace):
        for n in wp_names(row):
            att_by_name.setdefault(n, row)

    def attachment_for(item):
        return att_by_name.get(item["file"]) or att_by_name.get(shipped_key(item["file"]))

    records = list_all(site, auth, "/maars_publication?status=publish,draft&context=edit"
                       "&_fields=id,link,slug,title,date,meta,maars_doc_type,maars_year,content", pace)
    record_by_src: dict[str, dict] = {}
    for row in records:
        source = os.path.basename(((row.get("meta") or {}).get("_maars_source_file") or ""))
        if source:
            record_by_src.setdefault(source.lower(), row)

    terms: dict[str, dict] = {}
    for tax in ("maars_doc_type", "maars_year"):
        rows = list_all(site, auth, f"/{tax}?_fields=id,slug,name", pace)
        terms[tax] = {t["slug"]: t["id"] for t in rows} | {t["name"]: t["id"] for t in rows}

    def term_id(tax, value):
        value = str(value)
        if value in terms[tax]:
            return terms[tax][value]
        made = post(f"/{tax}", {"name": value, "slug": value})
        if isinstance(made, dict) and made.get("id"):
            terms[tax][value] = made["id"]
            return made["id"]
        print(f"    could not make {tax} term {value}: {str(made)[:100]}")
        return None

    plan: list[str] = []
    missing_files = 0

    for item in manifest:
        if not (item.get("title") and item.get("date")):
            continue
        att = attachment_for(item)
        if not att:
            missing_files += 1
            print(f"  NO FILE on the site for {item['src']} ({item['file']}) -- upload it first")
            continue
        want_meta = {
            "_maars_source_file": source_path(item["src"]),
            "_maars_doc_date": item["date"],
            "_maars_grade": "sourced",
            "_maars_attachment": str(att["id"]),
        }
        dt = term_id("maars_doc_type", item.get("doc_type", "")) if item.get("doc_type") else None
        yr = term_id("maars_year", item["year"])
        record = record_by_src.get(item["src"].lower())
        if not record:
            plan.append(f"create record: {item['title']}")
            payload = {"title": item["title"], "status": "publish", "content": "",
                       "date": item["date"] + "T09:00:00",
                       "meta": want_meta | {"_maars_verified_on": VERIFIED_ON}}
            if dt:
                payload["maars_doc_type"] = [dt]
            if yr:
                payload["maars_year"] = [yr]
            got = post("/maars_publication", payload)
            if isinstance(got, dict) and got.get("id"):
                record = {"id": got["id"], "meta": payload["meta"], "title": {"raw": item["title"]},
                          "date": payload["date"], "maars_doc_type": payload.get("maars_doc_type", []),
                          "maars_year": payload.get("maars_year", [])}
                record_by_src[item["src"].lower()] = record
                if not check:
                    print(f"  created {got.get('link')}")
            else:
                print(f"  FAILED to create {item['title']}: {str(got)[:160]}")
                continue

        update: dict = {}
        meta = record.get("meta") or {}
        changed_meta = {k: v for k, v in want_meta.items() if str(meta.get(k, "")) != v}
        if not meta.get("_maars_verified_on"):
            changed_meta["_maars_verified_on"] = VERIFIED_ON
        if changed_meta:
            update["meta"] = changed_meta
        title = (record.get("title") or {}).get("raw") or (record.get("title") or {}).get("rendered", "")
        if title and title != item["title"]:
            update["title"] = item["title"]
            # The slug follows the title, so the URL says what the record is.
            # WordPress keeps the old slug and redirects it.
            update["slug"] = ""
        if (record.get("date") or "")[:10] != item["date"]:
            update["date"] = item["date"] + "T09:00:00"
        if dt and record.get("maars_doc_type") != [dt]:
            update["maars_doc_type"] = [dt]
        if yr and record.get("maars_year") != [yr]:
            update["maars_year"] = [yr]
        if update:
            plan.append(f"update {item['title']}: {', '.join(sorted(update))}")
            post(f"/maars_publication/{record['id']}", update)
        if att.get("post") != record["id"]:
            plan.append(f"parent {item['file']} to {item['title']}")
            post(f"/media/{att['id']}", {"post": record["id"]})

    # A record describing a document that does not exist.
    for item in manifest:
        dup = item.get("duplicate_of")
        if not dup:
            continue
        record = record_by_src.get(item["src"].lower())
        if record and record.get("id", -1) > 0:
            plan.append(f"delete record for {item['src']} (a copy of {dup})")
            if not check:
                api(site, auth, "DELETE", f"/maars_publication/{record['id']}?force=true", pace=pace)

    # Other formats, after every record exists; the manifest is the authority.
    wanted: dict[int, list] = {}
    for item in manifest:
        of = item.get("alternate_of")
        if not of:
            continue
        att = attachment_for(item)
        record = record_by_src.get(of.lower())
        if not att or not record:
            print(f"  cannot join {item['src']} to {of}: file {'ok' if att else 'missing'}, "
                  f"record {'ok' if record else 'missing'}")
            continue
        wanted.setdefault(record["id"], []).append(str(att["id"]))
        if att.get("post") != record["id"]:
            post(f"/media/{att['id']}", {"post": record["id"]})
    for rid, ids in wanted.items():
        rec = next(r for r in record_by_src.values() if r["id"] == rid)
        have = [x for x in str((rec.get("meta") or {}).get("_maars_alternates", "")).split(",") if x]
        merged = list(dict.fromkeys(ids))
        if merged != have:
            plan.append(f"set other formats of record {rid}: {','.join(merged)}")
            post(f"/maars_publication/{rid}", {"meta": {"_maars_alternates": ",".join(merged)}})

    if args.issues:
        urls, full = site_media_maps(site, auth, pace)
        pubs = site_publications(site, auth, pace)
        issues = json.load(open(os.path.join(ROOT, "content", "html_archive.json")))
        unresolved_total = 0
        for issue in issues:
            record = record_by_src.get(issue["src"].lower())
            if not record:
                print(f"  no record for {issue['src']}")
                continue
            content, missing = resolve_tokens(issue["blocks"], urls, full, pubs)
            if missing:
                unresolved_total += len(missing)
                print(f"  {issue['src']}: unresolved {missing[:3]}")
                continue
            current = (record.get("content") or {}).get("raw", "")
            update = {}
            if current != content:
                update["content"] = content
            if not (record.get("meta") or {}).get("_maars_verified_on"):
                update["meta"] = {"_maars_verified_on": VERIFIED_ON}
            if update:
                plan.append(f"update text of {issue['title']}")
                post(f"/maars_publication/{record['id']}", update)
        if unresolved_total:
            print(f"  {unresolved_total} issue link(s) unresolved -- those issues were NOT updated")

    if args.text:
        bundle = json.load(open(os.path.join(ROOT, "content", "record_text.json")))
        for item in bundle["records"]:
            record = record_by_src.get(item["src"].lower())
            if not record:
                print(f"  no record for {item['src']}")
                continue
            if (record.get("content") or {}).get("raw", "") != item["blocks"]:
                plan.append(f"set the text of {item['src']}")
                post(f"/maars_publication/{record['id']}", {"content": item["blocks"]})

    print(f"  {len(plan)} change(s){' a run would make' if check else ' made'}; "
          f"{missing_files} record file(s) not on the site")
    if check:
        for line in plan[:60]:
            print("   ", line)
    return 1 if (missing_files or (check and plan)) else 0


if __name__ == "__main__":
    sys.exit(main())
