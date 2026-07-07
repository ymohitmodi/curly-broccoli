"""Tests for the validation ladder, human task queue, data importer, and
test-batch economics.

    python3 -m unittest tests.test_pipeline -v
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="darkfactory-pipe-"))
        shutil.copytree(REPO / "config", self.root / "config")
        shutil.copytree(REPO / "playbooks", self.root / "playbooks")
        os.environ["DARKFACTORY_ROOT"] = str(self.root)
        os.environ["DARKFACTORY_LLM"] = "mock"

    def tearDown(self):
        os.environ.pop("DARKFACTORY_ROOT", None)
        os.environ.pop("DARKFACTORY_LLM", None)
        shutil.rmtree(self.root, ignore_errors=True)


class TestLadder(Base):
    def test_full_gate_walk(self):
        """PURSUE candidate → auto-pass G1 → tasks at G2 → evidence → G3 →
        capital gate G4 requires an approval → approval applies next run."""
        from darkfactory.orchestrator import Orchestrator
        o = Orchestrator()
        o.run_skill("product_research")
        cand = o.memory.list_candidates(verdict="PURSUE")[0]

        o.run_skill("stage_gate")
        cand = o.memory.get_candidate(cand["id"])
        self.assertEqual(cand["data"]["gate"], "G2_validate")  # G1 auto-passed
        tasks = [t for t in o.memory.list_tasks("open") if t["candidate_id"] == cand["id"]]
        self.assertEqual({t["evidence_flag"] for t in tasks},
                         {"demand_verified", "concept_poll_won", "three_quotes_in"})

        # tasks are idempotent — a second run must not duplicate them
        o.run_skill("stage_gate")
        tasks2 = [t for t in o.memory.list_tasks("open") if t["candidate_id"] == cand["id"]]
        self.assertEqual(len(tasks2), len(tasks))

        # complete G2 evidence → advances to G3 (not a capital gate)
        for t in tasks:
            o.memory.complete_task(t["id"])
        o.run_skill("stage_gate")
        cand = o.memory.get_candidate(cand["id"])
        self.assertEqual(cand["data"]["gate"], "G3_sample")

        # complete G3 → G4 is a CAPITAL gate: held pending approval
        for t in o.memory.list_tasks("open"):
            if t["candidate_id"] == cand["id"]:
                o.memory.complete_task(t["id"])
        o.run_skill("stage_gate")
        cand = o.memory.get_candidate(cand["id"])
        self.assertEqual(cand["data"]["gate"], "G3_sample")  # NOT advanced
        pend = [a for a in o.memory.list_approvals("pending") if a["action"] == "advance_gate"]
        self.assertTrue(pend)
        self.assertEqual(pend[0]["payload"]["to"], "G4_test_batch")
        self.assertTrue(pend[0]["payload"]["kill_criteria_next"])  # pre-committed kills travel with the ask

        # a second run must not queue a duplicate approval
        o.run_skill("stage_gate")
        pend2 = [a for a in o.memory.list_approvals("pending") if a["action"] == "advance_gate"
                 and a["payload"]["candidate_id"] == cand["id"]]
        self.assertEqual(len(pend2), 1)

        # approve → next run applies the advancement
        o.memory.resolve_approval(pend[0]["id"], "approved")
        o.run_skill("stage_gate")
        cand = o.memory.get_candidate(cand["id"])
        self.assertEqual(cand["data"]["gate"], "G4_test_batch")

    def test_task_completion_records_evidence(self):
        from darkfactory.memory import Memory
        from darkfactory.config import load_config
        m = Memory(load_config().db_path)
        cid = m.add_candidate("x", "c", "n", None, {}, {}, 0.7, "PURSUE")
        tid = m.add_task(cid, "G2_validate", "demand_verified", "t", "i")
        m.complete_task(tid)
        self.assertTrue(m.get_candidate(cid)["data"]["gate_evidence"]["demand_verified"])


class TestImporter(Base):
    def test_helium10_style_csv(self):
        from darkfactory.datasources.imports import load_inbox_market
        from darkfactory.config import load_config
        cfg = load_config()
        inbox = cfg.workspace / "inbox" / "market"
        inbox.mkdir(parents=True)
        (inbox / "blackbox.csv").write_text(
            "Keyword,Category,Price,Reviews,Revenue,Search Volume,Weight\n"
            'magnetic knife strip,"Home & Kitchen",$24.99,"412","$98,000",21000,0.6\n'
            "bad row,,,,,\n", encoding="utf-8")
        rows, warnings = load_inbox_market(cfg.workspace)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["niche"], "magnetic knife strip")
        self.assertEqual(r["avg_price"], 24.99)
        self.assertEqual(r["est_monthly_revenue_usd"], 98000)
        self.assertEqual(r["top10_avg_reviews"], 412)
        self.assertTrue(any("imported 1 rows" in w for w in warnings))

    def test_real_data_preempts_sample(self):
        from darkfactory.datasources import DataHub
        from darkfactory.config import load_config
        cfg = load_config()
        hub = DataHub(cfg)
        self.assertTrue(len(hub.market_snapshot(["Home & Kitchen"])) > 1)  # fixtures
        inbox = cfg.workspace / "inbox" / "market"
        inbox.mkdir(parents=True)
        (inbox / "mine.csv").write_text("keyword,price\nsolo niche,29.99\n", encoding="utf-8")
        snap = hub.market_snapshot(["Home & Kitchen"])
        self.assertEqual(len(snap), 1)  # your data wins outright
        self.assertEqual(snap[0]["niche"], "solo niche")


class TestBatchEconomics(Base):
    def test_test_batch_plan(self):
        from darkfactory import economics
        from darkfactory.config import load_config
        cfg = load_config()
        p = economics.test_batch_plan(cfg, fob_unit=3.9, unit_weight_kg=0.9,
                                      sale_price=29.99, units=200)
        # air landed: 3.9 + 0.9*6.5 (5.85) + 1.365 duty + 0.30 = 11.415
        self.assertAlmostEqual(p["unit_economics_at_air"]["landed_cost"], 11.42, delta=0.02)
        # 200 units would bust the $2,000 tranche at this landed cost —
        # the plan must auto-size down to fit (cap/1.5 = $1,333 → 116 units)
        self.assertTrue(p["sized_down"])
        self.assertEqual(p["units_requested"], 200)
        self.assertLessEqual(p["all_in"], p["cap_usd"])   # within the 25% tranche
        self.assertLess(p["max_loss"], p["all_in"])        # liquidation recovers something
        self.assertEqual(p["days_to_signal"], 61)


if __name__ == "__main__":
    unittest.main()
