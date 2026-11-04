"""
Confidence scoring system for knowledge chunks.
Flags uncertainty, source quality, and contradictions.
Prometheus is honest about what it knows vs what it's unsure of.
"""

import re
from typing import List, Dict, Tuple, Optional


# Source reliability tiers — based on how field-tested each source is
SOURCE_TIERS = {
    # Primary — field tested, peer reviewed, or military verified
    "army_fm_3_05_70":    95,
    "army_tm_31_210":     90,
    "where_no_doctor":    95,
    "where_no_dentist":   93,
    "nuclear_survival":   92,

    # Historical practical — written by practitioners, pre-electricity
    "foxfire":            88,
    "survivor_library":   82,

    # Synthesis — derived from primary sources
    "the_knowledge":      85,
    "rebuild_ladder":     80,
    "reasoning":          80,

    # Regional — curated but may have local variation
    "plants_temperate":   85,
    "plants_tropical":    85,
    "plants_desert":      85,
    "plants_arctic":      85,
    "procedures":         88,
    "food_preservation":  87,
    "blacksmithing":      83,
    "soap_making":        85,
    "emergency_medicine": 88,
    "water_purification": 90,

    # Wikipedia — variable quality
    "wikipedia":          68,

    # General fallback
    "general":            55,
}

# Domains where we require two independent sources
CRITICAL_DOMAINS = {
    "medical", "medicine", "emergency_medicine",
    "water", "water_purification", "food_safety",
    "food_preservation", "plants_temperate",
    "plants_tropical", "plants_desert", "plants_arctic",
    "nuclear_survival", "where_no_doctor",
    "where_no_dentist", "poison", "chemical"
}

# Phrases that reduce confidence
UNCERTAINTY_PHRASES = [
    "may ", "might ", "could ", "possibly ", "perhaps ",
    "some sources", "reportedly", "allegedly", "it is said",
    "citation needed", "unverified", "disputed", "unclear",
    "some people", "various methods", "opinions differ",
    "traditionally believed", "folk remedy"
]

# Phrases that increase confidence
CONFIDENCE_PHRASES = [
    "tested", "proven", "verified", "confirmed",
    "studies show", "research shows", "clinical",
    "field tested", "laboratory", "measured",
    "documented", "recorded", "established"
]

# Specific measurement patterns boost confidence
MEASUREMENT_PATTERN = re.compile(
    r'\d+\.?\d*\s*('
    r'mg|ml|g|kg|lb|oz|cm|mm|m|ft|in|'
    r'degrees|°C|°F|hours|days|minutes|seconds|'
    r'liters|litres|gallons|cups|tablespoons|teaspoons|'
    r'percent|%|parts per|ppm'
    r')', re.IGNORECASE
)


