"""Skill 6 — review_miner: extract delight/complaint themes from competitor
and own-product reviews, then convert them into (a) product spec upgrades and
(b) listing copy angles. This is how the factory builds the '4.5-star
delightful product' instead of a me-too clone."""

from __future__ import annotations

from .base import Skill, SkillContext, register

SCHEMA = {
    "type": "object",
    "properties": {
        "complaint_themes": {"type": "array", "items": {"type": "object", "properties": {
            "theme": {"type": "string"}, "frequency": {"type": "string", "enum": ["high", "medium", "low"]},
            "product_fix": {"type": "string"}}, "required": ["theme", "frequency", "product_fix"]}},
        "delight_themes": {"type": "array", "items": {"type": "object", "properties": {
            "theme": {"type": "string"}, "listing_angle": {"type": "string"}},
            "required": ["theme", "listing_angle"]}},
        "spec_upgrades": {"type": "array", "items": {"type": "string"}},
        "copy_angles": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["complaint_themes", "delight_themes", "spec_upgrades", "copy_angles"],
}


@register
class ReviewMiner(Skill):
    name = "review_miner"
    description = "Mine reviews for complaint/delight themes → spec upgrades + copy angles."

    def run(self, ctx: SkillContext) -> dict:
        cands = [c for c in ctx.memory.list_candidates(verdict="PURSUE")
                 if c["stage"] in ("idea", "sourcing", "listing", "launched", "live")]
        if not cands:
            return {"summary": "No active candidates to mine reviews for."}

        done = []
        for cand in cands[:2]:
            reviews = ctx.hub.reviews(cand["niche"])
            if not reviews:
                continue
            messages = ctx.prompts.build(
                self.name,
                task=("Mine these reviews. Complaints become product_fix requirements (specific and "
                      "manufacturable — things you can put in an Alibaba spec sheet). Delights become "
                      "listing angles. Weight 1-2 star reviews heaviest. Return JSON only."),
                payload={"candidate": cand["name"], "niche": cand["niche"],
                         "reviews": reviews[:60]},
                genome=ctx.genome,
                recall_query=f"reviews complaints {cand['niche']}",
            )
            out = ctx.llm.chat_json(messages, SCHEMA, model=getattr(ctx.llm, "worker_model", None))

            md = [f"# Review Mining — {cand['name']} (candidate #{cand['id']})", "",
                  "## Complaint themes → product fixes",
                  "| theme | freq | fix to spec |", "|---|---|---|"]
            for t in out.get("complaint_themes", []):
                md.append(f"| {t['theme']} | {t['frequency']} | {t['product_fix']} |")
            md += ["", "## Delight themes → listing angles"]
            for t in out.get("delight_themes", []):
                md.append(f"- **{t['theme']}** → {t['listing_angle']}")
            md += ["", "## Spec upgrades"] + [f"- {s}" for s in out.get("spec_upgrades", [])]
            md += ["", "## Copy angles"] + [f"- {s}" for s in out.get("copy_angles", [])]
            path = ctx.write_artifact(f"reviews-c{cand['id']}.md", "\n".join(md) + "\n")

            data = cand.get("data") or {}
            data["spec_upgrades"] = out.get("spec_upgrades", [])
            data["copy_angles"] = out.get("copy_angles", [])
            ctx.memory.update_candidate(cand["id"], data=data)
            done.append(f"#{cand['id']} ({len(out.get('complaint_themes', []))} complaints mined, {path.name})")

        return {"summary": "Review mining: " + ("; ".join(done) if done else "no reviews found")}
