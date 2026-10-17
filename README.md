# ks0man-site — the Manhattan Area Amateur Radio Society's website

This repository is the code and the content of **https://ks0man.org**: WordPress, the
`maars-core` plugin, the `maars` block theme, a WebGL2 propagation scene, and the Society's
whole record carried over from ks0man.com. The same site also builds as one Docker image: start
it with `docker compose up -d` and open it in a browser on your own machine.

**What it is.** The content model (publications, people, facilities), the block theme, the
palette taken from the club's own 1997 stylesheet, the machinery that makes staleness visible
instead of hiding it — and every document, photograph and page of the old site.

**Where things stand.**

| | |
|---|---|
| The live site | https://ks0man.org runs this theme and plugin with the full archive. Content goes up through the REST tools in `tools/`; the theme and plugin through `tools/deploy_wp.py`. |
| The old site | ks0man.com, the 1997 hand-written site, is still up. Its redirect map is ready in `migrate/` and needs access to the old domain's server to deploy. ks0man.org itself already answers the old file names: see [Old addresses](#old-addresses). |
| The content | Everything: every file the old site served and every file in the folder the webmaster built it from. See [What ships](#what-ships-and-what-does-not). |
| Decisions | Privacy and disclosure are decided: the Society publishes its record in full. Questions about domains, officers and the repeater are still open. See [Open questions](#open-questions).

---

## Status

Read this before you trust anything below it.

| Thing | State | How that was established |
|---|---|---|
| The WebGL propagation scene actually draws | **Verified** | `pytest tests/test_webgl.py` loads the scene in headless Chromium on SwiftShader (software rasteriser, no GPU), waits for the canvas to report `data-maars-ready="1"`, then **reads the pixels back**: it fails if the image is flat, and fails again if switching bands does not change the image. PNGs are written to `tests/out/` — look at them, do not take the exit code's word for it. |
| Every PHP file is syntactically valid | **Verified** | `php -l` on each file, run as part of `tests/test_static.py`. Checked against PHP 8.1; the image runs PHP 8.3. |
| No developer data anywhere in the repository | **Verified** | `tests/test_static.py` greps the whole tree for address, phone, e-mail, LAN-IP and host-path patterns and fails the run. It is a gate, not a guideline. Since the Society's decisions of 17 September and 16 October 2026 the club's **own** record — `media/`, `content/html_archive.json`, `content/mirror_pages.json` and `content/record_text.json` — is exempt and publishes in full; a meta-check in the same file refuses to let that exemption grow to a fifth path. |
| File map, `theme.json`, `content/seed.json`, `docker-compose.yml` all present and parseable | **Verified** | `tests/test_static.py`. |
| **The site running in a real WordPress** | **Verified, but not in Docker** | There is still no Docker daemon in the environment this was built in, so `docker compose up` remains untested by its author. Everything above that has been exercised: the theme and plugin run on a real **WordPress 7.1** (PHP 8.1 + SQLite) built for the purpose, and the same code is live at **https://ks0man.org** with the full archive in it. Pages were rendered and measured in headless Chromium, not asserted. |
| Content completeness | **Verified** | Every file of the old site and of the webmaster's folder is on the live site: 267 dated documents and 405 files, checked against both sources file by file, and every page ks0man.com served is kept byte for byte. A test fails if any shipped file has no route to a reader. A 77-agent audit of the live site on 17 October 2026 confirmed 67 faults; each is fixed, and `tests/test_static.py` now checks the ones a test can see. |
| Link integrity | **Verified for the theme** | `tests/test_static.py` resolves every internal `href` in the theme against the pages the seed creates and the routes the plugin registers, and fails on one that goes nowhere — which is how `/archive/gaps/` was found 404ing in production. A full crawl of the live site is not part of the suite. |
| Redirects from ks0man.com | **Ready, not deployed** | `migrate/url_map.csv` and `migrate/ks0man_com.htaccess`: 479 rules, built by `tools/build_redirects.py` from what the live site actually holds, and **every one of the 471 redirect targets on the site was requested and answered 200** before the files were written; five more go to other sites' documents and three answer 410 Gone. An old file goes to the same bytes on the new site — a photograph to the original ks0man.com served, not a smaller copy. Deploying them needs access to the old domain's server. |

If the first boot fails, that is expected information, not a surprise. File it.

---

## Quick start

You need Docker with the Compose plugin. Nothing else — no PHP, no Node, no Composer, no npm.

```
git clone https://github.com/Atvriders/ks0man-site.git
cd ks0man-site
docker compose up -d
```

Then open **http://localhost:3039**.

The stack serves itself on whatever address you actually used. The site URL is auto-detected from the browser's request, so publishing on a LAN address or a different port works with no edit: `http://192.0.2.10:3039` is as valid as `http://localhost:3039`. Pin it by setting `MAARS_SITE_URL` in `docker-compose.yml` only if you are behind a proxy that rewrites the `Host` header.


First boot takes a minute or so: MariaDB initialises, WordPress sets itself up, and
`docker/entrypoint.sh` runs the first-boot seed once. Subsequent starts are quick. To watch it
happen:

```
docker compose logs -f
```

To stop, and to stop and throw away the database:

```
docker compose down          # stop, keep the data
docker compose down -v       # stop, delete the database volume, next boot re-seeds from scratch
```

There is no `.env` file and nothing to fill in first. Every value the stack needs — database
name, database password, the administrator account — is written literally in
`docker-compose.yml`, under a comment saying so, so the one file you read is the whole
configuration. Sign in at **http://localhost:3039/wp-login.php** as `maars_admin` with the
password on that line.

Those are local-development credentials. They are fine on a laptop and they are not fine
anywhere else: change every password in `docker-compose.yml` before this stack is reachable
from beyond localhost.

---

## What you will see on the homepage

Reading down the page:

1. **The dateline.** A banner across the top saying how many days it has been since the club last
   published anything. Today it is a long time, and the banner is red. It is computed at page load
   from the newest publication in the database. Nobody types it and nobody can turn it off without
   deleting the block.
2. **The next meeting.** A date, and directly under it the rule that produced the date: second
   Friday of the month, 6:30 P.M., doors at 6:00, at the Manhattan/Riley County Senior Center. The
   rule comes from the constitution and SOP as revised 11 December 2021. The date is never stored.
3. **The propagation scene.** A WebGL2 canvas — see below.
4. **Fact cards.** Repeater, nets, meeting logistics. Each one carries a freshness chip and a date.
   The repeater card is graded *unverified* and says so in the open.
5. **The shape of the archive.** Counts by document type and year, and a generated register of the
   months that are missing. The gap list writes itself from the data and cannot be flattered.

### Why there is a WebGL scene on a club homepage

It is a curved Earth, the D/E/F1/F2 ionospheric layers as shells, and animated HF rays launched from
Manhattan, Kansas. Drag to orbit it. Pick a band:

| Band | Frequency | What it is | What the scene shows |
|---|---|---|---|
| 80 m | 3.920 MHz | Kansas Sideband Net | High-angle hops, short skip, works after dark |
| 40 m | 7.260 MHz | Kansas Weather Net | The regional workhorse |
| 20 m | 14.290 MHz | Daytime DX | Long hops, low angle |
| 2 m | 147.255 MHz | KSØMAN repeater | The ray **leaves**. It does not come back. |

That last row is the reason the scene exists. A club website has about four seconds to answer "what
is this, and why would I care", and the honest answer is that these people bounce signals off the
sky and that 2 metres does not do that — which is precisely why the club needs a repeater on a tall
site. That is a diagram, not a paragraph. Three other properties earned it a place:

- It cannot go stale. It is computed physics with a handful of real club frequencies in it, not a
  fact somebody has to remember to update. It will be as true in 2034 as it is today.
- It is honest about being a teaching illustration, not a prediction. It does not claim to be a
  propagation forecast and it makes no network calls of any kind.
- It costs nothing to carry: raw WebGL2, one vanilla JS file, no three.js, no CDN, no build step.
  If the browser has no WebGL2, or JavaScript is off, the parent element gets a
  `maars-skywave--fallback` class and the page renders a static illustration and caption instead.
  Nothing throws, nothing is missing, and no reader is told to upgrade anything.

It also respects `prefers-reduced-motion`: with that set, it draws exactly one frame and stops.

---

## The anti-rot design, in plain words

The old site did not fail because nobody cared. The club kept meeting and kept writing minutes. The
repeater leaving the KSDB-FM tower in November 2023 **is** written down, in the club's own newsletter
for that month. The website simply was never told. The information existed; the hand-off failed.

The site's own accountability note about missing minutes was written in capital letters inside an
HTML comment — where no member would ever see it, because the page had no way to say it out loud.
It is on the page now: the old newsletters index here shows what the webmaster took off each page
but kept in its code, under its own heading.

So the design assumes the hand-off will fail again, and arranges for that failure to be visible
rather than silent. Three mechanisms, all of them on the site:

### 1. Never store a date a computer can compute

The single most-quoted defect on the current site is a homepage advertising a meeting in January
2024, still there in September 2026. So the meeting date is not stored. `maars_next_meeting()`
computes the second Friday of the month at 6:30 P.M. America/Chicago, and returns the rule string
alongside the date so the page can show *why* it says what it says. A rule cannot expire.

### 2. The dateline

`maars_days_since_last_publication()` counts the days since the newest publication. The
`maars/dateline` block prints that number on the page, in front of the public, and turns red past
120 days. Mild public embarrassment is the only enforcement mechanism a volunteer club actually has,
and it is free. A private admin dashboard is one more thing that rots.

### 3. Freshness grades, and facts that retract themselves

Every current fact carries a grade and a date. `maars_freshness_state()` returns the grade, the
`verified_on` date, the age in days, and whether it is stale.

| Grade | Means | Example here |
|---|---|---|
| `measured` | Somebody measured it, and the measurement is reproducible | Navy #00008C is 15.23:1 on white; magenta #990066 is 8.25:1 — both AAA, measured from the club's own 1997 stylesheet |
| `sourced` | Quoted from a dated club document | The meeting rule, the quorum rule, the founding date — all from the constitution and SOP of 11 December 2021 and the 1976 minutes |
| `unverified` | Nobody has confirmed it since the record stopped on 16 January 2024 | Everything about the repeater |

The repeater block is the worked example. All of this is on the page and all of it is stamped
**unverified**: 147.255 MHz out, 147.855 in, +600 kHz, CTCSS 88.5 Hz, open, Motorola Quantar; moved
off the KSDB-FM tower to a Riley County site in November 2023; the S-COM 7330 controller voted out
of the system in January 2024 with no replacement decided.

The rule behind that: **fail to silence, not to a stale answer.** A visitor who reads "not currently
confirmed" asks on the air. A visitor who reads "KSDB-FM tower" in 2027 drives to the wrong place and
concludes the club is dead. Wrong information on a repeater page is worse than absent information.

One thing the site deliberately does *not* do yet: it does not e-mail anybody. When it does, the
overdue digest goes to the Society e-mail reflector, because Article III of the
constitution says the reflector — not the website — is the official organ of the Society. Forty
people seeing "the repeater page is 200 days overdue" produces a correction; one person seeing it in
a private inbox produces avoidance.

### On the palette

The palette is kept exactly as measured from the 1997 stylesheet. It was never the problem. Navy and
magenta both clear WCAG AAA on white by a wide margin. The old site's accessibility failures were a
white-on-white link bug and 1,154 images with no alt text — a code defect and a content defect, not
a colour scheme. Both are fixed by process, not by a redesign.

---

## What ships, and what does not

### The Society's own record, in full — everything

Two decisions by the Society, recorded because each reverses the rule before it:

- **17 September 2026** — the club's own record is published in full. Every line of it stood
  on ks0man.com for twenty-seven years, so the migration is continuity, not new exposure.
- **16 October 2026** — *"anything we are missing needs to be added. do not skip adding
  anything. everything needs to be there."* Material by other authors now ships as it did on
  the old site, and so do the member lists from the webmaster's own folder, with addresses,
  telephone numbers and e-mail, which were never on ks0man.com. The Society was told that
  publishing those is new exposure rather than continuity, and decided to publish them.

So the image, this repository and https://ks0man.org carry:

- **267 dated documents**, 1998–2024 — 127 newsletters, 82 sets of minutes, 52 treasurer's
  reports and 6 year-end reports. Every year from 1998 to 2024 holds at least one. The old
  site's "Jan. 2017" minutes were a byte-for-byte copy of February's, so there is no January
  2017 record and that old link opens February; three sets of minutes the migration had filed
  as newsletters are filed as minutes; the 2012 treasurer's report is March's, as its own
  heading says.
- **The text of every record.** The 125 issues from the years the newsletter was a web page
  carry that page. The 142 records made from PDF and Word files carry the file's text, read by
  machine (`tools/prepare_record_text.py`): prose for minutes and newsletters, a table of label
  and amount for each treasurer's and year-end report, and the OCR for the eight scans with no
  text layer. The archive's search finds what the minutes say.
- **405 files**, 206 MB — every file the old site served **and** every file in the folder it
  was built from (`MAARS Page.zip`), including the Field Day videos, the webmaster's Photoshop,
  InDesign and PageMaker sources, the 1997 site graphics, and every web page of the old site
  twice over: byte for byte as ks0man.com served it, and as the webmaster kept it.
- **Every record page links its own file**, its kind and size, and any other format the club
  kept it in (`maars/original-file`). A web-era issue links the bundle of pages as served and
  names its page inside it.
- **Pages carried over from the old site and the folder** — the roster and three earlier
  rosters, twenty-seven Silent Key notices, the Field Day galleries, the Saturday breakfast
  notices, the running log of announcements from the old home page, the home page as it last
  stood, in autumn 2023, in 2015 and in the GeoCities years, notes on a repeater test site, and
  the exam page. What the webmaster took off a page by commenting it out — retired
  announcements, an officer's row, the note about the missing February 2023 minutes — is shown
  at the foot of that page under its own heading.
- **`/club-files/`** — every file outside the archive, by topic, generated from
  `media/manifest.json`. `tests/test_static.py` fails if any shipped file has no route to a
  reader, and if any file outside the archive has no section on that page.
- Club history and governance facts, and the repeater and net details, graded as before.

Every figure the site states about the archive is counted out of the database as the page
renders — see `[maars_archive_*]` in `wp/plugins/maars-core/inc/tally.php`.

### What is still not here

Only what does not exist: a photograph of the Sale Barn Cafe, an index page for the 1997 Field
Day gallery, and the GeoCities site's own sub-pages and pictures, all linked from the old pages
and gone at the source. `/archive/gaps/` names them. Five more links, on the old links page and
the home page, pointed at other sites' documents with the site's name missing, so they never
opened; the webmaster's own copy of the links page has the full addresses, and the pages here
use them.

Roster rows the webmaster hid in the rosters' code stay hidden on the pages, as they were on the
old site.

What is still refused everywhere: LAN IP addresses, hostnames, developer host paths and
credentials — anything about the machine this was built on rather than about the Society.

### Old addresses

ks0man.org was the old site's other name: the webmaster's pages linked `www.ks0man.org/<file>`,
and that domain is this site now. `wp/plugins/maars-core/inc/legacy.php` answers any old address
that would otherwise be a 404 — `/newsletter_03-01.html` opens its archive record,
`/Francis_2007_1.jpg` the photograph as ks0man.com served it, `/events.css` says 410 Gone. Its
map, `inc/legacy-map.php`, is generated by `tools/build_redirects.py` from the repository and
resolved against each install's own database, so it works on the live site and in the image
alike. Pointing ks0man.com at this site would make all of its addresses work the same way.

## How the content is made, and how it reaches a site

Everything in `content/` and `media/` is generated from two sources outside this repository:
the wget mirror of ks0man.com taken on 11 September 2026, and the webmaster's folder
(`MAARS Page.zip`, supplied on 16 October 2026). The tools that read them:

| Tool | Writes |
|---|---|
| `tools/ingest_webmaster_files.py` | the folder's files into `media/` and `media/manifest.json` |
| `tools/bundle_served_pages.py` | `ks0man-com-pages-as-served.zip`: every page the old site served, byte for byte |
| `tools/prepare_html_archive.py` | `content/html_archive.json`: the 125 web-era issues |
| `tools/prepare_pages.py` | `content/mirror_pages.json`: the carried-over pages and `/club-files/` |
| `tools/prepare_record_text.py` | `content/record_text.json`: the text of the PDF and Word records |
| `tools/build_redirects.py --plugin-only` | `wp/plugins/maars-core/inc/legacy-map.php` |

**In the image**, `docker/entrypoint.sh` imports all of it on every boot, and every importer is
idempotent: `import_media.php`, `import_html_archive.php`, `import_record_text.php`, then
`seed_pages.php`. `tools/seed.php` writes the seed's own pages on the first boot only;
`seed_pages.php` brings each one up to `content/seed.json` afterwards **unless it has been
edited** since the tooling wrote it (`_maars_seed_hash`), so a club member's correction made in
wp-admin is never overwritten. Set `MAARS_RESEED_PAGES=1` for one boot to update a volume an
older image filled.

**On the live site**, over REST with an application password, paced for a host that throttles
bursts:

```
WP_USER=… WP_APP_PASSWORD='…' python3 tools/push_media.py   --site https://ks0man.org
WP_USER=… WP_APP_PASSWORD='…' python3 tools/push_records.py --site https://ks0man.org --issues --text
WP_USER=… WP_APP_PASSWORD='…' python3 tools/push_pages.py   --site https://ks0man.org --seed about,privacy,… --facilities maars-weekly-net
WP_USER=… WP_APP_PASSWORD='…' python3 tools/build_redirects.py --site https://ks0man.org --verify
```

and the theme and plugin through wp-admin with `tools/deploy_wp.py`. `tools/build_content.py` is
the study-era converter; it is no longer how content is made.

---

## Running the tests

Both suites run locally with no Docker.

| Command | Checks | Requires |
|---|---|---|
| `python3 -m pytest tests/test_static.py` | File map complete; no personal-data patterns anywhere in the tree; `php -l` clean on every PHP file; `theme.json`, `content/seed.json` and `docker-compose.yml` parse | `php` on PATH (or `MAARS_PHP` set to a specific binary) |
| `python3 -m pytest tests/test_webgl.py` | The scene draws, is not blank, and changes when you change band; writes screenshots to `tests/out/` | Playwright with Chromium: `python3 -m playwright install chromium` |
| `python3 -m pytest tests/` | Both | Both |

Point the linter at a particular PHP if you have several:

```
MAARS_PHP=/usr/bin/php8.3 python3 -m pytest tests/test_static.py
```

After a WebGL run, open `tests/out/` and look at the images. A test that says the pixels are not
uniform is a weaker claim than your own eyes on the picture.

CI does not run the suites: they need PHP and a browser, and run locally before a push. On every
push to master, `.github/workflows/build.yml` checks that every `COPY` source in the Dockerfile
exists and that the image name matches `docker-compose.yml`, then builds and publishes the image
for amd64 and arm64.

---

## Project layout

| Path | What it is |
|---|---|
| `docker-compose.yml` | The site image plus `mariadb:11.4`; publishes the site on port 3039. |
| `Dockerfile` | `wordpress:6.7-php8.3-apache` plus the plugin, the theme and the seed. |
| `docker/entrypoint.sh` | Wraps the base image's entrypoint and runs the first-boot seed once. |
| `wp/plugins/maars-core/` | The club's own plugin — everything the rebuild adds to WordPress lives here. Plugin header in `maars-core.php`, real work in `inc/`. |
| `wp/plugins/maars-core/inc/post-types.php` | `maars_publication` (the archive), `maars_person` (non-public in this seed), `maars_facility` (repeaters and nets) |
| `wp/plugins/maars-core/inc/taxonomies.php` | Document type, year, callsign, facility kind |
| `wp/plugins/maars-core/inc/fields.php` | The meta keys: verified-on date, grade, source file, document date, frequency, tone, offset, schedule |
| `wp/plugins/maars-core/inc/freshness.php` | `maars_freshness_state()`, `maars_next_meeting()`, `maars_days_since_last_publication()` — the anti-rot core |
| `wp/plugins/maars-core/inc/blocks.php` | Four server-rendered blocks: `maars/next-meeting`, `maars/dateline`, `maars/fact`, `maars/skywave` |
| `wp/themes/maars/` | Block theme. `theme.json` carries the measured palette; `templates/` and `parts/` are plain HTML. |
| `wp/themes/maars/assets/js/skywave.js` | The propagation scene. `window.MAARSSkywave.mount(canvas, opts)`. Raw WebGL2, no libraries. |
| `wp/plugins/maars-core/inc/tally.php` | The archive counted at render time: the `[maars_archive_*]` shortcodes |
| `wp/plugins/maars-core/inc/original.php` | `maars/original-file`: a record's own file, its formats, a real link |
| `wp/plugins/maars-core/inc/legacy.php` | Answers old ks0man.com addresses, from the generated `inc/legacy-map.php` |
| `tools/` | The converters and importers above, and the REST tools that publish to a live site |
| `tools/seed.php` | Turns a seed JSON into WordPress posts, terms and meta at first boot. |
| `content/seed.json` | The site's own pages: About, Privacy, the gaps page, the officers, the nets. |
| `content/mirror_pages.json`, `content/html_archive.json`, `content/record_text.json` | The carried-over pages, the web-era issues, the text of the PDF and Word records |
| `media/` | Every file, and `manifest.json` saying what each one is |
| `tests/` | The two suites above. |

No Composer, no npm, no build step, no external JavaScript. That is deliberate: the club has to be
able to open a file and read it in ten years, on whatever machine it has then.

---

## Open questions

None of these are engineering problems, and none of them can be answered from the archive. The
site is arranged so that the answers drop in without a redesign.

**Decided.** Privacy and disclosure — the obituaries, the roster, the observer posts, the
officers' addresses, the treasury — are answered: on 17 September and 16 October 2026 the
Society decided to publish its record in full, as it published it.

**Still open.**

| # | Question | Why it matters |
|---|---|---|
| 1 | Who is the registrant of record for ks0man.com and ks0man.org, at which registrar, expiring when — and can two current officers log in this week? | The club has already lost four of its own domains. |
| 2 | Is ks0man.org now the canonical address, with ks0man.com redirecting to it? | 27 years of references are printed on paper, read aloud on nets and listed in third-party directories. The redirect map and the plugin's old-address handler are ready either way. |
| 3 | Who are the two named people who hold the site — a Webmaster and a Secretary? | If a second person cannot be named, the thing being built has to change shape. |
| 4 | Is the club still meeting — and is it the first or the second Friday? | The constitution and the old homepage say second. The January 2024 minutes say the Senior Center was reserved for the first. `maars_next_meeting()` implements the constitution; if the practice differs, the rule is wrong. |
| 5 | Who are the officers for 2025 and now? | The newest election on record is November 2023's, for 2024 (on `/officers/`), and not one chair of the seven standing committees is named anywhere in the corpus. |
| 6 | The repeater, as of today: where is it, at what power, into what antenna at what height, which controller, whose trustee licence, what coverage? Is the UHF repeater on the air? Is the EchoLink node live? | The most-consulted fact on the site is in three contradictory states across three pages of the record. Until it is answered, the repeater card stays `unverified`. |

Two more that are not blocking but should be recorded: who holds the physical minute book from 1976
(the largest recoverable gap — 1977 and 1979–1997 are otherwise blank), and whether anything
happened on 7 July 2026, the club's 50th anniversary, that should be written down.

**Full brief.** The reasoning behind each of these, with citations to the specific documents, is in
the private migration workspace (`ks0man-migration`): `study/arch_plan.json` under
`blocking_questions` and `open_questions`, the domain argument under `domain_decision`, and the
anti-rot rules in `study/arch_ops.json` under `anti_rot`. That workspace is **not** published, and
must not be: it holds working notes, credentials and the machine's own paths, none of which are
the Society's record and none of which belong in a public image.

---

## Provenance

Club history, governance text and archive metadata belong to the Manhattan Area Amateur Radio
Society. The code was written for the club's use; the club decides what licence, if any, it
carries. Material by other authors that the old site carried — articles, charts, a video — is
republished as it was there, by the Society's decision of 16 October 2026; whether each piece may
be republished remains the club's question to answer.
