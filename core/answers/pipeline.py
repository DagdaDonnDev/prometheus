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

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.answers.intent_router import IntentRouter, RoutingPlan
from core.ai.librarian import facts_block
from core.answers.sufficiency_gate import SourceSufficiencyGate
from core.answers.contradiction import ContradictionDetector
from core.answers.decision_gate import DecisionGate, ResponseMode
from core.ai.llm_bounds import build_bounds, COMPANION_PERSONALITY
from core.answers.intent_router import Intent
from core.answers.memory_filter import MemoryRelevanceFilter

# Companion tab only looks things up when the message is about these
COMPANION_TOPICS = [
    "stoic", "frankl", "camus", "jung", "aristotle", "epictetus", "aurelius",
    "seneca", "thoreau", "walden", "nietzsche", "philosoph", "psycholog",
    "existential", "absurd", "meaning of life", "buddh", "ethics", "virtue",
]

CRISIS_PROMPT = """
Someone has just told you they may want to die or hurt themselves. Nothing matters more right now.
- Be warm, calm and direct. Short sentences. No lists, no lectures.
- Take it seriously. Ask if they're safe right now.
- Encourage them to reach a real person today: someone they trust nearby, or the local
  emergency number or a crisis line if there's any way to reach one.
- Stay with them. Ask what's going on. Don't change the subject.
- Don't promise everything will be fine.
""".strip()

# Short follow-ups that ask about the previous answer ("why?", "yes but why")
FOLLOW_UP_STARTS = (
    "why", "how come", "how so", "what do you mean", "are you sure", "really",
    "says who", "based on what", "source", "proof", "explain", "but why",
    "yes but", "ok but", "okay but", "how do you know", "what makes",
)
FOLLOW_UP_NOTE = (
    "FOLLOW-UP: they're asking about your previous answer. Explain the reasoning "
    "behind it, using the sources above. If the sources don't support something "
    "you said, say so plainly and correct it."
)


def previous_question(tab, current: str) -> str:
    """The user's message before this one in the tab, or ""."""
    users = [m["content"] for m in getattr(tab, "history", []) if m.get("role") == "user"]
    if users and users[-1].strip() == current.strip():
        users = users[:-1]          # the current message is already in history
    return users[-1] if users else ""


def last_reply(tab) -> str:
    """The assistant's last reply in the tab, or ""."""
    replies = [m["content"] for m in getattr(tab, "history", []) if m.get("role") == "assistant"]
    return replies[-1] if replies else ""


def is_follow_up(text: str) -> bool:
    q = text.lower().strip(" ?!.")
    return len(q.split()) <= 6 and (q.startswith(FOLLOW_UP_STARTS) or q in ("why", "how", "source"))


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
    images:        List[str] = field(default_factory=list)   # page images of the passages used
    sources:       List[str] = field(default_factory=list)   # "Book, p. 12" for each passage used
    # What changes every message (facts found, rules for this answer, tone).
    # It travels WITH the newest message instead of in system_prompt, so the
    # model can reuse its memory of the chat so far: Ollama skips re-reading
    # whatever starts the same as last time (with_turn_context below).
    turn_context:  str = ""

    @property
    def full_prompt(self) -> str:
        """Everything the speaker is told, in order (for tests and the trace)."""
        return "\n\n".join(x for x in (self.system_prompt, self.turn_context) if x)


def with_turn_context(messages: List[Dict], turn_context: str) -> List[Dict]:
    """
    The chat to send: history unchanged (so it matches what the model read
    last time), and this message's context put in front of the newest
    message only. The saved history keeps just what the person typed.
    """
    if not turn_context or not messages or messages[-1].get("role") != "user":
        return messages
    last = dict(messages[-1])
    last["content"] = (f"[For this reply — not part of their message]\n{turn_context}\n\n"
                       f"[Their message]\n{last['content']}")
    return messages[:-1] + [last]


