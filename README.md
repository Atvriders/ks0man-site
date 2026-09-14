# ks0man-site — a runnable demonstration of the MAARS rebuild

This repository builds one Docker image containing WordPress, the `maars-core` plugin, the
`maars` block theme, and a WebGL2 propagation scene. You start it with `docker compose up -d`
and open it in a browser on your own machine.

**What it is.** A working demonstration of how the rebuilt MAARS site would behave: the content
model (publications, people, facilities), the block theme, the palette taken from the club's own
1997 stylesheet, and — the point of the whole exercise — the machinery that makes staleness
visible instead of hiding it.

**What it is not.**

| It is not | Because |
|---|---|
| The live site | ks0man.com is the 1997 hand-written site and is still live. ks0man.org is an empty WordPress install with a sample page. This touches neither. |
| A finished site | It ships a demonstration slice of content, not the club's 27 years of documents. See [What ships, and what does not](#what-ships-and-what-does-not). |
| A hosting migration | Nothing here deploys anywhere. It runs on your laptop, on port 8080, and stops when you stop it. |
| A decision | Nine questions still block a real launch and none of them are technical. See [Open questions](#open-questions-that-still-block-a-launch). |

---

## Status

Read this before you trust anything below it.

| Thing | State | How that was established |
|---|---|---|
| The WebGL propagation scene actually draws | **Verified** | `pytest tests/test_webgl.py` loads the scene in headless Chromium on SwiftShader (software rasteriser, no GPU), waits for the canvas to report `data-maars-ready="1"`, then **reads the pixels back**: it fails if the image is flat, and fails again if switching bands does not change the image. PNGs are written to `tests/out/` — look at them, do not take the exit code's word for it. |
| Every PHP file is syntactically valid | **Verified** | `php -l` on each file, run as part of `tests/test_static.py`. Checked against PHP 8.1; the image runs PHP 8.3. |
| No personal data anywhere in the repository | **Verified** | `tests/test_static.py` greps the whole tree for address, phone and e-mail patterns and fails the run. It is a gate, not a guideline. |
| File map, `theme.json`, `content/seed.json`, `docker-compose.yml` all present and parseable | **Verified** | `tests/test_static.py`. |
| **The site running in a real WordPress** | **NOT verified** | There is no Docker daemon in the environment this was built in. Not one line of this has ever booted against a live WordPress, a live MariaDB, or a live browser session on the real site. CI builds and publishes the image; **your first `docker compose up` is the first real test.** |
| Content completeness, link integrity, redirects | **NOT verified** | Out of scope for a demonstration. Those belong to the migration proper. |

If the first boot fails, that is expected information, not a surprise. File it.

---

## Quick start

You need Docker with the Compose plugin. Nothing else — no PHP, no Node, no Composer, no npm.

```
git clone https://github.com/Atvriders/ks0man-site.git
cd ks0man-site
docker compose up -d
```

Then open **http://localhost:8080**.

The stack serves itself on whatever address you actually used. The site URL is auto-detected from the browser's request, so publishing on a LAN address or a different port works with no edit: `http://192.0.2.10:3039` is as valid as `http://localhost:8080`. Pin it by setting `MAARS_SITE_URL` in `docker-compose.yml` only if you are behind a proxy that rewrites the `Host` header.


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
configuration. Sign in at **http://localhost:8080/wp-login.php** as `maars_admin` with the
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

So the design assumes the hand-off will fail again, and arranges for that failure to be visible
rather than silent. Three mechanisms, all of them in this demonstration:

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

One thing this demonstration deliberately does *not* do: it does not e-mail anybody. In the real
deployment the overdue digest goes to the Society e-mail reflector, because Article III of the
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

### What ships

- Club history and governance facts: founding on 7 July 1976 at a meeting called to order at
  7:40 P.M.; the members' vote to be a **Society**, not a Club; the constitution and SOP of
  11 December 2021, including Article III (the e-mail reflector is the official organ) and
  Article VII ("a quorum consists of the members present"); the meeting rule.
- The **shape** of the archive — counts, date ranges, gaps — without the documents themselves:

  | Category | Count | Range |
  |---|---:|---|
  | Newsletters and minutes | 209 | 1998–2024 |
  | Treasurer's reports | 49 | monthly |
  | Year-end reports | 6 | annual |
  | Memorials | 27 | — |
  | Member articles | 36 | — |
  | Images | 105 | — |

  2012 produced nothing at all. The newest content of any kind is 16 January 2024.

- Technical facts about the repeater and the nets, every one of them graded `unverified`.
- Officer references at **role level only** — President, Vice-President, Secretary, Treasurer,
  Repeater Trustee, Webmaster. No names attached to contact details.

### What does not ship, and why

None of the following is in the image, in this repository, or in `content/seed.json`:

- 28 personal e-mail addresses
- 7 phone numbers
- One private home address
- 17 storm-spotter observer posts with street addresses
- The 41-name member roster
- The 27 obituaries
- The scanned documents and photographs themselves

The reason is short. **The image is public on ghcr.io.** Anything baked into a public image is
public permanently: it is pulled, cached, mirrored and layered by strangers, and there is no
recall. A club cannot un-publish a Docker layer.

The second reason is that the club has not decided. Whether the obituaries may be republished in
full, whether the roster is public or members-only, whether the observer posts keep their address
column — those are open questions with real people behind them, and one of them may need county
emergency-management sign-off. A decision made by default is still a decision, and defaulting to
publication is the wrong default. Consent has not been given, so the answer is no.

This is enforced, not merely intended: `tests/test_static.py` scans the entire repository for those
patterns and fails. If you add a real e-mail address to a fixture, the build stops.

---

## Generating the full content locally

The club has all of the withheld material already, in its own mirror of the old site. The tool that
turns it into seed content runs on the club's machine and its output never leaves that machine.

```
python3 tools/build_content.py --help
```

It reads the club's local mirror of ks0man.com and writes a seed JSON in the same shape as
`content/seed.json`. Then:

1. Write it somewhere outside this repository, or to a filename that `.gitignore` covers. Do not
   commit it. Do not add it to a branch "temporarily".
2. Point the running container at it instead of the shipped seed. The least-effort route is a
   `docker-compose.override.yml` that bind-mounts your file over the seed the image ships; the
   `Dockerfile` shows where that seed lands inside the container.
3. `docker compose down -v && docker compose up -d` so the seed runs again on a clean database.
4. **Never push an image built from a real seed**, and never tag one with the public image name.
   The public image is `ghcr.io/atvriders/ks0man-site` and it must only ever be built by CI from
   what is in this repository.

The same rule applies to the mirror itself: it stays on the club's machine.

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

CI runs both suites and then builds and publishes the image. The workflow is
`.github/workflows/build.yml`.

---

## Project layout

| Path | What it is |
|---|---|
| `docker-compose.yml` | The site image plus `mariadb:11.4`; publishes the site on port 8080. |
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
| `tools/build_content.py` | Mirror to seed JSON. Runs on the club's machine only. |
| `tools/seed.php` | Turns a seed JSON into WordPress posts, terms and meta at first boot. |
| `content/seed.json` | The demonstration content. Public-safe by construction. |
| `tests/` | The two suites above. |

No Composer, no npm, no build step, no external JavaScript. That is deliberate: the club has to be
able to open a file and read it in ten years, on whatever machine it has then.

---

## Open questions that still block a launch

None of these are engineering problems, and none of them can be answered from the archive. The
demonstration is arranged so that the answers drop in without a redesign — but until they are
answered, no real site should go up.

| # | Question | Why it blocks |
|---|---|---|
| 1 | Who is the registrant of record for ks0man.com and ks0man.org, at which registrar, expiring when — and can two current officers log in this week? | The club has already lost four of its own domains. If the .com registration is unrecoverable, the launch plan inverts. Everything downstream waits on this. |
| 2 | Is ks0man.com the canonical address, with ks0man.org redirecting to it permanently? | 27 years of references are printed on paper, read aloud on nets and listed in third-party directories. A 301 fixes a browser request; it does not fix a filing cabinet. |
| 3 | Who provisioned the WordPress at ks0man.org, and who are the two named people who hold the site afterwards — a Webmaster and a Secretary? | If a second person cannot be named, the thing being built has to change shape. |
| 4 | Is the club still meeting — and is it the first or the second Friday? | The constitution and the old homepage say second. The January 2024 minutes say the Senior Center was reserved for the first. `maars_next_meeting()` implements the constitution; if the practice differs, the rule is wrong. |
| 5 | Who are the officers, by role, for 2024, 2025 and now? | The newest slate on record is 2023–24, and not one chair of the seven standing committees is named anywhere in the corpus. |
| 6 | Privacy, four answers: the 27 obituaries in full? The roster public, members-only, or not at all? The 17 observer posts as-is, address-free, or members-only? Per-person pages for living members? | This is the largest reputational risk in the project, and it is why the content above is missing. Nothing in these four categories imports until the answer is in writing. |
| 7 | Financial disclosure: the 6 year-end reports public and the 49 monthly reports members-only — or all public, or all members-only? | Hiding the treasury looks like something worth hiding; a named treasurer beside a running balance accurate to the cent is a ready-made pretext. Both directions have a cost. |
| 8 | May the personal officer addresses become role aliases, and the historical ones be stripped from the republished archive? Who receives each alias? | Determines whether the archive can be republished at all in its current form. |
| 9 | The repeater, as of today: where is it, at what power, into what antenna at what height, which controller, whose trustee licence, what coverage? Is the UHF repeater on the air? Is the EchoLink node live? | The most-consulted fact on the site is currently in three contradictory states across three pages. Until it is answered, the repeater card stays `unverified` — which is correct, but it is not a destination. |

Two more that are not blocking but should be recorded: who holds the physical minute book from 1976
(the largest recoverable gap — 1977 and 1979–1997 are otherwise blank), and whether anything
happened on 7 July 2026, the club's 50th anniversary, that should be written down.

**Full brief.** The reasoning behind each of these, with citations to the specific documents, is in
the private migration workspace (`ks0man-migration`): `study/arch_plan.json` under
`blocking_questions` and `open_questions`, the domain argument under `domain_decision`, and the
anti-rot rules in `study/arch_ops.json` under `anti_rot`. That workspace is **not** published, and
must not be: it contains the full mirror, and the mirror contains every piece of personal data this
repository refuses to carry.

---

## Provenance

Club history, governance text and archive metadata belong to the Manhattan Area Amateur Radio
Society. The code is a demonstration written for the club's use; the club decides what licence, if
any, it carries. Third-party reprints from the old site are not included here: only two of the
seventeen have a clean permission answer, and clearing the rest is somebody's real job before any
of them is republished.
