"""CLI entry point.

  darkfactory run                    start the 24/7 loop (launchd keeps it alive)
  darkfactory once <skill>           run one skill now
  darkfactory status                 schedule, failures, approvals, genome, budget
  darkfactory approvals              list pending approvals
  darkfactory approve <id>           sign off a gated action
  darkfactory reject <id>            reject a gated action
  darkfactory candidates             show the product funnel
  darkfactory log-outcome <id> ...   feed REAL results back (this trains Darwin)
  darkfactory evolve                 force a generation step now
  darkfactory console                open the Owner's Console (local web UI)
"""

from __future__ import annotations

import argparse
import json
import sys

from .orchestrator import Orchestrator
from .skills import SKILLS


def main(argv=None):
    p = argparse.ArgumentParser(prog="darkfactory", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("run")
    once = sub.add_parser("once")
    once.add_argument("skill", choices=sorted(SKILLS))
    sub.add_parser("status")
    sub.add_parser("approvals")
    for verb in ("approve", "reject"):
        s = sub.add_parser(verb)
        s.add_argument("approval_id", type=int)
    sub.add_parser("candidates")
    lo = sub.add_parser("log-outcome")
    lo.add_argument("candidate_id", type=int)
    lo.add_argument("--monthly-units", type=float, required=True)
    lo.add_argument("--margin-pct", type=float, required=True, help="realized net margin, e.g. 0.38")
    lo.add_argument("--rating", type=float, required=True)
    lo.add_argument("--cash-cycle-days", type=float, default=None,
                    help="days from supplier wire to full cash recovery — rewards capital velocity in fitness")
    sub.add_parser("evolve")
    sub.add_parser("tasks")
    td = sub.add_parser("task-done")
    td.add_argument("task_id", type=int)
    con = sub.add_parser("console")
    con.add_argument("--port", type=int, default=8787)
    con.add_argument("--no-browser", action="store_true")

    args = p.parse_args(argv)

    if args.cmd == "console":  # no orchestrator needed up front
        from .console import serve
        httpd = serve(port=args.port, open_browser=not args.no_browser)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[darkfactory] console stopped.")
        return

    orch = Orchestrator()
    orch = Orchestrator()

    if args.cmd == "run":
        try:
            orch.run_forever()
        except KeyboardInterrupt:
            print("\n[darkfactory] stopped.")
    elif args.cmd == "once":
        result = orch.run_skill(args.skill)
        print(result.get("summary", json.dumps(result, default=str)))
    elif args.cmd == "status":
        print(orch.status())
    elif args.cmd == "approvals":
        for a in orch.memory.list_approvals("pending"):
            print(f"#{a['id']} [{a['action']}] from {a['skill']}:")
            print(json.dumps(a["payload"], indent=2, default=str))
    elif args.cmd in ("approve", "reject"):
        status = "approved" if args.cmd == "approve" else "rejected"
        orch.memory.resolve_approval(args.approval_id, status)
        orch.memory.log_episode("owner", args.cmd, f"approval #{args.approval_id} {status}")
        print(f"approval #{args.approval_id} {status}")
    elif args.cmd == "candidates":
        for c in orch.memory.list_candidates(limit=50):
            print(f"#{c['id']:>3} [{c['verdict']:<6}] [{c['stage']:<9}] "
                  f"{(c['composite'] or 0):.2f}  {c['name'][:70]}")
    elif args.cmd == "log-outcome":
        cand = orch.memory.get_candidate(args.candidate_id)
        if not cand:
            sys.exit(f"no candidate #{args.candidate_id}")
        target = orch.cfg.constraint("target_monthly_units", 300)
        outcome = {"monthly_units": args.monthly_units, "margin_pct": args.margin_pct,
                   "rating": args.rating, "target_units": target}
        if args.cash_cycle_days:
            outcome["cash_conversion_days"] = args.cash_cycle_days
        orch.memory.update_candidate(args.candidate_id, outcome=outcome, stage="live")
        orch.memory.log_episode("owner", "outcome",
                                f"candidate #{args.candidate_id} real results: "
                                f"{args.monthly_units:.0f} u/mo, {args.margin_pct:.0%} margin, {args.rating}★")
        print("outcome logged — Darwin will use it at the next evolution step.")
    elif args.cmd == "tasks":
        tasks = orch.memory.list_tasks("open")
        if not tasks:
            print("No open tasks — the ladder is waiting on the factory, not you.")
        for t in tasks:
            print(f"#{t['id']:>3} [{t['gate']}] {t['title']}\n     {t['instructions']}\n")
    elif args.cmd == "task-done":
        t = orch.memory.complete_task(args.task_id)
        if not t:
            sys.exit(f"no task #{args.task_id}")
        orch.memory.log_episode("owner", "task_done", f"task #{t['id']} done: {t['title'][:80]}")
        print(f"✓ done — evidence '{t['evidence_flag']}' recorded on candidate #{t['candidate_id']}. "
              "The ladder advances on the next stage_gate run.")
    elif args.cmd == "evolve":
        print(orch.run_skill("evolution").get("summary"))


if __name__ == "__main__":
    main()
