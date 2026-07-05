from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SKILLS: dict[str, "type[Skill]"] = {}


def register(cls):
    SKILLS[cls.name] = cls
    return cls


@dataclass
class SkillContext:
    cfg: Any          # Config
    memory: Any       # Memory
    llm: Any          # BaseLLM
    hub: Any          # DataHub
    prompts: Any      # ContextBuilder
    genome: dict | None  # active genome row (id, params, ...) or None

    def genome_params(self) -> dict:
        from ..evolution import default_genome, _normalize_weights
        if self.genome and self.genome.get("params"):
            return self.genome["params"]
        return _normalize_weights(default_genome())

    def genome_id(self) -> int | None:
        return self.genome["id"] if self.genome else None

    def write_artifact(self, name: str, content: str) -> Path:
        """Persist a human-readable deliverable under workspace/artifacts/."""
        stamp = dt.date.today().isoformat()
        path = self.cfg.artifacts_dir / f"{stamp}-{name}"
        path.write_text(content, encoding="utf-8")
        return path

    def gate(self, skill: str, action: str, payload: dict) -> str:
        """Queue an approval if the action is human-gated; return status string."""
        gated = self.cfg.harness.get("require_approval", [])
        if action in gated:
            aid = self.memory.add_approval(skill, action, payload)
            return f"queued approval #{aid} ({action})"
        return f"auto-approved ({action} not gated)"


class Skill:
    name: str = "base"
    description: str = ""

    def run(self, ctx: SkillContext) -> dict:
        """Execute once. Return {'summary': str, ...}; orchestrator logs it."""
        raise NotImplementedError
