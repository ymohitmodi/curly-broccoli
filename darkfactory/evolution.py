"""Darwinian strategy evolution.

A GENOME is the tunable strategy of the whole factory — scoring weights,
risk thresholds, keyword bias, PPC targets. Skills read the active genome on
every run, so the factory's behavior IS its genome.

Weekly cycle:
  1. score fitness of each active genome from the candidates it produced
     (projected composite now; real logged outcomes dominate once you have them)
  2. keep elites, breed children by uniform crossover
  3. mutate: gaussian jitter bounded per-gene, scaled by risk_appetite;
     optionally one LLM-directed mutation ("what single parameter change would
     most improve results, given this evidence?")
  4. archive the old generation; children + elites become the new population

Hard constraints in objectives.yaml are OUTSIDE the genome — evolution can
never mutate away your margin floor or category exclusions.
"""

from __future__ import annotations

import json
import random
import statistics

# gene: (default, min, max)
GENE_SPACE: dict[str, tuple[float, float, float]] = {
    "w_demand":               (0.25, 0.05, 0.50),
    "w_competition_gap":      (0.25, 0.05, 0.50),
    "w_margin":               (0.25, 0.05, 0.50),
    "w_differentiation":      (0.15, 0.05, 0.40),
    "w_operational_simplicity": (0.10, 0.02, 0.30),
    "min_composite_pursue":   (0.62, 0.45, 0.80),  # score needed for PURSUE verdict
    "max_review_moat_frac":   (1.00, 0.40, 1.20),  # × objectives.max_top10_avg_reviews
    "keyword_longtail_bias":  (0.60, 0.20, 0.90),  # 1.0 = only long-tail
    "ad_target_acos":         (0.30, 0.15, 0.45),  # steady-state target ACOS
    "ad_bid_step":            (0.15, 0.05, 0.30),  # relative bid adjustment step
    "price_position":         (0.50, 0.20, 0.85),  # 0=undercut market, 1=premium
    "launch_acos_multiplier": (1.60, 1.00, 2.50),  # honeymoon: buy velocity above target ACOS
    "inventory_cover_days":   (75.0, 45.0, 100.0), # reorder target between low-inv fee & storage bloat
}

WEIGHT_GENES = ["w_demand", "w_competition_gap", "w_margin",
                "w_differentiation", "w_operational_simplicity"]


def default_genome() -> dict:
    return {k: v[0] for k, v in GENE_SPACE.items()}


def _clamp(gene: str, value: float) -> float:
    _, lo, hi = GENE_SPACE[gene]
    return max(lo, min(hi, value))


def _normalize_weights(params: dict) -> dict:
    total = sum(params[g] for g in WEIGHT_GENES) or 1.0
    for g in WEIGHT_GENES:
        params[g] = round(params[g] / total, 4)
    return params


def mutate(params: dict, scale: float, rng: random.Random) -> dict:
    child = dict(params)
    for gene, (_, lo, hi) in GENE_SPACE.items():
        if rng.random() < 0.5:
            span = hi - lo
            child[gene] = _clamp(gene, child[gene] + rng.gauss(0, scale * span))
    return _normalize_weights(child)


def crossover(a: dict, b: dict, rng: random.Random) -> dict:
    child = {g: (a if rng.random() < 0.5 else b).get(g, GENE_SPACE[g][0]) for g in GENE_SPACE}
    return _normalize_weights(child)


def composite_score(scores: dict, params: dict) -> float:
    """Weighted composite of a candidate's 0-1 subscores using genome weights."""
    mapping = {
        "w_demand": "demand", "w_competition_gap": "competition_gap",
        "w_margin": "margin_potential", "w_differentiation": "differentiation",
        "w_operational_simplicity": "operational_simplicity",
    }
    total = 0.0
    for gene, key in mapping.items():
        total += params.get(gene, GENE_SPACE[gene][0]) * float(scores.get(key, 0.0))
    return round(total, 4)


def genome_fitness(memory, genome_id: int) -> float:
    """0.6 × projected quality (top-3 candidate composites) +
       0.4 × realized outcomes (when you log real sales via `log-outcome`)."""
    cands = [c for c in memory.list_candidates(limit=500) if c["genome_id"] == genome_id]
    if not cands:
        return 0.0
    composites = sorted((c["composite"] or 0.0 for c in cands), reverse=True)[:3]
    projected = statistics.mean(composites)

    realized = []
    for c in cands:
        o = c.get("outcome") or {}
        if o:
            # Profit quality: margin vs. 35% floor
            margin_n = min(float(o.get("margin_pct", 0)) / 0.35, 1.5) / 1.5
            # Turnover: units vs. target
            units_n = min(float(o.get("monthly_units", 0)) / max(float(o.get("target_units", 300)), 1), 1.5) / 1.5
            # Delight: rating vs. 5
            rating_n = float(o.get("rating", 0)) / 5.0
            # Capital velocity: cash conversion cycle → turns/year, 4+/yr = perfect.
            # This is what separates "profitable on paper" from "compounding":
            # the same margin at 2x the capital turns makes ~2x the annual cash.
            ccd = float(o.get("cash_conversion_days", 0) or 0)
            turns_n = min((365.0 / ccd) / 4.0, 1.0) if ccd else 0.5  # unknown = neutral
            realized.append(max(0.0, min(1.0,
                0.35 * margin_n + 0.25 * units_n + 0.15 * rating_n + 0.25 * turns_n)))
    if realized:
        return round(0.4 * projected + 0.6 * statistics.mean(realized), 4)
    return round(projected, 4)


