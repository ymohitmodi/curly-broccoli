"""The Owner's Console — a local web UI for the whole factory.

    ./df console          → http://127.0.0.1:8787

Design goals:
  - zero new dependencies (stdlib http.server), binds to 127.0.0.1 ONLY
  - every use case: dashboard, approvals with one-click sign-off, candidate
    funnel + outcome logging, skill runs, artifact/report reading, playbook
    and config editing (with YAML validation before save), activity log
  - the Doctor: diagnoses every known failure mode in plain English and
    fixes what is safely fixable with one click
  - long skill runs execute as background jobs the UI polls — the console
    never freezes on a slow model call
"""

from __future__ import annotations

import datetime as dt
import json
import platform
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

from .config import load_config
from .memory import Memory

UI_PATH = Path(__file__).parent / "console_ui.html"

# background skill runs: {job_id: {skill, status, summary, started}}
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()

# directories the file API may touch: key -> (relative dir, allowed suffixes, writable)
FILE_ROOTS = {
    "artifacts": ("workspace/artifacts", (".md",), False),
    "reports":   ("workspace/reports", (".md",), False),
    "playbooks": ("playbooks", (".md",), True),
    "config":    ("config", (".yaml", ".yml"), True),
}


def _mem(cfg) -> Memory:
    return Memory(cfg.db_path)  # fresh connection per request → thread-safe


# --------------------------------------------------------------------------
# data assembly
# --------------------------------------------------------------------------

def overview(cfg) -> dict:
    mem = _mem(cfg)
    try:
        schedule = cfg.harness.get("schedule", {})
        now = dt.datetime.now(dt.timezone.utc)
        skills = []
        for name, every_h in schedule.items():
            last = mem.kv_get(f"lastrun:{name}")
            fails = int(mem.kv_get(f"failures:{name}") or 0)
            due = True
            if last:
                elapsed = (now - dt.datetime.fromisoformat(last)).total_seconds() / 3600
                due = elapsed >= float(every_h) * min(2 ** fails, 8)
            skills.append({"name": name, "every_hours": every_h, "last_run": last,
                           "failures": fails, "due": due})
        cands = mem.list_candidates(limit=500)
        funnel: dict[str, int] = {}
        for c in cands:
            funnel[c["stage"]] = funnel.get(c["stage"], 0) + 1
        verdicts: dict[str, int] = {}
        for c in cands:
            verdicts[c["verdict"] or "?"] = verdicts.get(c["verdict"] or "?", 0) + 1
        genome = mem.active_genome()
        calls = int(mem.kv_get(f"llm_calls:{dt.date.today().isoformat()}") or 0)
        return {
            "skills": skills,
            "approvals_pending": len(mem.list_approvals("pending")),
            "funnel": funnel,
            "verdicts": verdicts,
            "top_pursue": [{"id": c["id"], "name": c["name"], "stage": c["stage"],
                            "composite": c["composite"]}
                           for c in cands if c["verdict"] == "PURSUE"][:5],
            "genome": ({"generation": genome["generation"], "fitness": genome["fitness"]}
                       if genome else None),
            "llm": {"calls_today": calls,
                    "max_per_day": int(cfg.llm("max_calls_per_day", 300)),
                    "mode": cfg.llm("mode", "ollama")},
            "episodes_24h": len(mem.recent_episodes(24)),
        }
    finally:
        mem.close()


