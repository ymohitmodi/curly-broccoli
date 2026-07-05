"""Skill 4 — listing_writer: draft the full Amazon listing (title, bullets,
description, backend search terms) from the keyword map + differentiation
angle. Amazon's hard limits are validated IN CODE (never trusted to the
model). Publishing is human-gated."""

from __future__ import annotations

from .base import Skill, SkillContext, register

TITLE_MAX = 200
BULLET_MAX = 250
BACKEND_MAX_BYTES = 249

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}},
        "description": {"type": "string"},
        "backend_search_terms": {"type": "string"},
        "a_plus_outline": {"type": "array", "items": {"type": "string"}},
        "main_image_brief": {"type": "string"},
    },
    "required": ["title", "bullets", "description", "backend_search_terms",
                 "a_plus_outline", "main_image_brief"],
}


@register
class ListingWriter(Skill):
    name = "listing_writer"
    description = "Draft the complete Amazon listing for candidates in sourcing/listing stage."

    def run(self, ctx: SkillContext) -> dict:
        cands = [c for c in ctx.memory.list_candidates(verdict="PURSUE")
                 if c["stage"] in ("sourcing", "listing")]
        if not cands:
            return {"summary": "No candidates ready for listing drafts."}

        done = []
        for cand in cands[:1]:  # one great listing per run
            kws = ctx.memory.keywords_for(cand["id"], limit=60)
            title_kws = [k["keyword"] for k in kws if "title" in (k["intent"] or "")]
            bullet_kws = [k["keyword"] for k in kws if "bullets" in (k["intent"] or "")]
            backend_kws = [k["keyword"] for k in kws if "backend" in (k["intent"] or "")]

            messages = ctx.prompts.build(
                self.name,
                task=(f"Write the complete listing. Hard limits: title <= {TITLE_MAX} chars, "
                      f"5 bullets each <= {BULLET_MAX} chars, backend terms <= {BACKEND_MAX_BYTES} BYTES "
                      "(no commas needed, no repeats of words already in title/bullets, no competitor brands). "
                      "Title formula and bullet structure are in the playbook. Return JSON only."),
                payload={"candidate": cand["name"], "niche": cand["niche"],
                         "differentiation": (cand.get("data") or {}).get("differentiation_angle"),
                         "risks_to_preempt": (cand.get("data") or {}).get("risks", []),
                         "title_keywords": title_kws or [k["keyword"] for k in kws[:8]],
                         "bullet_keywords": bullet_kws or [k["keyword"] for k in kws[8:25]],
                         "backend_keywords": backend_kws or [k["keyword"] for k in kws[25:45]]},
                genome=ctx.genome,
                recall_query=f"listing copy conversion {cand['niche']}",
            )
            out = ctx.llm.chat_json(messages, SCHEMA, model=getattr(ctx.llm, "worker_model", None))
            out, violations = self._enforce_limits(out)

            md = self._render(cand, out, violations)
            path = ctx.write_artifact(f"listing-c{cand['id']}.md", md)
            ctx.memory.update_candidate(cand["id"], stage="listing")
            gate_msg = ctx.gate(self.name, "publish_listing",
                                {"candidate_id": cand["id"], "name": cand["name"], "artifact": str(path)})
            done.append(f"#{cand['id']} {cand['name'][:40]} ({gate_msg})")

        return {"summary": "Listing drafts: " + "; ".join(done)}

    @staticmethod
    def _enforce_limits(out: dict) -> tuple[dict, list[str]]:
        violations = []
        if len(out.get("title", "")) > TITLE_MAX:
            out["title"] = out["title"][:TITLE_MAX].rsplit(" ", 1)[0]
            violations.append(f"title truncated to {TITLE_MAX} chars")
        bullets = out.get("bullets", [])[:5]
        for i, b in enumerate(bullets):
            if len(b) > BULLET_MAX:
                bullets[i] = b[:BULLET_MAX].rsplit(" ", 1)[0]
                violations.append(f"bullet {i+1} truncated")
        out["bullets"] = bullets
        bt = out.get("backend_search_terms", "")
        while len(bt.encode("utf-8")) > BACKEND_MAX_BYTES:
            bt = bt.rsplit(" ", 1)[0]
            if " " not in bt:
                bt = bt.encode("utf-8")[:BACKEND_MAX_BYTES].decode("utf-8", "ignore")
                break
        if bt != out.get("backend_search_terms", ""):
            violations.append("backend terms trimmed to 249 bytes")
        out["backend_search_terms"] = bt
        return out, violations

    @staticmethod
    def _render(cand, out, violations) -> str:
        bullets = "\n".join(f"- {b}" for b in out.get("bullets", []))
        aplus = "\n".join(f"{i+1}. {m}" for i, m in enumerate(out.get("a_plus_outline", [])))
        note = ("\n> Auto-fixes applied: " + "; ".join(violations) + "\n") if violations else ""
        return f"""# Listing Draft — {cand['name']} (candidate #{cand['id']})
{note}
## Title ({len(out.get('title',''))}/{TITLE_MAX})
{out.get('title')}

## Bullets
{bullets}

## Description
{out.get('description')}

## Backend search terms ({len(out.get('backend_search_terms','').encode('utf-8'))}/{BACKEND_MAX_BYTES} bytes)
`{out.get('backend_search_terms')}`

## A+ content outline
{aplus}

## Main image brief (for your designer/supplier)
{out.get('main_image_brief')}
"""
