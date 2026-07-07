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
from .. import economics, quality
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
                    "evidence": {"type": "string", "description": "the specific NUMBERS from the market data that justify these scores"},
                    "risks": {"type": "array", "items": {"type": "string"}},
                    "seed_keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["niche", "product_concept", "scores", "differentiation_angle",
                             "evidence", "risks", "seed_keywords"],
            },
        }
    },
    "required": ["candidates"],
}

# Adversarial pass: a devil's advocate tries to kill each PURSUE candidate.
# NOTE: "SURVIVES" is deliberately first in the enum — schema-driven mock mode
# picks the first value, keeping the offline pipeline flowing.
KILL_SCHEMA = {
    "type": "object",
    "properties": {
        "reviews": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "product_concept": {"type": "string"},
                "verdict": {"type": "string", "enum": ["SURVIVES", "FATAL"]},
                "strongest_objection": {"type": "string"},
                "fatal_reason": {"type": "string"},
            }, "required": ["product_concept", "verdict", "strongest_objection", "fatal_reason"]},
        }
    },
    "required": ["reviews"],
}

SCORING_RUBRIC = """\
- Every score must be defensible from the NUMBERS in the data. If evidence is
  thin, the score goes DOWN, not up.
- demand: is the volume durable (12-mo trend), or a fad signature?
- competition_gap: could a newcomer with 0 reviews realistically reach page 1
  inside 90 days? If not, cap it at 0.4.
- differentiation must be a manufacturable fix to a documented complaint, not
  a color change. If the concept is a me-too, differentiation <= 0.3.
- A concept a supplier cannot quote from one paragraph is too vague — rewrite it.
- Risks must be specific and falsifiable ("IP risk: mechanism appears patented
  by X") — never generic ("competition is high")."""


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
                  "weaknesses in the data (notes, review moats, price position). In `evidence`, "
                  "cite the specific numbers that justify your scores. "
                  "Give 5-10 seed keywords per candidate. Return JSON only."),
            payload={"surviving_niches": survivors},
            genome=ctx.genome,
            recall_query="product research niche verdict " + " ".join(c for c in categories),
        )
        planner = getattr(ctx.llm, "planner_model", None)
        if ctx.cfg.llm("refinement", True):
            out = ctx.llm.chat_json_refined(messages, SCORE_SCHEMA, SCORING_RUBRIC, model=planner)
        else:
            out = ctx.llm.chat_json(messages, SCORE_SCHEMA, model=planner)

        threshold = params.get("min_composite_pursue", 0.62)
        pursued, lines, staged = 0, [], []
        by_niche = {n["niche"]: n for n in survivors}
        for cand in out.get("candidates", []):
            scores = {k: max(0.0, min(1.0, float(v))) for k, v in cand.get("scores", {}).items()}
            # evidence discipline: uncited scores are opinions — damp them
            scores, damped = quality.evidence_damp(scores, cand.get("evidence", ""))
            comp = composite_score(scores, params)
            verdict = "PURSUE" if comp >= threshold else ("WATCH" if comp >= threshold - 0.12 else "DROP")
            src = self._match_niche(cand.get("niche", ""), by_niche)
            # the JUDGE score: computed by code from market data + economics,
            # independent of genome weights — this is what evolution optimizes
            scores["objective"] = quality.objective_score(
                ctx.cfg, src, src.get("unit_economics_estimate"))
            cid = mem.add_candidate(
                name=cand.get("product_concept", cand.get("niche", "?")),
                category=src.get("category", "?"),
                niche=cand.get("niche", "?"),
                genome_id=ctx.genome_id(),
                data={"market": src, "differentiation_angle": cand.get("differentiation_angle"),
                      "evidence": cand.get("evidence", ""), "risks": cand.get("risks", []),
                      "evidence_damped": damped},
                scores=scores, composite=comp, verdict=verdict)
            mem.add_keywords(cid, [{"keyword": k, "intent": "seed", "source": "product_research", "score": 0.5}
                                   for k in cand.get("seed_keywords", [])])
            staged.append((cid, cand, verdict, comp))

        # adversarial kill-review: a devil's advocate attacks every PURSUE.
        # A candidate that cannot survive its strongest objection is not a bet.
        kills = self._kill_review(ctx, [(cid, c) for cid, c, v, _ in staged if v == "PURSUE"])
        for cid, cand, verdict, comp in staged:
            fatal = kills.get(cand.get("product_concept", ""))
            if verdict == "PURSUE" and fatal:
                verdict = "WATCH"
                mem.update_candidate(cid, verdict="WATCH")
                mem.log_episode(self.name, "kill_review",
                                f"#{cid} downgraded PURSUE→WATCH: {fatal[:180]}")
            if verdict == "PURSUE":
                pursued += 1
            lines.append(f"| {cid} | {cand.get('product_concept','?')[:60]} | {comp:.2f} | "
                         f"{verdict}{' †' if fatal else ''} |")

        report = (f"# Product Research Shortlist\n\n"
                  f"Hard-filter: {len(survivors)}/{len(niches)} niches survived.\n\n"
                  f"Rejected: " + "; ".join(f"{n} ({', '.join(r)})" for n, r in rejected) + "\n\n"
                  "| id | concept | composite | verdict |\n|---|---|---|---|\n" + "\n".join(lines)
                  + "\n\n† survived scoring but was downgraded by the adversarial kill-review "
                    "(see Activity for the objection)\n")
        path = ctx.write_artifact("product-shortlist.md", report)

        return {"summary": (f"Scored {len(out.get('candidates', []))} candidates "
                            f"({pursued} PURSUE after kill-review) from {len(survivors)} "
                            f"surviving niches; report {path.name}"),
                "pursued": pursued}

    def _kill_review(self, ctx: SkillContext, pursued: list) -> dict[str, str]:
        """Second, adversarial pass. Returns {product_concept: fatal_reason}
        for candidates that do NOT survive. Failure-safe: an error here never
        blocks the run — it just means no downgrades."""
        if not pursued:
            return {}
        payload = [{"product_concept": c.get("product_concept"),
                    "niche": c.get("niche"), "scores": c.get("scores"),
                    "differentiation_angle": c.get("differentiation_angle"),
                    "evidence": c.get("evidence"), "risks": c.get("risks")}
                   for _, c in pursued]
        messages = ctx.prompts.build(
            self.name,
            task=("You are now the DEVIL'S ADVOCATE. Your job is to kill these candidates. "
                  "For each: find the single strongest objection (IP exposure, fad demand, "
                  "differentiation a competitor copies in a week, hidden operational trap, "
                  "review moat undercounted, margin fragility at tariff/freight swings). "
                  "Verdict FATAL only if the objection would realistically lose the launch "
                  "budget — otherwise SURVIVES. Killing a good bet costs one idea; approving "
                  "a bad one costs $8,000. Return JSON only."),
            payload={"pursue_candidates": payload},
            genome=ctx.genome,
        )
        try:
            out = ctx.llm.chat_json(messages, KILL_SCHEMA,
                                    model=getattr(ctx.llm, "planner_model", None))
            return {r.get("product_concept", ""): r.get("fatal_reason", "")
                    for r in out.get("reviews", []) if r.get("verdict") == "FATAL"}
        except Exception as e:
            ctx.memory.log_episode(self.name, "kill_review_skipped", str(e)[:200])
            return {}

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
