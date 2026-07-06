"""Deterministic quality gates — code that judges LLM output before it is
accepted. Every skill's output passes through the relevant gate; failures
either trigger one corrective re-prompt or are repaired/damped in code.

The principle: the model PROPOSES, code DISPOSES. Anything checkable without
a model (lengths, math, mix ratios, banned phrases, evidence citations) is
checked without a model.
"""

from __future__ import annotations

import math
import re

# ---------------------------------------------------------------------------
# PPC math — the real formulas, not relative nudges.
# ---------------------------------------------------------------------------

CVR_PRIOR = 0.10       # cross-category Amazon CVR prior (~8-15% is normal)
CVR_PRIOR_WEIGHT = 8   # pseudo-clicks of prior belief (Bayesian smoothing)


def smoothed_cvr(orders: float, clicks: float) -> float:
    """Bayesian-smoothed conversion rate: keeps 3 clicks / 1 order from
    reading as 33% CVR, and 10 clicks / 0 orders from reading as 0%."""
    return (orders + CVR_PRIOR * CVR_PRIOR_WEIGHT) / (clicks + CVR_PRIOR_WEIGHT)


def target_cpc(target_acos: float, aov: float, cvr: float) -> float:
    """The bid a term is actually worth:
        profit-neutral CPC at target ACOS = ACOS × order value × CVR."""
    return round(target_acos * aov * cvr, 2)


def negative_confidence_clicks(confidence: float = 0.95, cvr: float = CVR_PRIOR) -> int:
    """Clicks with ZERO orders needed before negativing at `confidence`.
    P(0 orders | true CVR >= cvr) = (1-cvr)^n  =>  n = ln(1-conf)/ln(1-cvr).
    At 95% confidence and a 10% CVR prior: 29 clicks."""
    return math.ceil(math.log(1 - confidence) / math.log(1 - cvr))


# ---------------------------------------------------------------------------
# Listing QA — Amazon policy + conversion checklist, scored in code.
# ---------------------------------------------------------------------------

BANNED_PHRASES = [
    "best seller", "bestseller", "#1", "no. 1", "top rated", "guarantee",
    "guaranteed", "free shipping", "sale", "cheapest", "hot item",
    "money back", "refund", "fda approved", "anti-bacterial",
]
CAPS_ALLOWLIST = {"BPA", "USA", "USB", "LED", "N52", "XL", "XXL", "PVC", "ABS",
                  "FBA", "UV", "SGS", "FDA", "AQL", "PC", "TPU", "EVA", "OK"}


def listing_qa(out: dict, title_keywords: list[str] | None = None) -> dict:
    """Score a listing draft against a deterministic checklist.
    Returns {score, max, checks: [{name, passed, detail}]}."""
    checks: list[dict] = []

    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    title = out.get("title", "")
    bullets = out.get("bullets", [])
    desc = out.get("description", "")
    backend = out.get("backend_search_terms", "")
    all_text = " ".join([title] + bullets + [desc]).lower()

    check("title within 200 chars", len(title) <= 200, f"{len(title)} chars")
    check("title substantial (>= 80 chars)", len(title) >= 80, f"{len(title)} chars")
    if title_keywords:
        head = title[:80].lower()
        hit = any(k.lower() in head for k in title_keywords)
        check("primary keyword in first 80 chars (mobile cutoff)", hit,
              "front-load the strongest buy-intent term")
    check("exactly 5 bullets", len(bullets) == 5, f"{len(bullets)} bullets")
    check("bullets within 250 chars", all(len(b) <= 250 for b in bullets))
    hooked = sum(1 for b in bullets if re.match(r"^[A-Z][A-Z0-9 &'\-]{2,30}[:–\-]", b))
    check("bullets open with a benefit hook (HOOK: ...)", hooked >= 4,
          f"{hooked}/5 hooked")
    check("description 600-2500 chars", 600 <= len(desc) <= 2500, f"{len(desc)} chars")

    banned_hits = [p for p in BANNED_PHRASES if p in all_text]
    check("no policy-risk phrases", not banned_hits, ", ".join(banned_hits[:4]))
    emoji_hit = re.search(r"[\U0001F300-\U0001FAFF✀-➿]", title + "".join(bullets))
    check("no emojis in title/bullets", not emoji_hit)
    shouting = [w for w in re.findall(r"\b[A-Z]{4,}\b", title) if w not in CAPS_ALLOWLIST]
    check("no ALL-CAPS shouting in title", not shouting, ", ".join(shouting[:4]))

    bb = backend.encode("utf-8")
    check("backend terms within 249 bytes", len(bb) <= 249, f"{len(bb)} bytes")
    title_words = set(re.findall(r"[a-z]+", title.lower()))
    dup = [w for w in re.findall(r"[a-z]+", backend.lower()) if w in title_words]
    check("backend does not repeat title words", len(dup) <= 2,
          f"wasted: {', '.join(sorted(set(dup))[:6])}" if dup else "")

    passed = sum(1 for c in checks if c["passed"])
    return {"score": passed, "max": len(checks), "checks": checks,
            "failures": [c for c in checks if not c["passed"]]}


