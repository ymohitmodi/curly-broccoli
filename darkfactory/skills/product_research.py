"""Skill 1 — product_research: the top of the funnel.

Pipeline per run:
  1. pull a market snapshot for the allowed categories
  2. HARD pre-filter in code (exclusions, review moat, niche size, price band,
     unit economics) — bad niches never reach the model, saving tokens
  3. LLM scores survivors on 5 axes (0-1) using the playbook + genome
  4. composite = genome-weighted sum; verdict from genome threshold
  5. persist candidates + seed keywords; write a shortlist report
"""

from __future__ import annotations

import json

from .base import Skill, SkillContext, register
from .. import economics
from ..evolution import composite_score

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "niche": {"type": "string"},
                    "product_concept": {"type": "string", "description": "the differentiated product to build, not just the niche"},
                    "scores": {
                        "type": "object",
                        "properties": {
                            "demand": {"type": "number"},
                            "competition_gap": {"type": "number"},
                            "margin_potential": {"type": "number"},
                            "differentiation": {"type": "number"},
                            "operational_simplicity": {"type": "number"},
                        },
                        "required": ["demand", "competition_gap", "margin_potential",
                                     "differentiation", "operational_simplicity"],
                    },
                    "differentiation_angle": {"type": "string"},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "seed_keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["niche", "product_concept", "scores", "differentiation_angle",
                             "risks", "seed_keywords"],
            },
        }
    },
    "required": ["candidates"],
}


@register
class ProductResearch(Skill):
    name = "product_research"
    description = "Scan allowed categories, hard-filter, LLM-score, and shortlist product candidates."

    def run(self, ctx: SkillContext) -> dict:
        cfg, mem = ctx.cfg, ctx.memory
        categories = cfg.objectives.get("categories", [])
        niches = ctx.hub.market_snapshot(categories)

        survivors, rejected = [], []
        for n in niches:
            ok, reasons, econ = self._prefilter(ctx, n)
            if ok:
                n = dict(n)
                n["unit_economics_estimate"] = econ
                survivors.append(n)
            else:
                rejected.append((n["niche"], reasons))

        if not survivors:
            return {"summary": f"0/{len(niches)} niches passed hard filters; nothing sent to model.",
                    "rejected": rejected}

        # optional free trend signal
        trend = ctx.hub.trend_scores([n["niche"] for n in survivors])
        for n in survivors:
            if n["niche"] in trend:
                n["google_trend_momentum"] = trend[n["niche"]]

        params = ctx.genome_params()
        messages = ctx.prompts.build(
            self.name,
            task=("Score each surviving niche 0-1 on the five axes per the playbook rubric. "
                  "For each, define ONE concrete differentiated product concept that attacks the "
                  "weaknesses in the data (notes, review moats, price position). "
                  "Give 5-10 seed keywords per candidate. Return JSON only."),
            payload={"surviving_niches": survivors},
            genome=ctx.genome,
            recall_query="product research niche verdict " + " ".join(c for c in categories),
        )
        out = ctx.llm.chat_json(messages, SCORE_SCHEMA, model=getattr(ctx.llm, "planner_model", None))

        threshold = params.get("min_composite_pursue", 0.62)
        pursued, lines = 0, []
        by_niche = {n["niche"]: n for n in survivors}
        for cand in out.get("candidates", []):
            scores = {k: max(0.0, min(1.0, float(v))) for k, v in cand.get("scores", {}).items()}
            comp = composite_score(scores, params)
            verdict = "PURSUE" if comp >= threshold else ("WATCH" if comp >= threshold - 0.12 else "DROP")
            src = self._match_niche(cand.get("niche", ""), by_niche)
            cid = mem.add_candidate(
                name=cand.get("product_concept", cand.get("niche", "?")),
                category=src.get("category", "?"),
                niche=cand.get("niche", "?"),
                genome_id=ctx.genome_id(),
                data={"market": src, "differentiation_angle": cand.get("differentiation_angle"),
                      "risks": cand.get("risks", [])},
                scores=scores, composite=comp, verdict=verdict)
            mem.add_keywords(cid, [{"keyword": k, "intent": "seed", "source": "product_research", "score": 0.5}
                                   for k in cand.get("seed_keywords", [])])
            if verdict == "PURSUE":
                pursued += 1
            lines.append(f"| {cid} | {cand.get('product_concept','?')[:60]} | {comp:.2f} | {verdict} |")

        report = (f"# Product Research Shortlist\n\n"
                  f"Hard-filter: {len(survivors)}/{len(niches)} niches survived.\n\n"
                  f"Rejected: " + "; ".join(f"{n} ({', '.join(r)})" for n, r in rejected) + "\n\n"
                  "| id | concept | composite | verdict |\n|---|---|---|---|\n" + "\n".join(lines) + "\n")
        path = ctx.write_artifact("product-shortlist.md", report)

        return {"summary": (f"Scored {len(out.get('candidates', []))} candidates "
                            f"({pursued} PURSUE) from {len(survivors)} surviving niches; report {path.name}"),
                "pursued": pursued}

    @staticmethod
    def _match_niche(name: str, by_niche: dict[str, dict]) -> dict:
        """Attach model output back to source market data even if the model
        reworded the niche. Exact → substring → sole-survivor fallback."""
        if name in by_niche:
            return by_niche[name]
        low = name.lower()
        for k, v in by_niche.items():
            if low and (low in k.lower() or k.lower() in low):
                return v
        if len(by_niche) == 1:
            return next(iter(by_niche.values()))
        return {}

    def _prefilter(self, ctx: SkillContext, n: dict) -> tuple[bool, list[str], dict | None]:
        cfg = ctx.cfg
        params = ctx.genome_params()
        reasons: list[str] = []

        # policy exclusions by note text (cheap heuristic; the LLM re-checks later)
        note = (n.get("notes", "") + " " + n.get("niche", "")).lower()
        for word in ("battery", "electronic", "supplement", "glass", "oversize"):
            if word in note:
                reasons.append(f"exclusion keyword: {word}")

        moat_cap = cfg.constraint("max_top10_avg_reviews", 900) * params.get("max_review_moat_frac", 1.0)
        if n.get("top10_avg_reviews", 0) > moat_cap:
            reasons.append(f"review moat {n.get('top10_avg_reviews')} > {moat_cap:.0f}")
        if n.get("est_monthly_revenue_usd", 0) < cfg.constraint("min_monthly_revenue_niche_usd", 40000):
            reasons.append("niche too small")
        if n.get("est_unit_weight_kg", 0) > cfg.constraint("max_unit_weight_kg", 1.5):
            reasons.append("too heavy")

        price = n.get("avg_price", 0)
        econ = None
        if n.get("est_fob_unit_usd") and price:
            # price positioning per genome: 0 = match cheapest, 1 = premium
            target_price = price * (0.9 + 0.25 * params.get("price_position", 0.5))
            econ = economics.from_defaults(cfg, sale_price=round(target_price, 2),
                                           fob_unit=n["est_fob_unit_usd"],
                                           unit_weight_kg=n.get("est_unit_weight_kg", 0.5))
            ok, fails = economics.passes_gates(cfg, econ)
            if not ok:
                reasons.extend(fails)
        else:
            lo = cfg.constraint("min_sale_price_usd", 17)
            hi = cfg.constraint("max_sale_price_usd", 65)
            if not (lo <= price <= hi):
                reasons.append(f"price ${price} outside ${lo}-${hi}")

        return (not reasons, reasons, econ)
