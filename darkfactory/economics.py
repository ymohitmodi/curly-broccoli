"""Deterministic unit economics + cash-flow math. Money math is NEVER
delegated to the LLM — the model proposes, this module disposes.

Models the real 2026 cash path of your operation:
  FOB (Alibaba) → sea freight ($/kg, ~45d) → tariff stack (MFN + Section 301
  + Section 122, ~35% effective on most Chinese consumer goods post-Feb-2026)
  → FBA fulfillment fee + 3.5% fuel surcharge (Apr 2026) + inbound placement
  → 15% referral → returns/storage/low-inventory-fee-risk/misc
  → net margin & ROI on landed cost.

Plus the thing that actually kills FBA sellers: the cash conversion cycle.
A typical launch is ~20 weeks of working capital (wire day 0, live ~day 80,
cash recovered day 140+). launch_cash_plan() makes that visible BEFORE you
approve a PO, and reorder_plan() keeps you above the low-inventory-fee
threshold without drowning in storage fees.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UnitEconomics:
    sale_price: float
    fob_unit: float
    unit_weight_kg: float
    sea_freight_per_kg: float = 1.9
    duty_rate: float = 0.35               # 2026 stack: MFN + S301(25%) + S122(10%)
    fba_fee: float | None = None          # if None, estimated from weight ladder
    referral_rate: float = 0.15
    returns_rate: float = 0.03
    storage_per_unit: float = 0.45
    misc_rate: float = 0.02
    fuel_surcharge_rate: float = 0.035    # on FBA fulfillment fee, eff. Apr 2026
    inbound_placement_per_unit: float = 0.30  # ~0 if using Amazon-optimized splits
    low_inventory_fee_risk: float = 0.10  # expected value of $0.89-1.10/unit fee
    fba_fee_ladder: dict | None = None    # {max_kg: fee}

    def compute(self) -> dict:
        freight = self.unit_weight_kg * self.sea_freight_per_kg
        duty = self.fob_unit * self.duty_rate
        landed = self.fob_unit + freight + duty + self.inbound_placement_per_unit

        fba = self.fba_fee if self.fba_fee is not None else self._fba_from_ladder()
        fba_total = fba * (1 + self.fuel_surcharge_rate)
        referral = self.sale_price * self.referral_rate
        returns_cost = self.sale_price * self.returns_rate
        misc = self.sale_price * self.misc_rate

        total_cost = (landed + fba_total + referral + returns_cost
                      + self.storage_per_unit + self.low_inventory_fee_risk + misc)
        profit = self.sale_price - total_cost
        margin = profit / self.sale_price if self.sale_price else 0.0
        roi = profit / landed if landed else 0.0
        return {
            "sale_price": round(self.sale_price, 2),
            "landed_cost": round(landed, 2),
            "duty_per_unit": round(duty, 2),
            "fba_fee": round(fba_total, 2),
            "referral_fee": round(referral, 2),
            "total_cost": round(total_cost, 2),
            "unit_profit": round(profit, 2),
            "net_margin_pct": round(margin, 4),
            "roi_pct": round(roi, 4),
        }

    def _fba_from_ladder(self) -> float:
        ladder = self.fba_fee_ladder or {0.2: 3.5, 0.5: 4.0, 0.9: 5.4, 1.5: 6.9}
        for max_kg in sorted(float(k) for k in ladder):
            if self.unit_weight_kg <= max_kg:
                return float(ladder[max_kg] if max_kg in ladder else ladder[str(max_kg)])
        return max(float(v) for v in ladder.values()) + 2.0  # over ladder: penalize


def from_defaults(cfg, sale_price: float, fob_unit: float, unit_weight_kg: float) -> dict:
    """Unit economics using objectives.yaml economics_defaults."""
    d = cfg.objectives.get("economics_defaults", {})
    return UnitEconomics(
        sale_price=sale_price,
        fob_unit=fob_unit,
        unit_weight_kg=unit_weight_kg,
        sea_freight_per_kg=d.get("sea_freight_per_kg_usd", 1.9),
        duty_rate=d.get("duty_rate", 0.35),
        referral_rate=d.get("referral_rate", 0.15),
        returns_rate=d.get("returns_rate", 0.03),
        storage_per_unit=d.get("storage_per_unit_month_usd", 0.45),
        misc_rate=d.get("misc_rate", 0.02),
        fuel_surcharge_rate=d.get("fuel_surcharge_rate", 0.035),
        inbound_placement_per_unit=d.get("inbound_placement_per_unit_usd", 0.30),
        low_inventory_fee_risk=d.get("low_inventory_fee_risk_usd", 0.10),
        fba_fee_ladder=d.get("fba_fee_by_weight_kg"),
    ).compute()


def launch_cash_plan(cfg, po_units: int, landed_unit_cost: float, unit_profit: float,
                     monthly_units: float, launch_ad_budget: float = 0.0) -> dict:
    """The cash truth of a launch, day by day. A typical FBA brand's cash
    conversion cycle runs 60-120+ days; launches routinely tie up ~20 weeks of
    working capital. This makes that visible BEFORE the PO is approved."""
    cf = cfg.objectives.get("cashflow", {})
    deposit_frac = cf.get("supplier_deposit_frac", 0.30)
    production_days = cf.get("production_days", 30)
    freight_days = cf.get("freight_days", 45)
    checkin_days = cf.get("fba_checkin_days", 7)
    payout_lag = cf.get("amazon_payout_lag_days", 14)

    po_cost = po_units * landed_unit_cost
    live_day = production_days + freight_days + checkin_days
    daily_units = max(monthly_units / 30.0, 0.1)
    sellthrough_days = po_units / daily_units
    cash_recovered_day = live_day + sellthrough_days + payout_lag
    peak_wc = po_cost + launch_ad_budget
    total_profit = po_units * unit_profit
    ccd = cash_recovered_day  # cash conversion days from wire to full recovery
    return {
        "po_cost": round(po_cost, 2),
        "deposit_day0": round(po_cost * deposit_frac, 2),
        "balance_at_shipment": round(po_cost * (1 - deposit_frac), 2),
        "live_day": round(live_day),
        "first_payout_day": round(live_day + payout_lag),
        "sellthrough_days": round(sellthrough_days),
        "cash_recovered_day": round(cash_recovered_day),
        "peak_working_capital": round(peak_wc, 2),
        "expected_profit_on_po": round(total_profit, 2),
        "cash_conversion_days": round(ccd),
        "capital_turns_per_year": round(365.0 / ccd, 2) if ccd else 0.0,
        "annualized_roi_pct": round((total_profit / peak_wc) * (365.0 / ccd), 4)
                              if peak_wc and ccd else 0.0,
    }


def reorder_plan(cfg, units_on_hand: float, units_inbound: float,
                 monthly_units: float, cover_target_days: float = 75) -> dict:
    """Reorder math against the 2026 fee squeeze: stay ABOVE the low-inventory
    fee threshold (~28-35 days of supply) but BELOW the storage-fee bloat cap."""
    cf = cfg.objectives.get("cashflow", {})
    lead_days = cf.get("production_days", 30) + cf.get("freight_days", 45) + cf.get("fba_checkin_days", 7)
    low_inv_threshold = cf.get("low_inventory_threshold_days", 35)
    max_cover = cfg.constraint("max_days_of_stock", 90)

    daily = max(monthly_units / 30.0, 0.1)
    days_of_supply = units_on_hand / daily
    days_incl_inbound = (units_on_hand + units_inbound) / daily
    reorder_point_days = lead_days + low_inv_threshold  # order so stock never dips below threshold
    must_reorder = days_incl_inbound <= reorder_point_days
    target_days = min(max(cover_target_days, low_inv_threshold + 14), max_cover)
    reorder_qty = max(0, round((target_days + lead_days) * daily - units_on_hand - units_inbound))
    return {
        "days_of_supply": round(days_of_supply, 1),
        "days_incl_inbound": round(days_incl_inbound, 1),
        "low_inventory_fee_exposure": days_of_supply < low_inv_threshold,
        "reorder_point_days": round(reorder_point_days),
        "must_reorder_now": must_reorder,
        "recommended_reorder_qty": reorder_qty,
        "lead_time_days": lead_days,
    }


def passes_gates(cfg, econ: dict) -> tuple[bool, list[str]]:
    """Check hard economic constraints from objectives.yaml."""
    fails = []
    if econ["net_margin_pct"] < cfg.constraint("min_net_margin_pct", 0.35):
        fails.append(f"margin {econ['net_margin_pct']:.0%} < floor")
    if econ["roi_pct"] < cfg.constraint("min_roi_pct", 1.0):
        fails.append(f"ROI {econ['roi_pct']:.0%} < floor")
    lo, hi = cfg.constraint("min_sale_price_usd", 17), cfg.constraint("max_sale_price_usd", 65)
    if not (lo <= econ["sale_price"] <= hi):
        fails.append(f"price ${econ['sale_price']} outside ${lo}-${hi}")
    return (not fails, fails)
