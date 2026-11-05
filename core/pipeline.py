"""
Query Pipeline — the decision layers in one place
=================================================
Everything that decides HOW to answer lives here, with no UI code.
The window (ui/main_window.py) only handles threads, widgets and the
voice. Desktop and Android run this same code (the APK is the same
PySide6 app, built with pyside6-android-deploy).

Flow for every query:
    route()                    Step 1: intent + domain tiers + Training Path flag
    Training Path (optional)   DerivationEngine.run() — see core/training/
    prepare_knowledge()        Steps 2–10 of the Knowledge Path:
        2  tiered retrieval
        3  source sufficiency gate
        4  contradiction detection
        5  decision gate (+ sufficiency override)
        6  LLM bounds
        7  memory relevance filter (+ map context)
        8  system prompt
        9  status message for the user
        10 CLARIFY → questions only, no LLM call
    Step 11 (streaming + voice) is done by the front end.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.intent_router import IntentRouter, RoutingPlan
from core.sufficiency_gate import SourceSufficiencyGate
from core.contradiction import ContradictionDetector
from core.decision_gate import DecisionGate, ResponseMode
from core.llm_bounds import build_bounds
from core.memory_filter import MemoryRelevanceFilter

# Training results that are shown to the user; anything else falls back
TRAINING_SHOW_STATUSES = {"DERIVED", "NEEDS_DATA"}

BOUNDARY_SIGNALS = {
    "emergency": "🚨 Emergency mode — immediate action protocol",
    "safe_mode": "🛡 Safe mode — limited sources, conservative guidance only",
    "clarify":   "❓ Clarification needed before proceeding",
    "cautious":  "⚠ Caution mode — verify before acting",
}


@dataclass
class PreparedAnswer:
    """Everything a front end needs to finish the answer."""
    system_prompt: str
    mode:          ResponseMode
    intent:        str
    sufficiency:   str                 # SUFFICIENT / WEAK / CONFLICTING / NONE
    status_text:   str = ""            # short note for the status bar / snackbar
    clarify_text:  str = ""            # non-empty → show this, skip the LLM
    images:        List[str] = field(default_factory=list)


class QueryPipeline:

    def __init__(self, memory, knowledge, llm, map_engine=None):
        self.memory        = memory
        self.knowledge     = knowledge
        self.llm           = llm
        self.map_engine    = map_engine
        self.router        = IntentRouter()
        self.sufficiency   = SourceSufficiencyGate()
        self.contradiction = ContradictionDetector()
        self.gate          = DecisionGate()
        self.mem_filter    = MemoryRelevanceFilter()

    # ── Step 1 ─────────────────────────────────────────────────────────────

    def route(self, user_input: str, tab_id: str, trace=None) -> RoutingPlan:
        plan = self.router.route(user_input, tab_id)
        if trace:
            trace.intent           = plan.intent.value
            trace.is_strict        = plan.is_strict
            trace.allow_discussion = plan.allow_discussion
        return plan

    # ── Training Path helpers ──────────────────────────────────────────────

    @staticmethod
    def training_should_show(result: Dict) -> bool:
        return result.get("status") in TRAINING_SHOW_STATUSES

    @staticmethod
    def training_fallback_note(result: Dict) -> str:
        """Chat note explaining why a derivation fell back. Empty = say nothing."""
        reason = result.get("reason", "")
        if not reason or result.get("status") == "NO_MATCH":
            return ""
        return f"🧮 {reason} Answer below is from the library."

    # ── Steps 2–10 ─────────────────────────────────────────────────────────

    def prepare_knowledge(self, tab, user_input: str,
                          routing_plan: RoutingPlan, trace=None) -> PreparedAnswer:

        # Step 2: tiered retrieval
        knowledge_context, confidence_note = self.knowledge.search(
            query=user_input, routing_plan=routing_plan,
        )
        scores = self.knowledge.get_last_scores()
        if trace:
            trace.retrieval.has_sources  = scores.get("has_sources", False)
            trace.retrieval.conflict     = scores.get("conflict", False)
            trace.retrieval.top_score    = scores.get("top_score", 0)
            trace.retrieval.total_chunks = scores.get("sources_found", 0)

        # Step 3: source sufficiency
        raw_chunks = getattr(self.knowledge, "_last_raw_chunks", [])
        suff = self.sufficiency.evaluate(
            scored_chunks=raw_chunks,
            intent=routing_plan.intent,
            routing_plan=routing_plan,
        )
        verdict = suff.verdict.value
        if trace:
            trace.sufficiency.verdict        = verdict
            trace.sufficiency.chunk_count    = suff.chunk_count
            trace.sufficiency.avg_confidence = suff.avg_conf

        # Step 4: contradiction detection
        has_contradiction, desc = self.contradiction.detect(raw_chunks, tab_id=tab.id)
        contradiction_instruction = ""
        if has_contradiction and desc:
            contradiction_instruction = self.contradiction.format_contradiction_response(
                desc, raw_chunks
            )

        # Step 5: decision gate, then let sufficiency tighten the mode
        plan = self.gate.evaluate(
            query=user_input,
            tab_id=tab.id,
            confidence_score=scores.get("top_score", 75),
            sources_found=suff.chunk_count,
            sources_conflict=verdict == "CONFLICTING",
            context_complete=verdict == "SUFFICIENT",
        )
        override = self.sufficiency.gate_mode_override(
            suff, plan.mode.value, intent=routing_plan.intent
        )
        if override:
            plan.mode = ResponseMode(override)
        if trace:
            trace.gate_mode           = plan.mode.value
            trace.worst_case          = plan.worst_case_assumed
            trace.risk_domains        = plan.risk_domains
            trace.safe_mode_triggered = plan.mode.value == "safe_mode"

        # Step 6: LLM bounds
        bounds = build_bounds(
            plan=routing_plan,
            mode=plan.mode,
            has_sources=verdict == "SUFFICIENT",
            sources_conflict=verdict == "CONFLICTING",
            tab_id=tab.id,
        )
        if contradiction_instruction:
            bounds = contradiction_instruction + "\n\n" + bounds

        # Step 7: only the most relevant memory, plus map context if known
        context = self.mem_filter.filter(
            memory_data=self.memory.data, query=user_input, tab_id=tab.id,
        )
        map_context = self._map_context()
        if map_context:
            context = context + "\n\n" + map_context

        # Step 8: system prompt (order matters — guidance last)
        system_prompt = self.llm.build_system_prompt(
            tab_system=tab.system_prompt,
            user_context=context,
            knowledge_context=knowledge_context,
            confidence_note=confidence_note,
            decision_addendum=plan.system_addendum,
            llm_bounds=bounds,
        )
        if trace:
            trace.prompt_chars = len(system_prompt)

        # Step 9: what the user is told about the system's state
        status = self.boundary_message(plan.mode.value, verdict, verdict != "NONE")

        # Step 10: CLARIFY → ask questions, no LLM call
        clarify_text = ""
        if plan.mode == ResponseMode.CLARIFY and plan.clarifications:
            if trace:
                trace.clarify_triggered = True
            questions = "\n".join(f"{i+1}. {q}" for i, q in enumerate(plan.clarifications))
            clarify_text = (
                "Before I can give you the right guidance, I need a few details:\n\n"
                + questions
            )

        images = []
        get_images = getattr(self.knowledge, "get_last_images", None)
        if get_images:
            images = get_images() or []

        return PreparedAnswer(
            system_prompt=system_prompt,
            mode=plan.mode,
            intent=routing_plan.intent.value,
            sufficiency=verdict,
            status_text=status,
            clarify_text=clarify_text,
            images=images,
        )

    def _map_context(self) -> str:
        if not self.map_engine:
            return ""
        try:
            loc = self.memory.data["user"].get("location_estimate", "")
            if loc and self.map_engine.is_ready():
                results = self.map_engine.search_locations(loc, limit=1)
                if results:
                    return self.map_engine.context_for_prompt(results[0].lat, results[0].lon)
        except Exception:
            pass
        return ""

    @staticmethod
    def boundary_message(mode: str, sufficiency: str, has_sources: bool) -> str:
        """Short status note about mode and sources (empty when all is normal)."""
        source_note = ""
        if not has_sources:
            source_note = " | No verified sources found"
        elif sufficiency == "CONFLICTING":
            source_note = " | Sources conflict — conservative option shown"
        elif sufficiency == "WEAK":
            source_note = " | Limited sources — verify if possible"
        return (BOUNDARY_SIGNALS.get(mode, "") + source_note).strip(" |")
