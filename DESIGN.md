# ks0man-site — visual direction, revision 3: "Tuned"

Live at https://ks0man.waterburp.com/. Audience: licensed amateurs **aged 30–90**,
a professional club expecting something modern. Owner's words, which win over
everything below: **new idea for the header, modern, soft, smooth.**

## The idea
The analogue dial is gone. Every ham now reads a **waterfall** — the scrolling
spectrum on an IC-7300, a Flex, an RTL-SDR dongle. It is the one image that says
"radio" to a 30-year-old and a 90-year-old alike, and it is soft and smooth by
its nature: a continuous heat map with no hard edges.

**So the masthead becomes a receiver.** A slim live spectrum-and-waterfall band
across the top, tuned to the club's own 147.255 MHz repeater, with the identity
resting in it. Not a banner image, not a logo lockup — an instrument.

## Header spec (replaces the current text masthead entirely)
- Canvas strip, 150–190px tall, full-bleed, soft-faded at both vertical edges so
  it dissolves into the page rather than ending in a line.
- A calm noise floor with a marked carrier at **147.255**, drifting slowly.
  Ambient, never busy: one frame every ~80ms, not 60fps.
- `KSØMAN` sits over it in the display face, with `Manhattan Area Amateur Radio
  Society` beneath in the body face. No interpuncts.
- Decorative only: `aria-hidden`, the identity is real text. Under
  `prefers-reduced-motion` it draws ONE static frame.
- If canvas is unavailable it falls back to a soft navy gradient. Never blank,
  never an error.
- Navigation sits below the band on its own quiet row, not inside it.

## Soft and smooth, executed deliberately
The owner asked for soft and smooth. The risk is the generic card kit: identical
rounded boxes, one radius everywhere, the same grey shadow under each. Avoid it
by varying by ROLE:
- **Radius scale**: 16px major surfaces · 10px controls and inputs · 999px pills
  and chips · 0 on data tables. Never one value everywhere.
- **Shadows are navy-tinted, never grey**, and only on things genuinely raised:
  `0 1px 2px rgba(10,10,60,.05), 0 10px 30px rgba(10,10,60,.07)`. A table is not
  raised. A row is not raised.
- **Motion**: 200ms `cubic-bezier(.2,.7,.3,1)` on user-triggered changes only.
  The waterfall is the single ambient motion on the page. No scroll-triggered
  fade-ups, no hover lift on every block.
- **Gradients carry meaning or they do not appear.** The waterfall is a real
  signal-strength gradient. Decorative gradient washes are not allowed.

## Palette — softened, same identity
| token | hex | role |
|---|---|---|
| `--navy` | `#00008C` | the brand anchor, links, headings |
| `--navy-soft` | `#3B3BA8` | hover, secondary emphasis |
| `--magenta` | `#990066` | the archive, and only the archive |
| `--ink` | `#191933` | body text |
| `--paper` | `#FFFFFF` | raised surfaces |
| `--ground` | `#F4F5FA` | page ground, cool, softened off-white |
| `--haze` | `#E8EAF6` | quiet fills, the old lavender, calmed |
| `--rust` | `#8F2C00` | stale only |
| `--rule` | `#DDE0EE` | hairlines |
Every pair must still clear 4.5:1 (3.0 at ≥24px). Verify, do not assume.

## Type — unchanged, it works
Platypi display · Manrope body · Fira Code data, self-hosted by the parent theme.
Fira Code's zero is natively slashed, so **KSØMAN** renders the way a ham writes
it. The data face is for callsigns, frequencies, tones, offsets, counts and
money — never prose.

## Browser icon (new)
A navy rounded tile with three white arcs radiating from a point: a transmitting
antenna, legible at 16px. Ship `favicon.svg`, `favicon.ico` (16/32/48),
`icon-192.png`, `icon-512.png`, `apple-touch-icon.png` (180), and a web manifest.
Registered from the theme, not hand-pasted into a template.

## Keep, do not touch
- The skywave scene. It stays the page's one *large* bold moment; the waterfall
  is ambient chrome, not a competitor.
- Facts carry their age. "Last checked 12 January 2024 — 977 days ago."
- The honest voice. "2012 produced nothing at all" stays exactly as written —
  though it is now counted rather than typed, so it can say 2012 and 2014, or
  nothing at all, as the record changes under it.
- Everything revision 2 fixed: no caps eyebrows, no interpuncts, no nested boxes,
  no monospace on prose, counts beside their terms.

## The year table (/archive/gaps/, new)
The page that says what the record does not hold needed a shape, not another
list of sentences. It is a data table and follows the archive log's rule rather
than the card kit's: square corners, hairline rules, no shadow, figures in Fira
Code with tabular lining.

One piece of drawing, and it carries information rather than mood: behind each
count sits a bar ruled to that year's share of the fullest year (`--maars-graph`
#D9DCF3, the only fill on the site that encodes a quantity). A thin year is
visible as a shape before it is read as a figure. A year with nothing in it has
no bar to draw, which is the point of the page, so it is marked instead — the
record's magenta down the edge of the row and the word "none" where the count
would be, measured 7.57:1 on the page ground. Magenta appears nowhere else here.

Two columns, not three: the year is the link, because "read the year" repeated
down twenty-seven rows is the placeholder sentence this project already took out
of the archive log once.

## Accessibility floor — unchanged, non-negotiable
18px body (20px desktop) · line-height 1.65 · 48px targets · 3px navy focus ring
at 2px offset · no weight under 400 · no horizontal overflow at 390px ·
`prefers-reduced-motion` honoured everywhere including the waterfall.
