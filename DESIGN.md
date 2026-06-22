# Design

Visual system for AXIOM Edge. One dark theme, locked across all surfaces. No section
inverts. Pick one of everything and hold it everywhere.

Dials (deliberate overrides of the 8/6/4 baseline, because this is a data product):
- **DESIGN_VARIANCE: 4** — structured and precise. Strong grid, optical alignment, no
  decorative chaos. A quant instrument reads as ordered.
- **MOTION_INTENSITY: 3** — crisp and fast. Motion is feedback and continuity, never
  decoration on functional surfaces.
- **VISUAL_DENSITY: 6** — daily cockpit. Mono numbers, hairlines separate data, no
  card-in-card; data breathes in plain layout.

## Color

Single dark theme. Cool near-black surfaces, never `#000`. Off-white text, never `#fff`.
ONE signal accent (gold), solid, no gradients. Semantic pos/neg are reserved and never
reused as the brand accent.

```css
:root {
  /* Surfaces — cool near-black */
  --bg:               #0A0B0D;
  --surface:          #101113;
  --surface-elevated: #16181B;
  --surface-overlay:  #1C1F23;  /* modals, ⌘K palette */
  --border:           rgba(255,255,255,0.08);
  --border-strong:    rgba(255,255,255,0.14);

  /* Text — off-white */
  --text-primary:   #F4F5F6;
  --text-secondary: #A1A4AB;
  --text-tertiary:  #6B6F76;

  /* Accent — ONE signal color = AXIOM's "edge". LOCKED: signal gold. */
  --accent:       #E9B24A;
  --accent-hover: #F2BD5C;

  /* Semantics — reserved, never the brand accent */
  --pos: #34D399;  /* realized +EV / win  */
  --neg: #F2615C;  /* realized -EV / loss */
}
```

Decision: **signal gold `#E9B24A`** is the accent (the documented electric-blue
alternative `#5B9BFF` is rejected; never mix). Accent marks the active/primary series and
the single most important action on a surface. pos/neg carry sign only.

Discipline: hairline borders and negative space over heavy shadows. When a shadow is used,
tint it to the surface, never pure black. No AI-purple, no neon glow, no gradient text.

## Typography

- **Sans:** Geist (`--font-sans`). Display + UI. Tight tracking on the wordmark.
- **Mono:** Geist Mono (`--font-mono`). Self-hosted via `next/font`; no Google Fonts
  `<link>` in production. Never Inter.

**Numerics rule (non-negotiable):** every odd, probability, EV, ROC-AUC, dollar figure,
and percentage uses `--font-mono` with `font-variant-numeric: tabular-nums`. This is the
single biggest "elevated" tell in a data product — columns align, brand reinforced.

Type scale: one scale held across all pages. Labels in `--text-secondary` (11–12px,
uppercase, letter-spacing ~.06em). Metric values large mono. Body in sans.

## Components

A small, owned library. Every data surface ships **loading (skeleton), empty, and error**
states — not just the happy path.

- **Buttons:** `scale(0.97)` on `:active`, `transition: transform var(--dur-micro)
  var(--ease-out)`. Hover styling gated behind `@media (hover:hover) and (pointer:fine)`.
  WCAG AA contrast. One label per intent across the app.
- **Stat / metric block:** label `--text-secondary`, value large mono tabular, delta in
  `--pos`/`--neg`. No card chrome at this density unless elevation means something; group
  with hairlines and space.
- **Tables (TanStack):** sticky header, row hover, sortable, mono tabular cells,
  right-aligned numbers. ONE divider style between rows, used sparingly. Never `border-t` +
  `border-b` on every row.
- **Tooltips:** 125–200ms, origin-aware (`transform-origin` at trigger), `scale(0.97)`→`1`
  + opacity. Skip delay + animation on subsequent hovers in the same group.
- **Popovers / dropdowns:** scale from trigger (not center). 150–250ms, `--ease-out`.
  Modals stay centered.
- **Command palette (⌘K, `cmdk`):** instant open/close, no animation. Fuzzy nav to any
  page, game, or metric.
- **Skeletons, not spinners:** loaders match the final layout's shape.
- **Icons:** Phosphor (`@phosphor-icons/react`) only. One family, standardized stroke weight.

Enter animations never start from `scale(0)` — start at `scale(0.95)` + `opacity:0`, or
`@starting-style`. Stagger list/card reveals 30–80ms on first page load only. Only ever
animate `transform` and `opacity`.

## Layout

Unified dark surface with elevation tiers: `--surface` → `--surface-elevated` →
`--surface-overlay`. The sidebar may be a subtly different dark; flipping to a light panel
mid-app is forbidden (theme-lock violation in the current Streamlit app — retire it).

- App shell: persistent left sidebar nav (desktop) over the dark shell. Bottom tab bar on
  mobile (Today, Slate, Performance, Bankroll, More).
- Radius: one scale — inputs/buttons 8px (`--radius-sm`), cards 12px (`--radius-md`),
  pills full.
- Density 6: hairlines + space group content; generic card-in-card containers banned.
- Grid: strong, optically aligned. Numbers right-aligned in tabular columns.

## Charts

ONE charting system: **visx**, fed by a single shared `chartTheme` (colors, type, grid,
tooltip, axes) so every chart is a visually identical sibling. TanStack Table for tabular
data (visx scopes itself out of data grids).

- Mono tabular numerals on all axes + tooltips. Muted 1px grid (`--border`). No chartjunk,
  no drop shadows on data.
- `--accent` = active/primary series; `--pos`/`--neg` = sign only; inactive =
  `--text-tertiary`.
- Bespoke signature charts: reliability/calibration curve (with diagonal), ROC curve, EV
  distribution, bankroll equity curve.
- Motion: one subtle mount reveal on first paint (bars grow, line draws via
  stroke-dashoffset), then static. On data update, crossfade values — never replay the
  reveal. Hover/tooltip instant. A functional graph that animates on every interaction is
  worse than one that does not.

## Motion tokens

The built-in CSS easings are too weak; use Emil's curves.

```css
:root {
  --ease-out:    cubic-bezier(0.23, 1, 0.32, 1);
  --ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
  --ease-drawer: cubic-bezier(0.32, 0.72, 0, 1);
  --dur-micro: 140ms;  /* press, hover */
  --dur-sm:    200ms;  /* tooltip, dropdown */
  --dur-md:    260ms;  /* modal, drawer, palette */
}
```

Nothing over ~280ms. Keyboard / ⌘K actions are instant (never animate actions used dozens
of times a day). Honor `prefers-reduced-motion` for everything above intensity 3 (reduce to
opacity/color, keep comprehension).

## Brand mark

Wordmark `AXIOM` in Geist, tight tracking, with the QED tombstone `∎` (filled square that
closes a proof) in the accent. App icon = the `∎` mark on `#0A0B0D`, not the full wordmark;
maskable icon must keep `∎` inside the safe crop. AXIOM Insight is a restrained "AXIOM read"
component (one conviction line + calibrated mono confidence + proof mark), never a cartoon
mascot plastered across the UI.

## Anti-tells (reject on sight)

Inter-by-default · AI-purple/blue gradients · neon glows · pure `#000`/`#fff` · cards in
cards · gray text on colored backgrounds · rounded-square icon tile above headings · hero
eyebrow chips · em-dashes in UI copy · spinners · animating functional graphs on every
interaction · animating keyboard actions · `scale(0)` entrances · fake-precise numbers ·
hype verbs · happy-path-only states.
