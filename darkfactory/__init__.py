"""darkfactory — 24/7 agentic harness for an Amazon FBA private-label business.

Modules:
  config       load objectives.yaml + harness.yaml, resolve paths
  llm          Ollama client (local daemon serving local + cloud models) and mock
  memory       SQLite persistence: episodes, candidates, keywords, genomes, approvals
  context      budgeted prompt assembly: objectives + genome + playbook + recall + task
  economics    deterministic landed-cost / margin / ROI math (never left to the LLM)
  evolution    Darwinian strategy engine: genomes, fitness, selection, mutation
  skills       the seven business skills (product research → ads)
  orchestrator the 24/7 loop with per-skill cadence and failure backoff
"""

__version__ = "0.1.0"
