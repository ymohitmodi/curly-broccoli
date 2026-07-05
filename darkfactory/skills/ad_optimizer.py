"""Skill 5 — ad_optimizer: PPC management on a rules-first basis.

Deterministic rules (in code) find the obvious moves from search-term data:
bleeders → negatives, winners → exact harvest, bid steps toward target ACOS.
The LLM then reviews the rule output for strategy-level adjustments it can't
see (cannibalization, ranking plays). All bid/budget changes are human-gated
— the factory produces a change sheet, you approve it."""

from __future__ import annotations

from .base import Skill, SkillContext, register

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
        step = params.get("ad_bid_step", 0.15)

        actions = []
        for c in campaigns:
            for t in c.get("search_terms", []):
                spend, sales, clicks = t.get("spend", 0), t.get("sales", 0), t.get("clicks", 0)
                acos = (spend / sales) if sales else None
                if clicks >= 12 and t.get("orders", 0) == 0:
                    actions.append({"campaign": c["campaign"], "action": "negative_exact",
                                    "term": t["term"], "reason": f"{clicks} clicks, 0 orders, ${spend:.0f} bled"})
                elif acos is not None and acos > target_acos * 1.5 and clicks >= 10:
                    actions.append({"campaign": c["campaign"], "action": "lower_bid",
                                    "term": t["term"], "delta": f"-{step:.0%}",
                                    "reason": f"ACOS {acos:.0%} vs target {target_acos:.0%}"})
                elif acos is not None and acos < target_acos * 0.7 and t.get("orders", 0) >= 3:
                    actions.append({"campaign": c["campaign"], "action": "raise_bid_or_harvest_exact",
                                    "term": t["term"], "delta": f"+{step:.0%}",
                                    "reason": f"ACOS {acos:.0%} well under target — scale winner"})
            if c.get("acos") and c["acos"] < target_acos * 0.8 and c.get("spend_14d", 0) > 0.8 * 14 * c.get("daily_budget", 1):
                actions.append({"campaign": c["campaign"], "action": "raise_budget", "delta": "+20%",
                                "reason": f"budget-capped at ACOS {c['acos']:.0%} < target"})

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
