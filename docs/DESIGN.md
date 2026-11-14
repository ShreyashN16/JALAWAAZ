# Design system

The interface is for three very different people: a villager on a basic smartphone who may read Marathi
or Hindi slowly, an engineer on a phone in the field, and a district officer on a laptop. It is also
filmed for demo videos. The design choices follow from that.

## Principles

1. **The loop is the product.** The overview page opens with the actual report → fix → verification loop,
   with live counts, not a marketing banner. The false-closure rate leads every dashboard view.
2. **One ornament: the ripple.** Jal Awaaz is voice plus water, and a ripple is both a sound wave and a
   drop in water. It animates the call screen when someone speaks and marks map pins that need attention.
   Everything else is quiet: borders instead of shadows, no gradients, no decorative icons.
3. **Every number carries its n and its source.** Synthetic, simulated and approximate things are labelled
   where they appear, never only in a footnote.
4. **Villagers see their language first.** The phone is in Marathi, Hindi or Hinglish, with large type,
   large targets and an English gloss only where a demo audience needs it.
5. **Say what a button does.** "Report fix and request the call", not "Submit". Errors say what happened
   and what to do.

## Colour

Named after the materials of village water: lime-wash walls tinted with neel (indigo), and the kumkum,
haldi and leaf green that already mean "attention", "waiting" and "well" to most users.

| Token | Hex | Use |
|---|---|---|
| `--ink` (neel) | `#1D2B53` | text, top bar, primary dark surfaces |
| `--paper` (chuna) | `#EEF3F6` | page background, blue-tinted lime-wash |
| `--teal` (jal) | `#0A7E8C` | actions, links, the assistant speaking |
| `--red` (kumkum) | `#C62D42` | open and reopened tickets, P1, errors |
| `--haldi` | `#D99A06` | awaiting the caller's confirmation, P2 |
| `--green` (leaf) | `#2F8F5B` | verified by the caller |
| `--slate` | `#66738A` | no answer, muted |

Ticket states always use the same colours on the map, chips, timeline and charts. Colour is never the
only signal: chips have words, pins have numbers and names.

## Type

- **Bahnschrift** (Windows' DIN-style face; falls back to DIN Alternate, Segoe UI) for headings, numbers,
  ticket references and priority badges. It reads like infrastructure signage and has even, tabular figures.
- **Segoe UI** for English text and **Nirmala UI** for Devanagari (both ship with Windows; Noto Sans
  Devanagari elsewhere). No web fonts are downloaded, so the app works offline.
- Scale: 12 · 13.5 · 15 · 17 · 20 · 24 · 31 · 40 px. Devanagari body text on the phone is 15–21 px.
- No all-caps labels. Sentence case everywhere.

## Layout

- **Overview**: headline and the loop side by side; three doors (phone, engineer, dashboard) separated by
  rules, not cards; the "what is real" table; the five acts as a numbered sequence (it is one).
- **Phone**: a device frame on desktop with a "behind the call" rail (conversation with the model used for
  each turn, fields as they are understood, timings) so a viewer can follow; full screen on a phone.
- **Engineer**: one column, phone first. Job cards with a priority rail on the left, the reason for the
  priority in a box, the SLA as a pill, and buttons at least 52 px tall.
- **Dashboard**: figure strip (one bordered strip, the lead figure inverted), map and queue side by side,
  then trends, mix and attention, then activity and SMS. A drawer holds the full record of a ticket.
- Radius scales with hierarchy: 4 px chips, 6 px panels, 10 px job cards, 22 px sheets, 46 px the phone.

## Components (`web/assets/app.css`)

Buttons (`.btn`, `.btn-quiet`, `.btn-haldi`, `.btn-danger`, sizes `-sm`/`-lg`), switches, segmented
controls, state chips (`.chip.st-<STATE>`), priority badges (`.prio-1..3`), synthetic and simulated tags,
provider pills, figure strip, tables, bars, timeline, drawer, bottom sheet, toasts, skeletons, empty states,
the ripple, and the map (`map.js`: village dots, ticket pins, popovers, offline basemap).

## Accessibility

Visible focus ring on every control; keyboard-operable map (arrows, +/-), drawer (Escape) and talk button
(Space/Enter); `aria-live` on captions and toasts; `prefers-reduced-motion` turns off the ripples and
transitions; contrast of text on every token pair meets WCAG AA.
