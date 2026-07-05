# Playbook: Inventory & Cash-Flow Planning

Profit is an opinion; cash is a fact. Your job is to make sure the factory
never grows itself into a cash crunch and never bleeds avoidable fees.

## Doctrine
- Every PO must show its full cash timeline BEFORE approval: deposit, balance,
  live day, first payout, full recovery. If peak working capital exceeds the
  launch budget, the PO is too big — cut units, not the ad reserve.
- The ad/promo reserve (25% of launch budget) is untouchable by POs. A launch
  with inventory but no ad budget is a silent failure.
- Two-sided inventory target: stay ABOVE the low-inventory-fee threshold
  (35 days) and BELOW max cover (storage fees, capital lockup). The genome's
  inventory_cover_days is the current set point — honor it.
- Reorder point = lead time (production + freight + check-in) + threshold.
  With ~82-day leads, you are always ordering ~3 months blind: use conservative
  velocity (P25 of recent weeks, not the best week).
- Q4 rule: inventory landing Oct-Dec pays ~3× storage — either sell through
  fast with ads or delay the shipment; never park slow stock in peak season.

## Sequencing risks to always check
- Two launches inside one cash cycle without ledger headroom
- A reorder due while a new launch's balance payment is pending
- Velocity spikes (a viral week) tricking the reorder math — check the median
- Tariff/freight changes since the last PO — re-run economics, don't reuse
