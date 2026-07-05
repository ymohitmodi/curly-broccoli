"""Persistent memory for the factory (SQLite, zero external services).

Layers:
  episodes    — episodic log of everything every skill did (searchable recall)
  candidates  — the product funnel: idea → sourcing → listing → launched → live
  keywords    — master keyword map per candidate
  genomes     — Darwin engine populations, fitness, lineage
  approvals   — human-gated action queue (the factory prepares, YOU sign off)
  kv          — cursors, counters, last-run times

Recall is recency-weighted keyword match over episodes; it deliberately avoids
embedding services so memory works offline and stays free.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY, value TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY, ts TEXT, skill TEXT, kind TEXT,
    summary TEXT, detail TEXT
);
CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY, ts TEXT, name TEXT, category TEXT, niche TEXT,
    genome_id INTEGER, data TEXT, scores TEXT, composite REAL,
    verdict TEXT, stage TEXT DEFAULT 'idea', outcome TEXT
);
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY, candidate_id INTEGER, keyword TEXT,
    intent TEXT, source TEXT, score REAL,
    UNIQUE(candidate_id, keyword)
);
CREATE TABLE IF NOT EXISTS genomes (
    id INTEGER PRIMARY KEY, ts TEXT, generation INTEGER,
    params TEXT, fitness REAL, status TEXT DEFAULT 'active', note TEXT
);
CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY, ts TEXT, skill TEXT, action TEXT,
    payload TEXT, status TEXT DEFAULT 'pending', resolved_at TEXT
);
"""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class Memory:
    def __init__(self, db_path: Path | str):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- kv ---------------------------------------------------------------
    def kv_get(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def kv_set(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO kv(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, _now()))
        self.conn.commit()

    # ---- episodes / recall --------------------------------------------------
    def log_episode(self, skill: str, kind: str, summary: str, detail: dict | None = None):
        self.conn.execute(
            "INSERT INTO episodes(ts,skill,kind,summary,detail) VALUES(?,?,?,?,?)",
            (_now(), skill, kind, summary, json.dumps(detail or {}, default=str)))
        self.conn.commit()

    def recent_episodes(self, hours: int = 24, limit: int = 100) -> list[dict]:
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat(timespec="seconds")
        rows = self.conn.execute(
            "SELECT * FROM episodes WHERE ts>=? ORDER BY ts DESC LIMIT ?", (cutoff, limit)).fetchall()
        return [dict(r) for r in rows]

    def recall(self, query: str, k: int = 8) -> list[dict]:
        """Keyword recall over episode summaries, recency-weighted."""
        terms = [t.lower() for t in query.split() if len(t) > 2][:8]
        rows = self.conn.execute(
            "SELECT id, ts, skill, kind, summary FROM episodes ORDER BY id DESC LIMIT 800").fetchall()
        scored = []
        for i, r in enumerate(rows):
            text = (r["summary"] or "").lower()
            hits = sum(1 for t in terms if t in text)
            if hits:
                scored.append((hits + 1.0 / (i + 2), dict(r)))  # small recency bonus
        scored.sort(key=lambda x: -x[0])
        return [r for _, r in scored[:k]]

    # ---- candidates ---------------------------------------------------------
    def add_candidate(self, name: str, category: str, niche: str, genome_id: int | None,
                      data: dict, scores: dict, composite: float, verdict: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO candidates(ts,name,category,niche,genome_id,data,scores,composite,verdict) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (_now(), name, category, niche, genome_id,
             json.dumps(data, default=str), json.dumps(scores, default=str), composite, verdict))
        self.conn.commit()
        return cur.lastrowid

    def update_candidate(self, cid: int, **fields):
        allowed = {"stage", "verdict", "composite", "outcome", "data", "scores"}
        sets, vals = [], []
        for k, v in fields.items():
            if k not in allowed:
                raise ValueError(f"cannot update field {k}")
            if isinstance(v, (dict, list)):
                v = json.dumps(v, default=str)
            sets.append(f"{k}=?")
            vals.append(v)
        vals.append(cid)
        self.conn.execute(f"UPDATE candidates SET {', '.join(sets)} WHERE id=?", vals)
        self.conn.commit()

    def list_candidates(self, verdict: str | None = None, stage: str | None = None,
                        limit: int = 50) -> list[dict]:
        q, args = "SELECT * FROM candidates", []
        conds = []
        if verdict:
            conds.append("verdict=?"); args.append(verdict)
        if stage:
            conds.append("stage=?"); args.append(stage)
        if conds:
            q += " WHERE " + " AND ".join(conds)
        q += " ORDER BY composite DESC, id DESC LIMIT ?"
        args.append(limit)
        rows = self.conn.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            for col in ("data", "scores", "outcome"):
                d[col] = json.loads(d[col]) if d[col] else None
            out.append(d)
        return out

    def get_candidate(self, cid: int) -> dict | None:
        rows = self.conn.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchall()
        if not rows:
            return None
        d = dict(rows[0])
        for col in ("data", "scores", "outcome"):
            d[col] = json.loads(d[col]) if d[col] else None
        return d

    # ---- keywords -------------------------------------------------------------
    def add_keywords(self, candidate_id: int, rows: list[dict]):
        for r in rows:
            self.conn.execute(
                "INSERT OR IGNORE INTO keywords(candidate_id,keyword,intent,source,score) VALUES(?,?,?,?,?)",
                (candidate_id, r.get("keyword", "").strip().lower(), r.get("intent", ""),
                 r.get("source", ""), float(r.get("score", 0.5))))
        self.conn.commit()

    def keywords_for(self, candidate_id: int, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM keywords WHERE candidate_id=? ORDER BY score DESC LIMIT ?",
            (candidate_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ---- genomes ----------------------------------------------------------------
    def save_genome(self, generation: int, params: dict, fitness: float | None = None,
                    status: str = "active", note: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO genomes(ts,generation,params,fitness,status,note) VALUES(?,?,?,?,?,?)",
            (_now(), generation, json.dumps(params, default=str), fitness, status, note))
        self.conn.commit()
        return cur.lastrowid

    def set_genome_fitness(self, gid: int, fitness: float):
        self.conn.execute("UPDATE genomes SET fitness=? WHERE id=?", (fitness, gid))
        self.conn.commit()

    def archive_genomes(self, ids: list[int]):
        self.conn.executemany("UPDATE genomes SET status='archived' WHERE id=?",
                              [(i,) for i in ids])
        self.conn.commit()

    def promote_genome(self, gid: int, generation: int):
        """Carry an elite into the next generation KEEPING its id, so candidate
        attribution (and therefore fitness lineage) survives generations."""
        self.conn.execute("UPDATE genomes SET generation=? WHERE id=?", (generation, gid))
        self.conn.commit()

    def list_genomes(self, status: str | None = "active") -> list[dict]:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM genomes WHERE status=? ORDER BY generation DESC, fitness DESC", (status,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM genomes ORDER BY generation DESC, fitness DESC").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["params"] = json.loads(d["params"])
            out.append(d)
        return out

    def active_genome(self) -> dict | None:
        gs = self.list_genomes("active")
        if not gs:
            return None
        gs.sort(key=lambda g: (g["fitness"] is not None, g["fitness"] or 0), reverse=True)
        return gs[0]

    # ---- approvals ------------------------------------------------------------
    def add_approval(self, skill: str, action: str, payload: dict) -> int:
        cur = self.conn.execute(
            "INSERT INTO approvals(ts,skill,action,payload) VALUES(?,?,?,?)",
            (_now(), skill, action, json.dumps(payload, default=str)))
        self.conn.commit()
        return cur.lastrowid

    def list_approvals(self, status: str = "pending") -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM approvals WHERE status=? ORDER BY id", (status,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"])
            out.append(d)
        return out

    def resolve_approval(self, aid: int, status: str):
        assert status in ("approved", "rejected")
        self.conn.execute("UPDATE approvals SET status=?, resolved_at=? WHERE id=?",
                          (status, _now(), aid))
        self.conn.commit()

    def close(self):
        self.conn.close()
