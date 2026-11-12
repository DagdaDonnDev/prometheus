"""
LLM Bounding Layer
==================
Constrains what the LLM is allowed to do based on:
  - Intent (procedure, diagnose, discuss, etc.)
  - Response mode (emergency, safe, cautious, direct)
  - Tab context

COMPANION TAB IS FULLY EXEMPT from all bounding rules.
The companion tab has its own personality defined separately.

All other tabs: LLM is bounded to:
  - Summarise and present retrieved knowledge
  - Clarify ambiguous situations

It is explicitly NOT allowed to (in knowledge tabs):
  - Invent medical procedures not in the knowledge base
  - Speculate on diagnoses without source backing
  - Give dosages or quantities without cited sources
  - Deviate from emergency response format
  - Fill knowledge gaps with training data in strict domains
"""

from enum import Enum
from core.answers.intent_router import Intent, RoutingPlan
from core.answers.decision_gate import ResponseMode


# ── Companion tab — fully exempt, warm teacher personality ────────────────

COMPANION_PERSONALITY = """
You are {name}. Talk like a real person — calm, plain, a bit dry. Not a performer.{persona}
Your name is {name} — never say you don't have one. If they ask who you are: you're {name},
an offline companion on their own device.

- No exclamation marks, no gushing, no "Oh!" or "Ah," openers, no "I love that!".
- Be curious. Ask about what they said and follow the thread.
- Keep it short unless they want more. "mhm", "yeah?", "fair", "go on" are fine replies.
- Don't check on how they're feeling, don't assume something's wrong, don't reassure unless asked.
- No therapy talk: no "I hear you", "that sounds hard", "it's okay to feel", "how does that make you feel".
- Have opinions. Disagree sometimes.
- No lists, no advice unless they ask for it.
- If they ask you to tell them something ("tell me something interesting"), do it — don't
  hand the question back.
- If you don't know something — a film, a book, a person, a fact — say you don't know.
  Never make up plots, names or details.
- If they correct you, take it on board ("my mistake") and move on. Don't argue or repeat it.
- If they say they're in real danger or might hurt themselves, be straight with them about getting help.
"""


# ── LLM role constraints by intent (knowledge tabs only) ──────────────────

# Short, plain sentences. They used to be 500+ words of ALL-CAPS sections and
# numbered scripts ("Say: 'My sources disagree…'") around two library facts —
# a 1.7B model lost the facts and repeated the scripts in its replies.
# Each role: what to do, in two or three lines.
ROLE_CONSTRAINTS = {
    Intent.EMERGENCY: """
Emergency: give the library's steps, numbered, most urgent first, in short sentences.
No explaining until the steps are done. Add nothing the library doesn't say.
""",
    Intent.PROCEDURE: """
Give the library's steps in order, numbered. Keep amounts, times and temperatures exactly as the library has them — never invent a step or a number.
If a critical detail is missing, ask one clarifying question.
""",
    Intent.DIAGNOSE: """
Say what the library says these signs can mean. Never give a definite diagnosis, or a dose the library doesn't state.
Say what you'd need to know to narrow it down.
If uncertain, ask a clarifying question first.
""",
    Intent.IDENTIFY: """
Describe the identifying features the library gives.
Never call a plant or mushroom safe to eat unless the library clearly says so — if in doubt, say don't eat it.
""",
    Intent.LOCATE: """
Say where and how to find it, using what the library says.
""",
    Intent.EXPLAIN: """
Explain it simply, from the library. You may connect ideas, but don't pass off your own knowledge as the library's.
""",
    Intent.DISCUSS: """
Talk it through like a thoughtful friend; you may draw on what you know.
""",
    Intent.REFLECT: """
Listen first and acknowledge what they said, then gently offer something useful. No rushing to fix it, no hollow reassurance.
""",
    Intent.ASSESS: """
Weigh their options using what the library says, and name the key factors.
If something would change your answer, ask a clarifying question about it.
""",
    Intent.PLAN: """
Turn it into a short, ordered plan using the library. Don't assume tools or supplies they haven't mentioned.
""",
}

# ── Domain drift guards ────────────────────────────────────────────────────

DRIFT_GUARDS = {
    "medical": """
Medical: every step and every dose only from the library — if a dose isn't there, say it isn't.
End with what to watch for and when to get help.
""",
    "chemistry": """
Chemistry: amounts and temperatures only from the library. Give the safety warning before the steps.
If a step is unclear in the library, say so — don't guess.
""",
    "electronics": """
Electronics: voltages and part values only from the library. Warn before anything high-voltage.
Don't assume one part can replace another.
""",
}

# ── When the library falls short ──────────────────────────────────────────

FAILURE_INSTRUCTIONS = """
When the library falls short:
- Nothing on it: say so in your own words, then give the closest thing it has.
- Passages disagree: give both, and say which is the safer choice.
- Too vague to answer safely: ask up to two short questions.
- It needs something you don't have: say what's missing, then what you can say.
"""


def build_bounds(
    plan: RoutingPlan,
    mode: ResponseMode,
    has_sources: bool,
    sources_conflict: bool,
    tab_id: str,
) -> str:
    """
    Build the bounding instructions for the LLM.

    Companion tab: returns warm teacher personality, no constraints.
    All other tabs: returns role constraints, domain guards, failure modes.
    """

    # ── Companion tab — fully exempt ───────────────────────────────────────
    if tab_id == "prometheus":
        return COMPANION_PERSONALITY

    # ── Knowledge tabs — full bounding ────────────────────────────────────
    parts = []

    # Safety-critical sections keep every guard; elsewhere, guards meant for
    # missing or conflicting sources only go in when that's the case — small
    # models echo them as extra caveats and questions even when the sources
    # answer the question (the owner saw this in the Build tab).
    high_stakes = tab_id in ("medical", "chemistry")
    weak = (not has_sources) or sources_conflict or \
        mode in (ResponseMode.SAFE_MODE, ResponseMode.CLARIFY)

    role = ROLE_CONSTRAINTS.get(plan.intent, ROLE_CONSTRAINTS[Intent.EXPLAIN]).strip()
    # Asking questions only when the library falls short: with good passages
    # it tacked a "Clarification Needed:" list onto a complete answer (bench, lye)
    if not weak:
        role = "\n".join(ln for ln in role.splitlines() if "clarifying question" not in ln)
    parts.append(role)

    guard = DRIFT_GUARDS.get(tab_id, "")
    if guard:
        parts.append(guard.strip())

    # An emergency gets only what it needs: the steps, the domain's rule
    if plan.intent == Intent.EMERGENCY:
        return "\n\n".join(parts)

    if high_stakes or weak:
        parts.append(FAILURE_INSTRUCTIONS.strip())

    # Plain sentences, no "SOURCE STATUS:" labels — the speaker repeated those
    # in its replies ("Source status: Retrieved sources available.")
    if not has_sources:
        parts.append(
            "Nothing relevant came up in the library for this. Say so briefly in your own "
            "words, then help with what you can."
        )
    elif sources_conflict:
        parts.append(
            "The library passages disagree. Give both and say which is the safer choice."
        )
    else:
        parts.append(
            "Answer from the library below. Don't talk about \"sources\" or \"retrieved\" "
            "content — just answer."
        )

    if not plan.allow_discussion:
        parts.append("No opinions — stay close to what the library says.")
    else:
        parts.append(
            "You may draw on what you know too; the library passages come first."
        )

    return "\n\n".join(parts)
