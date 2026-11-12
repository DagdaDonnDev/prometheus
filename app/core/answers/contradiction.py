"""
Contradiction Detector
======================
Compares top retrieved chunks for opposing claims.
Forces structured output when contradictions are found.

Critical for: medical, chemistry, survival tradeoffs.
"""

import re
from typing import List, Dict, Tuple, Optional


# Pairs of opposing terms that signal contradiction. Bare "do"/"do not" and
# "should"/"should not" were dropped: nearly any two passages have them, and
# the log-shelter answer turned into a "Source A says… Source B says…" script.
OPPOSING_PAIRS = [
    (r'\bsafe\b', r'\b(dangerous|unsafe|not safe)\b'),
    (r'\bedible\b', r'\b(toxic|poisonous|inedible|not edible)\b'),
    (r'\bcan eat\b', r'\b(not eat|never eat|cannot eat)\b'),
    (r'\bboil\b', r"\b(do not|don't|never) boil\b"),
    (r'\badd\b', r"\b(do not|don't|never) add\b"),
    (r'\bapply\b', r"\b(do not|don't|never) apply\b"),
    (r'\bcures\b', r'\bdoes not cure\b'),
    (r'\beffective\b', r'\bineffective\b'),
    (r'\bworks\b', r'\bdoes not work\b'),
    (r'\bincreases\b', r'\bdecreases\b'),
]

UNIT = r'(mg|ml|g|kg|cm|mm|°c|°f|%|minutes?|hours?|days?|litres?|liters?)'

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
        query: str = "",
    ) -> Tuple[bool, Optional[str]]:
        """
        Do the top passages disagree about what was asked?

        Step 1: only passages that mention the subject
        Step 2: only SENTENCES that name the subject — "boil it" in a passage
                about pottery doesn't contradict "do not boil" about wounds
        Step 3: opposing claims (safe / dangerous, edible / toxic …), or
                numbers in the SAME unit more than 2x apart
        """
        from core.ai.librarian import coverage, subject_words
        if query and subject_words(query):
            chunks = [c for c in chunks if coverage(query, c.get("content", ""))[0] >= 1]
        if len(chunks) < 2:
            return False, None
        words = subject_words(query) if query else []

        def about(text: str) -> List[str]:
            sentences = [x for x in re.split(r"(?<=[.!?;:])\s+", text.lower()) if x.strip()]
            if not words:
                return sentences
            return [x for x in sentences if any(w[:5] in x for w in words)]

        top = [" ".join(about(c.get("content", ""))) for c in chunks[:3]]
        for text_a, text_b in zip(top, top[1:]):
            result = self._check_pair(text_a, text_b)
            if result:
                return True, result
        conflict = self._numeric_conflict(self._extract_numbers(top[0]), self._extract_numbers(top[1]))
        if conflict:
            return True, conflict
        return False, None

    def _check_pair(self, text_a: str, text_b: str) -> Optional[str]:
        """One says X, the other says the opposite (and neither says both)."""
        for pos_pat, neg_pat in OPPOSING_PAIRS:
            a_pos, a_neg = re.search(pos_pat, text_a), re.search(neg_pat, text_a)
            b_pos, b_neg = re.search(pos_pat, text_b), re.search(neg_pat, text_b)
            if a_pos and not a_neg and b_neg and not b_pos:
                return f"one says '{a_pos.group(0)}', another says '{b_neg.group(0)}'"
            if a_neg and not a_pos and b_pos and not b_neg:
                return f"one says '{a_neg.group(0)}', another says '{b_pos.group(0)}'"
        return None

    def _extract_numbers(self, text: str) -> List[Tuple[float, str]]:
        """(value, unit) pairs — "10 minutes" and "10 mg" are never compared."""
        out = []
        for n, unit in re.findall(r'\b(\d+\.?\d*)\s*' + UNIT + r'(?![a-z])', text.lower()):
            unit = unit.rstrip("s").replace("liter", "litre")
            try:
                out.append((float(n), unit))
            except ValueError:
                pass
        return out

    def _numeric_conflict(
        self,
        nums_a: List[Tuple[float, str]],
        nums_b: List[Tuple[float, str]],
    ) -> Optional[str]:
        """
        The same unit in both, no value within 10% of the other's, and the
        largest more than 2x apart → the sources give different amounts.
        """
        for unit in sorted({u for _, u in nums_a} & {u for _, u in nums_b}):
            set_a = {round(v, 2) for v, u in nums_a if u == unit}
            set_b = {round(v, 2) for v, u in nums_b if u == unit}
            if any(abs(a - b) / max(abs(a), abs(b), 1) < 0.10 for a in set_a for b in set_b):
                continue
            a_max, b_max = max(set_a), max(set_b)
            if a_max > 0 and b_max > 0 and max(a_max, b_max) / min(a_max, b_max) > 2.0:
                return (f"the amounts differ ({', '.join(str(n) for n in sorted(set_a)[:3])} vs "
                        f"{', '.join(str(n) for n in sorted(set_b)[:3])} {unit}); "
                        "use the more conservative one")
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
