"""Offline fixture provider. Realistic-shaped data so the whole factory can be
exercised (and demoed, and unit-tested) without any credentials or network.

Replace with real feeds by flipping providers in harness.yaml — the skills
never know the difference.
"""

from __future__ import annotations

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str):
    with open(FIXTURES / name, encoding="utf-8") as f:
        return json.load(f)


def market_snapshot(categories: list[str]) -> list[dict]:
    data = _load("market.json")
    cats = {c.lower() for c in categories}
    return [n for n in data if n["category"].lower() in cats] or data


def campaigns() -> list[dict]:
    return _load("campaigns.json")


def reviews(niche: str) -> list[dict]:
    data = _load("reviews.json")
    hits = [r for r in data if niche.lower() in r.get("niche", "").lower()]
    return hits or data
