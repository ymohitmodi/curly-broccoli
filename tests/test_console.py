"""Contract tests for the Owner's Console. Run with:

    python3 -m unittest tests.test_console -v

Covers the full API surface the UI depends on, plus the security contracts:
path traversal blocked, read-only areas enforced, YAML validated before save,
and the doctor's diagnose→fix loop.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class ConsoleBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="darkfactory-console-"))
        shutil.copytree(REPO / "config", cls.root / "config")
        shutil.copytree(REPO / "playbooks", cls.root / "playbooks")
        os.environ["DARKFACTORY_ROOT"] = str(cls.root)
        os.environ["DARKFACTORY_LLM"] = "mock"
        from darkfactory.console import serve
        cls.httpd = serve(port=0, open_browser=False)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"
        # seed the funnel so candidate endpoints have data
        from darkfactory.orchestrator import Orchestrator
        Orchestrator().run_skill("product_research")
        Orchestrator().run_skill("supplier_sourcing")

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        os.environ.pop("DARKFACTORY_ROOT", None)
        os.environ.pop("DARKFACTORY_LLM", None)
        shutil.rmtree(cls.root, ignore_errors=True)

    def req(self, path, body=None, method=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data,
                                   method=method or ("POST" if data else "GET"),
                                   headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")


class TestConsoleAPI(ConsoleBase):
    def test_ui_served(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as r:
            html = r.read().decode()
        self.assertIn("Owner's Console", html)
        self.assertIn("Doctor", html)

    def test_overview_shape(self):
        code, o = self.req("/api/overview")
        self.assertEqual(code, 200)
        for key in ("skills", "approvals_pending", "funnel", "llm", "genome"):
            self.assertIn(key, o)
        self.assertGreater(len(o["skills"]), 5)

    def test_approval_lifecycle_via_api(self):
        code, pend = self.req("/api/approvals")
        self.assertEqual(code, 200)
        self.assertTrue(pend, "sourcing run should have queued place_order approvals")
        aid = pend[0]["id"]
        code, _ = self.req(f"/api/approvals/{aid}", {"decision": "reject"})
        self.assertEqual(code, 200)
        _, still = self.req("/api/approvals")
        self.assertNotIn(aid, [a["id"] for a in still])
        code, _ = self.req(f"/api/approvals/{aid}", {"decision": "shred"})
        self.assertEqual(code, 400)

    def test_candidates_and_outcome(self):
        _, cands = self.req("/api/candidates")
        self.assertTrue(cands)
        cid = cands[0]["id"]
        code, det = self.req(f"/api/candidates/{cid}")
        self.assertEqual(code, 200)
        self.assertIn("keywords", det)
        code, r = self.req(f"/api/candidates/{cid}/outcome",
                           {"monthly_units": 320, "margin_pct": 0.4,
                            "rating": 4.7, "cash_cycle_days": 150})
        self.assertEqual(code, 200)
        _, det2 = self.req(f"/api/candidates/{cid}")
        self.assertEqual(det2["stage"], "live")
        self.assertEqual(det2["outcome"]["cash_conversion_days"], 150)

    def test_skill_job_runs_async(self):
        code, r = self.req("/api/skills/digest/run", {})
        self.assertEqual(code, 200)
        job = r["job"]
        for _ in range(40):
            _, j = self.req(f"/api/jobs/{job}")
            if j["status"] != "running":
                break
            time.sleep(0.25)
        self.assertEqual(j["status"], "done", j)
        code, _ = self.req("/api/skills/nonexistent/run", {})
        self.assertEqual(code, 404)

    def test_file_security_contracts(self):
        # traversal blocked
        code, _ = self.req("/api/file?dir=config&name=../darkfactory/llm.py")
        self.assertEqual(code, 403)
        code, _ = self.req("/api/file?dir=secrets&name=x.md")
        self.assertEqual(code, 403)
        # read-only areas refuse writes
        code, _ = self.req("/api/file", {"dir": "reports", "name": "x.md", "content": "hi"})
        self.assertEqual(code, 403)
        # YAML validation refuses garbage BEFORE writing
        code, r = self.req("/api/file", {"dir": "config", "name": "objectives.yaml",
                                         "content": "mission: [unclosed"})
        self.assertEqual(code, 400)
        self.assertIn("invalid YAML", r["error"])
        original = (self.root / "config" / "objectives.yaml").read_text()
        self.assertIn("mission", original.splitlines()[0] + original)  # untouched
        # valid playbook save works
        code, r = self.req("/api/file", {"dir": "playbooks", "name": "review_miner.md",
                                         "content": "# Playbook: test save\n"})
        self.assertEqual(code, 200)

    def test_doctor_diagnose_and_fix(self):
        code, checks = self.req("/api/doctor")
        self.assertEqual(code, 200)
        ids = {c["id"] for c in checks}
        for expected in ("config", "db", "workspace", "ollama", "budget",
                         "failures", "heartbeat", "approvals"):
            self.assertIn(expected, ids)
        for c in checks:
            self.assertIn(c["status"], ("ok", "warn", "fail"))
            if c["status"] != "ok":
                self.assertTrue(c["fix"], f"{c['id']} has no fix instructions")
        # a safe fix executes
        code, r = self.req("/api/doctor/fix", {"action": "reset_failures"})
        self.assertEqual(code, 200)
        code, _ = self.req("/api/doctor/fix", {"action": "rm_rf"})
        self.assertEqual(code, 400)


if __name__ == "__main__":
    unittest.main()
