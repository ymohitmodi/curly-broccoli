"""Skill 2 — supplier_sourcing: turn a PURSUE candidate into an Alibaba-ready
sourcing package: RFQ message, target unit economics, negotiation ladder,
and a supplier red-flag checklist. Placing the order stays human-gated."""

from __future__ import annotations

import json

from .base import Skill, SkillContext, register
from .. import economics

SCHEMA = {
    "type": "object",
    "properties": {
        "rfq_message": {"type": "string", "description": "ready-to-send Alibaba RFQ, professional, includes specs, QC and packaging requirements"},
        "spec_sheet": {"type": "array", "items": {"type": "string"}},
        "negotiation_ladder": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "step": {"type": "string"}, "ask": {"type": "string"}, "give": {"type": "string"}},
                "required": ["step", "ask", "give"]},
        },
        "target_fob_usd": {"type": "number"},
        "walkaway_fob_usd": {"type": "number"},
        "moq_strategy": {"type": "string"},
        "red_flags": {"type": "array", "items": {"type": "string"}},
        "qc_checklist": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["rfq_message", "spec_sheet", "negotiation_ladder", "target_fob_usd",
                 "walkaway_fob_usd", "moq_strategy", "red_flags", "qc_checklist"],
}


@register
class SupplierSourcing(Skill):
    name = "supplier_sourcing"
    description = "Build Alibaba RFQ + negotiation package for PURSUE candidates."

    def run(self, ctx: SkillContext) -> dict:
        cands = [c for c in ctx.memory.list_candidates(verdict="PURSUE") if c["stage"] == "idea"]
        if not cands:
            return {"summary": "No PURSUE candidates awaiting sourcing packages."}

        done = []
        for cand in cands[:2]:  # max 2 per run — depth over breadth
            market = (cand.get("data") or {}).get("market", {})
            fob = market.get("est_fob_unit_usd", 3.0)
            weight = market.get("est_unit_weight_kg", 0.5)
            price = market.get("avg_price", 25.0)
            econ = economics.from_defaults(ctx.cfg, sale_price=price, fob_unit=fob, unit_weight_kg=weight)

            budget = ctx.cfg.constraint("launch_budget_usd", 8000)
            messages = ctx.prompts.build(
                self.name,
                task=("Create the full sourcing package for this candidate. The RFQ must specify the "
                      "differentiation angle as concrete product requirements (materials, tolerances, "
                      "packaging) so suppliers quote the RIGHT product. Negotiation ladder: every ask "
                      "paired with a give. target_fob must keep unit economics above the constraint "
                      "floors after all costs shown in TASK DATA. Return JSON only."),
                payload={"candidate": {k: cand[k] for k in ("id", "name", "niche", "category", "scores", "data")},
                         "unit_economics_at_current_fob": econ,
                         "launch_budget_usd": budget},
                genome=ctx.genome,
                recall_query=f"sourcing supplier negotiation {cand['niche']}",
            )
            out = ctx.llm.chat_json(messages, SCHEMA, model=getattr(ctx.llm, "worker_model", None))

            target_econ = economics.from_defaults(ctx.cfg, sale_price=price,
                                                  fob_unit=float(out.get("target_fob_usd", fob)),
                                                  unit_weight_kg=weight)
            md = self._render(cand, out, econ, target_econ)
            path = ctx.write_artifact(f"sourcing-c{cand['id']}.md", md)
            ctx.memory.update_candidate(cand["id"], stage="sourcing")
            gate_msg = ctx.gate(self.name, "place_order",
                                {"candidate_id": cand["id"], "name": cand["name"],
                                 "target_fob_usd": out.get("target_fob_usd"),
                                 "walkaway_fob_usd": out.get("walkaway_fob_usd"),
                                 "artifact": str(path)})
            done.append(f"#{cand['id']} {cand['name'][:40]} ({gate_msg})")

        return {"summary": f"Sourcing packages built for {len(done)}: " + "; ".join(done)}

    @staticmethod
    def _render(cand, out, econ_now, econ_target) -> str:
        ladder = "\n".join(f"{i+1}. **{s['step']}** — ask: {s['ask']} | give: {s['give']}"
                           for i, s in enumerate(out.get("negotiation_ladder", [])))
        return f"""# Sourcing Package — {cand['name']} (candidate #{cand['id']})

## Unit economics
| | at est. FOB | at target FOB ${out.get('target_fob_usd')} |
|---|---|---|
| landed cost | ${econ_now['landed_cost']} | ${econ_target['landed_cost']} |
| unit profit | ${econ_now['unit_profit']} | ${econ_target['unit_profit']} |
| net margin | {econ_now['net_margin_pct']:.0%} | {econ_target['net_margin_pct']:.0%} |
| ROI | {econ_now['roi_pct']:.0%} | {econ_target['roi_pct']:.0%} |

**Walkaway FOB:** ${out.get('walkaway_fob_usd')} — above this the deal fails your margin floor.
**MOQ strategy:** {out.get('moq_strategy')}

## RFQ (copy-paste to Alibaba)
{out.get('rfq_message')}

## Spec sheet
{chr(10).join('- ' + s for s in out.get('spec_sheet', []))}

## Negotiation ladder
{ladder}

## Supplier red flags
{chr(10).join('- ' + s for s in out.get('red_flags', []))}

## Pre-shipment QC checklist
{chr(10).join('- ' + s for s in out.get('qc_checklist', []))}
"""
