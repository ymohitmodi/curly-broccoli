"""Context manager: assembles every prompt under a hard character budget.

Priority order (higher survives truncation):
  1. mission + hard constraints (always, verbatim — the factory's law)
  2. active strategy genome (what Darwin currently believes works)
  3. the skill's playbook (the editable domain expertise)
  4. relevant recalled memory (what the factory already learned/did)
  5. task payload (today's data)

This is what keeps a 24/7 loop coherent for months: every call re-grounds the
model in objectives + evolved strategy + memory, instead of drifting.
"""

from __future__ import annotations

import json

import yaml


class ContextBuilder:
    def __init__(self, cfg, memory):
        self.cfg = cfg
        self.memory = memory
        self.budget = int(cfg.harness.get("context", {}).get("budget_chars", 28000))
        self.recall_items = int(cfg.harness.get("context", {}).get("recall_items", 8))

    def build(self, skill_name: str, task: str, payload: dict | None = None,
              genome: dict | None = None, recall_query: str | None = None) -> list[dict]:
        obj = self.cfg.objectives
        law = yaml.safe_dump({
            "mission": obj.get("mission", ""),
            "categories": obj.get("categories", []),
            "exclusions": obj.get("exclusions", []),
            "constraints": obj.get("constraints", {}),
        }, sort_keys=False)

        sections: list[tuple[str, str, bool]] = [  # (title, body, protected)
            ("BUSINESS LAW (hard constraints — never violate)", law, True),
        ]
        if genome:
            sections.append(("ACTIVE STRATEGY GENOME (evolved parameters — apply them)",
                             json.dumps(genome.get("params", genome), indent=2), True))
        playbook = self.cfg.playbook(skill_name)
        if playbook:
            sections.append((f"PLAYBOOK: {skill_name}", playbook, False))
        if recall_query:
            hits = self.memory.recall(recall_query, k=self.recall_items)
            if hits:
                lines = [f"- [{h['ts']}] ({h['skill']}/{h['kind']}) {h['summary']}" for h in hits]
                sections.append(("RELEVANT MEMORY (what you already know/did)", "\n".join(lines), False))
        if payload:
            sections.append(("TASK DATA", json.dumps(payload, indent=2, default=str), False))

        system = (
            "You are the strategy engine of a private-label Amazon FBA business run as a "
            "'dark factory': you do the analysis; a human only signs off on money-spending actions. "
            "Be quantitative, cite the numbers you were given, and never invent market data. "
            "If data is insufficient for a confident call, say so and lower your scores."
        )

        body = self._fit(sections)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": body + f"\n\n# YOUR TASK\n{task}"},
        ]

    def _fit(self, sections: list[tuple[str, str, bool]]) -> str:
        """Trim unprotected sections (largest first) until under budget."""
        def render(secs):
            return "\n\n".join(f"# {t}\n{b}" for t, b, _ in secs)

        out = render(sections)
        while len(out) > self.budget:
            idx = max(
                (i for i, s in enumerate(sections) if not s[2] and len(s[1]) > 500),
                key=lambda i: len(sections[i][1]), default=None)
            if idx is None:
                break
            t, b, p = sections[idx]
            sections[idx] = (t, b[: max(500, len(b) // 2)] + "\n…[truncated to fit context budget]", p)
            out = render(sections)
        return out