# ---------------------------------------------------------------------------
# Keyword map QA — mix, dedupe, and volume enforced in code.
# ---------------------------------------------------------------------------

def clean_keyword_map(keywords: list[dict], longtail_bias: float) -> dict:
    """Normalize + dedupe a keyword map and judge its tier mix.
    Returns {keywords, longtail_fraction, mix_ok, count_ok, notes}."""
    seen: set[str] = set()
    cleaned: list[dict] = []
    for k in keywords:
        term = re.sub(r"\s+", " ", str(k.get("keyword", "")).strip().lower())
        if not term or term in seen or len(term.split()) > 8:
            continue
        seen.add(term)
        k = dict(k)
        k["keyword"] = term
        k["relevance"] = max(0.0, min(1.0, float(k.get("relevance", 0.5))))
        cleaned.append(k)

    n = len(cleaned)
    lt = sum(1 for k in cleaned if k.get("tier") == "longtail")
    frac = lt / n if n else 0.0
    return {
        "keywords": cleaned,
        "longtail_fraction": round(frac, 3),
        "mix_ok": abs(frac - longtail_bias) <= 0.18,
        "count_ok": n >= 30,
        "notes": (f"{n} unique terms, {frac:.0%} long-tail vs {longtail_bias:.0%} target"),
    }


# ---------------------------------------------------------------------------
# Evidence discipline — scores must cite the numbers they were given.
# ---------------------------------------------------------------------------

def evidence_damp(scores: dict, evidence: str, damp: float = 0.8) -> tuple[dict, bool]:
    """A score without cited numbers is an opinion. If the evidence string
    contains no digits from the market data, damp all subscores."""
    has_numbers = bool(re.search(r"\d", evidence or ""))
    if has_numbers:
        return scores, False
    return {k: round(float(v) * damp, 3) for k, v in scores.items()}, True


# ---------------------------------------------------------------------------
# Objective candidate quality — the JUDGE for evolution fitness.
# Computed from market data + deterministic economics, never from the
# genome-weighted composite (that would let genomes grade their own homework).
# ---------------------------------------------------------------------------

def objective_score(cfg, market: dict, econ: dict | None) -> float:
    """0-1 quality judged by code: margin strength, ROI strength, demand
    depth, and attackability of the review moat."""
    if not market:
        return 0.0
    floor = cfg.constraint("min_net_margin_pct", 0.35)
    roi_floor = cfg.constraint("min_roi_pct", 1.0)
    demand_floor = cfg.constraint("min_monthly_revenue_niche_usd", 40000)
    moat_cap = cfg.constraint("max_top10_avg_reviews", 900)

    margin_n = roi_n = 0.5
    if econ:
        margin_n = _clamp((econ["net_margin_pct"] - floor) / max(floor, 0.01) * 2 + 0.5)
        roi_n = _clamp((econ["roi_pct"] - roi_floor) / max(roi_floor, 0.01) + 0.5)
    demand_n = _clamp(market.get("est_monthly_revenue_usd", 0) / (demand_floor * 4))
    moat = market.get("top10_avg_reviews", moat_cap)
    moat_n = _clamp(1.0 - moat / max(moat_cap * 1.5, 1))
    trend_n = _clamp(market.get("trend_12m", 0.5))

    return round(0.30 * margin_n + 0.25 * roi_n + 0.20 * demand_n
                 + 0.15 * moat_n + 0.10 * trend_n, 4)


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))