class Evolution:
    def __init__(self, cfg, memory, llm=None):
        self.cfg = cfg
        self.memory = memory
        self.llm = llm
        evo = cfg.harness.get("evolution", {})
        self.pop_size = int(evo.get("population_size", 6))
        self.elites = int(evo.get("elites", 2))
        risk = float(cfg.objectives.get("risk_appetite", 0.4))
        self.scale = float(evo.get("mutation_scale", 0.15)) * (0.5 + risk)
        self.llm_mutation = bool(evo.get("llm_mutation", True))
        self.rng = random.Random(42)  # deterministic lineage; change to unseed

    def ensure_population(self) -> list[dict]:
        pop = self.memory.list_genomes("active")
        if pop:
            return pop
        base = _normalize_weights(default_genome())
        self.memory.save_genome(1, base, note="seed:defaults")
        for _ in range(self.pop_size - 1):
            self.memory.save_genome(1, mutate(base, self.scale, self.rng), note="seed:jitter")
        return self.memory.list_genomes("active")

    def step(self) -> dict:
        """Run one generation. Returns a summary for the episode log."""
        pop = self.ensure_population()
        for g in pop:
            self.memory.set_genome_fitness(g["id"], genome_fitness(self.memory, g["id"]))
        pop = self.memory.list_genomes("active")
        pop.sort(key=lambda g: g["fitness"] or 0, reverse=True)

        gen = max(g["generation"] for g in pop) + 1
        elites = pop[: self.elites]
        children: list[tuple[dict, str]] = []

        while len(children) < self.pop_size - self.elites - (1 if self.llm_mutation and self.llm else 0):
            a, b = self._tournament(pop), self._tournament(pop)
            child = mutate(crossover(a["params"], b["params"], self.rng), self.scale, self.rng)
            children.append((child, f"cross:{a['id']}x{b['id']}"))

        if self.llm_mutation and self.llm and pop:
            directed = self._llm_mutation(pop[0])
            if directed:
                children.append((directed, f"llm-directed from {pop[0]['id']}"))

        elite_ids = {e["id"] for e in elites}
        self.memory.archive_genomes([g["id"] for g in pop if g["id"] not in elite_ids])
        for e in elites:  # promote in place: id (and candidate lineage) survives
            self.memory.promote_genome(e["id"], gen)
        for params, note in children:
            self.memory.save_genome(gen, params, note=note)

        return {
            "generation": gen,
            "best_fitness": elites[0]["fitness"] if elites else None,
            "best_params": elites[0]["params"] if elites else None,
            "children": len(children),
        }

    def _tournament(self, pop: list[dict], k: int = 3) -> dict:
        picks = self.rng.sample(pop, min(k, len(pop)))
        return max(picks, key=lambda g: g["fitness"] or 0)

    def _llm_mutation(self, best: dict) -> dict | None:
        """Ask the planner model for ONE evidence-based parameter change."""
        schema = {
            "type": "object",
            "properties": {
                "gene": {"type": "string", "enum": list(GENE_SPACE)},
                "new_value": {"type": "number"},
                "rationale": {"type": "string"},
            },
            "required": ["gene", "new_value", "rationale"],
        }
        recent = self.memory.recent_episodes(hours=24 * 14, limit=30)
        evidence = "\n".join(f"- {e['skill']}/{e['kind']}: {e['summary']}" for e in recent)
        messages = [
            {"role": "system", "content": "You tune one strategy parameter of an Amazon FBA product-selection engine based on evidence. Be conservative; move one gene."},
            {"role": "user", "content":
                f"Current best genome (fitness {best['fitness']}):\n{json.dumps(best['params'], indent=2)}\n\n"
                f"Gene bounds: {json.dumps({k: v[1:] for k, v in GENE_SPACE.items()})}\n\n"
                f"Recent factory evidence:\n{evidence}\n\n"
                "Propose the single gene change most likely to raise fitness."},
        ]
        try:
            out = self.llm.chat_json(messages, schema, model=getattr(self.llm, "planner_model", None))
            gene = out["gene"]
            if gene in GENE_SPACE:
                child = dict(best["params"])
                child[gene] = _clamp(gene, float(out["new_value"]))
                self.memory.log_episode("evolution", "llm_mutation",
                                        f"directed mutation {gene} -> {child[gene]}: {out.get('rationale','')[:200]}")
                return _normalize_weights(child)
        except Exception as e:  # LLM mutation is optional; never break the cycle
            self.memory.log_episode("evolution", "llm_mutation_failed", str(e)[:200])
        return None
