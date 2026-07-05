"""Deterministic unit economics. Money math is NEVER delegated to the LLM —
the model proposes, this module disposes.

Models the real cash path of your operation:
  FOB (Alibaba) → sea freight ($/kg, ~45d) → duty/tariff → FBA fulfillment fee
  → 15% referral → returns/storage/misc → net margin & ROI on landed cost.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UnitEconomics:
    sale_price: float
    fob_unit: float
    unit_weight_kg: float
    sea_freight_per_kg: float = 1.9
    duty_rate: float = 0.25
    fba_fee: float | None = None          # if None, estimated from weight ladder
    referral_rate: float = 0.15
    returns_rate: float = 0.03
    storage_per_unit: float = 0.45
    misc_rate: float = 0.02
    fba_fee_ladder: dict | None = None    # {max_kg: fee}

    def compute(self) -> dict:
        freight = self.unit_weight_kg * self.sea_freight_per_kg
        duty = self.fob_unit * self.duty_rate
        landed = self.fob_unit + freight + duty

        fba = self.fba_fee if self.fba_fee is not None else self._fba_from_ladder()
        referral = self.sale_price * self.referral_rate
        returns_cost = self.sale_price * self.returns_rate
        misc = self.sale_price * self.misc_rate

        total_cost = landed + fba + referral + returns_cost + self.storage_per_unit + misc
        profit = self.sale_price - total_cost
        margin = profit / self.sale_price if self.sale_price else 0.0
        roi = profit / landed if landed else 0.0
        return {
            "sale_price": round(self.sale_price, 2),
            "landed_cost": round(landed, 2),
            "fba_fee": round(fba, 2),
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
        duty_rate=d.get("duty_rate", 0.25),
        referral_rate=d.get("referral_rate", 0.15),
        returns_rate=d.get("returns_rate", 0.03),
        storage_per_unit=d.get("storage_per_unit_month_usd", 0.45),
        misc_rate=d.get("misc_rate", 0.02),
        fba_fee_ladder=d.get("fba_fee_by_weight_kg"),
    ).compute()


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
