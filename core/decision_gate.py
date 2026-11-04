"""
Decision Gate
=============
Sits between user query and LLM response.
Decides HOW to respond before generating text.

Never shown to the user — internal reasoning layer only.
Confidence scores are never displayed — they only change behaviour.

Flow:
    User query
        → DecisionGate.evaluate()
        → ResponsePlan (mode, template, assumptions, clarifications)
        → System prompt built around the plan
        → LLM generates within those constraints
"""

from dataclasses import dataclass, field
from typing import List
from enum import Enum


# ── Response modes ─────────────────────────────────────────────────────────

class ResponseMode(Enum):
    DIRECT     = "direct"     # High confidence — answer directly
    CAUTIOUS   = "cautious"   # Medium confidence — answer with caveats
    CLARIFY    = "clarify"    # Low confidence + ambiguous — ask first
    SAFE_MODE  = "safe_mode"  # Very low / conflicting — stabilise only
    EMERGENCY  = "emergency"  # Urgent threat — structured format only


# ── Keyword sets ───────────────────────────────────────────────────────────

HIGH_RISK_DOMAINS = {
    "medical": [
        "bleed", "bleeding", "wound", "fracture", "broken", "burn", "shock",
        "unconscious", "pulse", "breath", "breathing", "chest", "seizure",
        "poisoning", "overdose", "allergic", "anaphylaxis", "infection",
        "sepsis", "fever", "childbirth", "labour", "labor", "delivery",
        "stroke", "heart", "cardiac", "cpr", "resuscitation", "tourniquet",
        "suture", "stitch", "amputation", "crush", "spinal", "head injury",
        "concussion", "dose", "dosage", "medicine", "drug", "antibiotic",
        "symptoms", "sick", "illness", "injured", "injury", "injur",
        "treat", "treatment", "diagnose", "diagnosis", "pain", "hurt",
        # Food safety — misidentification is life threatening
        "can i eat", "safe to eat", "edible", "mushroom", "berry", "berries",
        "plant safe", "poisonous", "toxic plant", "is it safe",
    ],
    "chemical": [
        "acid", "caustic", "lye", "bleach", "ammonia", "chlorine", "cyanide",
        "explosive", "gunpowder", "fume", "toxic", "poison", "contaminate",
        "solvent", "flammable", "combustible", "oxidiser", "react",
        "synthesis", "distill", "methanol",
    ],
    "electrical": [
        "live wire", "mains", "high voltage", "electrocute", "short circuit",
        "capacitor charge", "generator connect", "battery terminals",
    ],
    "structural": [
        "load bearing", "foundation collapse", "trench", "excavate",
        "roof weight", "wall support", "scaffold", "demolish", "tunnel",
    ],
    "emergency": [
        "dying", "not breathing", "no pulse", "unconscious", "right now",
        "emergency", "critical", "life threatening", "can't stop bleeding",
        "bleeding badly", "bleeding a lot", "bleeding and", "i'm bleeding",
        "won't stop", "getting worse fast", "turning blue", "unresponsive",
    ],
}

AMBIGUITY_MARKERS = [
    "maybe", "might", "think", "not sure", "possibly", "could be",
    "looks like", "seems", "appears", "kind of", "sort of",
    "i don't know", "unsure", "unclear", "not certain", "maybe",
    "possibly", "perhaps",
]


# ── Response plan ──────────────────────────────────────────────────────────

@dataclass
class ResponsePlan:
    mode: ResponseMode
    is_high_risk: bool
    risk_domains: List[str]
    is_emergency: bool
    worst_case_assumed: bool
    assumptions: List[str]
    clarifications: List[str]
    confidence_band: str
    system_addendum: str
    format_template: str


# ── Decision gate ──────────────────────────────────────────────────────────

