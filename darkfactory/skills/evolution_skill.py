"""Skill 7 — evolution: the weekly Darwin generation step (see evolution.py)."""

from __future__ import annotations

from .base import Skill, SkillContext, register
from ..evolution import Evolution


@register
class EvolutionSkill(Skill):
    name = "evolution"
    description = "Score genome fitness and breed the next strategy generation."

    def run(self, ctx: SkillContext) -> dict:
        evo = Evolution(ctx.cfg, ctx.memory, llm=ctx.llm)
        result = evo.step()
        return {"summary": (f"Generation {result['generation']} bred "
                            f"({result['children']} children, best fitness "
                            f"{result['best_fitness']})"),
                **result}
