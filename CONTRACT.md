# ks0man-site — LOCKED INTERFACE CONTRACT
Agents: write files at these exact paths with these exact names. Do not invent alternatives.
Repo root: the repository root (paths below are relative to it).

## What this is
The code and content of https://ks0man.org, the Society's site: WordPress + the
`maars-core` plugin + the `maars` block theme + a WebGL2 homepage. The same site ships as
ONE public image on GHCR, started with `docker compose up`, and goes to the live site
through the REST tools in tools/ (content) and tools/deploy_wp.py (theme and plugin).

## HARD RULE — WHOSE INFORMATION IS IT
Amended 17 September 2026 by the Society's decision, which is recorded here because it
reverses the rule this file carried before it.

THE SOCIETY'S OWN RECORD PUBLISHES IN FULL. The newsletters, minutes, reports and
photographs are the club's information about the club; every line of it stood on
ks0man.com for twenty-seven years, so the migration is continuity, not new exposure.
Contact details inside those documents and the memorial portraits go with them,
unredacted. The club asked for the whole record to be reachable by its own members.

WHAT STILL MUST NEVER BE COMMITTED, and is gated in tests/test_static.py:
- Third-party copyright material. Not ours to republish; link to the source instead.
- Anything about the machine this was built on: LAN IPs, hostnames, developer host
  paths, credentials. The gate covers the whole tree, archive payload included.
The PII gate covers every path EXCEPT the four archive payload paths — `media/`,
`content/html_archive.json`, `content/mirror_pages.json` and `content/record_text.json` —
and a meta-check refuses to let that exemption grow to a fifth.

AMENDED AGAIN 16 OCTOBER 2026: "anything we are missing needs to be added. do not
skip adding anything. everything needs to be there." Material by other authors
now ships, as it did on the old site, and so do the member lists from the
webmaster's own folder -- addresses, telephone numbers and e-mail -- which were
never on ks0man.com. The Society was told that publishing those is new exposure
rather than continuity, and decided to publish them. tools/screen_media.py now
REPORTS what the shipped PDFs carry rather than refusing any of it.

## Every file has a route to a reader
A file in the media library that no page leads to is not on the site. Every
item in media/manifest.json is one of: an archive record (title + date), another
format of one (alternate_of), placed on a page ({{media:...}} token), or listed
on /club-files/ (category). tests/test_static.py fails on any other.
Record pages link their own file through `maars/original-file`, which reads
`_maars_attachment` (the file) and `_maars_alternates` (other formats). A record from the
years the newsletter was a web page links ks0man-com-pages-as-served.zip, every page
ks0man.com served byte for byte (tools/bundle_served_pages.py), and names its page in it.
Every record made from a PDF or Word file carries the file's machine-read text
(content/record_text.json, tools/prepare_record_text.py), so the archive's search can
find what the minutes and reports say.