class QueryPipeline:

    def __init__(self, memory, knowledge, llm, map_engine=None):
        self.config        = getattr(llm, "config", None)
        self.memory        = memory
        self.knowledge     = knowledge
        self.llm           = llm
        self.map_engine    = map_engine
        self.router        = IntentRouter()
        self.sufficiency   = SourceSufficiencyGate()
        self.contradiction = ContradictionDetector()
        self.gate          = DecisionGate()
        self.mem_filter    = MemoryRelevanceFilter()
        from core.ai.librarian import Librarian
        self.librarian     = Librarian(llm)

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
        return f"🧮 {reason} This answer is from the library."

    # ── Steps 2–10 ─────────────────────────────────────────────────────────

    def prepare_knowledge(self, tab, user_input: str,
                          routing_plan: RoutingPlan, trace=None, progress=None) -> PreparedAnswer:
        """
        Everything before the speaker starts talking. With two models this
        makes up to two short model calls (the brief, the librarian), so the
        window runs it on a background thread; progress(text) reports
        "Checking the library…" while it works.
        """

        # Crisis wording → crisis response, in any tab
        if routing_plan.is_crisis:
            return self._prepare_crisis(trace)

        # Companion tab: a short friend-like prompt instead of the knowledge
        # pipeline (emergencies still go the full way below)
        if tab.id == "prometheus" and routing_plan.intent != Intent.EMERGENCY:
            return self._prepare_companion(user_input, routing_plan, trace, tab=tab,
                                           progress=progress)

        # Step 2: tiered retrieval. A short follow-up ("yes but why") has nothing
        # to search for on its own — search with the previous question too, so
        # the model keeps the sources behind the answer it's being asked about.
        follow_up = is_follow_up(user_input) and bool(previous_question(tab, user_input))
        search_q = (f"{previous_question(tab, user_input)} {user_input}"
                    if follow_up else user_input)
        # Two models: the speaker writes the librarian a clear request first —
        # search words and the full question ("their missions" → which missions).
        # Not in an emergency: there the message is searched as written, and the
        # speaker reads the field-manual passages itself, word for word.
        use_librarian = self.librarian.enabled() and routing_plan.intent != Intent.EMERGENCY
        question = user_input
        # Low power: no separate request step — the librarian works from the
        # message as written (one model call fewer per question)
        low_power = getattr(self.config, "low_power_active", False)
        if use_librarian and not low_power:
            if progress:
                progress("Checking the library")
            brief = self.librarian.brief(user_input, previous_question(tab, user_input),
                                         last_reply(tab))
            search_q = f"{brief.search} {search_q}"
            question = brief.question
            if trace:
                trace.brief_ms = brief.ms
        knowledge_context, confidence_note = self.knowledge.search(
            query=search_q, routing_plan=routing_plan,
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

        # Step 7b: a named thing with its own Wikipedia article (never for
        # medical or strict questions — those stay on the field manuals)
        wiki_sources = []
        if not routing_plan.is_strict and tab.id != "medical":
            wiki_text, wiki_sources = self._wikipedia_background(search_q, 100)
            if wiki_text:
                knowledge_context = (knowledge_context + "\n\n---\n\n" if knowledge_context else "") + \
                    "[General reference — lower priority than the sources above]\n" + wiki_text
            else:
                missing = self._not_in_library_note(user_input)
                if missing:
                    knowledge_context = (knowledge_context + "\n\n" if knowledge_context else "") + missing

        # Step 7c: the librarian reads the passages and keeps only the facts
        # that answer the question; the speaker gets those instead of the
        # passages, and may state nothing else about it
        if use_librarian and (raw_chunks or wiki_sources):
            passages = [(self.knowledge.scorer._source_label(r.get("source", ""), r.get("domain", "")),
                         r.get("content", ""))
                        for r in (getattr(self.knowledge, "_last_used_chunks", None)
                                  or raw_chunks[:max(1, getattr(self.knowledge, "prompt_passages", 3))])]
            if not routing_plan.is_strict and tab.id != "medical":
                passages += self._wiki_passages(search_q, 200)
            facts = self.librarian.extract(question, passages)
            if trace:
                trace.librarian_ms = facts.ms
            if not facts.failed:
                knowledge_context = facts_block(facts)

        # Step 8: the section's role is the fixed instructions; everything
        # decided for THIS question (rules, facts, guidance — guidance last)
        # goes with the newest message
        system_prompt = self._tab_system(tab)
        turn_context = self.llm.build_system_prompt(
            tab_system="",
            user_context=context,
            knowledge_context=knowledge_context,
            confidence_note=confidence_note,
            decision_addendum=(plan.system_addendum + "\n\n" + FOLLOW_UP_NOTE
                               if follow_up else plan.system_addendum),
            llm_bounds=bounds,
        )
        turn_context = turn_context.strip()
        if trace:
            trace.prompt_chars = len(system_prompt) + len(turn_context)

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

        images = list(getattr(self.knowledge, "get_last_images", lambda: [])() or [])
        sources = list(getattr(self.knowledge, "get_last_sources", lambda: [])() or []) + wiki_sources

        return PreparedAnswer(
            system_prompt=system_prompt,
            turn_context=turn_context,
            mode=plan.mode,
            intent=routing_plan.intent.value,
            sufficiency=verdict,
            status_text=status,
            clarify_text=clarify_text,
            images=images,
            sources=sources,
        )

    def assistant_name(self) -> str:
        return (getattr(self.config, "assistant_name", "") or "Prometheus").strip()

    def companion_personality(self) -> str:
        """The companion prompt with the chosen name and persona filled in."""
        persona = (getattr(self.config, "assistant_persona", "") or "").strip()
        return COMPANION_PERSONALITY.strip().format(
            name=self.assistant_name(),
            persona=f"\nHow you come across: {persona}" if persona else "",
        )

    def _tab_system(self, tab) -> str:
        """Tab prompt with the assistant's chosen name."""
        name = self.assistant_name()
        return tab.system_prompt.replace("You are Prometheus", f"You are {name}")

    def _prepare_crisis(self, trace=None) -> PreparedAnswer:
        if trace:
            trace.gate_mode = "emergency"
            trace.risk_domains = ["crisis"]
        return PreparedAnswer(
            system_prompt=CRISIS_PROMPT,
            mode=ResponseMode.EMERGENCY,
            intent="crisis",
            sufficiency="NONE",
            status_text="",
        )

    def _prepare_companion(self, user_input: str, routing_plan: RoutingPlan,
                           trace=None, tab=None, progress=None) -> PreparedAnswer:
        """
        Friend-like chat. Kept deliberately small: every extra token in the
        prompt is read by the model before its first word (that was ~3 s).

        Step 1: the companion personality
        Step 2: their name, if known, then a short line of what they've told
                you about themselves (core/you/profile) and earlier chat topics
        Step 3: only for philosophy/psychology questions, two short
                passages from the companion shelf as background
        Step 4: if the message names something with a Wikipedia article
                (a film, show, band, book, person), that article's opening
        """
        parts = [self.companion_personality()]

        name = (self.memory.data.get("user", {}) or {}).get("name")
        if name:
            parts.append(f"Their name is {name}.")

        # Step 2b: what they've told you about themselves, and what earlier
        # chats in this tab were about (titles only — a new chat stays fresh)
        from core.you.profile import about_line, earlier_topics
        for line in (about_line(self.memory), earlier_topics(tab)):
            if line:
                parts.append(line)

        # Everything above changes rarely → the fixed instructions. Everything
        # below changes per message → turn context (see with_turn_context).
        stable, parts = parts, []

        # With two models, anything looked up goes to the librarian first and
        # only its facts reach this prompt (collected here, read in Step 4b)
        use_librarian = self.librarian.enabled()
        passages = []

        q = user_input.lower()
        if any(t in q for t in COMPANION_TOPICS):
            from core.answers.confidence import trim_passage
            search = getattr(self.knowledge, "_search_domains", None)
            chunks = search(user_input, ["companion"], 2) if search else []
            if chunks and use_librarian:
                passages += [("Companion shelf", c["content"]) for c in chunks]
            elif chunks:
                notes = "\n\n".join(trim_passage(c["content"], user_input, 90) for c in chunks)
                parts.append(
                    "Background you can draw on, in your own words, only if it helps:\n" + notes
                )
            if trace:
                trace.retrieval.total_chunks = len(chunks)
                trace.retrieval.has_sources = bool(chunks)

        # Step 3b: a note of theirs (Obsidian) that the message names by title
        from core.library.obsidian import notes_named_in
        own = notes_named_in(user_input)
        if own and use_librarian:
            passages += [(f"Their note — {t}", b) for t, b in own]
        elif own:
            parts.append("From their own notes (they wrote this):\n" +
                         "\n\n".join(f"{t}: {b}" for t, b in own))

        # Step 4 — what Wikipedia has on the thing being talked about, or, if
        # it's something we have nothing on, say so. A follow-up that doesn't
        # name it ("go into the lore", "their missions") keeps the subject
        # from the last few messages — that's where the made-up lore came from.
        subject = self._subject_text(tab, user_input) if not own else user_input
        carried = subject != user_input
        wiki_notes, sources = self._wikipedia_background(subject)
        sources = [f"Obsidian — {t}" for t, _ in own] + sources
        if wiki_notes and use_librarian:
            passages += self._wiki_passages(subject, 250)
        elif wiki_notes:
            parts.append(("Earlier in this chat they asked about this — use it only if they "
                          "still are.\n" if carried else "") + wiki_notes)
        elif not own and not passages:
            missing = self._not_in_library_note(subject)
            if missing and carried:
                missing = "If they're still on the same subject — " + missing
            if missing:
                parts.append(missing)

        # Step 4b: the librarian reads what was found and keeps only the facts
        # that answer them; the speaker may say nothing else about it
        if passages:
            if progress:
                progress("Checking the library")
            question = (f"{user_input} (about: {subject})" if carried else user_input)
            facts = self.librarian.extract(question, passages)
            if trace:
                trace.librarian_ms = facts.ms
            if facts.failed:            # librarian unreachable: the speaker reads them itself
                parts.append("Background from the library — use only this for facts about it:\n" +
                             "\n\n".join(f"{label}: {' '.join(text.split()[:110])}"
                                           for label, text in passages))
            else:
                parts.append(("If they're still on the same subject — " if carried else "") +
                             facts_block(facts, "it"))

        # Step 5: how to sound right now — read from their message in code,
        # last in the prompt (a small model can't pick tone up on its own)
        from core.ai.tone import detect_tone
        tone, how = detect_tone(user_input, previous_question(tab, user_input) if tab else "")
        parts.append(f"Right now: {how}")

        system_prompt = "\n\n".join(stable)
        turn_context = "\n\n".join(parts)
        if trace:
            trace.gate_mode = "direct"
            trace.risk_domains = [f"tone:{tone}"]
            trace.prompt_chars = len(system_prompt) + len(turn_context)
        return PreparedAnswer(
            system_prompt=system_prompt,
            turn_context=turn_context,
            mode=ResponseMode.DIRECT,
            intent=f"chat_{tone}",          # sets the temperature (core/ai/llm.py)
            sufficiency="NONE",
            status_text="",
            sources=sources,
        )

    @staticmethod
    def _subject_text(tab, user_input: str) -> str:
        """
        The message that names what's being talked about.

        Step 1: the current message, if it names something (an article, or a
                specific thing we don't have)
        Step 2: otherwise, if it reads like a continuation (short, "more",
                "it/they/their", "lore"…), the newest of the last 4 messages
                that did name something
        Step 3: otherwise the current message (a new topic)
        """
        from core.library.wiki_lookup import asked_about, find_articles
        # Step 1
        if find_articles(user_input, max_articles=1) or asked_about(user_input):
            return user_input
        # Step 2 — "anyway…", "how was your day" start something new
        q = user_input.lower()
        if re.match(r"(anyway|anyways|by the way|btw|different question|new question|"
                    r"forget that|never ?mind|how are you|how was your|how's your|good morning|"
                    r"good night|hey|hi|hello)\b", q):
            return user_input
        continuing = (len(q.split()) <= 8 or is_follow_up(user_input) or re.search(
            r"\b(more|it|its|it's|they|them|their|he|his|she|her|that|this|those|lore|story|"
            r"plot|ending|character|characters|details?|history)\b", q))
        if continuing and tab is not None:
            users = [m["content"] for m in getattr(tab, "history", []) if m.get("role") == "user"]
            if users and users[-1].strip() == user_input.strip():
                users = users[:-1]
            for earlier in reversed(users[-4:]):
                if find_articles(earlier, max_articles=1) or asked_about(earlier):
                    return earlier
        # Step 3
        return user_input

    @staticmethod
    def _not_in_library_note(user_input: str) -> str:
        """
        They asked about a specific thing (a film, book, person…) and there's
        no article for it: the model must say so, not invent a plot.
        """
        from core.library.wiki_lookup import asked_about
        thing = asked_about(user_input)
        if not thing:
            return ""
        return (f'NOT IN YOUR LIBRARY: you have nothing about "{thing}" — it isn\'t in your '
                f'offline database. Say that plainly, e.g. "I don\'t have {thing} in my '
                f'database." Don\'t guess, and don\'t describe it from memory.')

    @staticmethod
    def _wiki_passages(text: str, words: int = 250):
        """[("Wikipedia — Title", opening ~words)] for the articles a message names."""
        from core.library.wiki_lookup import find_articles, lead
        return [(f"Wikipedia — {title}", lead(path, words))
                for title, path in find_articles(text, max_articles=2)]

    @staticmethod
    def _wikipedia_background(user_input: str, words: int = 110):
        """
        Openings of the Wikipedia articles the message names (by title — a few
        milliseconds, no search). Returns (prompt text, ["Wikipedia — Title"]).
        """
        from core.library.wiki_lookup import find_articles, lead
        found = find_articles(user_input, max_articles=2)
        if not found:
            return "", []
        notes = [f"{title}: {lead(path, words)}" for title, path in found]
        text = ("What Wikipedia says (use it for facts; talk about it in your own words):\n"
                + "\n\n".join(notes) +
                "\nThat is ALL your library has on this. If they ask for more than it says "
                "(lore, plot, names, events), say that's all you've got on it — never fill in.")
        return text, [f"Wikipedia — {title}" for title, _ in found]

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
