"""Configuration loading and path resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Config:
    objectives: dict[str, Any] = field(default_factory=dict)
    harness: dict[str, Any] = field(default_factory=dict)
    root: Path = REPO_ROOT

    @property
    def workspace(self) -> Path:
        ws = self.root / "workspace"
        ws.mkdir(parents=True, exist_ok=True)
        return ws

    @property
    def reports_dir(self) -> Path:
        d = self.workspace / "reports"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def artifacts_dir(self) -> Path:
        d = self.workspace / "artifacts"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def db_path(self) -> Path:
        rel = self.harness.get("memory", {}).get("db_path", "workspace/darkfactory.db")
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def playbook(self, skill_name: str) -> str:
        """Load the editable domain playbook for a skill (playbooks/<name>.md),
        plus the shared benchmarks file (playbooks/benchmarks.md) that grounds
        every skill in researched market numbers instead of model vibes."""
        parts = []
        path = self.root / "playbooks" / f"{skill_name}.md"
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
        bench = self.root / "playbooks" / "benchmarks.md"
        if bench.exists():
            parts.append(bench.read_text(encoding="utf-8"))
        return "\n\n".join(parts)

    def llm(self, key: str, default: Any = None) -> Any:
        return self.harness.get("llm", {}).get(key, default)

    def constraint(self, key: str, default: Any = None) -> Any:
        return self.objectives.get("constraints", {}).get(key, default)


def load_config(root: Path | None = None) -> Config:
    """Resolve the project root holding config/, playbooks/, workspace/.

    Priority: explicit arg → DARKFACTORY_ROOT env → current directory (if it
    has config/objectives.yaml) → the repo containing this file. The cwd rule
    makes non-editable installs work: run `darkfactory` from your project
    directory and everything resolves there, not in site-packages."""
    if root is None:
        if os.environ.get("DARKFACTORY_ROOT"):
            root = Path(os.environ["DARKFACTORY_ROOT"]).resolve()
        elif (Path.cwd() / "config" / "objectives.yaml").exists():
            root = Path.cwd()
        else:
            root = REPO_ROOT
    objectives = _load_yaml(root / "config" / "objectives.yaml")
    harness = _load_yaml(root / "config" / "harness.yaml")

    # Environment overrides
    if os.environ.get("OLLAMA_HOST"):
        harness.setdefault("llm", {})["host"] = os.environ["OLLAMA_HOST"]
    if os.environ.get("DARKFACTORY_LLM"):
        harness.setdefault("llm", {})["mode"] = os.environ["DARKFACTORY_LLM"]

    return Config(objectives=objectives, harness=harness, root=root)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
