# NOEMA Visual DNA — the Brand Guardian's checklist

Source of truth: the live landing (V6) and the Instagram @noemalearn. This
page does not redesign anything; it condenses `docs/brand-os.md` and
`docs/motion-system.md` into what a reviewer checks before a piece ships.
Every new piece must look like the next frame of the same film.

## The world

Knowledge is a territory; NOEMA is the cobalt sky over it; **Mino** is the
small figure crossing it, seen from behind or in profile. One world, one
place: snow-crested ridges, green flanks, a worn track, pines, one tree, a
small house with an ember roof, haze. Plus its **bleach**: the same frame
burnt to bone, only the shadows left in ink.

## Palette (exact)

| Token | Hex | Use |
|---|---|---|
| cobalt | `#1D3FD1` | Sky, colour field, primary action on bone |
| cobalt-deep | `#1733AD` | Hover, accent text on bone |
| ultramarine | `#12247A` | Depth, dark grounds |
| ink | `#0B1440` | All type on light ground (blue-black, never grey) |
| bone | `#F6F2EA` | Product ground, editorial statements, Mino's body |
| ember | `#E4471F` | The one warm signal: one button, one word, the hoodie |

Earth green, peach light and snow live only inside the landscapes.

## Type

- Display: **Inter** 500–600, tracking −0.03 to −0.045 em, monumental, one idea per line.
- Wordmark: **Newsreader**, only as the masthead.
- Metadata: **JetBrains Mono** caps, 11–12 px, letter-spaced. Never a paragraph.
- One accent word per composition, in ember or cobalt. Never two.

## Composition

One monumental image as the protagonist · the sky as negative space · one
line of type · one figure, small against a large land · tiny mono metadata in
a corner · grain over the image (never on text) · no card grids · radical
reduction.

## Mino

Locked (owner decision, 2026-09-25). The drop-shaped body, the single curl
leaning right, large glossy eyes with two highlights, bone mitts, ember
hoodie with the three-lobed mark, stubby dark feet. In landscapes: from
behind or in profile, a few percent of the frame, with his own shadow. In the
interface: the SVG rig. Never a new pose sheet, never a 3D face, never a
sticker, never a second mascot.

## Motion

Slow camera push (transform only), environment barely moving (grass, haze,
water), Mino breathing and shifting weight, type revealed once (14 px rise,
560 ms, `cubic-bezier(0.2, 0, 0, 1)`). Nothing glows, pulses or sparkles.

## Paid and social: what may change

Ads may be faster and louder in **hook, copy and pace**: an opening question
on frame one, a cut every 1–2 s, product footage of a real lesson, captions,
a direct CTA. They may not change the **palette, type, Mino, the world or the
grain**. A viewer who knows the Instagram must recognise the ad as NOEMA with
the logo covered.

## Rejection list (automatic)

Purple-to-blue gradients · neon · cyberpunk · glassmorphism · glow · robots ·
brains and neural nets · stock photos or people · Duolingo-style mascot
antics, confetti, XP, streak guilt · generic AI SaaS dashboards as hero art ·
a second display family · buzzwords (AI-powered, unlock, revolutionise,
supercharge, seamless) · invented numbers, testimonials or logos · medical
claims about ADHD.

## Review procedure

1. Cover the logo: does it still read as NOEMA? If not, reject.
2. Put it beside the last three @noemalearn posts: same campaign? If not, reject.
3. Check palette by sampling: any dominant colour off the table above → reject.
4. Check type: Inter + mono only (Newsreader only as the wordmark).
5. Check Mino against `public/brand/mino/icon-512.png`.
6. Check copy against the banned list and the "nothing invented" rule.
7. Log the verdict (APPROVED / CHANGES / REJECTED, one line why) in the
   piece's folder. Two CHANGES in a row on the same drift → flag "visual drift"
   in the daily report.
