"""
Contradiction Detector
======================
Compares top retrieved chunks for opposing claims.
Forces structured output when contradictions are found.

Critical for: medical, chemistry, survival tradeoffs.
"""

import re
from typing import List, Dict, Tuple, Optional


# Pairs of opposing terms that signal contradiction
OPPOSING_PAIRS = [
    # Action opposites
    (r'\bdo\b', r'\bdo not\b'),
    (r'\bshould\b', r'\bshould not\b'),
    (r'\bsafe\b', r'\bdangerous\b'),
    (r'\bedible\b', r'\btoxic\b'),
    (r'\bcan eat\b', r'\bnot eat\b'),
    (r'\bboil\b', r'\bdo not boil\b'),
    (r'\badd\b', r'\bdo not add\b'),
    (r'\bapply\b', r'\bdo not apply\b'),

    # Quantity opposites (different numbers for same thing)
    # Detected separately via numeric comparison

    # Outcome opposites
    (r'\bcures\b', r'\bdoes not cure\b'),
    (r'\beffective\b', r'\bineffective\b'),
    (r'\bworks\b', r'\bdoes not work\b'),
    (r'\bincreases\b', r'\bdecreases\b'),
    (r'\brightens\b', r'\bdarkens\b'),
]

# High-risk topics where contradiction is most dangerous
HIGH_RISK_CONTRADICTION_TOPICS = {
    "medical", "medicine", "emergency_medicine",
    "where_no_doctor", "chemistry", "soap_making",
    "plants_temperate", "plants_tropical",
    "plants_desert", "plants_arctic",
}


class ContradictionDetector:

    def detect(
        self,
        chunks: List[Dict],
        tab_id: str = "",
    ) -> Tuple[bool, Optional[str]]:
        """
        Check top chunks for contradictions.
        Returns (has_contradiction, description).
        """
        if len(chunks) < 2:
            return False, None

        # Focus on top 3 chunks
        top = chunks[:3]
        texts = [c.get("content", "").lower() for c in top]
        sources = [c.get("source", "unknown") for c in top]

        # Check opposing pairs
        for text_a, text_b in zip(texts, texts[1:]):
            result = self._check_pair(text_a, text_b)
            if result:
                return True, result

        # Check numeric disagreement on quantities
        nums_a = self._extract_numbers(texts[0])
        nums_b = self._extract_numbers(texts[1])
        numeric_conflict = self._numeric_conflict(nums_a, nums_b)
        if numeric_conflict:
            return True, numeric_conflict

        return False, None

    def _check_pair(self, text_a: str, text_b: str) -> Optional[str]:
        """Check two text chunks for opposing claims."""
        for pos_pat, neg_pat in OPPOSING_PAIRS:
            a_has_pos = bool(re.search(pos_pat, text_a))
            a_has_neg = bool(re.search(neg_pat, text_a))
            b_has_pos = bool(re.search(pos_pat, text_b))
            b_has_neg = bool(re.search(neg_pat, text_b))

            # One source says positive, other says negative
            if (a_has_pos and not a_has_neg) and (b_has_neg and not b_has_pos):
                pos_word = pos_pat.replace(r'\b', '').strip()
                neg_word = neg_pat.replace(r'\b', '').strip()
                return (
                    f"Sources appear to disagree: "
                    f"one suggests '{pos_word}' while another suggests '{neg_word}'."
                )
            if (a_has_neg and not a_has_pos) and (b_has_pos and not b_has_neg):
                pos_word = pos_pat.replace(r'\b', '').strip()
                neg_word = neg_pat.replace(r'\b', '').strip()
                return (
                    f"Sources appear to disagree: "
                    f"one suggests '{neg_word}' while another suggests '{pos_word}'."
                )

        return None

    def _extract_numbers(self, text: str) -> List[float]:
        """Extract all numeric values from text."""
        numbers = re.findall(
            r'\b(\d+\.?\d*)\s*(?:mg|ml|g|kg|cm|mm|°C|°F|%|minutes?|hours?|days?|litres?|liters?)\b',
            text
        )
        result = []
        for n in numbers:
            try:
                result.append(float(n))
            except ValueError:
                pass
        return result

    def _numeric_conflict(
        self,
        nums_a: List[float],
        nums_b: List[float]
    ) -> Optional[str]:
        """
        Detect conflicting numeric values.
        Only flags when values differ by more than 2x with no overlap.
        Uses rounded comparison to avoid float equality issues.
        """
        if not nums_a or not nums_b:
            return None

        # Round to 2dp to avoid float equality fragility
        set_a = {round(n, 2) for n in nums_a}
        set_b = {round(n, 2) for n in nums_b}

        # Check for overlap within 10% tolerance
        def near_match(a, b):
            return abs(a - b) / max(abs(a), abs(b), 1) < 0.10

        has_overlap = any(
            near_match(a, b) for a in set_a for b in set_b
        )

        if has_overlap:
            return None

        a_max = max(set_a)
        b_max = max(set_b)
        if a_max > 0 and b_max > 0:
            ratio = max(a_max, b_max) / min(a_max, b_max)
            if ratio > 2.0:
                return (
                    f"Sources give different numeric values "
                    f"({', '.join(str(n) for n in sorted(set_a)[:3])} vs "
                    f"{', '.join(str(n) for n in sorted(set_b)[:3])}). "
                    f"Use the more conservative value."
                )

        return None

    def format_contradiction_response(
        self,
        description: str,
        chunks: List[Dict],
    ) -> str:
        """
        Build a structured output for contradicting sources.
        Injected into the system prompt to force structured response.
        """
        # Book titles, not file names ("building_with_straw_bales,_a_practical…"
        # was written out twice), and no numbered script — the speaker copied
        # "4. Tell the user to verify before acting" into its reply
        def label(chunk, fallback):
            from core.library.titles import title_for
            source = chunk.get("source", "")
            return title_for(source) or source.replace("_", " ").strip() or fallback
        source_a = label(chunks[0], "one book") if chunks else "one book"
        source_b = label(chunks[1], "another") if len(chunks) > 1 else "another"
        if source_a == source_b:
            source_a, source_b = f"one part of {source_a}", "another part"
        return (
            f"Two library passages disagree ({description}). Say briefly what {source_a} "
            f"says and what {source_b} says, which is the safer choice, and that it's worth "
            f"checking before acting. Don't quietly pick one."
        )
