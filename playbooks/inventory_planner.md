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

## PO sizing arithmetic (show it, every time)
- Reorder qty = (cover_target_days + lead_days) × daily_velocity − on_hand −
  inbound, where daily_velocity is the CONSERVATIVE estimate: use the median
  of recent weeks, never the best week; a viral spike in the input becomes
  dead stock in the output.
- Stress-test every plan at ±30% velocity: at −30%, when do you cross
  max_days_of_stock (storage bleed)? at +30%, when do you stock out (rank
  loss + low-inventory fee on the way back)? The plan must name both dates.
- A stockout costs more than the lost sales: rank decays within days and
  costs launch-grade PPC to rebuild. Between a mild overstock and a stockout,
  overstock — EXCEPT into Q4 storage rates, where the math flips.

## Sequencing risks to always check
- Two launches inside one cash cycle without ledger headroom
- A reorder due while a new launch's balance payment is pending
- Velocity spikes (a viral week) tricking the reorder math — check the median
- Tariff/freight changes since the last PO — re-run economics, don't reuse
