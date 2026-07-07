"""Tests for the quality gates and the judge-vs-policy fitness fix.

    python3 -m unittest tests.test_quality -v
"""

from __future__ import annotations

import math
import unittest

from darkfactory import quality


class TestPPCMath(unittest.TestCase):
    def test_smoothed_cvr_resists_small_samples(self):
        # 1 order / 3 clicks must NOT read as 33%
        self.assertLess(quality.smoothed_cvr(1, 3), 0.20)
        # 0 orders / 10 clicks must NOT read as 0%
        self.assertGreater(quality.smoothed_cvr(0, 10), 0.03)
        # large samples converge to the empirical rate
        self.assertAlmostEqual(quality.smoothed_cvr(100, 1000), 0.10, delta=0.005)

    def test_target_cpc_formula(self):
        # 30% ACOS × $27.50 AOV × 10% CVR = $0.825 — hand-checked
        self.assertAlmostEqual(quality.target_cpc(0.30, 27.50, 0.10), 0.82, delta=0.011)

    def test_negative_confidence_clicks(self):
        # ln(0.05)/ln(0.9) = 28.4 → 29 clicks for 95% confidence at 10% CVR
        self.assertEqual(quality.negative_confidence_clicks(0.95, 0.10), 29)
        self.assertEqual(quality.negative_confidence_clicks(0.90, 0.10),
                         math.ceil(math.log(0.10) / math.log(0.90)))


class TestListingQA(unittest.TestCase):
    GOOD = {
        "title": "BrandX Magnetic Spice Rack for Refrigerator — N52 Magnets, Anti-Slip Rails, 16 Jar Capacity, Space Saving Kitchen Organizer for Fridge Side and Metal Surfaces",
        "bullets": [
            "NEVER SLIDES: full-back N52 magnet sheet holds 8 kg fully loaded on any fridge",
            "PROTECTS YOUR FRIDGE: rubber-lined rails prevent scratches on stainless doors",
            "FITS 16 JARS: two tiers sized for standard 4 oz spice jars with room to spare",
            "BUILT TO LAST: powder-coated steel resists chips, rust and kitchen grease",
            "IN THE BOX: rack, surface prep wipe, and quick-start placement guide included",
        ],
        "description": "x" * 800,
        "backend_search_terms": "condimento organizador cocina pantry door shelf herb tin holder camper rv",
    }

    def test_good_listing_scores_high(self):
        qa = quality.listing_qa(dict(self.GOOD), title_keywords=["magnetic spice rack"])
        self.assertGreaterEqual(qa["score"], qa["max"] - 1, qa["failures"])

    def test_policy_violations_caught(self):
        bad = dict(self.GOOD)
        bad["title"] = "BEST SELLER #1 AMAZING Spice Rack guarantee free shipping"
        qa = quality.listing_qa(bad, title_keywords=["spice rack"])
        names = {f["name"] for f in qa["failures"]}
        self.assertIn("no policy-risk phrases", names)
        self.assertIn("title substantial (>= 80 chars)", names)

    def test_backend_dup_and_bytes(self):
        bad = dict(self.GOOD)
        bad["backend_search_terms"] = "magnetic spice rack refrigerator " * 12
        qa = quality.listing_qa(bad, title_keywords=["magnetic spice rack"])
        names = {f["name"] for f in qa["failures"]}
        self.assertIn("backend terms within 249 bytes", names)
        self.assertIn("backend does not repeat title words", names)


class TestKeywordGate(unittest.TestCase):
    def test_dedupe_and_mix(self):
        kws = ([{"keyword": "Magnetic Spice Rack", "tier": "head", "intent": "buy",
                 "relevance": 0.9, "placement": "title"},
                {"keyword": "magnetic  spice rack", "tier": "head", "intent": "buy",
                 "relevance": 0.9, "placement": "title"}]  # dup after normalize
               + [{"keyword": f"long tail term number {i} for fridge", "tier": "longtail",
                   "intent": "problem", "relevance": 0.5, "placement": "backend"}
                  for i in range(30)])
        qa = quality.clean_keyword_map(kws, longtail_bias=0.60)
        self.assertEqual(len(qa["keywords"]), 31)          # dup folded
        self.assertGreater(qa["longtail_fraction"], 0.9)
        self.assertFalse(qa["mix_ok"])                     # 97% ≫ 60%+18%
        self.assertTrue(qa["count_ok"])


class TestEvidenceAndJudge(unittest.TestCase):
    def test_evidence_damp(self):
        scores = {"demand": 0.8, "margin_potential": 0.6}
        damped, was = quality.evidence_damp(scores, "it feels like a strong market")
        self.assertTrue(was)
        self.assertAlmostEqual(damped["demand"], 0.64)
        same, was = quality.evidence_damp(scores, "33k searches, top10 avg 620 reviews")
        self.assertFalse(was)
        self.assertEqual(same, scores)

    def test_objective_score_orders_correctly(self):
        from darkfactory.config import load_config
        cfg = load_config()
        strong = {"est_monthly_revenue_usd": 160000, "top10_avg_reviews": 300, "trend_12m": 0.65}
        weak = {"est_monthly_revenue_usd": 45000, "top10_avg_reviews": 1300, "trend_12m": 0.45}
        econ_good = {"net_margin_pct": 0.42, "roi_pct": 1.6}
        econ_thin = {"net_margin_pct": 0.30, "roi_pct": 0.8}
        s1 = quality.objective_score(cfg, strong, econ_good)
        s2 = quality.objective_score(cfg, weak, econ_thin)
        self.assertGreater(s1, s2)
        self.assertGreater(s1, 0.6)
        self.assertLess(s2, 0.55)
        self.assertEqual(quality.objective_score(cfg, {}, None), 0.0)

    def test_fitness_uses_judge_not_composite(self):
        """A genome whose candidates have inflated composites but weak
        objective scores must NOT outrank one with the reverse."""
        import os, tempfile
        from darkfactory.memory import Memory
        from darkfactory.evolution import genome_fitness
        m = Memory(os.path.join(tempfile.mkdtemp(), "t.db"))
        flatterer = m.save_genome(1, {"w": 1})
        honest = m.save_genome(1, {"w": 1})
        m.add_candidate("puffed", "c", "n", flatterer, {}, {"objective": 0.30}, 0.95, "PURSUE")
        m.add_candidate("solid", "c", "n", honest, {}, {"objective": 0.80}, 0.55, "PURSUE")
        self.assertGreater(genome_fitness(m, honest), genome_fitness(m, flatterer))


if __name__ == "__main__":
    unittest.main()
