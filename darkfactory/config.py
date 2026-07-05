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
        """Load the editable domain playbook for a skill (playbooks/<name>.md)."""
        path = self.root / "playbooks" / f"{skill_name}.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def llm(self, key: str, default: Any = None) -> Any:
        return self.harness.get("llm", {}).get(key, default)

    def constraint(self, key: str, default: Any = None) -> Any:
        return self.objectives.get("constraints", {}).get(key, default)


def load_config(root: Path | None = None) -> Config:
    root = root or REPO_ROOT
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
