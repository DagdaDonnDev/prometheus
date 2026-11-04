"""
Training Graph — 3-tier confidence DAG
======================================
Holds every concept the Training Path knows, how confident it is in each,
and how they depend on one another.

Rules:
  - Tier-1 axioms are locked at confidence 1.0 and never retrained.
  - A concept's confidence can never exceed its weakest parent's
    (the cap is pushed down to every descendant).
  - A quarantined concept counts as confidence 0 for its children,
    so a contradiction cascades down everything built on it.
  - Only user-confirmed successes count towards lemma promotion.

Persistence:
  memory/training/graph.json    learned state per concept
  memory/training/history.json  every derivation attempt (audit trail)

Seed definitions (names, parents, statements) always come from
axiom_seeds.py, so improving a seed never needs a data migration.
"""

import json
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.training.axiom_seeds import CONCEPTS

TRAINING_DIR  = Path("memory/training")
GRAPH_PATH    = TRAINING_DIR / "graph.json"
HISTORY_PATH  = TRAINING_DIR / "history.json"
HISTORY_LIMIT = 2000

# A concept counts as trained (usable as a parent) at or above this
TRAINED_THRESHOLD = 0.5

# Lemma promotion and demotion rules
LEMMA_MIN_SUCCESSES   = 3
LEMMA_MIN_CONFIDENCE  = 0.8
LEMMA_MIN_SUCCESS_RATE = 0.75
LEMMA_DEMOTE_BELOW    = 0.5

# Learned fields saved per concept
STATE_FIELDS = (
    "confidence", "verdict_count", "success_count",
    "quarantined", "quarantine_reason", "trust_level", "updated",
)


