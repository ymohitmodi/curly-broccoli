# Playbook: PPC Optimization

The rules engine already generated the mechanical moves (negatives, bid steps,
harvests). Your job is the strategy layer the rules can't see.

## Campaign doctrine
- Structure: 1 auto (discovery, low bids) → harvest winners into manual exact
  (own them) + broad (expand). Never let auto and exact bid against each other
  on the same term: harvested terms get negatived in auto.
- Launch phase: target ACOS may exceed break-even deliberately — you are buying
  ranking and reviews. Honor the genome's ad_target_acos as the CURRENT phase target.
- Profit phase: ACOS ceiling = margin. Terms above it get bid-decayed, not paused
  outright (rank memory matters).

## What to look for beyond the rules
- **Cannibalization**: auto spending on terms exact already owns → negative in auto.
- **Ranking plays**: a mid-tier term with strong conversion but page-2 organic rank
  deserves an aggressive exact push even at high ACOS — organic rank pays it back.
- **Search-term mismatch**: high spend terms that reveal the LISTING is attracting
  the wrong intent → flag a listing fix, not just a negative.
- **Budget starvation**: campaigns capping out before 6pm with ACOS under target
  are leaving profit on the table.
- **Dayparting/placement**: top-of-search multipliers only where conversion proves it.

## Discipline
- Change bids in steps (the genome's ad_bid_step), never wholesale rewrites.
- Minimum data before judging a term: ~10 clicks (negatives), ~3 orders (winners).
- Every recommendation must cite the numbers that justify it.