## The manifest (media/manifest.json), field by field
src (name on ks0man.com or in the folder) · file (name it ships under) · kind · bytes ·
origin (`mirror` or `webmaster-folder`) · title + date + doc_type + year (an archive record) ·
category (its /club-files/ section) · alternate_of (another format of that record) ·
duplicate_of (a byte-for-byte copy of that record's file: no record of its own; its old
address opens that record) · stored_as (the name the host converted it to: favicon.ico is
stored as favicon.jpg) · contains (a bundle's entries) · note.
Every file outside the archive has a category, so /club-files/ holds all of them.

## Versions (pinned, do not change)
- Base image: `wordpress:7.1-php8.3-apache`
- DB: `mariadb:11.4`
- Image name: `ghcr.io/atvriders/ks0man-site`
- PHP target: 8.3 (code must also pass `php -l` on 8.1)
- WordPress text domain: `maars`
- No Composer, no npm, no build step. Plain PHP + vanilla JS only.
- WebGL: raw WebGL2. NO three.js, NO external libraries, NO CDN.

## File map (exact)
docker-compose.yml
Dockerfile
.dockerignore
README.md
.github/workflows/build.yml
docker/entrypoint.sh                 # wraps the base image entrypoint, runs first-boot seed
wp/plugins/maars-core/maars-core.php # plugin header + bootstrap ONLY; requires inc/*.php
wp/plugins/maars-core/inc/post-types.php
wp/plugins/maars-core/inc/taxonomies.php
wp/plugins/maars-core/inc/fields.php
wp/plugins/maars-core/inc/freshness.php
wp/plugins/maars-core/inc/blocks.php
wp/plugins/maars-core/inc/tally.php   # the archive counted at render time; the [maars_archive_*] shortcodes
wp/plugins/maars-core/inc/original.php # maars/original-file: a record's own file, its formats, a real link
wp/plugins/maars-core/inc/uploads.php  # lets site managers upload the archive's source formats (.psd .ttf .indd .pm)
wp/plugins/maars-core/inc/legacy.php   # answers an old ks0man.com / www.ks0man.org address that reaches this site
wp/plugins/maars-core/inc/legacy-map.php # GENERATED by tools/build_redirects.py: old name -> what it is now
wp/themes/maars/style.css
wp/themes/maars/theme.json
wp/themes/maars/functions.php
wp/themes/maars/templates/index.html
wp/themes/maars/templates/front-page.html
wp/themes/maars/templates/archive-maars_publication.html
wp/themes/maars/templates/single-maars_publication.html
wp/themes/maars/parts/header.html
wp/themes/maars/parts/footer.html
wp/themes/maars/assets/js/skywave.js
wp/themes/maars/assets/css/maars.css
tools/build_content.py               # the study-era converter; no longer how content is made
tools/seed.php
tools/seed_pages.php                 # publishes content/mirror_pages.json, AFTER the media import, and
                                     # brings untouched seed pages and facilities up to the seed
tools/lib_tokens.php                 # the image's token resolver, shared by the importers
tools/import_media.php               # media/ into the library, and the archive records made from it
tools/import_html_archive.php        # the 125 web-era issues, into the image, AFTER the media import
tools/import_record_text.php         # the text of the 142 PDF and Word records, into the image
tools/prepare_html_archive.py        # converts the web-era issues to content/html_archive.json
tools/prepare_record_text.py         # reads every PDF and Word record into content/record_text.json
tools/bundle_served_pages.py         # every page ks0man.com served, byte for byte, into one zip
tools/ingest_webmaster_files.py      # brings "MAARS Page.zip" (the webmaster's folder) into media/
tools/push_records.py                # makes and links archive records on a live site over REST
tools/deploy_wp.py                   # uploads the theme and plugin zips through wp-admin
tools/push_media.py                  # uploads media/ to a live site over REST, idempotent
tools/push_pages.py                  # publishes mirror_pages.json to a live site, tokens resolved
tools/prepare_pages.py               # converts the un-migrated pages of ks0man.com to blocks
tools/build_redirects.py             # decides every old address from the repo, resolves it on the live site
migrate/url_map.csv                  # every old URL and where it goes now
migrate/ks0man_com.htaccess          # the same, as Apache rules, for the old domain
migrate/README.md
content/seed.json
content/mirror_pages.json            # roster, Silent Keys, galleries, history, /club-files/: tokens, not URLs
content/html_archive.json            # the 125 issues from the years the newsletter WAS the web page
content/record_text.json             # the machine-read text of the 142 records made from PDF and Word files
tests/test_webgl.py
tests/test_static.py

## PHP naming contract (agents MUST match these exactly)
Prefix every global function `maars_`. Text domain `maars`.
- `maars_register_post_types()`      hooked to `init` prio 5
- `maars_register_taxonomies()`      hooked to `init` prio 5
- `maars_register_meta()`            hooked to `init` prio 6
- `maars_register_blocks()`          hooked to `init` prio 10
- `maars_freshness_state( int $post_id ): array`  returns
    [ 'grade' => 'measured'|'sourced'|'unverified', 'verified_on' => 'YYYY-MM-DD'|'',
      'age_days' => int|null, 'stale' => bool ]
- `maars_next_meeting( ?int $from_ts = null ): array` returns
    [ 'ts' => int, 'iso' => 'YYYY-MM-DD', 'label' => string, 'rule' => string ]
  Rule: 2nd Friday of the month, 6:30 PM America/Chicago (constitution SOP).
  MUST carry a `rule` string naming its source so the page can show WHY.
- `maars_days_since_last_publication(): int`

## Post types (slug => rewrite)
- `maars_publication` => `/archive/%year%/`   (newsletters, minutes, treasurer, year-end)
- `maars_person`      => `/people/`           (NON-PUBLIC in seed: 'public' => false)
- `maars_facility`    => `/on-the-air/`       (repeaters + nets; 'public' => true)
Core `post` = News (the 36 Current Topics). Core `page` = standing pages.

## Taxonomies
- `maars_doc_type`  (hierarchical, on maars_publication): newsletter, minutes, treasurer-report, year-end-report
- `maars_year`      (non-hier, on maars_publication + post)
- `maars_callsign`  (non-hier, on all; 'public' => false in seed)
- `maars_facility_kind` (non-hier, on maars_facility): repeater, net

## Meta keys (all register_post_meta, single, REST-exposed, sanitized)
`_maars_verified_on` (string YYYY-MM-DD) · `_maars_grade` (string) · `_maars_source_file` (string)
`_maars_doc_date` (string YYYY-MM-DD) · `_maars_freq_mhz` (string) · `_maars_tone_hz` (string)
`_maars_offset` (string) · `_maars_schedule` (string)
`_maars_attachment` (string, attachment ID) · `_maars_alternates` (string, comma-separated IDs) — maars_publication only
Not REST-registered, written by the importers: `_maars_media_file` (attachment: the name it shipped
under) · `_maars_media_src` (attachment: its source name) · `_maars_seed_hash` (seed page or facility:
md5 of the text the tooling last wrote; a page whose text no longer matches has been edited, and
tools/seed_pages.php leaves it alone unless MAARS_RESEED_PAGES=1)

## Blocks (server-rendered, registered in PHP with render_callback, no JS build)
- `maars/next-meeting`   → computed date + the rule that produced it
- `maars/dateline`       → "last published N days ago" banner; red when > 120 days
- `maars/fact`           → wraps a fact with its freshness grade chip
- `maars/skywave`        → the WebGL2 canvas + <noscript>/fallback
- `maars/masthead`       → the 2 m receiver at the head of the site: trace, waterfall, identity
- `maars/original-file`  → an archive record's own file: name, kind, size, link, other formats

## Media and page references outside the seed
content/mirror_pages.json, content/html_archive.json and the seed reference media
and archive records by TOKEN, never by URL, because the name a file ships under is
not the URL WordPress gives it:
    {{media:<file as shipped>}}   {{media-full:<file>}} (the upload itself, never the
    -scaled copy WordPress shows)   {{pub:<source file on ks0man.com>}}
Resolvers: tools/lib_tokens.php (in the image, used by tools/seed_pages.php and
tools/import_html_archive.php, after tools/import_media.php) and tools/push_media.py's
resolve_tokens() (against a live site, used by push_pages.py and push_records.py). Both REFUSE to publish a page with an
unresolved token. An attachment is identified by slug, by media_details
.original_image, or by _maars_media_src -- NOT by the file on disk, which
WordPress renames (fd18-tower.jpg is stored as fd18-tower-scaled.jpg).

## Archive figures (shortcodes, inc/tally.php)
Every number about the archive is counted at render time. No template, page or
post may state a total in prose: the theme shipped "266 items", "14 pages in
all" and "209 newsletters" from the study of ks0man.com, and the About page went
on saying 209 and "2012 produced nothing" after the archive had 210 and a 2012
report. Year counts count archive records only: maars_year is on core posts too,
and its term counts are not used.
- `[maars_archive_count]`       → published maars_publication posts
- `[maars_archive_span]`        → "1998 to 2024"
- `[maars_archive_first_year]` · `[maars_archive_last_year]`
- `[maars_archive_kinds]`       → "127 newsletters, 82 sets of meeting minutes, …"
  (plurals come from `maars_doc_type_terms()['<slug>']['plural']`)
- `[maars_archive_pages per_page=20]` → pages the list runs to; per_page MUST equal
  MAARS_ARCHIVE_PER_PAGE (maars-core.php), which the archive's main query uses — the
  query block inherits it, so /archive/page/9/ is page 9 (gated by tests/test_static.py)
- `[maars_archive_gap_years]`   → "2012 and 2014"; runs collapse to "2000 to 2011"
- `[maars_archive_gaps]`        → the whole sentence, or empty when there are none
- `[maars_archive_coverage]`    → the gaps sentence, OR "Every year from 1998 to 2024 holds
  at least one document." -- prose about gaps must use this, never assert gaps itself
- `[maars_archive_newest]`      → date on the newest document of any kind, news posts included
- `[maars_archive_newest_record]` → month of the newest archive record ("January 2024"); prose
  about "the newest of them" means the archive's documents and uses this
- `[maars_archive_year_table]`  → the record year by year, gaps marked (.maars-yeartable)
Shortcodes are processed in block templates by get_the_block_template_html().

## Routes that are not pages
`/archive/` (maars_publication) · `/on-the-air/` (maars_facility) ·
`/archive/<year>/` (maars_year) · `/archive/type/<slug>/` (maars_doc_type) ·
`/archive/gaps/` → the page `archive-gaps`, via add_rewrite_rule() in post-types.php.
An old address — `/newsletter_03-01.html`, `/Francis_2007_1.jpg` — that would be a 404 is
redirected by inc/legacy.php from inc/legacy-map.php: ks0man.org was the old site's other
name, and the webmaster's pages linked www.ks0man.org/<file>.
Rewrite rules are flushed once per deploy by `maars_maybe_flush_rewrites()`;
bump `MAARS_REWRITE_VERSION` in maars-core.php whenever a rule changes.
Every internal href in the theme is checked against this list by
tests/test_static.py — a link to a URL nothing serves fails the build.

## theme.json palette (EXACT — measured from the club's own stylesheet)
navy #00008C (15.23:1 on white, AAA) · magenta #990066 (8.25:1) · lavender #DBDBFB
ink #14142B · paper #FFFFFF · ground #FBFBFD · alarm #A5171B
Dark variants: navy #9FA0F2 · magenta #F09FD0 · ground #0C0C18 · paper #14142A · ink #EDEDF7
Fonts: theme.json fontFamilies only; system stacks (no webfont downloads in the image).

## skywave.js contract
- Global entry: `window.MAARSSkywave.mount(canvasEl, opts)` returns `{ destroy() }`
- Raw WebGL2. If `getContext('webgl2')` is null → add class `maars-skywave--fallback`
  to the canvas's parent and return without throwing.
- Scene: curved Earth surface + D/E/F1/F2 ionosphere shells + animated HF ray hops
  launched from Manhattan, Kansas. Orbitable (pointer drag), respects
  `prefers-reduced-motion` (renders one static frame).
- Band selector data (REAL club frequencies, from the corpus):
    80m 3.920 MHz "Kansas Sideband Net"  · 40m 7.260 MHz "Kansas Weather Net"
    20m 14.290 MHz "daytime DX"          · 2m 147.255 MHz "KSØMAN repeater (line of sight — no skip)"
  At 2m the scene MUST show the ray escaping to space, not refracting. That is the teaching point.
- Must set `canvas.dataset.maarsReady = "1"` once the first frame has drawn (tests assert this).
- No external network calls of any kind.

## AMENDMENT 1 (owner instruction, supersedes anything above)
**All environment variables live INLINE in docker-compose.yml. There is no .env file and no
.env.example, and compose must NOT use `env_file:`.**
- Each service declares a literal `environment:` block with real, working values, so that a bare
  `docker compose up -d` works with no setup step at all.
- Values are LOCAL-DEV credentials only, written literally (e.g. `MARIADB_PASSWORD: maars_local_dev`).
  Put a comment directly above the credentials block saying, in one line, that these are local
  development values and must be changed before the stack is exposed beyond localhost.
- Do NOT use `${VAR:-default}` interpolation for the credentials; the point of this amendment is
  that everything needed is visible in the one file.
- The published port is a literal `3039:80`. No interpolation, so it works with no .env present.
- docker/entrypoint.sh must read exactly the variable names compose sets; no others.
- tests/test_static.py must NOT expect .env.example, and its PII/secret gate must allow these
  clearly-labelled local-dev credentials while still failing on anything that looks like a real
  secret, key, token or personal address.
- README quick start becomes: `docker compose up -d`, then open http://localhost:3039. No copy step.

## Tests
tests/test_static.py  — pure-python: asserts file map exists, no PII regexes anywhere in repo,
                        every PHP file passes `php -l`, theme.json + seed.json parse, compose parses.
tests/test_webgl.py   — Playwright + Chromium(SwiftShader): loads a harness page, waits for
                        dataset.maarsReady, asserts the canvas is NOT blank (pixel variance),
                        asserts band switching changes the rendered image, screenshots to tests/out/.
PHP binary for linting: $MAARS_PHP (exported by tests; falls back to `php`).
