"""
Training Session — user verdicts and lemma promotion
====================================================
After a derivation is shown, the user says whether it was right.
Only these verdicts move a concept's confidence.

Verdicts:
  correct        confidence up, counts as a success
  not_quite      confidence down a little
  incorrect      confidence down more
  contradiction  the result contradicts a trusted source —
                 quarantine the concept and cascade down its dependants

Lemma promotion:
  After 3+ confirmed successes, confidence ≥ 80% and success rate ≥ 75%,
  the concept is promoted to a stored lemma (trust_level = "derived",
  lower than "sourced" tier-1 axioms). A lemma is demoted automatically
  if confidence falls below 50% or a contradiction is reported.
"""

from typing import Dict, Optional

from core.training.graph import TrainingGraph

VERDICT_DELTAS = {
    "correct":       +0.25,
    "not_quite":     -0.10,
    "incorrect":     -0.25,
    "contradiction":  0.0,    # handled by quarantine instead
}

VERDICT_LABELS = {
    "correct":       "Right",
    "not_quite":     "Not quite",
    "incorrect":     "Wrong",
    "contradiction": "Contradicts a source",
}


class TrainingSession:

    def __init__(self, graph: TrainingGraph):
        self.graph = graph
        self._pending: Dict[str, Dict] = {}   # tab_id → last DERIVED result

    def remember(self, tab_id: str, result: Dict):
        """Hold a derivation until the user gives a verdict."""
        if result.get("status") == "DERIVED":
            self._pending[tab_id] = result

    def pending(self, tab_id: str) -> Optional[Dict]:
        return self._pending.get(tab_id)

    def apply_verdict(self, tab_id: str, verdict: str) -> str:
        """
        Apply the user's verdict to the last derivation in this tab.
        Returns a short message for the status bar.
        """
        result = self._pending.pop(tab_id, None)
        if not result or verdict not in VERDICT_DELTAS:
            return ""

        cid  = result["concept_id"]
        name = result["concept_name"]

        if verdict == "contradiction":
            self.graph.quarantine(cid, "user reported a contradiction with a source")
            self.graph.apply_delta(cid, -0.25, success=False)
            return f"{name} is on hold. Anything built on it is trusted less until it's re-checked."

        new_conf = self.graph.apply_delta(
            cid, VERDICT_DELTAS[verdict], success=(verdict == "correct")
        )

        if verdict == "correct" and self.promote_lemma(cid):
            return f"{name} is now a trusted result (confirmed {self.graph.get(cid)['success_count']} times)."
        if verdict == "correct":
            return f"Thanks — {name} is more trusted now."
        if new_conf < 0.5 and self.graph.get(cid)["trust_level"] == "trained":
            return f"Noted. {name} needs more checking before it's relied on."
        return "Noted."

    def promote_lemma(self, cid: str) -> bool:
        return self.graph.promote_lemma(cid)
