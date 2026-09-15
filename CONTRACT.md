# ks0man-site — LOCKED INTERFACE CONTRACT
Agents: write files at these exact paths with these exact names. Do not invent alternatives.
Repo root: /home/kasm-user/ks0man-site

## What this is
A runnable demonstration of the ks0man.org rebuild: WordPress + the `maars-core` plugin +
the `maars` block theme + a WebGL2 homepage, shipped as ONE public image on GHCR and started
with `docker compose up`.

## HARD RULE — NO PERSONAL DATA IN THE IMAGE
The image is PUBLIC on ghcr.io. The source archive contains 28 personal e-mail addresses,
7 phone numbers, a home address, a 41-name member roster and 17 storm-spotter street addresses.
NONE of that may be baked into the image or committed to this repo. Seed content is limited to:
club history, governance facts, the archive's SHAPE, and technical facts marked UNVERIFIED.
Officer names appear ONLY where already-public and role-level (no e-mails, no phones).
The club generates full content locally with tools/build_content.py against their own mirror.

## Versions (pinned, do not change)
- Base image: `wordpress:6.7-php8.3-apache`
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
tools/build_content.py
tools/seed.php
content/seed.json
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

## Blocks (server-rendered, registered in PHP with render_callback, no JS build)
- `maars/next-meeting`   → computed date + the rule that produced it
- `maars/dateline`       → "last published N days ago" banner; red when > 120 days
- `maars/fact`           → wraps a fact with its freshness grade chip
- `maars/skywave`        → the WebGL2 canvas + <noscript>/fallback

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
