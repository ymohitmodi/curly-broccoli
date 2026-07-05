# 🏭 darkfactory — 24/7 Agentic AI Harness for Amazon FBA

A "dark factory" for a solopreneur private-label Amazon FBA business: it runs
around the clock on your MacBook Air, drives **Ollama cloud models** (heavy
reasoning in Ollama's cloud, orchestration + all your data local), and works
your entire pipeline — product selection → Alibaba sourcing → keywords/SEO →
listing copy → PPC → review mining — with **Darwinian strategy evolution**,
**persistent memory**, and **human-gated spending**. You set objectives once;
the factory grinds; you approve the money moves and read one daily digest.

```
             ┌──────────────────────────────────────────────────────────┐
             │                    ORCHESTRATOR (24/7)                   │
             │   per-skill cadence · failure backoff · budget breaker   │
             └──────┬───────────────────────────────────────────┬───────┘
                    │ every prompt                              │ weekly
 ┌──────────────────▼───────────────────┐          ┌────────────▼───────────┐
 │           CONTEXT MANAGER            │          │      DARWIN ENGINE     │
 │ objectives (law) + genome (strategy) │◄─────────┤ genomes · fitness ·    │
 │ + playbook (craft) + memory (recall) │  params  │ crossover · mutation   │
 └──────────────────┬───────────────────┘          └────────────▲───────────┘
                    │                                           │ outcomes
 ┌──────────────────▼───────────────────────────────────────────┴───────────┐
 │  SKILLS   product_research → supplier_sourcing → keyword_seo →           │
 │           listing_writer → ad_optimizer → review_miner → digest          │
 └───────┬──────────────────────┬───────────────────────┬───────────────────┘
         │                      │                       │
 ┌───────▼───────┐   ┌──────────▼──────────┐   ┌────────▼────────┐
 │   DATA HUB    │   │   MEMORY (SQLite)   │   │ APPROVAL QUEUE  │
 │ sample│spapi  │   │ episodes·candidates │   │ you sign every  │
 │ trends (free) │   │ keywords·genomes    │   │ $-move: orders, │
 └───────────────┘   └─────────────────────┘   │ bids, publishes │
                                               └─────────────────┘
```

## Why this design wins as a force multiplier

- **Deterministic where it must be, generative where it helps.** Landed cost,
  margins, ROI, Amazon field limits, and PPC trigger rules are *code*
  (`economics.py`, rules in `ad_optimizer.py`) — the model never does money
  math. The LLM does what LLMs are good at: scoring, differentiation, copy,
  negotiation strategy.
- **Hard constraints are law, strategy is evolved.** Your margin floor,
  category exclusions, and budget live in `config/objectives.yaml` and can
  never be mutated. Everything tunable — scoring weights, PURSUE threshold,
  long-tail bias, target ACOS, price positioning — is a **genome** that
  evolves weekly against fitness measured from the factory's own results,
  and from **real outcomes you log** (`darkfactory log-outcome`). Real sales
  data dominates fitness, so Darwin optimizes for money, not vibes.
- **Nothing spends without you.** Orders, listing publishes, bid changes go
  to an approval queue. Dark factory ≠ unsupervised wallet.
- **Free-first data.** Ships with an offline sample provider (runs day one),
  Google Trends (free), and a wired skeleton for Amazon SP-API + Ads API —
  which are *free for registered sellers* and the ToS-compliant way to get
  real data. **Don't scrape amazon.com** — it risks the seller account that
  feeds you.

## Quickstart (MacBook Air)

**The easy way — one command does everything** (installs what's missing,
verifies with 13 tests, dry-runs the pipeline, sets up the 24/7 service,
and walks you through each step with plain-English prompts):

```bash
git clone <this repo> && cd curly-broccoli
./scripts/setup_macos.sh
```

Then use the friendly `./df` shortcut for everything: `./df status`,
`./df approvals`, `./df approve 3`. Full walkthrough for non-technical
operators: see **The Owner's Manual** below.

**The manual way**, if you prefer to see each step:

```bash
# 1. Ollama with cloud models (heavy models run in Ollama's cloud,
#    served through your local daemon — perfect for an Air)
brew install ollama
ollama signin                      # enables *-cloud models
ollama pull qwen3:8b               # local fallback model

# 2. Install
git clone <this repo> && cd curly-broccoli
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                   # + '.[trends]' for Google Trends

# 3. Verify every contract (13 tests: Ollama wire protocol, money math,
#    Amazon field limits, failure isolation, approvals, full pipeline)
python -m unittest tests.test_contracts -v

# 4. Dry-run the ENTIRE factory offline, zero tokens (mock LLM + sample data)
DARKFACTORY_LLM=mock python -m darkfactory once product_research
DARKFACTORY_LLM=mock python -m darkfactory once supplier_sourcing
python -m darkfactory status
python -m darkfactory candidates

# 5. Edit YOUR objectives and model choices
$EDITOR config/objectives.yaml     # categories, margin floor, budget, exclusions
$EDITOR config/harness.yaml        # model names from `ollama list`, cadences

# 6. Go 24/7
./scripts/install_macos.sh         # launchd service: auto-start, auto-restart
tail -f workspace/logs/darkfactory.log
```

Daily driver commands:

```bash
python -m darkfactory status                 # schedule, failures, approvals, genome
python -m darkfactory approvals              # what the factory is waiting on
python -m darkfactory approve 3              # sign off a gated action
python -m darkfactory candidates             # the product funnel
python -m darkfactory once ad_optimizer      # force any skill now
python -m darkfactory log-outcome 7 --monthly-units 340 --margin-pct 0.38 --rating 4.6
                                             # feed real results → trains Darwin
```

Read `workspace/reports/digest-<date>.md` every morning — funnel, approvals,
activity, current genome. Deliverables (sourcing packages, listings, keyword
maps, PPC change sheets) land in `workspace/artifacts/`.

---

# 🧭 The Owner's Manual

*For a strong Amazon seller who is NOT a programmer. No jargon. This section
tells you exactly what to do on day 1, every day, every week, and how to
squeeze more money out of the system over time.*

## What you actually bought yourself here, in plain words

Think of this as **hiring a tireless analyst team** that works while you
sleep: a product researcher, a sourcing manager, a keyword specialist, a
copywriter, a launch manager, a PPC manager, a review analyst, and a CFO
watching your cash. They live inside your MacBook. Every few hours each one
does its job and files its work as simple documents you can read.

Three rules they always follow:

1. **They never spend your money.** Anything that costs money — placing an
   order, publishing a listing, changing ad bids — goes into a queue and
   waits for YOUR signature (`./df approve`). You are the only wallet.
2. **They never do math by "gut feel."** Margins, tariffs, fees, cash
   timelines are calculated by fixed formulas, not by AI guessing.
3. **They learn from results.** When you tell the system how a product
   actually performed, its strategy literally evolves toward what made
   you money (that's the "Darwin" part).

## Day 1 — set it up (30 minutes, mostly waiting)

1. Open the **Terminal** app (press `⌘+Space`, type `Terminal`, hit Enter).
2. Paste these two lines and press Enter (replace the address with your
   repo's address from GitHub's green "Code" button):

   ```bash
   git clone <this repo> && cd curly-broccoli
   ./scripts/setup_macos.sh
   ```
3. Answer the yes/no questions it asks (it explains each one). When it
   finishes, your factory is installed, verified, and running 24/7.
4. **The one file you must make yours:** open `config/objectives.yaml` in
   TextEdit (`open -e config/objectives.yaml`). This is your business on one
   page — the categories you hunt in, your launch budget, your margin floor,
   what you refuse to sell. The factory obeys this file like law. Edit the
   numbers to match YOUR situation, save, done. (The AI can never override
   this file — only you can.)
5. **Tell it which AI models to use:** run `ollama list` in Terminal, then
   open `config/harness.yaml` (`open -e config/harness.yaml`) and set
   `planner_model` and `worker_model` to names from that list — cloud models
   end in `-cloud`. If unsure, ask in the Ollama app which cloud models your
   plan includes.

## The Console — your cockpit (use this instead of typing commands)

```bash
cd curly-broccoli && ./df console
```

One command opens the **Owner's Console** in your browser — a private local
app (127.0.0.1 only; your data never leaves the Mac) that covers everything
without typing another command:

- **Dashboard** — what needs your signature, factory heartbeat, AI budget
  meter, strategy fitness, the product funnel, and per-skill health with
  one-click "Run now".
- **Approvals** — every money decision as a card: what it is, who prepared
  it, the key numbers, a "Read the full package" button, and Approve /
  Reject with a confirmation step. Rejecting is always safe.
- **Products** — the whole funnel, filterable by verdict. Click any product
  for its score breakdown, risks, keywords — and a form to **log real
  results** (units, margin, rating, cash-cycle days) that feeds evolution.
- **Skills** — your analyst team as cards, each with a plain-English job
  description and a Run-now button (runs in the background; you get a toast
  with the result).
- **Documents** — every digest and deliverable, rendered beautifully.
- **Playbooks & Config** — edit your business law and coaching notes right
  in the browser; YAML is validated *before* saving, so you can't break the
  factory with a typo.
- **Activity** — the full 3-day log of everything the factory did.
- **Doctor** — the console solves its own problems: it checks configuration,
  database, workspace, the Ollama daemon, your model names, the AI budget,
  skill failures, the 24/7 heartbeat, aging approvals, and the launchd
  service — each with a plain-English explanation and, where safe, a
  **"Fix it for me"** button. Red badge on the sidebar = open the Doctor.

## Your daily 10 minutes (morning coffee routine)

The console way: `./df console` → glance at the Dashboard → clear the
Approvals queue → done. Or the terminal way:

```bash
cd curly-broccoli          # always start here
open workspace/reports/    # 1. read today's digest (2 min)
./df approvals             # 2. see what's waiting for your signature
./df approve 3             # 3. approve what you agree with (by number)
./df status                # 4. green check: everything running, no failures
```

**Reading the digest** (it's one page, always the same shape):
- **"Your approval queue"** — the only part that needs action. Each line is
  a money decision the factory prepared and is waiting on.
- **"Product funnel"** — how many ideas → sourcing → listing → live. If the
  funnel is empty for days, your constraints may be too tight (see
  "Improving" below).
- **"Last 24h activity"** — one line per thing each analyst did. Skim it.
- **"Active strategy genome"** — the strategy dials the system currently
  believes in. You don't need to touch these; they evolve on their own.

**Before you approve an order (`place_order`)**: open the matching sourcing
package in `workspace/artifacts/` — it shows the negotiation plan, the FOB
price to fight for, the walk-away price, AND the full cash timeline (when
money leaves, when it comes back, and how much is tied up at peak). If the
cash plan says your money is stuck for 10 months — reject it. That's the
system doing its job.

## Your weekly 20 minutes

1. Skim the week's **artifacts** (`open workspace/artifacts/`): sourcing
   packages, keyword maps, listing drafts, launch plans, PPC change sheets.
   These are your deliverables — use them in Alibaba chats, Seller Central,
   and your ad console.
2. **Feed results back** (this is the single highest-leverage habit):
   for every live product, once a week tell the factory the truth:

   ```bash
   ./df log-outcome 7 --monthly-units 340 --margin-pct 0.38 --rating 4.6 --cash-cycle-days 150
   ```

   (#7 is the candidate number from `./df candidates`.) Every Sunday night
   the strategy evolves against these real numbers. **No feedback = no
   evolution.** Sellers who skip this step own a clever toy; sellers who do
   it own a system that gets measurably better every week.
3. Glance at `./df candidates` — anything marked PURSUE that you disagree
   with? That disagreement is information: tighten `objectives.yaml` so the
   factory learns your taste.

## Keeping it running 24/7 (and knowing that it is)

- **Is it alive?** → `./df status`. Every skill shows its last run time.
  If "last run" times are recent, it's working.
- **The Mac must be awake to work.** Three good setups:
  - *Best:* keep the MacBook plugged in, lid open, and let the setup script's
    "prevent sleep on power" option do its thing. Screen can be off
    (brightness zero) — that's fine.
  - *Good:* plugged in with lid closed **plus** an external display or
    "Amphetamine"-style app — or just accept catch-up mode:
  - *Acceptable:* let it sleep. Nothing breaks and nothing is lost — the
    factory remembers its schedule and runs everything that's due the moment
    the Mac wakes. You lose "24/7", you keep "every day".
- **It restarts itself.** The background service (launchd) relaunches the
  factory if it ever crashes, and starts it automatically when you log in.
- **If something looks stuck:**
  ```bash
  tail -20 workspace/logs/darkfactory.err   # what went wrong, last lines
  launchctl unload ~/Library/LaunchAgents/com.darkfactory.harness.plist
  launchctl load ~/Library/LaunchAgents/com.darkfactory.harness.plist   # restart
  ```
- **A failing skill never stops the others.** If one analyst hits an error
  (e.g. a data source is down), it backs off and retries later while the
  rest keep working. `./df status` shows a failure count per skill — a
  number above 0 that keeps climbing for a day is worth a look in the logs.
- **Cost control is built in.** The factory stops calling AI models after
  `max_calls_per_day` (in `config/harness.yaml`) and resumes at midnight —
  it can never run away with your token budget.

## Troubleshooting for humans

| What you see | What it means | What to do |
|---|---|---|
| `./df status` shows old "last run" times | Mac was asleep or service stopped | Wake/plug in the Mac; restart the service (two `launchctl` lines above) |
| A skill shows failures: 3+ | A data source or model call keeps failing | `tail -40 workspace/logs/darkfactory.err`; usually Ollama isn't running → open the Ollama app |
| "Daily LLM budget reached" in digest | Factory hit its own spending brake | Fine. It resumes at midnight. Raise `max_calls_per_day` if you want more |
| Funnel empty for a week | Your gates are (correctly) strict, or market data is stale | See "Improving" ladder below — loosen ONE constraint at a time, or wire real data |
| An approval you don't understand | Never approve blind | Open the artifact file named in the approval; if still unclear, `./df reject <id>` — rejecting is always safe |

## How to improve results — the ladder (climb one rung at a time)

**Rung 1 — Make the objectives truly yours (day 1, 15 min).**
Everything in `config/objectives.yaml` is a business decision only you can
make: categories you know, budget you can lose, margin you demand. Garbage
in, garbage out; sharp in, sharp out.

**Rung 2 — Feed it real market research (week 1, zero coding).**
The built-in sample data proves the machine works, but decisions need your
data. Export competitor reviews from tools you already use and drop the file
at `workspace/inbox/reviews.json`; keep a simple inventory file at
`workspace/inbox/inventory.json` (`[{"candidate_id": 7, "units_on_hand": 260,
"units_inbound": 0}]`). The review miner and cash planner pick these up
automatically.

**Rung 3 — Log outcomes religiously (every week, 2 min per product).**
`./df log-outcome …` as above. This is the flywheel. Skipping it is like
hiring a great team and never telling them what sold.

**Rung 4 — Edit the playbooks like you'd coach an employee (monthly).**
The files in `playbooks/` are plain English instructions each analyst reads
before every task. Learned something the hard way — a supplier trick, a
listing angle that converts, a PPC pattern? Write it into the matching
playbook. No code. The very next run obeys it. Also refresh
`playbooks/benchmarks.md` quarterly (fees and tariffs move — ask any AI
chat to update the numbers, paste them in).

**Rung 5 — Wire your real Amazon data (one-time, ~an hour with a helper).**
Free for registered sellers: Seller Central → Apps & Services → Develop
Apps → create credentials → paste into `.env` (copy `.env.example`) → flip
`datasources:` in `config/harness.yaml` from `sample` to `spapi`. This is
the biggest single jump in decision quality: real prices, real fees, real
search terms. The file `darkfactory/datasources/spapi.py` tells a developer
(or an AI coding assistant) exactly what to fill in.

**Rung 6 — Tune the evolution (advanced, optional).**
Raise `risk_appetite` in objectives.yaml (0.4 → 0.6) to let strategy mutate
more boldly; widen a gene's range in `darkfactory/evolution.py` if you want
Darwin exploring further (e.g. higher launch aggression). Watch the digest's
fitness number over a month — it should trend up.

## What NOT to do

- **Don't approve orders without opening the sourcing artifact.** The
  approval queue is a signature, not a rubber stamp.
- **Don't skip the golden sample.** No cash plan survives a bad factory
  batch — validate a physical sample before the balance payment, always.
- **Don't scrape amazon.com for data.** It violates the seller agreement you
  signed and risks the account this whole machine feeds. SP-API is the
  legitimate free pipe.
- **Don't run two big launches inside one cash cycle** unless the
  cash-inventory ledger explicitly shows headroom. The factory will warn
  you ("OVER-COMMITTED") — believe it.
- **Don't edit files inside `darkfactory/`** unless you know Python. Your
  levers are `config/*.yaml`, `playbooks/*.md`, approvals, and log-outcome —
  they're designed to be all you need.

---

## The skills

| skill | cadence | output |
|---|---|---|
| `product_research` | 6h | hard-filtered, genome-scored candidate shortlist + seed keywords |
| `supplier_sourcing` | 24h | Alibaba RFQ, spec sheet, negotiation ladder, target/walkaway FOB, QC checklist, **full PO cash plan** |
| `keyword_seo` | 24h | 40–60 term clustered keyword map (tier/intent/placement/relevance) |
| `listing_writer` | 24h | full listing: title, bullets, description, backend terms (limits enforced in code), A+ outline, image brief |
| `launch_strategist` | 24h | 90-day launch plan: honeymoon phases, Vine, New Selection credits, PPC ramp, **kill criteria** |
| `ad_optimizer` | 12h | rules-first PPC change sheet: negatives, harvests, bid steps toward genome ACOS |
| `review_miner` | 24h | complaint→spec-upgrade and delight→copy-angle extraction |
| `inventory_planner` | 12h | cash-conversion-cycle plans, reorder points vs. low-inventory fee, working-capital ledger |
| `evolution` | weekly | fitness scoring + next genome generation (incl. one LLM-directed mutation) |
| `digest` | 24h | the owner's report |

## Research-grounded (July 2026)

The factory's numbers come from current research, not folklore, and live in
`playbooks/benchmarks.md` — injected into **every** prompt so no skill
reasons from stale training data:

- **2026 cost stack**: ~35% effective China tariff (25% Section 301 + 10%
  Section 122; IEEPA struck down Feb 2026, de minimis gone), Amazon's 3.5%
  fuel surcharge, inbound placement fees, low-inventory-level fee
  ($0.89–1.10/unit under ~28 days supply), 3× peak-season storage — all in
  `economics.py`.
- **Cash is the killer**: research shows the typical launch ties up working
  capital ~20 weeks and sellers underestimate it by ~30%. Every PO approval
  now shows deposit→live→payout→recovery day by day, capital turns/yr, and a
  velocity floor (`min_capital_turns_per_year`) rejects products that would
  turn your business into a warehouse.
- **Launch physics**: 2–4 week honeymoon, 20+ reviews in 30 days, Vine per
  functional variation ($200/parent, 30 units), New Selection Program
  credits, front-loaded launch ACOS — encoded in `launch_strategist` and its
  playbook, with the aggression level (`launch_acos_multiplier`) as a Darwin
  gene.
- **Fitness = compounding, not vanity**: realized fitness now weights capital
  velocity 25% alongside margin 35%, turnover 25%, rating 15% — the same
  margin at twice the capital turns makes twice the annual cash, and Darwin
  now knows it. Log `--cash-cycle-days` with your outcomes to feed it.

Each skill's *craft* lives in an editable markdown playbook (`playbooks/*.md`)
that is injected into its prompts — raise the bar by editing prose, not code.

## Extending

- **New skill**: drop a `@register` class in `darkfactory/skills/`, add a
  cadence in `harness.yaml`, optionally a playbook. ~50 lines.
- **Real Amazon data**: register a (free) developer app in Seller Central,
  fill `.env`, flip `datasources:` to `spapi`, and implement the TODOs in
  `darkfactory/datasources/spapi.py` (the header maps each feed to the right
  SP-API surface — Product Fees API replaces the estimate ladder, search-term
  reports feed keywords + PPC).
- **New gene**: add it to `GENE_SPACE` in `evolution.py` and read it in a
  skill via `ctx.genome_params()` — Darwin starts tuning it automatically.
- **Different models**: it's all Ollama model names in `harness.yaml`;
  cloud (`*-cloud`) and local models are interchangeable per role.

## Honest limits (read once)

- Sample market data is fixture data — decisions get real when you wire
  SP-API or import real research exports.
- An Air with the lid closed sleeps; the persistent scheduler catches up on
  wake, or keep it on power with sleep disabled for true 24/7 (see
  `scripts/install_macos.sh` output).
- An agent harness multiplies *your* judgment; it doesn't replace validating
  a golden sample with your own hands before an $8k PO. That's why the
  approval queue exists — keep using it.
