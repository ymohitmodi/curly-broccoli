"""The 24/7 loop.

Wakes every minute, runs whatever skills are due (per-skill cadence from
harness.yaml), persists last-run times in SQLite so restarts never double-run
or skip, and applies exponential backoff to a skill that keeps failing —
one broken feed never takes the factory down.

Keep-alive on macOS is launchd's job (scripts/install_macos.sh), not ours:
if this process dies, launchd restarts it, and memory picks up where it left off.
"""

from __future__ import annotations

import datetime as dt
import time
import traceback

from .config import load_config
from .context import ContextBuilder
from .datasources import DataHub
from .llm import BudgetExceeded, make_llm
from .memory import Memory
from .skills import SKILLS, SkillContext


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Orchestrator:
    def __init__(self, cfg=None):
        self.cfg = cfg or load_config()
        self.memory = Memory(self.cfg.db_path)
        self.llm = make_llm(self.cfg, memory=self.memory)
        self.hub = DataHub(self.cfg)
        self.prompts = ContextBuilder(self.cfg, self.memory)

    def _ctx(self) -> SkillContext:
        genome = self.memory.active_genome()
        if genome is None:  # first ever run: seed the Darwin population
            from .evolution import Evolution
            Evolution(self.cfg, self.memory).ensure_population()
            genome = self.memory.active_genome()
        return SkillContext(cfg=self.cfg, memory=self.memory, llm=self.llm,
                            hub=self.hub, prompts=self.prompts, genome=genome)

    # ---- single skill -----------------------------------------------------
    def run_skill(self, name: str) -> dict:
        if name not in SKILLS:
            raise KeyError(f"unknown skill '{name}'. Available: {', '.join(sorted(SKILLS))}")
        skill = SKILLS[name]()
        started = _now()
        try:
            result = skill.run(self._ctx())
            self.memory.log_episode(name, "run", result.get("summary", "ok"),
                                    {"elapsed_s": (_now() - started).total_seconds(), **result})
            self.memory.kv_set(f"lastrun:{name}", started.isoformat())
            self.memory.kv_set(f"failures:{name}", "0")
            return result
        except BudgetExceeded as e:
            self.memory.log_episode(name, "skipped", str(e))
            return {"summary": str(e)}
        except Exception as e:
            fails = int(self.memory.kv_get(f"failures:{name}") or 0) + 1
            self.memory.kv_set(f"failures:{name}", str(fails))
            self.memory.log_episode(name, "error", f"{type(e).__name__}: {e}",
                                    {"traceback": traceback.format_exc()[-2000:], "consecutive": fails})
            return {"summary": f"ERROR ({fails} consecutive): {e}"}

    # ---- scheduling -------------------------------------------------------
    def due_skills(self) -> list[str]:
        schedule = self.cfg.harness.get("schedule", {})
        due = []
        for name, every_hours in schedule.items():
            if name not in SKILLS:
                continue
            last = self.memory.kv_get(f"lastrun:{name}")
            fails = int(self.memory.kv_get(f"failures:{name}") or 0)
            # backoff: double the interval per consecutive failure (cap 8x)
            interval = float(every_hours) * min(2 ** fails, 8)
            if last is None:
                due.append(name)
                continue
            elapsed = (_now() - dt.datetime.fromisoformat(last)).total_seconds() / 3600
            if elapsed >= interval:
                due.append(name)
        return due

    def run_forever(self, tick_seconds: int = 60):
        print(f"[darkfactory] 24/7 loop started; skills: {', '.join(sorted(SKILLS))}")
        self.memory.log_episode("orchestrator", "start", "24/7 loop started")
        while True:
            for name in self.due_skills():
                print(f"[darkfactory] {_now().isoformat(timespec='seconds')} running {name} …")
                result = self.run_skill(name)
                print(f"[darkfactory]   {name}: {result.get('summary','')}")
            time.sleep(tick_seconds)

    def status(self) -> str:
        lines = ["skill                | last run             | consecutive failures",
                 "---------------------+----------------------+---------------------"]
        for name in sorted(self.cfg.harness.get("schedule", {})):
            last = self.memory.kv_get(f"lastrun:{name}") or "never"
            fails = self.memory.kv_get(f"failures:{name}") or "0"
            lines.append(f"{name:<21}| {last[:19]:<21}| {fails}")
        pending = self.memory.list_approvals("pending")
        lines.append("")
        lines.append(f"pending approvals: {len(pending)}"
                     + ("".join(f"\n  #{a['id']} [{a['action']}] {a['skill']}" for a in pending)))
        genome = self.memory.active_genome()
        if genome:
            lines.append(f"active genome: gen {genome['generation']} fitness {genome['fitness']}")
        today_calls = self.memory.kv_get(f"llm_calls:{dt.date.today().isoformat()}") or "0"
        lines.append(f"LLM calls today: {today_calls}")
        return "\n".join(lines)
