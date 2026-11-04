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
        "won't stop", "getting worse fast", "turning blue", "unresponsive",
    ],
}

AMBIGUITY_MARKERS = [
    "maybe", "might", "think", "not sure", "possibly", "could be",
    "looks like", "seems", "appears", "kind of", "sort of",
    "i don't know", "unsure", "unclear", "not certain",
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
                          context_complete, sources_conflict)

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
        if score >= 88 and sources >= 2:
            return "high"
        if score >= 70 and sources >= 1:
            return "medium"
        if score >= 50:
            return "low"
        return "very_low"

    # ── Mode selection ─────────────────────────────────────────────────────

    def _mode(self, band, is_emergency, is_high_risk, has_ambiguity,
              context_complete, sources_conflict) -> ResponseMode:

        if is_emergency:
            return ResponseMode.EMERGENCY

        if band == "very_low" or (sources_conflict and is_high_risk):
            return ResponseMode.SAFE_MODE

        if is_high_risk and has_ambiguity and band in ("low", "very_low"):
            return ResponseMode.CLARIFY

        if is_high_risk and band == "low":
            return ResponseMode.SAFE_MODE

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
        template = ""

        if mode == ResponseMode.EMERGENCY:
            parts.append(
                "EMERGENCY MODE.\n"
                "Life-threatening situation. Response rules:\n"
                "- First instruction must be doable in under 5 seconds.\n"
                "- Maximum 4 steps. Short sentences only. No preamble.\n"
                "- One escalation condition at the end.\n"
                "- Do not hedge or qualify the first action."
            )
            template = (
                "STEP 1 — Do this now: [single immediate action]\n"
                "STEP 2 — [next]\n"
                "STEP 3 — [next]\n"
                "MONITOR — [what to watch]\n"
                "ESCALATE if — [single condition]"
            )

        elif mode == ResponseMode.SAFE_MODE:
            parts.append(
                "SAFE MODE.\n"
                "Confidence or context is insufficient for full guidance.\n"
                "- Conservative, stabilising instructions only.\n"
                "- No guessing or extrapolation.\n"
                "- State explicitly what you are uncertain about.\n"
                "- Tell the user what information would allow a better answer.\n"
                "- Do not provide step-by-step procedures for high-risk actions "
                "without clearer context."
            )
            template = (
                "What I can tell you safely: [conservative action]\n"
                "What I am uncertain about: [honest statement]\n"
                "What would help me give better guidance: [specific information needed]"
            )

        elif mode == ResponseMode.CLARIFY:
            parts.append(
                "CLARIFICATION REQUIRED before proceeding.\n"
                "- Ask clarifying questions before giving any instructions.\n"
                "- Maximum 3 questions.\n"
                "- Brief acknowledgement first, then ask.\n"
                "- Do not provide the answer yet.\n"
                "- Do not assume unstated details."
            )
            template = (
                "Brief acknowledgement of the situation.\n"
                "Before I can give you the right answer, I need to know:\n"
                "1. [question]\n"
                "2. [question if needed]\n"
                "3. [question if needed]"
            )

        elif mode == ResponseMode.CAUTIOUS:
            parts.append(
                "CAUTIOUS MODE.\n"
                "- Answer with clear steps.\n"
                "- Flag any steps where confidence is lower.\n"
                "- Include one verification step where appropriate.\n"
                "- Do not omit information but be honest about uncertainty.\n"
                "- Never present uncertain information as definitive."
            )
            template = (
                "Clear answer with steps.\n"
                "Note uncertainty where it exists.\n"
                "Include what to check or verify."
            )

        elif mode == ResponseMode.DIRECT:
            parts.append(
                "High confidence. Give a direct, clear answer.\n"
                "No unnecessary hedging. Be concise and actionable."
            )
            template = "Direct answer with steps if applicable."

        # Worst-case assumptions — state them before instructions
        if worst_case and assumptions:
            assumption_lines = "\n".join(f"- {a}" for a in assumptions)
            parts.append(
                f"WORST-CASE ASSUMPTIONS APPLIED:\n{assumption_lines}\n"
                "State these assumptions at the start of your response "
                "before giving any instructions."
            )

        # High risk gate
        if is_high_risk and mode not in (ResponseMode.EMERGENCY, ResponseMode.SAFE_MODE):
            domains = ", ".join(risk_domains)
            parts.append(
                f"HIGH-RISK DOMAIN(S): {domains}.\n"
                "If any critical detail is missing or ambiguous, "
                "state your assumption explicitly before proceeding. "
                "Never proceed silently on an ambiguous high-risk instruction."
            )

        # Source conflict
        if sources_conflict:
            parts.append(
                "SOURCE CONFLICT: available sources do not fully agree.\n"
                "Present the most conservative option.\n"
                "Note the disagreement briefly without overwhelming the user."
            )

        if template:
            parts.append(f"RESPONSE FORMAT TO FOLLOW:\n{template}")

        return "\n\n".join(parts), template