class DecisionGate:
    """
    Evaluates every query before it reaches the LLM.
    Returns a ResponsePlan that shapes the system prompt.
    Confidence is used internally — never surfaced to user.
    """

    def evaluate(
        self,
        query: str,
        tab_id: str,
        confidence_score: int,
        sources_found: int,
        sources_conflict: bool,
        context_complete: bool,
    ) -> ResponsePlan:

        q = query.lower()

        # Detect risk domains
        risk_domains = [
            domain for domain, keywords in HIGH_RISK_DOMAINS.items()
            if any(kw in q for kw in keywords)
        ]

        is_high_risk  = len(risk_domains) > 0
        is_emergency  = "emergency" in risk_domains
        has_ambiguity = any(m in q for m in AMBIGUITY_MARKERS)

        # Worst-case bias — assume highest-risk interpretation when ambiguous
        worst_case_assumed = is_high_risk and has_ambiguity
        assumptions = self._assumptions(q, risk_domains) if worst_case_assumed else []

        # Confidence band — internal only
        band = self._band(confidence_score, sources_found, sources_conflict, context_complete)

        # Choose mode
        mode = self._mode(band, is_emergency, is_high_risk, has_ambiguity,
                          context_complete, sources_conflict, tab_id)

        # Clarifying questions if needed
        clarifications = (
            self._clarifications(q, risk_domains, tab_id)
            if mode == ResponseMode.CLARIFY else []
        )

        # Build system addendum
        addendum, template = self._build(
            mode, is_high_risk, is_emergency, worst_case_assumed,
            assumptions, risk_domains, sources_conflict
        )

        return ResponsePlan(
            mode=mode,
            is_high_risk=is_high_risk,
            risk_domains=risk_domains,
            is_emergency=is_emergency,
            worst_case_assumed=worst_case_assumed,
            assumptions=assumptions,
            clarifications=clarifications,
            confidence_band=band,
            system_addendum=addendum,
            format_template=template,
        )

    # ── Confidence banding ─────────────────────────────────────────────────

    def _band(self, score, sources, conflict, complete) -> str:
        if conflict or not complete:
            return "low" if score >= 70 else "very_low"
        if score >= 80 and sources >= 2:
            return "high"
        if score >= 65 and sources >= 1:
            return "medium"
        if score >= 50:
            return "low"
        return "very_low"

    # ── Mode selection ─────────────────────────────────────────────────────

    def _mode(self, band, is_emergency, is_high_risk, has_ambiguity,
              context_complete, sources_conflict, tab_id="") -> ResponseMode:

        if is_emergency:
            return ResponseMode.EMERGENCY

        # Companion tab — always DIRECT unless emergency
        if tab_id == "prometheus":
            return ResponseMode.DIRECT

        # Conflicting sources: CAUTIOUS (show both options) not SAFE_MODE
        if sources_conflict and is_high_risk:
            return ResponseMode.CAUTIOUS

        # High-risk + ambiguous query: CLARIFY before anything else
        if is_high_risk and has_ambiguity:
            return ResponseMode.CLARIFY

        # No sources at all in a high-risk domain = safe mode
        if not context_complete and is_high_risk:
            return ResponseMode.SAFE_MODE

        # Very low confidence: safe_mode if no context, clarify if high-risk with context
        if band == "very_low":
            if not is_high_risk and not context_complete:
                return ResponseMode.SAFE_MODE
            if context_complete and is_high_risk:
                return ResponseMode.CLARIFY
            return ResponseMode.SAFE_MODE

        # High-risk domains: stay CAUTIOUS even at high band (life safety)
        # Exception: procedure intent with good sources can be direct —
        # but since _mode doesn't receive intent, we rely on band for this
        if is_high_risk:
            if band == "low":
                return ResponseMode.SAFE_MODE
            return ResponseMode.CAUTIOUS  # medium or high: still cautious for safety

        if band == "medium":
            return ResponseMode.CAUTIOUS

        if band == "low":
            return ResponseMode.CAUTIOUS

        return ResponseMode.DIRECT

    # ── Worst-case assumptions ─────────────────────────────────────────────

    def _assumptions(self, q, risk_domains) -> List[str]:
        out = []

        if "medical" in risk_domains:
            if any(w in q for w in ["bleed", "wound", "cut"]):
                out.append("Assuming serious wound with significant bleeding until confirmed otherwise.")
            if any(w in q for w in ["fell", "fall", "hit", "crash"]):
                out.append("Assuming possible spinal injury — treating as such until ruled out.")
            if any(w in q for w in ["fever", "sick", "ill"]):
                out.append("Assuming active infection risk until confirmed otherwise.")

        if "chemical" in risk_domains:
            out.append("Assuming chemical hazard is present and dangerous until confirmed safe.")

        if "electrical" in risk_domains:
            out.append("Assuming live electrical hazard until confirmed de-energised.")

        if "structural" in risk_domains:
            out.append("Assuming structural instability risk — confirming load-bearing status required.")

        return out

    # ── Clarifying questions ───────────────────────────────────────────────

    def _clarifications(self, q, risk_domains, tab_id) -> List[str]:
        questions = []

        if "medical" in risk_domains:
            if any(w in q for w in ["bleed", "wound", "cut", "injur"]):
                questions = [
                    "Where on the body is the injury?",
                    "Is bleeding actively occurring — and is it spurting or seeping?",
                    "Is the person conscious and responsive?",
                ]
            elif any(w in q for w in ["sick", "fever", "pain", "ill"]):
                questions = [
                    "How long have the symptoms been present?",
                    "What is the approximate temperature if known?",
                    "What other symptoms are present alongside this?",
                ]
            else:
                questions = [
                    "Can you describe what is happening in more detail?",
                    "Is this affecting you or someone else?",
                    "How urgent is the situation right now?",
                ]

        elif "chemical" in risk_domains:
            questions = [
                "What specific materials are involved?",
                "Is there already exposure, or is this preparation?",
                "What is the intended purpose?",
            ]

        elif "electrical" in risk_domains:
            questions = [
                "Is the power source currently disconnected?",
                "What voltage are you working with if known?",
                "What are you trying to achieve?",
            ]

        elif "structural" in risk_domains:
            questions = [
                "What is the structure made of?",
                "What load is it currently supporting?",
                "What outcome are you working toward?",
            ]

        else:
            questions = ["Can you give me a bit more detail about your situation?"]

        return questions[:3]

    # ── System prompt addendum builder ─────────────────────────────────────

    def _build(self, mode, is_high_risk, is_emergency, worst_case,
               assumptions, risk_domains, sources_conflict):

        parts = []

        if mode == ResponseMode.EMERGENCY:
            parts.append(
                "EMERGENCY MODE.\n"
                "Lead with the single most critical action — doable in seconds.\n"
                "Continue in priority order. Short sentences. No preamble.\n"
                "A 2-step answer is better than a padded 4-step one.\n"
                "End with the one condition that changes everything.\n"
                "Vary the phrasing naturally — clarity matters more than format."
            )

        elif mode == ResponseMode.SAFE_MODE:
            parts.append(
                "SAFE MODE — not enough information for full guidance.\n"
                "Say what you can safely say, then be honest about what you cannot.\n"
                "Tell the person what you need to know to help them properly.\n"
                "Keep it natural — don't follow a script, just be genuinely careful."
            )

        elif mode == ResponseMode.CLARIFY:
            parts.append(
                "CLARIFICATION NEEDED before answering.\n"
                "Acknowledge briefly, then ask what you need.\n"
                "2-3 questions only — the ones that will actually change your answer.\n"
                "Don't give the answer yet."
            )

        elif mode == ResponseMode.CAUTIOUS:
            parts.append(
                "Answer clearly but flag uncertainty honestly.\n"
                "Match length and format to the question — "
                "a simple question needs a direct answer with a caveat, "
                "not a five-step procedure with warnings at every stage.\n"
                "If something needs verifying, say so once and move on."
            )

        elif mode == ResponseMode.DIRECT:
            parts.append(
                "Answer directly. Match the length to what's actually needed.\n"
                "Steps where they help, prose where it reads better. No padding."
            )

        # Worst-case assumptions — natural language, not a header
        if worst_case and assumptions:
            assumption_lines = "\n".join(f"- {a}" for a in assumptions)
            parts.append(
                f"State these assumptions briefly before answering:\n{assumption_lines}"
            )

        # High risk — intent not script
        if is_high_risk and mode not in (ResponseMode.EMERGENCY, ResponseMode.SAFE_MODE):
            domains = ", ".join(risk_domains)
            parts.append(
                f"High-risk area ({domains}): if anything critical is unclear, "
                "say what you're assuming. Don't guess silently."
            )

        # Source conflict
        if sources_conflict:
            parts.append(
                "Sources disagree here. Give the safer option. "
                "Note the disagreement in one sentence."
            )

        return "\n\n".join(parts), ""
