"""
Source Sufficiency Gate
=======================
Intermediate check between retrieval and generation.

Evaluates:
  - Chunk count
  - Average confidence
  - Source diversity
  - Agreement between sources

Outputs one of: SUFFICIENT / WEAK / CONFLICTING / NONE

Enforces:
  WEAK        → CAUTIOUS or CLARIFY
  CONFLICTING → SAFE_MODE
  NONE        → SAFE_MODE or CLARIFY

Prevents thin retrieval from producing confident answers.
Also blocks peer data from medical/chemistry/diagnose intents.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum

from core.intent_router import Intent, RoutingPlan


class Sufficiency(Enum):
    SUFFICIENT  = "SUFFICIENT"
    WEAK        = "WEAK"
    CONFLICTING = "CONFLICTING"
    NONE        = "NONE"


# Intents where peer data is never allowed
PEER_BLOCKED_INTENTS = {
    Intent.DIAGNOSE,
    Intent.PROCEDURE,
    Intent.IDENTIFY,
    Intent.EMERGENCY,
}

# Intents that are conversation, not instruction — no sources needed
COMPANION_INTENTS = {Intent.DISCUSS, Intent.REFLECT}

# Minimum chunks required for SUFFICIENT verdict per intent
MIN_CHUNKS = {
    Intent.EMERGENCY:  2,
    Intent.PROCEDURE:  3,
    Intent.DIAGNOSE:   3,
    Intent.IDENTIFY:   2,
    Intent.LOCATE:     1,
    Intent.EXPLAIN:    2,
    Intent.DISCUSS:    1,
    Intent.REFLECT:    1,
    Intent.ASSESS:     2,
    Intent.PLAN:       2,
}

# Minimum average confidence for SUFFICIENT
MIN_AVG_CONFIDENCE = {
    Intent.EMERGENCY:  75,
    Intent.PROCEDURE:  70,
    Intent.DIAGNOSE:   75,
    Intent.IDENTIFY:   70,
    Intent.LOCATE:     55,
    Intent.EXPLAIN:    55,
    Intent.DISCUSS:    40,   # companion — very low bar
    Intent.REFLECT:    30,   # companion — even lower
    Intent.ASSESS:     60,
    Intent.PLAN:       55,
}


@dataclass
class SufficiencyResult:
    verdict:     Sufficiency
    reason:      str
    chunk_count: int
    avg_conf:    float
    diversity:   int         # number of unique sources
    has_peer:    bool        # peer-sourced data present
    peer_blocked: bool       # peer blocked for this intent


class SourceSufficiencyGate:
    """
    Evaluates whether retrieved sources are sufficient to answer safely.
    """

    def evaluate(
        self,
        scored_chunks: List[Dict],
        intent: Intent,
        routing_plan: RoutingPlan,
    ) -> SufficiencyResult:

        # Strip peer chunks if intent blocks them
        peer_blocked = intent in PEER_BLOCKED_INTENTS
        has_peer = any(
            c.get("domain") == "personal" or
            "peer" in c.get("source", "").lower()
            for c in scored_chunks
        )

        if peer_blocked:
            scored_chunks = [
                c for c in scored_chunks
                if c.get("domain") != "personal" and
                "peer" not in c.get("source", "").lower()
            ]

        count = len(scored_chunks)

        # NONE — nothing retrieved
        if count == 0:
            return SufficiencyResult(
                verdict      = Sufficiency.NONE,
                reason       = "No sources retrieved for this query.",
                chunk_count  = 0,
                avg_conf     = 0.0,
                diversity    = 0,
                has_peer     = has_peer,
                peer_blocked = peer_blocked,
            )

        # Calculate stats
        scores = [c.get("confidence", {}).get("score", 50) for c in scored_chunks]
        avg_conf = sum(scores) / len(scores)
        sources = set(c.get("source", "") for c in scored_chunks)
        diversity = len(sources)

        # CONFLICTING — top and bottom scores diverge significantly
        if len(scores) >= 2:
            spread = max(scores) - min(scores)
            if spread > 35 and count >= 2:
                # Check if they're actually saying different things
                # (high spread with multiple sources = likely conflict)
                if diversity >= 2:
                    return SufficiencyResult(
                        verdict     = Sufficiency.CONFLICTING,
                        reason      = (
                            f"Sources show significant disagreement "
                            f"(confidence spread: {spread:.0f}%). "
                            f"Presenting conservative option."
                        ),
                        chunk_count = count,
                        avg_conf    = avg_conf,
                        diversity   = diversity,
                        has_peer    = has_peer,
                        peer_blocked = peer_blocked,
                    )

        min_count = MIN_CHUNKS.get(intent, 2)
        min_conf  = MIN_AVG_CONFIDENCE.get(intent, 60)

        # WEAK — insufficient quantity or confidence
        reasons = []
        if count < min_count:
            reasons.append(
                f"Only {count} chunk(s) found (need {min_count} for this query type)."
            )
        if avg_conf < min_conf:
            reasons.append(
                f"Average source confidence {avg_conf:.0f}% "
                f"below threshold {min_conf}% for this query type."
            )

        if reasons:
            return SufficiencyResult(
                verdict     = Sufficiency.WEAK,
                reason      = " ".join(reasons),
                chunk_count = count,
                avg_conf    = avg_conf,
                diversity   = diversity,
                has_peer    = has_peer,
                peer_blocked = peer_blocked,
            )

        # SUFFICIENT
        return SufficiencyResult(
            verdict     = Sufficiency.SUFFICIENT,
            reason      = (
                f"{count} sources, avg confidence {avg_conf:.0f}%, "
                f"{diversity} unique source(s)."
            ),
            chunk_count = count,
            avg_conf    = avg_conf,
            diversity   = diversity,
            has_peer    = has_peer,
            peer_blocked = peer_blocked,
        )

    def gate_mode_override(
        self,
        result: SufficiencyResult,
        current_mode: str,
        intent: Optional[Intent] = None,
    ) -> Optional[str]:
        """
        Returns a mode override if sufficiency requires it.
        Returns None if current mode is acceptable.

        Two exceptions:
          - EMERGENCY is never downgraded. Someone bleeding needs the
            emergency protocol even when the library has nothing.
          - Companion intents (discuss, reflect) are never forced into
            SAFE_MODE for lack of sources — they don't need sources to
            be warm and present.
        """
        v = result.verdict

        # Step 1: emergency always holds
        if current_mode == "emergency":
            return None

        # Step 2: companion conversation works without sources
        if intent in COMPANION_INTENTS and v in (Sufficiency.NONE, Sufficiency.WEAK):
            return None

        if v == Sufficiency.NONE:
            # Force safe_mode unless already clarify
            if current_mode not in ("safe_mode", "clarify"):
                return "safe_mode"

        elif v == Sufficiency.CONFLICTING:
            # Force safe_mode
            if current_mode != "safe_mode":
                return "safe_mode"

        elif v == Sufficiency.WEAK:
            # Upgrade to at least cautious
            if current_mode == "direct":
                return "cautious"

        return None  # no override needed
