"""Skill — stage_gate: the validation ladder engine (config/pipeline.yaml).

The honest recipe of elite operators: nobody wins 90% of launches; they win
90%+ of their CAPITAL by making losers die cheap. This engine enforces it:

  G1 shortlist → G2 desk validation ($150 cap) → G3 golden sample ($300 cap)
  → G4 air-freight micro-test (25% of budget) → G5 sea-freight scale (75%)

Fully deterministic — no LLM. For every PURSUE candidate it:
  1. generates precise human work orders for missing gate evidence
     (the factory cannot run a PickFu poll or squeeze a sample — you can;
     it tells you exactly what to do and records the result)
  2. advances the gate when all evidence is in — capital gates (G4/G5)
     additionally require your signature in the approval queue
  3. reminds you of the pre-written kill criteria at every hold

Evidence arrives by completing tasks (./df task-done N or the console).
"""

from __future__ import annotations

import yaml

from .base import Skill, SkillContext, register


def load_pipeline(cfg) -> dict:
    path = cfg.root / "config" / "pipeline.yaml"
    if not path.exists():
        return {"gates": {}, "capital_gates": []}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"gates": {}, "capital_gates": []}


def gate_capital_cap(cfg, gate_def: dict) -> float:
    if "max_capital_frac" in gate_def:
        return float(gate_def["max_capital_frac"]) * cfg.constraint("launch_budget_usd", 8000)
    return float(gate_def.get("max_capital_usd", 0))


@register
class StageGate(Skill):
    name = "stage_gate"
    description = "Enforce the validation ladder: evidence, capital caps, kill criteria."

    def run(self, ctx: SkillContext) -> dict:
        pipe = load_pipeline(ctx.cfg)
        gates: dict = pipe.get("gates", {})
        capital_gates = set(pipe.get("capital_gates", []))
        if not gates:
            return {"summary": "No pipeline gates configured (config/pipeline.yaml missing)."}
        order = list(gates.keys())

        # apply gate advancements you approved since the last run (idempotent:
        # only applies if the candidate is still sitting at the 'from' gate)
        for a in ctx.memory.list_approvals("approved"):
            if a["action"] != "advance_gate":
                continue
            p = a["payload"]
            cand = ctx.memory.get_candidate(int(p.get("candidate_id", 0)))
            if cand and (cand.get("data") or {}).get("gate", order[0]) == p.get("from"):
                data = cand["data"] or {}
                data["gate"] = p["to"]
                ctx.memory.update_candidate(cand["id"], data=data)
                ctx.memory.log_episode(self.name, "advance",
                                       f"#{cand['id']} advanced to {p['to']} (approval #{a['id']})")

        pending_gate_approvals = {
            (a["payload"].get("candidate_id"), a["payload"].get("to"))
            for a in ctx.memory.list_approvals("pending") if a["action"] == "advance_gate"}

        advanced, held, tasked = [], [], 0
        lines = []
        for cand in ctx.memory.list_candidates(verdict="PURSUE", limit=100):
            data = cand.get("data") or {}
            gate_id = data.get("gate", order[0])
            if gate_id not in gates:
                gate_id = order[0]

            # follow advancements within one run so the NEXT gate's work
            # orders appear immediately instead of one cadence later
            missing: list[str] = []
            for _ in range(len(order) + 1):
                gd = gates[gate_id]
                if gd.get("auto") and gd.get("next"):
                    gate_id = gd["next"]
                    data["gate"] = gate_id
                    ctx.memory.update_candidate(cand["id"], data=data)
                    continue

                needed = gd.get("evidence", {}) or {}
                have = data.get("gate_evidence", {})
                missing = [flag for flag in needed if not have.get(flag)]
                for flag in missing:  # idempotent work orders
                    tid = ctx.memory.add_task(
                        cand["id"], gate_id, flag,
                        title=f"[{gd.get('label', gate_id)}] {flag.replace('_', ' ')} — "
                              f"#{cand['id']} {cand['name'][:40]}",
                        instructions=str(needed[flag].get("task", "")).strip())
                    if tid:
                        tasked += 1
                if missing:
                    held.append(f"#{cand['id']} at {gate_id}: waiting on {', '.join(missing)}")
                    break
                nxt = gd.get("next")
                if not nxt:
                    break  # top of the ladder
                if gate_id in capital_gates or nxt in capital_gates:
                    if (cand["id"], nxt) in pending_gate_approvals:
                        gate_msg = "awaiting your approval"
                    else:
                        gate_msg = ctx.gate(self.name, "advance_gate", {
                            "candidate_id": cand["id"], "name": cand["name"],
                            "from": gate_id, "to": nxt,
                            "capital_cap_next_usd": round(gate_capital_cap(ctx.cfg, gates[nxt]), 2),
                            "kill_criteria_next": gates[nxt].get("kill_if", []),
                        })
                    if not gate_msg.startswith("auto-approved"):
                        held.append(f"#{cand['id']} at {gate_id} ({gate_msg})")
                        break
                data["gate"] = nxt
                ctx.memory.update_candidate(cand["id"], data=data)
                advanced.append(f"#{cand['id']} → {nxt}")
                ctx.memory.log_episode(self.name, "advance",
                                       f"#{cand['id']} {cand['name'][:50]} advanced to {nxt}")
                gate_id = nxt

            lines.append(
                f"### #{cand['id']} {cand['name'][:60]}\n"
                f"- gate: **{gd.get('label', gate_id)}** · capital cap this gate: "
                f"${gate_capital_cap(ctx.cfg, gd):,.0f}\n"
                + ("- missing evidence: " + ", ".join(missing) + "\n" if missing
                   else "- all evidence in ✓\n")
                + ("- **kill criteria (pre-committed — obey them):**\n"
                   + "".join(f"  - {k}\n" for k in gd.get("kill_if", []))))

        if not lines:
            return {"summary": "No PURSUE candidates on the ladder."}

        report = ("# Validation Ladder\n\n"
                  "Losers die cheap; winners earn the next tranche. "
                  "Complete tasks (console → Dashboard, or `./df tasks`) to submit evidence.\n\n"
                  + "\n".join(lines))
        path = ctx.write_artifact("validation-ladder.md", report)
        return {"summary": (f"Ladder: {len(advanced)} advanced ({'; '.join(advanced) or '—'}), "
                            f"{len(held)} held, {tasked} new work orders; {path.name}")}
