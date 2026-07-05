"""Skill — launch_strategist: the first-90-days plan.

Research: a 2026 Amazon launch is a velocity game. A new ASIN gets a 2-4 week
"honeymoon" of extra visibility while the algorithm samples shopper response;
early conversion gets baked into the ranking baseline, and 20+ reviews in the
first 30 days reads as demand. Vine ($200/parent, up to 30 units, per
functional variation since Feb 2026) is the cleanest early-review source
above ~$20 AOV, and the New Selection Program credits coupon + Vine fees in
the first 60 days. Launch-phase ACOS deliberately exceeds the steady-state
target — that multiplier is a Darwin gene.

Output: a week-by-week 90-day plan with budgets, milestones, and kill
criteria for every candidate whose listing draft exists.
"""

from __future__ import annotations

from .base import Skill, SkillContext, register
from .. import economics

SCHEMA = {
    "type": "object",
    "properties": {
        "weekly_plan": {"type": "array", "items": {"type": "object", "properties": {
            "week": {"type": "integer"},
            "focus": {"type": "string"},
            "actions": {"type": "array", "items": {"type": "string"}},
            "ppc_budget_usd": {"type": "number"},
            "milestone": {"type": "string"}},
            "required": ["week", "focus", "actions", "ppc_budget_usd", "milestone"]}},
        "review_velocity_target": {"type": "string"},
        "kill_criteria": {"type": "array", "items": {"type": "string"}},
        "pricing_ladder": {"type": "string"},
    },
    "required": ["weekly_plan", "review_velocity_target", "kill_criteria", "pricing_ladder"],
}


@register
class LaunchStrategist(Skill):
    name = "launch_strategist"
    description = "Build the 90-day launch plan: honeymoon, Vine, coupons, PPC phases, kill criteria."

    def run(self, ctx: SkillContext) -> dict:
        cands = [c for c in ctx.memory.list_candidates(verdict="PURSUE", stage="listing")
                 if not (c.get("data") or {}).get("launch_plan_done")]
        if not cands:
            return {"summary": "No listed candidates awaiting a launch plan."}

        params = ctx.genome_params()
        launch_acos = params.get("ad_target_acos", 0.30) * params.get("launch_acos_multiplier", 1.6)
        budget = ctx.cfg.constraint("launch_budget_usd", 8000)
        ad_reserve = budget * (1 - ctx.cfg.objectives.get("cashflow", {}).get("max_launch_cash_frac", 0.75))

        done = []
        for cand in cands[:1]:
            market = (cand.get("data") or {}).get("market", {})
            econ = economics.from_defaults(
                ctx.cfg, sale_price=market.get("avg_price", 25.0),
                fob_unit=market.get("est_fob_unit_usd", 3.0),
                unit_weight_kg=market.get("est_unit_weight_kg", 0.5))
            kws = ctx.memory.keywords_for(cand["id"], limit=25)

            messages = ctx.prompts.build(
                self.name,
                task=(f"Build the 12-week launch plan. Launch-phase target ACOS = {launch_acos:.0%} "
                      f"(steady-state {params.get('ad_target_acos', 0.3):.0%} — the premium buys velocity "
                      f"and rank during the honeymoon). Total ads+promo reserve: ${ad_reserve:,.0f}. "
                      "Weeks 1-4 are the honeymoon: conversion there sets the ranking baseline. "
                      "Include Vine enrollment (30 units, $200, expect ~20-25 reviews in 2-4 weeks), "
                      "New Selection Program credits, coupon strategy, the PPC phase ramp on the "
                      "priority keywords, and explicit kill criteria (when to stop feeding a loser). "
                      "Return JSON only."),
                payload={"candidate": cand["name"], "niche": cand["niche"],
                         "unit_economics": econ,
                         "priority_keywords": [k["keyword"] for k in kws[:15]],
                         # margin is pre-ad-spend, so breakeven ACOS ≈ net margin
                         "breakeven_acos": econ["net_margin_pct"]},
                genome=ctx.genome,
                recall_query=f"launch vine ppc honeymoon {cand['niche']}",
            )
            out = ctx.llm.chat_json(messages, SCHEMA, model=getattr(ctx.llm, "planner_model", None))

            md = [f"# 90-Day Launch Plan — {cand['name']} (candidate #{cand['id']})", "",
                  f"Launch ACOS target: **{launch_acos:.0%}** (genome multiplier "
                  f"{params.get('launch_acos_multiplier', 1.6):.2f}× over steady-state "
                  f"{params.get('ad_target_acos', 0.3):.0%}) · Ads/promo reserve: ${ad_reserve:,.0f}",
                  "", f"**Review velocity target:** {out.get('review_velocity_target')}",
                  f"**Pricing ladder:** {out.get('pricing_ladder')}", "",
                  "| wk | focus | PPC $ | milestone |", "|---|---|---|---|"]
            for w in out.get("weekly_plan", []):
                md.append(f"| {w['week']} | {w['focus']} | ${w['ppc_budget_usd']:.0f} | {w['milestone']} |")
            md += ["", "## Week-by-week actions"]
            for w in out.get("weekly_plan", []):
                md.append(f"**Week {w['week']}** — " + "; ".join(w.get("actions", [])))
            md += ["", "## Kill criteria (stop feeding a loser)"]
            md += [f"- {k}" for k in out.get("kill_criteria", [])]
            path = ctx.write_artifact(f"launch-plan-c{cand['id']}.md", "\n".join(md) + "\n")

            data = cand.get("data") or {}
            data["launch_plan_done"] = True
            ctx.memory.update_candidate(cand["id"], data=data)
            done.append(f"#{cand['id']} ({path.name})")

        return {"summary": "Launch plans built: " + "; ".join(done)}
