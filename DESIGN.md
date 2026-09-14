# ks0man-site — visual direction "Second Friday" (LOCKED)

Audience: licensed amateurs, **ages 30–90**, shown to a professional club.
Goal: modern and professional. Credible, not fashionable. Legible before clever.

## The idea
Amateur radio is a **record-keeping culture**. Every contact is logged: date, time
in UTC, callsign, frequency, mode. This club's 48-year archive — 209 newsletters,
49 treasurer's reports, 27 Silent Keys — is a logbook. So the site is built as a
station log: a short panel of what is true **now**, each fact carrying when it was
last checked, and beneath it the **record**.

## Signature: the log line
One recurring row, in real logbook conventions — fixed columns, monospaced,
tabular figures, slashed zeros, hairline rule between entries. Used for the
archive index, the net schedule, the officer register and the repeater facts.
It is not decoration: it encodes that this club keeps records. Spend the
boldness here and keep everything else quiet.

## Colour (all ratios computed, not estimated)
| token | hex | role | contrast |
|---|---|---|---|
| `--maars-navy` | `#00008C` | now / primary / links | 15.23:1 on paper (AAA) |
| `--maars-magenta` | `#990066` | the record / archive | 8.25:1 on paper (AAA) |
| `--maars-ink` | `#14142B` | dark surfaces, body text | 17.4:1 on paper |
| `--maars-paper` | `#FFFFFF` | cards, panels | — |
| `--maars-ground` | `#F6F6FB` | page ground, cool, biased to navy | — |
| `--maars-lavender` | `#DBDBFB` | standing-fact panel | navy on it = 11.27:1 |
| `--maars-rust` | `#8F2C00` | stale / unverified | ΔE76 62.6 from magenta |
| `--maars-rule` | `#D7D7E4` | hairlines | — |

Navy = now. Magenta = the record. Never swap them.
Dark surfaces: headings inherit the surface colour, links go lavender. (Fixed bug.)

## Type — all self-hosted, already in the image, zero third-party requests
VERIFIED by rendering, not assumed. The migration study claimed Literata and
Fira Sans; **both are wrong**. Literata 404s. What Twenty Twenty-Five actually
ships is Manrope, Fira Code, Platypi, Vollkorn, Ysabeau Office, Roboto Slab, Beiruti.

| role | face | why |
|---|---|---|
| display | **Platypi** | contemporary serif with real character; professional without being stuffy |
| body | **Manrope** | geometric sans, wide apertures, excellent at 18px for older readers |
| data | **Fira Code** | **its zero is natively slashed** — exactly how a ham writes KSØMAN. Verified by render. Manrope's is not, so callsigns and frequencies must be Fira Code. |

Callsigns, frequencies, dates, dollar amounts, tones and offsets ALWAYS render in
the data face with `font-variant-numeric: tabular-nums`.

## Accessibility floor — non-negotiable, this audience is 30 to 90
- Body text **18px** minimum (not 16), line-height 1.65, measure 66–72ch.
- Every interactive target **≥ 48px**; nav items ≥ 48px tall.
- Focus: 3px solid navy outline with 2px offset, never removed.
- Every text/background pair ≥ 4.5:1 (3.0 for ≥24px). `tests/test_contrast.py` enforces.
- No font weight below 400. No grey-on-grey. No text over photographs.
- Respect `prefers-reduced-motion`; motion is limited to ≤200ms state changes.

## Restraint
One memorable thing: the log line. Everything else is quiet. No gradients, no
drop shadows beyond a 1px hairline, no rounded-corner cards everywhere, no
decorative numbering. Border-radius is 2px, used sparingly.
