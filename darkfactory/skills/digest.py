"""Skill 8 — digest: the daily owner's report. Everything you need to know in
one markdown file: funnel state, pending approvals (your to-do list), what
every skill did, and the current strategy genome."""

from __future__ import annotations

import datetime as dt

from .base import Skill, SkillContext, register


@register
class Digest(Skill):
    name = "digest"
    description = "Daily owner's report: funnel, approvals, activity, genome."

    def run(self, ctx: SkillContext) -> dict:
        mem = ctx.memory
        episodes = mem.recent_episodes(hours=24)
        approvals = mem.list_approvals("pending")
        cands = mem.list_candidates(limit=200)

        funnel: dict[str, int] = {}
        for c in cands:
            key = f"{c['stage']}/{c['verdict']}"
            funnel[key] = funnel.get(key, 0) + 1

        md = [f"# Dark Factory Daily Digest — {dt.date.today().isoformat()}", ""]

        md += ["## ⚠ Your approval queue (the factory is waiting on you)"]
        if approvals:
            for a in approvals:
                md.append(f"- **#{a['id']}** [{a['action']}] from {a['skill']}: "
                          f"{str(a['payload'])[:140]} → `darkfactory approve {a['id']}` or `reject {a['id']}`")
        else:
            md.append("- (empty — nothing blocked on you)")

        md += ["", "## Product funnel"]
        for k, v in sorted(funnel.items()):
            md.append(f"- {k}: {v}")
        top = [c for c in cands if c["verdict"] == "PURSUE"][:5]
        if top:
            md += ["", "### Top PURSUE candidates",
                   "| id | name | stage | composite |", "|---|---|---|---|"]
            for c in top:
                md.append(f"| {c['id']} | {c['name'][:50]} | {c['stage']} | {c['composite']:.2f} |")

        md += ["", "## Last 24h activity"]
        if episodes:
            for e in episodes[:30]:
                md.append(f"- [{e['ts'][11:16]}] **{e['skill']}**/{e['kind']}: {e['summary'][:160]}")
        else:
            md.append("- (no activity)")

        genome = mem.active_genome()
        if genome:
            md += ["", "## Active strategy genome",
                   f"generation {genome['generation']}, fitness {genome['fitness']}",
                   "```json", str(genome["params"]), "```"]

        report = "\n".join(md) + "\n"
        path = ctx.cfg.reports_dir / f"digest-{dt.date.today().isoformat()}.md"
        path.write_text(report, encoding="utf-8")
        return {"summary": f"Digest written to {path.name}: {len(approvals)} approvals pending, "
                           f"{len(episodes)} episodes in 24h."}