def run_skill_job(cfg, skill: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {"skill": skill, "status": "running", "summary": None,
                        "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}

    def worker():
        try:
            from .orchestrator import Orchestrator
            result = Orchestrator(cfg).run_skill(skill)
            status = "error" if str(result.get("summary", "")).startswith("ERROR") else "done"
            with JOBS_LOCK:
                JOBS[job_id].update(status=status, summary=result.get("summary", ""))
        except Exception as e:  # job must never crash the server
            with JOBS_LOCK:
                JOBS[job_id].update(status="error", summary=f"{type(e).__name__}: {e}")

    threading.Thread(target=worker, daemon=True).start()
    return job_id


# --------------------------------------------------------------------------
# the Doctor — every known failure mode, diagnosed and (where safe) fixable
# --------------------------------------------------------------------------

def doctor(cfg) -> list[dict]:
    checks: list[dict] = []

    def add(cid, name, status, detail, fix="", fix_action=None):
        checks.append({"id": cid, "name": name, "status": status, "detail": detail,
                       "fix": fix, "fix_action": fix_action})

    # 1. config
    try:
        assert cfg.objectives.get("mission"), "objectives.yaml missing 'mission'"
        assert cfg.harness.get("schedule"), "harness.yaml missing 'schedule'"
        add("config", "Configuration files", "ok",
            f"{len(cfg.objectives.get('categories', []))} categories, "
            f"{len(cfg.harness.get('schedule', {}))} skills scheduled.")
    except Exception as e:
        add("config", "Configuration files", "fail", str(e),
            "Open the Config tab and restore the missing keys, or restore the file from git.")

    # 2. database + workspace
    try:
        mem = _mem(cfg)
        mem.kv_set("doctor:ping", dt.datetime.now(dt.timezone.utc).isoformat())
        mem.close()
        add("db", "Memory database", "ok", f"Read/write OK at {cfg.db_path.name}.")
    except Exception as e:
        add("db", "Memory database", "fail", str(e),
            "The database file may be locked or corrupted. Restart the service; "
            "worst case, rename workspace/darkfactory.db (the factory rebuilds, "
            "but loses memory).")
    try:
        p = cfg.workspace / ".doctor-write-test"
        p.write_text("ok"); p.unlink()
        add("workspace", "Workspace folder", "ok", str(cfg.workspace))
    except Exception as e:
        add("workspace", "Workspace folder", "fail", str(e),
            "Check disk space and folder permissions.", "create_workspace")

    # 3. the AI brain
    mode = cfg.llm("mode", "ollama")
    if mode == "mock":
        add("ollama", "AI models", "warn",
            "Running in MOCK mode — the pipeline works but all analysis is fake placeholder text.",
            "Fine for testing. For real analysis set llm.mode: ollama in harness.yaml (Config tab).")
    else:
        host = cfg.llm("host", "http://localhost:11434")
        try:
            import requests
            r = requests.get(f"{host}/api/version", timeout=3)
            r.raise_for_status()
            add("ollama", "Ollama daemon", "ok", f"Reachable at {host} (v{r.json().get('version', '?')}).")
            try:
                tags = requests.get(f"{host}/api/tags", timeout=5).json()
                have = {m.get("name", "").split(":latest")[0] for m in tags.get("models", [])}
                have |= {m.get("name", "") for m in tags.get("models", [])}
                missing = [m for m in {cfg.llm("planner_model"), cfg.llm("worker_model"),
                                       cfg.llm("fast_model")} - {None}
                           if m not in have and not m.endswith("-cloud")]
                if missing:
                    add("models", "Configured models", "warn",
                        f"Not found locally: {', '.join(missing)} (cloud models appear after use).",
                        f"Run in Terminal:  ollama pull {missing[0]}   — or pick a model you have "
                        "from `ollama list` and set it in the Config tab.")
                else:
                    add("models", "Configured models", "ok",
                        f"planner={cfg.llm('planner_model')} · worker={cfg.llm('worker_model')}.")
            except Exception:
                add("models", "Configured models", "warn", "Could not list models.",
                    "Run `ollama list` in Terminal to verify your model names.")
        except Exception:
            add("ollama", "Ollama daemon", "fail",
                f"Cannot reach {host} — the factory cannot think without it.",
                "Open the Ollama app (or run `brew services start ollama` in Terminal), "
                "wait 10 seconds, then press Re-check.")

    # 4. token budget
    mem = _mem(cfg)
    try:
        calls = int(mem.kv_get(f"llm_calls:{dt.date.today().isoformat()}") or 0)
        cap = int(cfg.llm("max_calls_per_day", 300))
        if calls >= cap:
            add("budget", "Daily AI budget", "fail",
                f"{calls}/{cap} calls used — the factory is paused until midnight.",
                "Reset the counter if intentional, or raise llm.max_calls_per_day in the Config tab.",
                "reset_budget")
        elif calls >= cap * 0.9:
            add("budget", "Daily AI budget", "warn", f"{calls}/{cap} calls used (>90%).",
                "The factory pauses at the cap and resumes at midnight. No action needed.")
        else:
            add("budget", "Daily AI budget", "ok", f"{calls}/{cap} calls used today.")

        # 5. skill failures
        failing = [(n, int(mem.kv_get(f"failures:{n}") or 0))
                   for n in cfg.harness.get("schedule", {})]
        failing = [(n, f) for n, f in failing if f > 0]
        if failing:
            worst = max(f for _, f in failing)
            add("failures", "Skill failures",
                "fail" if worst >= 3 else "warn",
                "; ".join(f"{n}: {f} consecutive" for n, f in failing),
                "See the last error in the Activity tab. After fixing the cause "
                "(usually Ollama or a data source), reset the counters so skills retry immediately.",
                "reset_failures")
        else:
            add("failures", "Skill failures", "ok", "No skill is in a failure state.")

        # 6. heartbeat
        eps = mem.recent_episodes(26)
        any_run = any(mem.kv_get(f"lastrun:{n}") for n in cfg.harness.get("schedule", {}))
        if not eps and any_run:
            add("heartbeat", "24/7 heartbeat", "warn",
                "No activity in 26h — the Mac was probably asleep or the service stopped.",
                "Plug the Mac in and wake it. If it stays quiet, restart the service:\n"
                "launchctl unload ~/Library/LaunchAgents/com.darkfactory.harness.plist\n"
                "launchctl load ~/Library/LaunchAgents/com.darkfactory.harness.plist")
        else:
            add("heartbeat", "24/7 heartbeat", "ok",
                f"{len(eps)} actions in the last 26h." if eps else "Fresh install — nothing run yet.")

        # 7. approvals aging
        pend = mem.list_approvals("pending")
        old = [a for a in pend
               if (dt.datetime.now(dt.timezone.utc)
                   - dt.datetime.fromisoformat(a["ts"])).days >= 3]
        if old:
            add("approvals", "Approval queue", "warn",
                f"{len(old)} approval(s) waiting more than 3 days — the factory is blocked on you.",
                "Open the Approvals tab and decide. Rejecting is always safe.")
        else:
            add("approvals", "Approval queue", "ok",
                f"{len(pend)} pending, none older than 3 days.")
    finally:
        mem.close()

    # 8. 24/7 service (macOS only)
    if platform.system() == "Darwin":
        try:
            out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=5)
            if "com.darkfactory.harness" in out.stdout:
                add("service", "Background service", "ok", "launchd service is loaded.")
            else:
                add("service", "Background service", "warn",
                    "The 24/7 service is not installed — the factory only runs while the console does.",
                    "Run in Terminal:  ./scripts/install_macos.sh")
        except Exception:
            add("service", "Background service", "warn", "Could not query launchd.",
                "Run `launchctl list | grep darkfactory` in Terminal.")
    return checks


def doctor_fix(cfg, action: str) -> str:
    mem = _mem(cfg)
    try:
        if action == "reset_failures":
            for n in cfg.harness.get("schedule", {}):
                mem.kv_set(f"failures:{n}", "0")
            mem.log_episode("console", "fix", "failure counters reset from console")
            return "All failure counters reset — skills will retry on their normal schedule."
        if action == "reset_budget":
            mem.kv_set(f"llm_calls:{dt.date.today().isoformat()}", "0")
            mem.log_episode("console", "fix", "daily LLM budget counter reset from console")
            return "Daily AI budget counter reset — the factory resumes immediately."
        if action == "create_workspace":
            for p in (cfg.workspace, cfg.reports_dir, cfg.artifacts_dir,
                      cfg.workspace / "inbox", cfg.workspace / "logs"):
                Path(p).mkdir(parents=True, exist_ok=True)
            return "Workspace folders created."
        raise ValueError(f"unknown fix action: {action}")
    finally:
        mem.close()


# --------------------------------------------------------------------------
# safe file access
# --------------------------------------------------------------------------

def _file_root(cfg, key: str) -> tuple[Path, tuple, bool]:
    if key not in FILE_ROOTS:
        raise PermissionError(f"unknown file area: {key}")
    rel, suffixes, writable = FILE_ROOTS[key]
    root = (cfg.root / rel).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root, suffixes, writable


def list_files(cfg, key: str) -> list[dict]:
    root, suffixes, _ = _file_root(cfg, key)
    out = []
    for p in sorted(root.iterdir(), reverse=True):
        if p.is_file() and p.suffix in suffixes:
            out.append({"name": p.name,
                        "modified": dt.datetime.fromtimestamp(p.stat().st_mtime)
                        .isoformat(timespec="minutes"),
                        "size": p.stat().st_size})
    return out


def _safe_path(cfg, key: str, name: str) -> tuple[Path, bool]:
    root, suffixes, writable = _file_root(cfg, key)
    if "/" in name or "\\" in name or name.startswith("."):
        raise PermissionError("invalid file name")
    p = (root / name).resolve()
    if p.parent != root or p.suffix not in suffixes:
        raise PermissionError("path outside allowed area")
    return p, writable


def read_file(cfg, key: str, name: str) -> str:
    p, _ = _safe_path(cfg, key, name)
    return p.read_text(encoding="utf-8")


def write_file(cfg, key: str, name: str, content: str) -> str:
    p, writable = _safe_path(cfg, key, name)
    if not writable:
        raise PermissionError(f"{key} files are read-only deliverables")
    if p.suffix in (".yaml", ".yml"):
        try:
            parsed = yaml.safe_load(content)
            if not isinstance(parsed, dict):
                raise ValueError("top level must be a mapping (key: value pairs)")
        except Exception as e:
            raise ValueError(f"Not saved — invalid YAML: {e}") from e
    p.write_text(content, encoding="utf-8")
    return f"Saved {name}. Changes apply from the next skill run."


# --------------------------------------------------------------------------
# HTTP plumbing
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "darkfactory-console"
    cfg = None  # injected by serve()

    def log_message(self, *a):
        pass

    def _send(self, code: int, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        cfg = self.cfg
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        parts = [p for p in url.path.split("/") if p]
        try:
            if url.path == "/":
                return self._send(200, UI_PATH.read_bytes(), "text/html; charset=utf-8")
            if url.path == "/api/overview":
                return self._send(200, overview(cfg))
            if url.path == "/api/approvals":
                mem = _mem(cfg)
                try:
                    return self._send(200, mem.list_approvals(q.get("status", "pending")))
                finally:
                    mem.close()
            if url.path == "/api/candidates":
                mem = _mem(cfg)
                try:
                    return self._send(200, mem.list_candidates(limit=200))
                finally:
                    mem.close()
            if len(parts) == 3 and parts[:2] == ["api", "candidates"]:
                mem = _mem(cfg)
                try:
                    c = mem.get_candidate(int(parts[2]))
                    if not c:
                        return self._send(404, {"error": "no such candidate"})
                    c["keywords"] = mem.keywords_for(c["id"], limit=60)
                    return self._send(200, c)
                finally:
                    mem.close()
            if url.path == "/api/episodes":
                mem = _mem(cfg)
                try:
                    return self._send(200, mem.recent_episodes(int(q.get("hours", 48)), limit=200))
                finally:
                    mem.close()
            if url.path == "/api/doctor":
                return self._send(200, doctor(cfg))
            if url.path == "/api/files":
                return self._send(200, list_files(cfg, q.get("dir", "artifacts")))
            if url.path == "/api/file":
                return self._send(200, {"name": q.get("name"),
                                        "content": read_file(cfg, q.get("dir", ""), q.get("name", ""))})
            if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
                with JOBS_LOCK:
                    job = JOBS.get(parts[2])
                return self._send(200 if job else 404, job or {"error": "no such job"})
            return self._send(404, {"error": "not found"})
        except PermissionError as e:
            return self._send(403, {"error": str(e)})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        cfg = self.cfg
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        try:
            body = self._body()
            if len(parts) == 3 and parts[:2] == ["api", "approvals"]:
                decision = body.get("decision")
                if decision not in ("approve", "reject"):
                    return self._send(400, {"error": "decision must be approve or reject"})
                mem = _mem(cfg)
                try:
                    aid = int(parts[2])
                    mem.resolve_approval(aid, "approved" if decision == "approve" else "rejected")
                    mem.log_episode("owner", decision, f"approval #{aid} {decision}d from console")
                finally:
                    mem.close()
                return self._send(200, {"ok": True})
            if len(parts) == 4 and parts[:2] == ["api", "candidates"] and parts[3] == "outcome":
                mem = _mem(cfg)
                try:
                    cid = int(parts[2])
                    if not mem.get_candidate(cid):
                        return self._send(404, {"error": "no such candidate"})
                    outcome = {"monthly_units": float(body["monthly_units"]),
                               "margin_pct": float(body["margin_pct"]),
                               "rating": float(body["rating"]),
                               "target_units": cfg.constraint("target_monthly_units", 300)}
                    if body.get("cash_cycle_days"):
                        outcome["cash_conversion_days"] = float(body["cash_cycle_days"])
                    mem.update_candidate(cid, outcome=outcome, stage="live")
                    mem.log_episode("owner", "outcome",
                                    f"candidate #{cid} results logged from console: "
                                    f"{outcome['monthly_units']:.0f} u/mo, "
                                    f"{outcome['margin_pct']:.0%}, {outcome['rating']}★")
                finally:
                    mem.close()
                return self._send(200, {"ok": True,
                                        "message": "Logged. Darwin uses this at the next evolution step."})
            if len(parts) == 4 and parts[:2] == ["api", "skills"] and parts[3] == "run":
                from .skills import SKILLS
                if parts[2] not in SKILLS:
                    return self._send(404, {"error": f"unknown skill {parts[2]}"})
                return self._send(200, {"job": run_skill_job(cfg, parts[2])})
            if url.path == "/api/doctor/fix":
                return self._send(200, {"ok": True, "message": doctor_fix(cfg, body.get("action", ""))})
            if url.path == "/api/file":
                msg = write_file(cfg, body.get("dir", ""), body.get("name", ""),
                                 body.get("content", ""))
                return self._send(200, {"ok": True, "message": msg})
            return self._send(404, {"error": "not found"})
        except PermissionError as e:
            return self._send(403, {"error": str(e)})
        except (ValueError, KeyError) as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})


def serve(port: int = 8787, cfg=None, open_browser: bool = True) -> ThreadingHTTPServer:
    cfg = cfg or load_config()
    Handler.cfg = cfg
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{httpd.server_port}"
    print(f"[darkfactory] console at {url}  (Ctrl-C to stop)")
    if open_browser:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    return httpd
