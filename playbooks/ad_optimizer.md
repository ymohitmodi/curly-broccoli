# Playbook: PPC Optimization

The rules engine already did the arithmetic — every bid suggestion on the
sheet shows its own math (target CPC = target ACOS × AOV × smoothed CVR;
negatives at 95% statistical confidence). Do NOT second-guess the arithmetic.
Your job is the layer formulas cannot see.

## Campaign doctrine
- Structure: 1 auto (discovery, conservative bids) → harvest converting terms
  into manual EXACT (own them) and PHRASE (expand them). Every harvested term
  is immediately negative-exacted in auto — the same term must never run in
  two campaigns (self-auction).
- Negation hierarchy: negative-EXACT kills one query; negative-PHRASE kills a
  family. Use phrase negatives only for whole wrong intents ("jar", "refill",
  "replacement") — never to prune a family you partly want.
- Launch phase: the genome's launch multiplier deliberately buys velocity above
  break-even. Profit phase: ACOS ceiling = net margin; terms above it decay via
  the target-CPC formula, not pauses (rank memory outlasts a bad week).

## What to look for beyond the formulas
- **Cannibalization**: auto or broad spending on terms exact already owns.
  Symptom: same search term rows in two campaigns. Action: negative in the
  discovery campaign, never in exact.
- **Ranking plays**: a term with CVR ≥ category norm but organic rank page 2 —
  overbid it ON PURPOSE (up to 2× formula CPC) for 2–3 weeks; organic rank
  repays the premium. Flag it as an investment with an end date, not a bid fix.
- **Intent mismatch**: high spend + high clicks + CVR < 5% while the listing
  converts elsewhere = the TERM is wrong, not the bid ("fridge organizer"
  shoppers wanting bins, not racks). Recommend a listing/targeting fix, and
  negative the term even if it has occasional orders.
- **Budget starvation**: campaign capped before day's end at ACOS under target
  → raising budget is free profit; the sheet's +20% steps are floors, not
  ceilings, when the pattern repeats 3+ days.
- **Placement leverage**: if top-of-search shows CVR ≥ 1.5× rest-of-search,
  shift spend there via placement multiplier instead of raising the base bid
  (raises pay everywhere; multipliers pay only where it converts).
- **Dayparting**: only with ≥2 weeks of hourly data and a consistent dead
  window ≥ 6h; otherwise it's noise-chasing.

## Discipline
- Minimum evidence: never judge a term under 5 clicks; never call a winner
  under 2 orders; the negation threshold is computed, not vibes.
- Every extra_action must cite the row numbers that justify it and state the
  expected effect in dollars or rank, e.g. "shifts ~$40/wk from 129% ACOS term
  to 20% ACOS term ≈ +$30/wk profit".
- One structural change per campaign per cycle — PPC needs attribution, and
  five simultaneous changes destroy it.