class ConfidenceScorer:

    def score_chunk(self, chunk: str, source: str) -> Dict:
        """
        Score a knowledge chunk for reliability.
        Returns score (0-100), level, and explanation flags.
        """
        base = SOURCE_TIERS.get(source, 55)
        modifier = 0
        flags = []

        text_lower = chunk.lower()

        # Penalize uncertainty language
        for phrase in UNCERTAINTY_PHRASES:
            if phrase in text_lower:
                modifier -= 4
                flags.append(f"Uncertain language: '{phrase.strip()}'")
                break  # Only flag once even if multiple matches

        # Boost confidence language
        for phrase in CONFIDENCE_PHRASES:
            if phrase in text_lower:
                modifier += 5
                flags.append("Contains verified/tested claims")
                break

        # Boost for specific measurements
        if MEASUREMENT_PATTERN.search(chunk):
            modifier += 8
            flags.append("Contains specific measurable values")

        # Penalize contradictory signals
        contradiction_words = ["however", "but some", "although", "on the other hand",
                               "contradicts", "disagrees", "varies"]
        for word in contradiction_words:
            if word in text_lower:
                modifier -= 3
                flags.append("Contains contradictory information")
                break

        # Penalize very short chunks (less context)
        if len(chunk.split()) < 30:
            modifier -= 5
            flags.append("Short chunk — limited context")

        final = max(0, min(100, base + modifier))

        return {
            "score": final,
            "level": self._level(final),
            "flags": flags,
            "source": source
        }

    def _level(self, score: int) -> str:
        if score >= 88:
            return "HIGH"
        if score >= 70:
            return "MEDIUM"
        if score >= 50:
            return "LOW"
        return "UNCERTAIN"

    def check_contradiction(self, chunks_a: List[str], chunks_b: List[str]) -> bool:
        """
        Simple contradiction detection between two sets of chunks.
        Looks for numeric disagreement on the same topic.
        """
        # Extract numbers from each set
        nums_a = set(re.findall(r'\b\d+\.?\d*\b', " ".join(chunks_a)))
        nums_b = set(re.findall(r'\b\d+\.?\d*\b', " ".join(chunks_b)))

        # If both sources have numbers but none in common — possible disagreement
        if nums_a and nums_b and not (nums_a & nums_b):
            return True

        return False

    def format_for_prompt(self, results: List[Dict]) -> str:
        """
        Format search results with confidence indicators for injection into prompt.
        """
        if not results:
            return ""

        output = []
        for r in results:
            conf = r.get("confidence", {})
            level = conf.get("level", "UNKNOWN")
            source = conf.get("source", "unknown")
            score = conf.get("score", 0)

            indicator = {
                "HIGH":      "✓",
                "MEDIUM":    "~",
                "LOW":       "?",
                "UNCERTAIN": "⚠",
            }.get(level, "?")

            header = f"[{indicator} {level} confidence ({score}%) | Source: {source}]"
            output.append(f"{header}\n{r['content']}")

        return "\n\n---\n\n".join(output)

    def build_confidence_note(self, results: List[Dict], is_critical: bool) -> str:
        """
        Build a note to append to system prompt about source confidence.
        """
        if not results:
            return (
                "No specific knowledge found for this query. "
                "Reason from first principles and clearly state uncertainty."
            )

        levels = [r.get("confidence", {}).get("level", "UNKNOWN") for r in results]
        sources = [r.get("confidence", {}).get("source", "unknown") for r in results]

        high_count = levels.count("HIGH")
        uncertain_count = levels.count("UNCERTAIN") + levels.count("LOW")

        notes = []

        if is_critical:
            notes.append(
                "⚠ CRITICAL DOMAIN: This query involves safety-critical information. "
                "Always state your confidence level explicitly in the response."
            )

        if high_count >= 2:
            notes.append(
                f"Multiple high-confidence sources agree ({', '.join(set(sources))}). "
                "You can answer with confidence but still note the source."
            )
        elif high_count == 1:
            notes.append(
                "One high-confidence source found. "
                "Answer helpfully but acknowledge this is a single source."
            )
        elif uncertain_count > 0:
            notes.append(
                "Sources for this query have lower confidence. "
                "Be helpful but clearly flag uncertainty. "
                "Suggest the user verify before acting on medical or safety information."
            )

        if uncertain_count >= 2:
            notes.append(
                "The redundancy principle was not met — "
                "two independent high-confidence sources not found. "
                "Tell the user this explicitly."
            )

        return " ".join(notes)


# ── Redundancy-aware search wrapper ───────────────────────────────────────

class RedundancyChecker:
    """
    Ensures critical queries get two independent source confirmations.
    """

    def __init__(self, scorer: ConfidenceScorer):
        self.scorer = scorer

    def is_critical(self, domain: str, query: str) -> bool:
        if domain in CRITICAL_DOMAINS:
            return True

        # Also check query text for critical keywords
        critical_keywords = [
            "dose", "dosage", "how much", "how many",
            "edible", "poisonous", "toxic", "safe to eat",
            "treat", "cure", "medicine", "drug",
            "radiation", "fallout", "contaminated",
            "suture", "stitch", "wound", "fracture", "bone",
            "purify", "filter", "safe to drink"
        ]
        query_lower = query.lower()
        return any(kw in query_lower for kw in critical_keywords)

    def redundancy_met(self, results: List[Dict]) -> Tuple[bool, str]:
        """
        Check if redundancy principle is satisfied.
        Returns (met: bool, explanation: str)
        """
        if not results:
            return False, "No sources found."

        high_confidence = [
            r for r in results
            if r.get("confidence", {}).get("level") in ("HIGH", "MEDIUM")
        ]

        unique_sources = set(
            r.get("confidence", {}).get("source", "") for r in high_confidence
        )

        if len(unique_sources) >= 2:
            return True, f"Confirmed by {len(unique_sources)} independent sources."

        if len(unique_sources) == 1:
            return False, (
                f"Only one source found: {list(unique_sources)[0]}. "
                "For critical information, a second source is recommended."
            )

        return False, "No high-confidence sources found for this query."
