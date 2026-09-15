# ks0man-site — visual direction, revision 2

Audience: licensed radio amateurs, **ages 30–90**, shown to a professional club.
Revision 1 shipped and is live. This revision fixes what it got wrong.

## What revision 1 got right — keep all of it
- Navy `#00008C` on white. It is the ink on the club's own bumper sticker and it
  measures 15.23:1. Magenta `#990066` for the archive, navy for now.
- Platypi display / Manrope body / Fira Code data, self-hosted by the parent theme.
- **Fira Code's zero is natively slashed**, so KSØMAN renders the way a ham writes it.
- Facts carry their age. "Last checked 12 January 2024, 977 days ago" is the most
  valuable sentence on the site and the reason it exists.
- The honest voice: "2012 produced nothing at all." Never soften this.

## What revision 1 got wrong — fix all of it

**1. Stop shouting labels.** Tracked-out ALL-CAPS eyebrows are on nearly every
block: STANDING FACTS, NEXT MEETING, MEETING, REPEATER, NET, COMPUTED, SOURCED,
THE RECORD. Delete every one. Where a label earns its place, set it in sentence
case at a smaller size and a quieter colour. "The archive" does not need "THE
RECORD" above it; the heading already says so.

**2. Stop joining things with middle dots.** `MAARS · KSØMAN`,
`Society · Manhattan, Kansas`, `147.255 MHz out · +600 kHz · CTCSS 88.5 Hz`.
Use real punctuation, real words, or real layout. A specification is a list of
labelled values, not a sentence stitched together with interpuncts.

**3. Stop nesting boxes.** The homepage is a tinted panel containing white cards
containing bordered chips — three borders deep before you reach a fact. Separate
rows with a hairline rule, not with a box. At most one bordered container per
screen, and only when it genuinely holds something apart.

**4. The provenance line is furniture, not an alarm.** Today it is a bordered,
coloured chip with a title, a sentence, an internal file path and a date. It
outweighs the fact it describes. Reduce it to ONE quiet line under the value:
  `Last checked 12 January 2024 — 977 days ago.`
Colour it only when genuinely stale, and never show an internal mirror path to a
club member. The word carries the meaning; the colour only reinforces it.

**5. Restrict the data face.** Fira Code is for callsigns, frequencies, tones,
offsets, grid squares, counts and money. It is NOT for prose dates. "Friday,
October 9, 2026 at 6:30 P.M." is a sentence and belongs in the body face.

**6. Fix the hierarchy.** The single thing a visitor came for is the next
meeting. It should be the largest, first, and unmistakable. Right now it sits in
a box of equal weight to the row beneath it, and both state the second-Friday
rule, so the page says the same thing twice.

**7. Fix the archive facets.** Counts currently wrap onto their own line, so it
reads "Minutes / (3)". Put the count beside its term. The whole page also sits
left of centre with a large dead gutter; centre the column properly.

**8. Cut the page down.** The homepage is 6,363px tall for a small amount of
information. Losing the nested boxes and the repeated explanation should roughly
halve it. Explain the mechanism once, in one place, not beside every fact.

## Where the boldness goes
One memorable thing: **the skywave scene**. Everything else stays quiet and
disciplined. If an element competes with it, calm the element.

## Voice
Plain, specific, unhurried. Sentence case. No filler, no selling, no exclamation.
State the fact, then say when it was last checked. A 78-year-old reading this on
an iPad in a church basement is the test.

## Accessibility floor — unchanged and non-negotiable
18px body minimum (20px desktop), line-height 1.65, 48px targets, 3px navy
focus ring at 2px offset, no weight under 400, every pair ≥4.5:1 (3.0 at ≥24px),
no horizontal overflow at 390px, `prefers-reduced-motion` honoured.
`tests/test_contrast.py` enforces the contrast floor; run it.
