"""
Intent Router
=============
Classifies every query BEFORE retrieval happens.
Determines:
  - Primary intent (what the user actually needs)
  - Relevant domains (hard partitioned)
  - Source priority order for this query
  - Whether this is a knowledge query, discussion, or clarification

This runs before RAG so we search the RIGHT places
in the RIGHT order from the start.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class Intent(Enum):
    # Knowledge retrieval
    PROCEDURE    = "procedure"    # how do I do X step by step
    IDENTIFY     = "identify"     # what is this / is this safe
    DIAGNOSE     = "diagnose"     # what is wrong / what are these symptoms
    LOCATE       = "locate"       # where do I find X
    EXPLAIN      = "explain"      # why does X work / what is X

    # Conversation
    DISCUSS      = "discuss"      # open ended conversation / philosophy
    REFLECT      = "reflect"      # processing feelings / events
    CLARIFY      = "clarify"      # follow-up on previous answer

    # Action
    EMERGENCY    = "emergency"    # urgent threat right now
    ASSESS       = "assess"       # evaluate my situation
    PLAN         = "plan"         # what should I do next


# ── Hard domain partitions ─────────────────────────────────────────────────
# Each tab has exactly these domain tiers in priority order.
# Tier 1 = searched first and trusted most.
# Tier 2 = general survival cross-domain sources.
# Tier 3 = Wikipedia (broad but lower confidence).
# None in tier 3 for medical — Wikipedia not authoritative enough for medicine.

DOMAIN_PARTITIONS = {
    "survival": {
        "tier1": [
            "survival", "water_purification", "food_preservation",
            "plants_temperate", "plants_tropical", "plants_desert",
            "plants_arctic", "weather_patterns",
        ],
        "tier2": [
            "army_fm_3_05_70", "survivor_library", "foxfire",
            "the_knowledge", "rebuild_ladder",
        ],
        "tier3": ["wikipedia"],
    },
    "medical": {
        "tier1": [
            "medical", "emergency_medicine",
            "where_no_doctor", "where_no_dentist",
        ],
        "tier2": [
            "army_fm_3_05_70",    # FM covers field medicine
            "plants_temperate",   # medicinal herbs
            "plants_tropical", "plants_desert", "plants_arctic",
            "survivor_library",
        ],
        "tier3": [],   # No Wikipedia for medical — not authoritative
    },
    "electronics": {
        "tier1": ["electronics"],
        "tier2": [
            "build", "chemistry",
            "army_fm_3_05_70", "survivor_library", "the_knowledge",
        ],
        "tier3": ["wikipedia"],
    },
    "navigation": {
        "tier1": ["navigation", "weather_patterns"],
        "tier2": [
            "army_fm_3_05_70", "survival",
            "survivor_library",
        ],
        "tier3": ["wikipedia"],
    },
    "farming": {
        "tier1": [
            "farming", "food_preservation",
            "plants_temperate", "plants_tropical",
            "plants_desert", "plants_arctic", "soil_maps",
        ],
        "tier2": [
            "survivor_library", "foxfire", "the_knowledge",
            "army_fm_3_05_70",
        ],
        "tier3": ["wikipedia"],
    },
    "build": {
        "tier1": ["build", "blacksmithing"],
        "tier2": [
            "electronics", "chemistry",
            "survivor_library", "the_knowledge",
            "army_fm_3_05_70",
        ],
        "tier3": ["wikipedia"],
    },
    "chemistry": {
        "tier1": ["chemistry", "blacksmithing", "soap_making"],
        "tier2": [
            "food_preservation", "electronics",
            "survivor_library", "the_knowledge",
        ],
        "tier3": ["wikipedia"],
    },
    "prometheus": {
        # Companion: all domains, but companion sources first
        "tier1": [
            "companion", "medical",  # psychological and physical wellbeing
        ],
        "tier2": [
            "survival", "army_fm_3_05_70", "the_knowledge",
            "foxfire", "survivor_library",
        ],
        "tier3": ["wikipedia"],
    },
}

# ── Intent detection patterns ──────────────────────────────────────────────

INTENT_PATTERNS = {
    Intent.EMERGENCY: [
        "help", "urgent", "dying", "emergency", "right now",
        "can't stop", "cannot stop", "won't stop", "not breathing", "no pulse",
        "getting worse", "critical", "life threatening", "unresponsive",
        "bleeding badly", "bleeding a lot", "losing blood", "turning blue",
        "bleeding and", "bleed and",
    ],
    Intent.PROCEDURE: [
        "how do i", "how to", "steps to", "step by step",
        "instructions for", "process for", "what do i do",
        "how should i", "can you show", "walk me through",
        "how can i", "what is the procedure", "how do you",
    ],
    Intent.IDENTIFY: [
        "what is this", "is this safe", "can i eat", "is it poisonous",
        "what plant", "what animal", "identify", "recognise", "looks like",
        "what kind of", "safe to eat", "edible", "is this plant", "what mushroom",
        "toxic", "is it dangerous",
    ],
    Intent.DIAGNOSE: [
        "symptoms", "what's wrong", "why is", "cause of",
        "getting sick", "feeling", "pain in", "signs of",
        "what could", "could it be", "sick", "fever", "ill",
        "hurting", "aching", "infection", "disease", "condition",
        "is it serious", "what does it mean", "they seem",
    ],
    Intent.LOCATE: [
        "where can i find", "where to find", "how to find",
        "source of", "obtain", "look for", "where is",
        "where do i get", "find some", "locate",
    ],
    Intent.EXPLAIN: [
        "why does", "how does", "what is", "explain", "tell me about",
        "describe", "what causes", "understand", "what does",
    ],
    Intent.DISCUSS: [
        "what do you think", "thoughts on", "talk about",
        "discuss", "opinion", "feel about", "believe",
        "philosophy", "meaning", "purpose", "stoicism", "stoic",
        "frankl", "marcus aurelius", "epictetus", "seneca",
        "what does it mean to", "is there meaning", "makes sense",
    ],
    Intent.REFLECT: [
        "i feel", "i'm scared", "i'm worried", "im scared", "im worried",
        "struggling", "can't cope", "cannot cope", "overwhelmed",
        "alone", "lonely", "missing", "grief", "lost someone",
        "afraid", "hopeless", "pointless", "worthless",
        "don't know if", "not sure i", "hard to keep going",
        "i am scared", "feeling lost", "feeling alone",
    ],
    Intent.ASSESS: [
        "should i", "is it worth", "better to", "right choice",
        "what are my options", "assess", "evaluate",
        "situation is", "what do you recommend", "which is better",
        "what would you do",
    ],
    Intent.PLAN: [
        "what next", "next steps", "priority",
        "where do i start", "order of",
        "sequence", "roadmap", "what should i focus",
    ],
}

# Intents that require hard domain isolation (no tier bleeding)
STRICT_INTENTS = {Intent.DIAGNOSE, Intent.PROCEDURE, Intent.IDENTIFY}

# Intents where discussion is appropriate (LLM can expand beyond retrieval)
DISCUSSION_INTENTS = {Intent.DISCUSS, Intent.REFLECT, Intent.PLAN, Intent.ASSESS}


@dataclass
class RoutingPlan:
    intent:          Intent
    tab_id:          str
    tier1_domains:   List[str]
    tier2_domains:   List[str]
    tier3_domains:   List[str]
    is_strict:       bool          # hard domain isolation — no tier bleeding
    allow_discussion: bool         # LLM can expand beyond retrieved text
    n_tier1:         int = 3       # chunks to fetch from tier 1
    n_tier2:         int = 2       # chunks to fetch from tier 2
    n_tier3:         int = 1       # chunks to fetch from tier 3


class IntentRouter:
    """
    Classifies query intent and builds retrieval routing plan
    before any RAG search happens.
    """

    def route(self, query: str, tab_id: str) -> RoutingPlan:
        intent = self._classify(query, tab_id)
        partition = DOMAIN_PARTITIONS.get(tab_id, DOMAIN_PARTITIONS["prometheus"])

        # Emergency always gets more results and strict domains
        if intent == Intent.EMERGENCY:
            return RoutingPlan(
                intent          = intent,
                tab_id          = tab_id,
                tier1_domains   = partition["tier1"],
                tier2_domains   = partition["tier2"],
                tier3_domains   = [],   # no wiki in emergency
                is_strict       = True,
                allow_discussion = False,
                n_tier1         = 5,
                n_tier2         = 3,
                n_tier3         = 0,
            )

        # Discussion/reflection intents — companion tab gets all domains
        if intent in DISCUSSION_INTENTS and tab_id == "prometheus":
            return RoutingPlan(
                intent          = intent,
                tab_id          = tab_id,
                tier1_domains   = partition["tier1"],
                tier2_domains   = partition["tier2"],
                tier3_domains   = partition["tier3"],
                is_strict       = False,
                allow_discussion = True,
                n_tier1         = 3,
                n_tier2         = 2,
                n_tier3         = 1,
            )

        is_strict = intent in STRICT_INTENTS
        allow_disc = intent in DISCUSSION_INTENTS

        return RoutingPlan(
            intent          = intent,
            tab_id          = tab_id,
            tier1_domains   = partition["tier1"],
            tier2_domains   = partition["tier2"],
            tier3_domains   = partition.get("tier3", []),
            is_strict       = is_strict,
            allow_discussion = allow_disc,
            n_tier1         = 4 if is_strict else 3,
            n_tier2         = 2,
            n_tier3         = 0 if is_strict else 1,
        )

    def _classify(self, query: str, tab_id: str = "") -> Intent:
        """Score query against intent patterns, return best match."""
        q = query.lower()
        scores = {intent: 0 for intent in Intent}

        for intent, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                if pattern in q:
                    scores[intent] += 1

        # Emergency overrides everything — even a single match
        if scores[Intent.EMERGENCY] > 0:
            return Intent.EMERGENCY

        # In medical tab: DIAGNOSE overrides REFLECT when both present
        if tab_id == "medical" and scores[Intent.DIAGNOSE] > 0:
            return Intent.DIAGNOSE

        # Reflection overrides discuss and explain when present
        if scores[Intent.REFLECT] > 0:
            return Intent.REFLECT

        # Diagnose overrides explain when present — medical context
        if scores[Intent.DIAGNOSE] > 0 and scores[Intent.DIAGNOSE] >= scores[Intent.EXPLAIN]:
            return Intent.DIAGNOSE

        # Identify overrides plan/explain when present
        if scores[Intent.IDENTIFY] > 0 and scores[Intent.IDENTIFY] >= scores[Intent.PLAN]:
            return Intent.IDENTIFY

        # Discuss overrides explain for philosophical queries
        if scores[Intent.DISCUSS] > 0 and scores[Intent.DISCUSS] >= scores[Intent.EXPLAIN]:
            return Intent.DISCUSS

        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return Intent.EXPLAIN   # safe default

        return best
