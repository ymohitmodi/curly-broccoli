"""Skill — inventory_planner: cash-flow and inventory discipline.

Research says this is the #1 FBA killer: profitable sellers die of cash, not
of bad products. A typical launch ties up working capital for ~20 weeks
(wire day 0 → live ~day 80 → cash recovered day 140+), growth makes it
WORSE, and 2026 added a low-inventory-level fee that punishes running lean
while storage fees punish running fat.

All math is deterministic (economics.launch_cash_plan / reorder_plan); the
LLM only writes the risk commentary. Outputs:
  - pre-PO cash plans for candidates in sourcing (visible before you approve)
  - reorder alerts for live candidates (from logged outcomes + optional
    workspace/inbox/inventory.json with {candidate_id, units_on_hand,
    units_inbound})
  - a portfolio working-capital ledger vs. your launch budget
"""

from __future__ import annotations

import json
from pathlib import Path

from .base import Skill, SkillContext, register
from .. import economics

SCHEMA = {
    "type": "object",
    "properties": {
        "risk_commentary": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["risk_commentary", "actions"],
}


@register
class InventoryPlanner(Skill):
    name = "inventory_planner"
    description = "Cash conversion cycle, reorder points, working-capital ledger."

    def run(self, ctx: SkillContext) -> dict:
        cfg, mem = ctx.cfg, ctx.memory
        params = ctx.genome_params()
        budget = cfg.constraint("launch_budget_usd", 8000)
        max_po_frac = cfg.objectives.get("cashflow", {}).get("max_launch_cash_frac", 0.75)
        min_turns = cfg.objectives.get("cashflow", {}).get("min_capital_turns_per_year", 2.0)
        target_units = cfg.constraint("target_monthly_units", 300)

        sections, flags, committed = [], [], 0.0

        # 1) Pre-PO cash plans for candidates awaiting order approval
        for cand in mem.list_candidates(verdict="PURSUE"):
            market = (cand.get("data") or {}).get("market", {})
            if not market:
                continue
            econ = economics.from_defaults(
                cfg, sale_price=market.get("avg_price", 25.0),
                fob_unit=market.get("est_fob_unit_usd", 3.0),
                unit_weight_kg=market.get("est_unit_weight_kg", 0.5))
            if cand["stage"] in ("sourcing", "listing"):
                max_po_cash = budget * max_po_frac
                po_units = max(int(max_po_cash / max(econ["landed_cost"], 0.01)), 1)
                plan = economics.launch_cash_plan(
                    cfg, po_units=po_units, landed_unit_cost=econ["landed_cost"],
                    unit_profit=econ["unit_profit"],
                    monthly_units=target_units,
                    launch_ad_budget=budget * (1 - max_po_frac))
                verdict = "OK"
                if plan["capital_turns_per_year"] < min_turns:
                    verdict = f"⚠ REJECT: {plan['capital_turns_per_year']} capital turns/yr < {min_turns} floor"
                    flags.append(f"#{cand['id']} fails capital-velocity floor")
                sections.append(
                    f"### #{cand['id']} {cand['name'][:60]} — pre-PO cash plan ({verdict})\n"
                    f"- PO: {po_units} units × ${econ['landed_cost']} landed = ${plan['po_cost']:,} "
                    f"(deposit ${plan['deposit_day0']:,} day 0, balance ${plan['balance_at_shipment']:,} at shipment)\n"
                    f"- Live day ~{plan['live_day']}, first payout day ~{plan['first_payout_day']}, "
                    f"cash fully recovered day ~{plan['cash_recovered_day']}\n"
                    f"- Peak working capital ${plan['peak_working_capital']:,} vs. launch budget ${budget:,}\n"
                    f"- Expected profit on PO ${plan['expected_profit_on_po']:,} → "
                    f"{plan['capital_turns_per_year']} capital turns/yr, "
                    f"annualized ROI {plan['annualized_roi_pct']:.0%}\n")
                committed += plan["peak_working_capital"]

        # 2) Reorder checks for live candidates (needs real outcome + inventory)
        inventory = self._load_inventory(cfg)
        for cand in mem.list_candidates(stage="live"):
            o = cand.get("outcome") or {}
            inv = inventory.get(cand["id"], {})
            if not o.get("monthly_units"):
                continue
            plan = economics.reorder_plan(
                cfg, units_on_hand=inv.get("units_on_hand", 0),
                units_inbound=inv.get("units_inbound", 0),
                monthly_units=o["monthly_units"],
                cover_target_days=params.get("inventory_cover_days", 75))
            line = (f"### #{cand['id']} {cand['name'][:60]} — reorder check\n"
                    f"- {plan['days_of_supply']}d on hand ({plan['days_incl_inbound']}d incl. inbound); "
                    f"reorder point {plan['reorder_point_days']}d (lead {plan['lead_time_days']}d)\n")
            if plan["low_inventory_fee_exposure"]:
                line += "- 🔴 BELOW low-inventory-fee threshold — paying $0.89-1.10/unit right now\n"
                flags.append(f"#{cand['id']} paying low-inventory fees")
            if plan["must_reorder_now"] and plan["recommended_reorder_qty"] > 0:
                gate = ctx.gate(self.name, "place_order",
                                {"candidate_id": cand["id"], "reorder": True,
                                 "qty": plan["recommended_reorder_qty"]})
                line += f"- ⚠ REORDER NOW: {plan['recommended_reorder_qty']} units ({gate})\n"
                flags.append(f"#{cand['id']} reorder due")
            sections.append(line)

        if not sections:
            return {"summary": "No candidates need cash/inventory planning yet."}

        if committed > budget:
            flags.append(f"OVER-COMMITTED: ${committed:,.0f} planned vs ${budget:,} budget — "
                         "launches must be sequenced, not parallel (growth-into-cash-crunch)")

        # 3) LLM risk commentary on the deterministic numbers
        messages = ctx.prompts.build(
            self.name,
            task=("Review this working-capital ledger. Identify sequencing risks (overlapping POs, "
                  "growth-into-cash-crunch, Q4 storage-fee exposure) and give concrete actions. "
                  "Return JSON only."),
            payload={"launch_budget_usd": budget, "committed_working_capital": round(committed, 2),
                     "flags": flags, "ledger": sections},
            genome=ctx.genome,
            recall_query="cash flow inventory reorder working capital",
        )
        out = ctx.llm.chat_json(messages, SCHEMA, model=getattr(ctx.llm, "planner_model", None))

        md = ("# Cash & Inventory Ledger\n\n"
              f"**Committed working capital: ${committed:,.0f}** vs. launch budget ${budget:,}\n\n"
              + "\n".join(sections)
              + "\n## Risk commentary\n" + out.get("risk_commentary", "")
              + "\n\n## Actions\n" + "\n".join(f"- {a}" for a in out.get("actions", [])))
        path = ctx.write_artifact("cash-inventory-ledger.md", md)
        return {"summary": f"Ledger: ${committed:,.0f} committed, {len(flags)} flags "
                           f"({'; '.join(flags) if flags else 'none'}); {path.name}"}

    @staticmethod
    def _load_inventory(cfg) -> dict[int, dict]:
        """Optional real inventory levels: workspace/inbox/inventory.json
        [{candidate_id, units_on_hand, units_inbound}] — or SP-API later."""
        p = Path(cfg.workspace) / "inbox" / "inventory.json"
        if not p.exists():
            return {}
        try:
            rows = json.loads(p.read_text(encoding="utf-8"))
            return {int(r["candidate_id"]): r for r in rows}
        except (ValueError, KeyError):
            return {}
