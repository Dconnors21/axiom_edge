# Product

## Register

product

## Users

Sharp sports bettors and prospective acquirers of the product.

- **Sharp bettors** open AXIOM Edge daily to find where the model disagrees with the
  market. Their context is time-sensitive and pre-decision: a slate is live, lines move,
  and they want the calibrated read, the edge, and the EV per side before they act. They
  are numerate and skeptical; they trust a product that shows its math and distrust one
  that hypes.
- **Acquirers / evaluators** assess whether this is a credible, well-built quant instrument.
  Their job is to judge rigor and honesty at a glance: is the calibration real, are the
  numbers stated plainly, does the craft signal a serious team.

The primary task on any screen is the same: read the model's output, understand the edge,
size the bet responsibly. Never "sell the user a pick."

## Product Purpose

AXIOM Edge is an AI sports-betting analytics product. It runs trained models (NBA at
0.7147 ROC-AUC via XGBoost + CalibratedClassifierCV; MLB at baseline AUC ~0.51; NHL) and
surfaces, per game, a calibrated win probability, the model's edge versus the market, and
expected value per side, plus stake sizing (Kelly fraction / flat unit) and honest model
performance tracking.

It exists to turn a private modeling edge into a daily, trustworthy decision instrument.
Success looks like: a sharp bettor checks it every slate and trusts the number on the
hundredth use, and an evaluator concludes a high-end technology firm could have built it.

The models are fixed. The product is the presentation layer — a serving layer over the ML,
never a retraining of it.

## Brand Personality

**Earned certainty.** Declarative, exact, unhurried. The name means a self-evident truth;
the posture is showing the math, presenting real numbers honestly, and never overselling.

Three words: **precise, honest, confident.**

- Voice: short sentences, real numbers, no hype. Banned verbs: unleash, revolutionize,
  next-gen, and any manufactured urgency ("BET NOW," countdowns, FOMO).
- Tagline appears once, never plastered: "Not a pick. An axiom. ∎"
- Intellectual honesty is the brand. The MLB model is at ~0.51 and the product says so
  plainly rather than dressing it up. Honesty is the credibility moat.
- Emotional goal: the calm confidence of a quant fund's internal terminal, not the
  adrenaline of a casino.

## Anti-references

- **A casino / sportsbook app.** No neon, no green-felt, no slot-machine motion, no
  coercive "bet now" urgency.
- **Generic SaaS template.** No AI-purple/blue gradients, no hero eyebrow chips, no
  rounded-square icon tile above every heading, no spinner-driven loading.
- **Hype fintech.** No vanity precision, no rounded-up fake metrics, no growth-hacking copy.
- The reference class to live up to instead: Linear, Vercel, Ramp, Mercury, and a quant
  fund's internal terminal. The data is the hero.

## Design Principles

1. **Show the math.** Every number is real and sourced. Honesty over polish — when the
   model is weak (MLB ~0.51), state it plainly. Credibility is the product.
2. **Correct on the hundredth use, not impressive in one screenshot.** Optimize for the
   daily operator, not the demo. When the two conflict, the operator wins.
3. **The data is the hero.** Chrome recedes; numbers, hairlines, and negative space carry
   the design. No decoration on functional surfaces.
4. **Restraint is the flex.** One accent, one type system, one charting language, one icon
   family, held identically across every page. Consistency reads as rigor.
5. **Responsible by default.** Informational, never coercive. Conservative defaults, quiet
   responsible-gambling affordances, user control over anything that pushes a decision.

## Accessibility & Inclusion

- Target **WCAG 2.1 AA**: verified text/background contrast on every surface, including
  numbers on the dark shell and accent-on-surface.
- Honor `prefers-reduced-motion`: reduce anything above motion intensity 3 to opacity/color
  only, never lose comprehension; functional charts stay static.
- Color never carries meaning alone — sign (+/−), labels, and position back up the
  pos/neg color semantics for color-blind users.
- Tabular numerics and right-aligned numeric columns aid scanning for all users.
