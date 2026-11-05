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

    # Scientific reference — universal laws and constants (Training Path anchors)
    "scientific_reference":        96,
    "fundamental_laws_physics":    96,
    "electronics_reference":       96,
    "chemistry_reference":         96,
    "mechanics_and_materials":     95,
    "navigation_reference":        96,
    "mathematics_reference":       97,
    "computer_science_reference":  95,
    "universal_constants":         97,

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

    def format_for_prompt(self, results: List[Dict], query: str = "",
                          max_words: int = 0) -> str:
        """
        Format retrieved chunks for injection into the system prompt.

        Structured so the model clearly understands:
        - Which source is most authoritative
        - What to trust vs treat with caution
        - How to handle disagreement

        No raw scores — the model doesn't need numbers, it needs guidance.
        """
        if not results:
            return ""

        output = []
        for i, r in enumerate(results):
            conf   = r.get("confidence", {})
            level  = conf.get("level", "UNKNOWN")
            source = r.get("source", conf.get("source", "unknown"))
            domain = r.get("domain", "")
            tier   = r.get("_tier", "")

            # Source label — human readable, not numeric
            source_label = self._source_label(source, domain)

            # Trust instruction — what the model should do with this source
            trust = {
                "HIGH":      "Use this directly.",
                "MEDIUM":    "Use this — note if anything seems uncertain.",
                "LOW":       "Use with caution — flag uncertainty to the user.",
                "UNCERTAIN": "Treat carefully — mention uncertainty explicitly.",
            }.get(level, "Use carefully.")

            # Tier label for context
            tier_note = ""
            if tier == "tier3":
                tier_note = " (general reference — lower priority)"
            elif tier == "personal":
                tier_note = " (from your personal documents — unverified)"

            header = f"[Source {i+1}: {source_label}{tier_note} — {trust}]"
            text = trim_passage(r["content"], query, max_words) if max_words else r["content"]
            output.append(f"{header}\n{text}")

        return "\n\n---\n\n".join(output)

    def _source_label(self, source: str, domain: str) -> str:
        """Human-readable source label for the model."""
        labels = {
            "army_fm_3_05_70":    "US Army Survival Manual FM 3-05.70",
            "army_tm_31_210":     "US Army Field Manual TM 31-210",
            "where_no_doctor":    "Where There Is No Doctor (Hesperian)",
            "where_no_dentist":   "Where There Is No Dentist (Hesperian)",
            "nuclear_survival":   "Nuclear War Survival Skills (Kearny)",
            "foxfire":            "Foxfire Book Series",
            "survivor_library":   "Survivor Library",
            "the_knowledge":      "The Knowledge (Dartnell)",
            "wikipedia":          "Wikipedia",
            "emergency_medicine": "Emergency Medicine Reference",
            "water_purification": "Water Purification Manual",
            "food_preservation":  "Food Preservation Guide",
            "blacksmithing":      "Practical Blacksmithing",
            "soap_making":        "Soap Making Reference",
            "plants_temperate":   "Temperate Plant Field Guide",
            "plants_tropical":    "Tropical Plant Field Guide",
            "plants_desert":      "Desert Plant Field Guide",
            "plants_arctic":      "Arctic Plant Field Guide",
            "companion":          "Psychological Support Resources",
            "scientific_reference": "Scientific Reference (laws and constants)",
            "personal":           "Personal Document",
        }
        # Try exact match first, then domain, then clean up source string
        label = labels.get(source) or labels.get(domain)
        if label:
            return label
        # Fall back to cleaned source name
        return source.replace("_", " ").title()

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


# ── Passage trimming ────────────────────────────────────────────────────────
# Chunks are ~400 words. Sending six of them made every prompt ~3,000 tokens,
# and a small model on a CPU has to read all of that before its first word
# (about 3 seconds). Only the part around what was asked is needed.

_STOP_WORDS = {
    "the", "and", "for", "how", "what", "when", "where", "why", "who", "can",
    "you", "your", "are", "was", "with", "this", "that", "from", "have", "does",
    "into", "will", "should", "would", "could", "about", "there", "their", "them",
}


def trim_passage(text: str, query: str, max_words: int = 130) -> str:
    """
    Keep the ~max_words around the sentence that best matches the query.

    Step 1: split into sentences
    Step 2: find the sentence sharing the most words with the query
    Step 3: grow the window one sentence at a time (after, then before)
            until it reaches max_words
    """
    import re as _re
    words = text.split()
    if len(words) <= max_words:
        return text

    q = {w for w in _re.findall(r"[a-z0-9]+", (query or "").lower())
         if len(w) > 2 and w not in _STOP_WORDS}

    # Step 1
    sentences = [s for s in _re.split(r"(?<=[.!?:])\s+", text) if s.strip()]
    if len(sentences) <= 1:
        # No punctuation (common in PDF text): window around the first query word
        hit = next((i for i, w in enumerate(words)
                    if _re.sub(r"[^a-z0-9]", "", w.lower()) in q), 0)
        start = max(0, hit - max_words // 3)
        window = words[start:start + max_words]
        return ("… " if start else "") + " ".join(window) + (" …" if start + max_words < len(words) else "")

    # Step 2
    def score(s):
        return len(q & set(_re.findall(r"[a-z0-9]+", s.lower())))
    best = max(range(len(sentences)), key=lambda i: score(sentences[i]))

    # Step 3
    lo = hi = best
    count = len(sentences[best].split())
    while count < max_words and (lo > 0 or hi < len(sentences) - 1):
        if hi < len(sentences) - 1:
            hi += 1
            count += len(sentences[hi].split())
        if count < max_words and lo > 0:
            lo -= 1
            count += len(sentences[lo].split())
    out = " ".join(sentences[lo:hi + 1])
    out_words = out.split()
    if len(out_words) > max_words + 40:          # one very long sentence
        out = " ".join(out_words[:max_words + 40])
    return ("… " if lo > 0 else "") + out + (" …" if hi < len(sentences) - 1 else "")

