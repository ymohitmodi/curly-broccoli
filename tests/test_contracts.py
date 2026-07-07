"""Contract tests for the dark factory. Run with:

    python3 -m unittest tests.test_contracts -v

Covers every seam that could break silently:
  - skill registry ↔ schedule ↔ genome-gene contracts
  - Ollama /api/chat wire contract (request shape validated by a strict stub,
    response envelope parsing, malformed-JSON repair retry)
  - deterministic money math vs. hand-computed values
  - Amazon listing field limits (bytes, not chars, for backend terms)
  - approval queue lifecycle
  - orchestrator failure isolation, backoff counting, recovery
  - daily LLM budget circuit breaker
  - full end-to-end pipeline in mock mode
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _make_root() -> Path:
    """Isolated project root (config copied, fresh workspace/db)."""
    root = Path(tempfile.mkdtemp(prefix="darkfactory-test-"))
    shutil.copytree(REPO / "config", root / "config")
    shutil.copytree(REPO / "playbooks", root / "playbooks")
    return root


class Base(unittest.TestCase):
    def setUp(self):
        self.root = _make_root()
        os.environ["DARKFACTORY_ROOT"] = str(self.root)
        os.environ["DARKFACTORY_LLM"] = "mock"

    def tearDown(self):
        os.environ.pop("DARKFACTORY_ROOT", None)
        os.environ.pop("DARKFACTORY_LLM", None)
        shutil.rmtree(self.root, ignore_errors=True)

    def orch(self):
        from darkfactory.orchestrator import Orchestrator
        return Orchestrator()


class TestInternalContracts(Base):
    def test_schedule_matches_registry(self):
        from darkfactory.skills import SKILLS
        o = self.orch()
        sched = set(o.cfg.harness.get("schedule", {}))
        self.assertEqual(sched, set(SKILLS))

    def test_genes_used_are_defined(self):
        import re
        from darkfactory.evolution import GENE_SPACE
        used = set()
        for p in (REPO / "darkfactory").rglob("*.py"):
            used |= set(re.findall(r'params\.get\("([a-z_]+)"', p.read_text()))
        self.assertFalse(used - set(GENE_SPACE), f"undefined genes referenced: {used - set(GENE_SPACE)}")

    def test_weights_normalized_after_mutation(self):
        import random
        from darkfactory.evolution import WEIGHT_GENES, default_genome, mutate, _normalize_weights
        g = mutate(_normalize_weights(default_genome()), 0.3, random.Random(1))
        self.assertAlmostEqual(sum(g[w] for w in WEIGHT_GENES), 1.0, places=2)


class TestEconomics(Base):
    def test_unit_economics_hand_math(self):
        from darkfactory import economics
        e = economics.UnitEconomics(sale_price=29.99, fob_unit=3.9, unit_weight_kg=0.9).compute()
        # landed = 3.9 + 0.9*1.9 + 3.9*0.35 + 0.30 = 7.275
        self.assertAlmostEqual(e["landed_cost"], 7.275, delta=0.011)
        # fba = 5.4 * 1.035
        self.assertAlmostEqual(e["fba_fee"], 5.589, delta=0.011)
        self.assertAlmostEqual(e["net_margin_pct"], 0.3527, delta=0.001)

    def test_cash_plan_hand_math(self):
        from darkfactory import economics
        from darkfactory.config import load_config
        p = economics.launch_cash_plan(load_config(), 500, 7.275, 10.58, 300, launch_ad_budget=2000)
        self.assertEqual(p["live_day"], 82)          # 30 prod + 45 freight + 7 checkin
        self.assertEqual(p["sellthrough_days"], 50)  # 500u @ 10/day
        self.assertEqual(p["cash_recovered_day"], 146)

    def test_reorder_low_inventory_exposure(self):
        from darkfactory import economics
        from darkfactory.config import load_config
        r = economics.reorder_plan(load_config(), 260, 0, 320, cover_target_days=75)
        self.assertTrue(r["low_inventory_fee_exposure"])   # 24.4d < 35d threshold
        self.assertEqual(r["reorder_point_days"], 117)     # 82 lead + 35 threshold
        self.assertTrue(r["must_reorder_now"])


class TestListingLimits(Base):
    def test_amazon_field_limits_enforced(self):
        from darkfactory.skills.listing_writer import ListingWriter
        out, _ = ListingWriter._enforce_limits({
            "title": "x" * 300, "bullets": ["b" * 300] * 7,
            "backend_search_terms": "wörd " * 80,  # multibyte: bytes != chars
            "description": "d", "a_plus_outline": [], "main_image_brief": ""})
        self.assertLessEqual(len(out["title"]), 200)
        self.assertEqual(len(out["bullets"]), 5)
        self.assertTrue(all(len(b) <= 250 for b in out["bullets"]))
        self.assertLessEqual(len(out["backend_search_terms"].encode("utf-8")), 249)


class TestApprovals(Base):
    def test_lifecycle(self):
        o = self.orch()
        aid = o.memory.add_approval("s", "place_order", {"x": 1})
        self.assertEqual(o.memory.list_approvals("pending")[0]["id"], aid)
        o.memory.resolve_approval(aid, "approved")
        self.assertFalse(o.memory.list_approvals("pending"))
        self.assertEqual(o.memory.list_approvals("approved")[0]["payload"], {"x": 1})
        with self.assertRaises(AssertionError):
            o.memory.resolve_approval(aid, "bogus")


class TestOrchestrator(Base):
    def test_failure_isolation_and_recovery(self):
        o = self.orch()
        o.hub.market_provider = "spapi"  # unconfigured on purpose → NotConfigured
        self.assertTrue(o.run_skill("product_research")["summary"].startswith("ERROR"))
        self.assertEqual(o.memory.kv_get("failures:product_research"), "1")
        # other skills unaffected
        self.assertIn("Digest written", o.run_skill("digest")["summary"])
        # recovery resets the backoff counter
        o.hub.market_provider = "sample"
        self.assertFalse(o.run_skill("product_research")["summary"].startswith("ERROR"))
        self.assertEqual(o.memory.kv_get("failures:product_research"), "0")

    def test_due_scheduling(self):
        o = self.orch()
        self.assertEqual(set(o.due_skills()), set(o.cfg.harness["schedule"]))
        o.run_skill("digest")
        self.assertNotIn("digest", o.due_skills())

    def test_budget_breaker(self):
        from darkfactory.llm import BudgetExceeded, OllamaClient
        o = self.orch()
        c = OllamaClient(o.cfg, memory=o.memory)
        c.max_calls_per_day = 2
        c._check_budget(); c._check_budget()
        with self.assertRaises(BudgetExceeded):
            c._check_budget()


class _StrictOllamaStub(BaseHTTPRequestHandler):
    """Validates the exact /api/chat request contract; any drift → 400.
    First schema-formatted call returns malformed JSON to force the
    client's repair-retry path."""
    state = {"schema_calls": 0}

    def log_message(self, *a):
        pass

    def do_POST(self):
        from darkfactory.llm import _fill_schema
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ok = (self.path == "/api/chat"
              and isinstance(body.get("model"), str) and body["model"]
              and isinstance(body.get("messages"), list) and body["messages"]
              and all(m.get("role") in ("system", "user", "assistant")
                      and isinstance(m.get("content"), str) for m in body["messages"])
              and body.get("stream") is False
              and isinstance(body.get("options", {}).get("temperature"), (int, float)))
        if not ok:
            self.send_response(400); self.end_headers(); return
        fmt = body.get("format")
        if isinstance(fmt, dict):
            self.state["schema_calls"] += 1
            content = ("here you go {nope" if self.state["schema_calls"] == 1
                       else json.dumps(_fill_schema(fmt)))
        else:
            content = "plain reply"
        data = json.dumps({"model": body["model"], "done": True,
                           "message": {"role": "assistant", "content": content}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class TestOllamaWireContract(Base):
    def test_chat_json_with_repair_against_strict_stub(self):
        _StrictOllamaStub.state["schema_calls"] = 0
        server = HTTPServer(("127.0.0.1", 0), _StrictOllamaStub)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            os.environ["DARKFACTORY_LLM"] = "ollama"
            os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{server.server_port}"
            o = self.orch()
            schema = {"type": "object", "properties": {"verdict": {"type": "string"}},
                      "required": ["verdict"]}
            out = o.llm.chat_json([{"role": "user", "content": "test"}], schema)
            self.assertIn("verdict", out)
            self.assertEqual(_StrictOllamaStub.state["schema_calls"], 2)  # repair happened
        finally:
            server.shutdown()
            os.environ.pop("OLLAMA_HOST", None)


class TestEndToEnd(Base):
    def test_full_pipeline_mock(self):
        o = self.orch()
        for skill in o.cfg.harness["schedule"]:
            result = o.run_skill(skill)
            self.assertFalse(result["summary"].startswith("ERROR"),
                             f"{skill}: {result['summary']}")
        # funnel produced candidates and gated approvals
        self.assertTrue(o.memory.list_candidates())
        self.assertTrue(o.memory.list_approvals("pending"))


if __name__ == "__main__":
    unittest.main()
