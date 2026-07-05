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
