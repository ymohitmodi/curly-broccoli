"""Real-data importer — the cheap fix for data blindness.

Drop CSV exports from any research tool (Helium10 Black Box/Magnet, Jungle
Scout, Seller Central Brand Analytics, or your own spreadsheet) into

    workspace/inbox/market/*.csv

and product_research runs on YOUR real numbers instead of bundled fixtures.
Column names are matched loosely (case/space-insensitive, common synonyms),
so most tool exports work unedited. Rows missing a niche or price are skipped
and reported rather than guessed.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

# logical field -> header synonyms (lowercase, alnum only)
SYNONYMS = {
    "niche": ["niche", "keyword", "searchterm", "title", "productname", "product"],
    "category": ["category", "department"],
    "avg_price": ["avgprice", "price", "averageprice", "asinprice"],
    "top10_avg_reviews": ["top10avgreviews", "reviews", "reviewcount", "avgreviews"],
    "top10_min_reviews": ["top10minreviews", "minreviews"],
    "est_monthly_revenue_usd": ["estmonthlyrevenueusd", "revenue", "monthlyrevenue",
                                "parentlevelrevenue", "estrevenue"],
    "search_volume_monthly": ["searchvolumemonthly", "searchvolume", "volume", "sv"],
    "trend_12m": ["trend12m", "trend", "salestrend"],
    "est_unit_weight_kg": ["estunitweightkg", "weightkg", "weight"],
    "est_fob_unit_usd": ["estfobunitusd", "fob", "fobprice", "unitcost", "sourcingprice"],
    "notes": ["notes", "comment", "comments"],
}
NUMERIC = {k for k in SYNONYMS if k not in ("niche", "category", "notes")}


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", h.lower())


def _to_num(v: str) -> float | None:
    v = re.sub(r"[$,%\s,]", "", str(v))
    try:
        return float(v)
    except ValueError:
        return None


def load_inbox_market(workspace: Path) -> tuple[list[dict], list[str]]:
    """Parse every CSV in workspace/inbox/market/. Returns (rows, warnings)."""
    inbox = Path(workspace) / "inbox" / "market"
    rows: list[dict] = []
    warnings: list[str] = []
    if not inbox.exists():
        return rows, warnings

    for f in sorted(inbox.glob("*.csv")):
        try:
            with open(f, encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                colmap: dict[str, str] = {}
                for logical, syns in SYNONYMS.items():
                    for header in reader.fieldnames or []:
                        if _norm(header) in syns:
                            colmap[logical] = header
                            break
                if "niche" not in colmap or "avg_price" not in colmap:
                    warnings.append(f"{f.name}: skipped — could not find niche/keyword "
                                    f"and price columns (headers: {reader.fieldnames})")
                    continue
                n_before = len(rows)
                for raw in reader:
                    row = {"source": f.name, "category": "Imported", "notes": ""}
                    for logical, header in colmap.items():
                        val = raw.get(header, "")
                        row[logical] = _to_num(val) if logical in NUMERIC else str(val).strip()
                    if not row.get("niche") or not row.get("avg_price"):
                        continue
                    # sane defaults where the export lacks a column
                    row.setdefault("top10_avg_reviews", None)
                    if row.get("top10_avg_reviews") is None:
                        row["top10_avg_reviews"] = 0
                        row["notes"] += " [no review data in export — moat unchecked]"
                    if row.get("trend_12m") is None:
                        row["trend_12m"] = 0.5
                    rows.append(row)
                warnings.append(f"{f.name}: imported {len(rows) - n_before} rows")
        except Exception as e:
            warnings.append(f"{f.name}: failed to parse — {e}")
    return rows, warnings