class TrainingGraph:

    def __init__(self, graph_path: Path = GRAPH_PATH, history_path: Path = HISTORY_PATH):
        # RLock, not Lock: _propagate_cap calls back into locked methods
        # on the same thread (the v22 deadlock fix)
        self._lock = threading.RLock()
        self._graph_path   = Path(graph_path)
        self._history_path = Path(history_path)
        self.nodes: Dict[str, Dict] = {}
        self._load()

    # ── Loading and saving ─────────────────────────────────────────────────

    def _load(self):
        # Step 1: build every node from the seed definitions
        for seed in CONCEPTS:
            node = dict(seed)
            node.setdefault("result_markers", [])
            node.setdefault("violations", [])
            node.setdefault("inputs", [])
            node.setdefault("sample_problems", [])
            is_axiom = seed["tier"] == 1
            node.update({
                "confidence":        1.0 if is_axiom else 0.0,
                "verdict_count":     0,
                "success_count":     0,
                "quarantined":       False,
                "quarantine_reason": "",
                "trust_level":       "sourced" if is_axiom else "untrained",
                "updated":           0.0,
            })
            self.nodes[seed["id"]] = node

        # Step 2: lay saved learning on top (axioms stay locked)
        saved = {}
        if self._graph_path.exists():
            try:
                saved = json.loads(self._graph_path.read_text())
            except Exception:
                saved = {}
        for cid, state in saved.items():
            node = self.nodes.get(cid)
            if not node or node["tier"] == 1:
                continue
            for key in STATE_FIELDS:
                if key in state:
                    node[key] = state[key]

        # Step 3: make sure saved values still respect parent caps
        for cid in self._topological_order():
            self._apply_cap(cid)

    def save(self):
        with self._lock:
            self._graph_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                cid: {k: n[k] for k in STATE_FIELDS}
                for cid, n in self.nodes.items() if n["tier"] != 1
            }
            tmp = self._graph_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(self._graph_path)

    # ── Queries ────────────────────────────────────────────────────────────

    def get(self, cid: str) -> Optional[Dict]:
        return self.nodes.get(cid)

    def concepts_for_tab(self, tab_id: str) -> List[Dict]:
        return [n for n in self.nodes.values() if tab_id in n["tabs"]]

    def effective_confidence(self, cid: str) -> float:
        """Confidence as seen by children — 0 if quarantined."""
        node = self.nodes[cid]
        return 0.0 if node["quarantined"] else node["confidence"]

    def is_trained(self, cid: str) -> bool:
        node = self.nodes[cid]
        if node["tier"] == 1:
            return True
        return (not node["quarantined"]) and node["confidence"] >= TRAINED_THRESHOLD

    def missing_parents(self, cid: str) -> List[str]:
        """Parents that are not yet trained (ids)."""
        return [p for p in self.nodes[cid]["parents"] if not self.is_trained(p)]

    def ancestors(self, cid: str) -> List[str]:
        """Every concept this one depends on, nearest first, no repeats."""
        out, queue = [], list(self.nodes[cid]["parents"])
        while queue:
            p = queue.pop(0)
            if p in out:
                continue
            out.append(p)
            queue.extend(self.nodes[p]["parents"])
        return out

    def children(self, cid: str) -> List[str]:
        return [n["id"] for n in self.nodes.values() if cid in n["parents"]]

    def descendants(self, cid: str) -> List[str]:
        out, queue = [], self.children(cid)
        while queue:
            c = queue.pop(0)
            if c in out:
                continue
            out.append(c)
            queue.extend(self.children(c))
        return out

    def cap_for(self, cid: str) -> float:
        """Highest confidence this concept may hold: its weakest parent."""
        parents = self.nodes[cid]["parents"]
        if not parents:
            return 1.0
        return min(self.effective_confidence(p) for p in parents)

    def success_rate(self, cid: str) -> float:
        node = self.nodes[cid]
        if node["verdict_count"] == 0:
            return 0.0
        return node["success_count"] / node["verdict_count"]

    # ── Updates ────────────────────────────────────────────────────────────

    def record_attempt(self, cid: str, record: Dict):
        """
        Append an attempt to the audit history.
        Does NOT touch success_count — only apply_delta does that,
        after the user confirms (the v22 double-count fix).
        """
        with self._lock:
            history = self._read_history()
            history.append({"concept": cid, "time": time.time(), **record})
            history = history[-HISTORY_LIMIT:]
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            self._history_path.write_text(json.dumps(history, indent=1))

    def apply_delta(self, cid: str, delta: float, success: bool = False,
                    counts_as_verdict: bool = True) -> float:
        """
        Change a concept's confidence by delta, cap it by its parents,
        push the new cap down to every descendant, and save.
        Returns the new confidence.
        """
        with self._lock:
            node = self.nodes[cid]
            if node["tier"] == 1:
                return 1.0   # axioms are locked

            # Step 1: move confidence, clamp to 0..1
            node["confidence"] = max(0.0, min(1.0, node["confidence"] + delta))

            # Step 2: count the verdict
            if counts_as_verdict:
                node["verdict_count"] += 1
                if success:
                    node["success_count"] += 1

            # Step 3: trust level follows confidence
            if node["trust_level"] == "untrained" and node["confidence"] >= TRAINED_THRESHOLD:
                node["trust_level"] = "trained"
            if node["trust_level"] == "derived" and node["confidence"] < LEMMA_DEMOTE_BELOW:
                node["trust_level"] = "trained"   # lemma auto-demoted

            node["updated"] = time.time()

            # Step 4: respect parents, then push the cap to children
            self._apply_cap(cid)
            self._propagate_cap(cid)
            self.save()
            return node["confidence"]

    def quarantine(self, cid: str, reason: str):
        """Block a concept and cascade the loss of trust to its descendants."""
        with self._lock:
            node = self.nodes[cid]
            if node["tier"] == 1:
                return   # axioms are never quarantined
            node["quarantined"] = True
            node["quarantine_reason"] = reason
            if node["trust_level"] == "derived":
                node["trust_level"] = "trained"   # a lemma loses its status
            node["updated"] = time.time()
            self._propagate_cap(cid)
            self.save()

    def release(self, cid: str):
        """Lift a quarantine. Confidence restarts low so it must be re-earned."""
        with self._lock:
            node = self.nodes[cid]
            node["quarantined"] = False
            node["quarantine_reason"] = ""
            node["confidence"] = min(node["confidence"], 0.25)
            node["trust_level"] = "untrained"
            node["updated"] = time.time()
            self._apply_cap(cid)
            self.save()

    # ── Lemmas ─────────────────────────────────────────────────────────────

    def eligible_for_promotion(self, cid: str) -> bool:
        node = self.nodes[cid]
        return (
            node["tier"] != 1 and
            not node["quarantined"] and
            node["trust_level"] != "derived" and
            node["success_count"] >= LEMMA_MIN_SUCCESSES and
            node["confidence"] >= LEMMA_MIN_CONFIDENCE and
            self.success_rate(cid) >= LEMMA_MIN_SUCCESS_RATE
        )

    def promote_lemma(self, cid: str) -> bool:
        with self._lock:
            if not self.eligible_for_promotion(cid):
                return False
            self.nodes[cid]["trust_level"] = "derived"
            self.nodes[cid]["updated"] = time.time()
            self.save()
            return True

    def reset(self):
        """Forget all learning. Axioms stay."""
        with self._lock:
            for f in (self._graph_path, self._history_path):
                if f.exists():
                    f.unlink()
            self.nodes.clear()
            self._load()

    # ── Internals ──────────────────────────────────────────────────────────

    def _apply_cap(self, cid: str):
        node = self.nodes[cid]
        if node["tier"] == 1:
            return
        cap = self.cap_for(cid)
        if node["confidence"] > cap:
            node["confidence"] = cap

    def _propagate_cap(self, cid: str):
        """Re-cap every descendant, parents before children."""
        with self._lock:   # re-entrant: safe when called while already locked
            order = self._topological_order()
            affected = set(self.descendants(cid))
            for c in order:
                if c in affected:
                    self._apply_cap(c)
                    child = self.nodes[c]
                    if child["trust_level"] == "derived" and child["confidence"] < LEMMA_DEMOTE_BELOW:
                        child["trust_level"] = "trained"

    def _topological_order(self) -> List[str]:
        """Concept ids ordered so every parent comes before its children."""
        order, seen = [], set()

        def visit(c):
            if c in seen:
                return
            seen.add(c)
            for p in self.nodes[c]["parents"]:
                visit(p)
            order.append(c)

        for c in self.nodes:
            visit(c)
        return order

    def _read_history(self) -> List[Dict]:
        if self._history_path.exists():
            try:
                return json.loads(self._history_path.read_text())
            except Exception:
                return []
        return []
