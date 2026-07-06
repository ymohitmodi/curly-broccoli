"""Skill 3 — keyword_seo: expand seed keywords into a clustered master keyword
map (head / mid / long-tail, buyer intent), scored and stored per candidate.
Long-tail bias comes from the genome — Darwin learns how deep to fish."""

from __future__ import annotations

import json

from .base import Skill, SkillContext, register
from .. import quality

SCHEMA = {
    "type": "object",
    "properties": {
        "keywords": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "keyword": {"type": "string"},
                "tier": {"type": "string", "enum": ["head", "mid", "longtail"]},
                "intent": {"type": "string", "enum": ["buy", "compare", "problem", "browse"]},
                "relevance": {"type": "number"},
                "placement": {"type": "string", "enum": ["title", "bullets", "backend", "ppc_exact", "ppc_broad"]},
            }, "required": ["keyword", "tier", "intent", "relevance", "placement"]},
        }
    },
    "required": ["keywords"],
}


@register
class KeywordSeo(Skill):
    name = "keyword_seo"
    description = "Expand and cluster the master keyword map for active candidates."

    def run(self, ctx: SkillContext) -> dict:
        cands = [c for c in ctx.memory.list_candidates(verdict="PURSUE")
                 if c["stage"] in ("idea", "sourcing", "listing")]
        if not cands:
            return {"summary": "No PURSUE candidates need keyword maps."}

        params = ctx.genome_params()
        bias = params.get("keyword_longtail_bias", 0.6)
        done = []
        for cand in cands[:2]:
            seeds = [k["keyword"] for k in ctx.memory.keywords_for(cand["id"], limit=30)]
            trend = ctx.hub.trend_scores(seeds[:10])
            messages = ctx.prompts.build(
                self.name,
                task=(f"Build a 40-60 term master keyword map. Long-tail bias = {bias:.2f} "
                      f"(fraction of terms that should be long-tail/problem queries). Score relevance 0-1. "
                      "Assign each term its single best placement. Return JSON only."),
                payload={"candidate": cand["name"], "niche": cand["niche"],
                         "differentiation": (cand.get("data") or {}).get("differentiation_angle"),
                         "seed_keywords": seeds, "google_trend_momentum": trend},
                genome=ctx.genome,
                recall_query=f"keywords seo {cand['niche']}",
            )
            worker = getattr(ctx.llm, "worker_model", None)
            out = ctx.llm.chat_json(messages, SCHEMA, model=worker)

            # code-enforced quality: dedupe/normalize, then check count and
            # tier mix against the genome's bias — one corrective re-prompt
            # if the model ignored the brief
            qa = quality.clean_keyword_map(out.get("keywords", []), bias)
            if not (qa["mix_ok"] and qa["count_ok"]):
                retry = messages + [
                    {"role": "assistant", "content": json.dumps(out)},
                    {"role": "user", "content":
                        f"Quality gate failed: {qa['notes']}. Requirements: >= 40 unique terms "
                        f"and a long-tail fraction within ±18% of {bias:.0%}. Rebalance and "
                        "return the corrected full map as JSON only."},
                ]
                try:
                    out = ctx.llm.chat_json(retry, SCHEMA, model=worker)
                    qa = quality.clean_keyword_map(out.get("keywords", []), bias)
                except Exception:
                    pass  # keep the first map rather than fail the run
            kw_clean = qa["keywords"]

            rows = [{"keyword": k["keyword"], "intent": f"{k['tier']}/{k['intent']}/{k['placement']}",
                     "source": "keyword_seo", "score": float(k.get("relevance", 0.5))}
                    for k in kw_clean]
            ctx.memory.add_keywords(cand["id"], rows)

            md = [f"# Keyword Map — {cand['name']} (candidate #{cand['id']})", "",
                  f"Quality gate: {qa['notes']} — mix {'OK' if qa['mix_ok'] else 'off-target'}, "
                  f"count {'OK' if qa['count_ok'] else 'thin'}", "",
                  "| keyword | tier | intent | placement | relevance |", "|---|---|---|---|---|"]
            for k in sorted(kw_clean, key=lambda x: -float(x.get("relevance", 0))):
                md.append(f"| {k['keyword']} | {k['tier']} | {k['intent']} | {k['placement']} | {float(k.get('relevance',0)):.2f} |")
            path = ctx.write_artifact(f"keywords-c{cand['id']}.md", "\n".join(md) + "\n")
            done.append(f"#{cand['id']} +{len(rows)} terms ({path.name})")

        return {"summary": "Keyword maps updated: " + "; ".join(done)}
