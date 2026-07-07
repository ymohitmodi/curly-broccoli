"""Skill 5 — ad_optimizer: PPC management with real bid math.

Deterministic rules (in code) do the quantitative work with the actual
formulas, not relative nudges:

  bid a term is worth  = target ACOS × order value × smoothed CVR
  negate at 95% conf   = 0 orders after ceil(ln .05 / ln(1-CVR_prior)) clicks
                         (29 clicks at the 10% cross-category CVR prior)
  CVR is Bayesian-smoothed so 3 clicks never reads as a 33% conversion rate.

Every recommendation shows its arithmetic — you can check any line by hand.
The LLM then reviews the sheet for structure-level plays the formulas can't
see (cannibalization, ranking pushes, intent mismatch). All bid/budget
changes are human-gated."""

from __future__ import annotations

from .base import Skill, SkillContext, register
from .. import quality

SCHEMA = {
    "type": "object",
    "properties": {
        "strategy_notes": {"type": "string"},
        "extra_actions": {"type": "array", "items": {"type": "object", "properties": {
            "campaign": {"type": "string"}, "action": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["campaign", "action", "reason"]}},
    },
    "required": ["strategy_notes", "extra_actions"],
}


@register
class AdOptimizer(Skill):
    name = "ad_optimizer"
    description = "Rules-first PPC optimization: negatives, harvests, bid steps toward target ACOS."

    def run(self, ctx: SkillContext) -> dict:
        campaigns = ctx.hub.campaigns()
        if not campaigns:
            return {"summary": "No campaign data available."}

        params = ctx.genome_params()
        target_acos = params.get("ad_target_acos", 0.30)
        neg_clicks = quality.negative_confidence_clicks(0.95)

        actions = []
        for c in campaigns:
            # campaign AOV as the fallback order value for zero-order terms
            c_orders = sum(t.get("orders", 0) for t in c.get("search_terms", []))
            c_sales = sum(t.get("sales", 0) for t in c.get("search_terms", []))
            aov_fallback = (c_sales / c_orders) if c_orders else 25.0

            for t in c.get("search_terms", []):
                spend, sales = t.get("spend", 0), t.get("sales", 0)
                clicks, orders = t.get("clicks", 0), t.get("orders", 0)
                if clicks < 5:
                    continue  # not enough signal to judge anything
                cpc = spend / clicks
                aov = (sales / orders) if orders else aov_fallback
                cvr = quality.smoothed_cvr(orders, clicks)
                worth = quality.target_cpc(target_acos, aov, cvr)

                if orders == 0 and (clicks >= neg_clicks or spend >= 1.5 * aov_fallback):
                    actions.append({
                        "campaign": c["campaign"], "action": "negative_exact", "term": t["term"],
                        "delta": "—",
                        "reason": (f"{clicks} clicks, 0 orders, ${spend:.0f} bled — at a 10% CVR "
                                   f"prior, P(still no order)≈{(1-quality.CVR_PRIOR)**clicks:.0%}; "
                                   "this term does not convert for this product")})
                elif cpc > worth * 1.25 and clicks >= 8:
                    actions.append({
                        "campaign": c["campaign"], "action": "lower_bid_to_target", "term": t["term"],
                        "delta": f"→ ${worth:.2f}",
                        "reason": (f"paying ${cpc:.2f}/click; worth = {target_acos:.0%} ACOS × "
                                   f"${aov:.2f} AOV × {cvr:.1%} CVR = ${worth:.2f}")})
                elif cpc < worth * 0.8 and orders >= 2:
                    actions.append({
                        "campaign": c["campaign"], "action": "raise_bid_and_harvest_exact",
                        "term": t["term"], "delta": f"→ ${worth:.2f}",
                        "reason": (f"paying ${cpc:.2f} for a term worth ${worth:.2f} "
                                   f"({orders} orders, {cvr:.1%} CVR) — buy the impression "
                                   "share you're leaving to competitors; own it in exact")})

            if c.get("acos") and c["acos"] < target_acos * 0.8 \
                    and c.get("spend_14d", 0) > 0.8 * 14 * c.get("daily_budget", 1):
                actions.append({"campaign": c["campaign"], "action": "raise_budget",
                                "delta": "+20%", "term": "—",
                                "reason": (f"spending {c['spend_14d']/(14*c['daily_budget']):.0%} of budget "
                                           f"at {c['acos']:.0%} ACOS vs {target_acos:.0%} target — "
                                           "budget cap is the binding constraint, not efficiency")})

        messages = ctx.prompts.build(
            self.name,
            task=("Review the rule-generated PPC change sheet against the campaign data. Add any "
                  "strategy-level actions the rules miss (structure, ranking pushes, dayparting, "
                  "cannibalization between auto and exact). Return JSON only."),
            payload={"campaigns": campaigns, "rule_actions": actions,
                     "target_acos": target_acos},
            genome=ctx.genome,
            recall_query="ppc acos bids negatives campaign",
        )
        out = ctx.llm.chat_json(messages, SCHEMA, model=getattr(ctx.llm, "worker_model", None))

        md = ["# PPC Change Sheet", "", f"Target ACOS (genome): {target_acos:.0%}", "",
              "| campaign | action | term | delta | reason |", "|---|---|---|---|---|"]
        for a in actions:
            md.append(f"| {a['campaign']} | {a['action']} | {a.get('term','—')} | {a.get('delta','—')} | {a['reason']} |")
        md += ["", "## Model strategy notes", out.get("strategy_notes", ""), "", "## Extra actions"]
        for a in out.get("extra_actions", []):
            md.append(f"- **{a['campaign']}**: {a['action']} — {a['reason']}")
        path = ctx.write_artifact("ppc-change-sheet.md", "\n".join(md) + "\n")

        gate_msg = ctx.gate(self.name, "change_bids",
                            {"actions": actions, "extra": out.get("extra_actions", []),
                             "artifact": str(path)})
        return {"summary": f"{len(actions)} rule actions + {len(out.get('extra_actions', []))} "
                           f"strategy actions ({gate_msg}); sheet {path.name}"}
