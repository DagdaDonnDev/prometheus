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
from core.ai.librarian import Facts, facts_block, loose_block, relevant, subject_words
from core.library.figures import wants_picture
from core.answers.tracer import short
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


# Words that point back at what was just being talked about
_LEANS_BACK = re.compile(r"\b(it|its|it's|they|them|their|theirs|he|him|his|she|her|hers|that|this|"
                         r"those|these|one|ones|more|story|lore|plot|ending|sequel|sequels|else|"
                         r"too|also|same|another)\b", re.I)


def leans_on_last(text: str) -> bool:
    """A short message that refers back ("what's the story of it?", "the game")."""
    q = text.lower()
    return len(q.split()) <= 10 and bool(_LEANS_BACK.search(q))


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



def _facts_note(facts) -> str:
    """The librarian's answer for the log."""
    if facts.failed:
        return "(couldn't be asked)"
    if facts.found and facts.text:
        return short(facts.text, 500)
    said = short(getattr(facts, "raw", ""), 160)
    return "NOT FOUND" + (f" (it wrote: {said})" if said and said.upper() != "NOT FOUND" else "")


def picture_note(lines: List[str], asked: bool) -> str:
    """What the speaker is told about pictures under its reply."""
    if lines:
        captioned = any(" — " in l for l in lines)
        return ("PICTURE shown under your reply (you CAN show pictures — never say you can't): "
                + "; ".join(lines) + ". Say in a few words that it's there"
                + ("; describe it only by its caption above." if captioned else
                   " — you can't see it, so don't describe what's in it.")
                + " No \"Source:\" line — sources are listed under your reply.")
    if asked:
        return "PICTURE: your library has no picture of this — say so in a few words."
    return ""


def _trace_librarian(trace, facts):
    """Time, words and Ollama's timing for the librarian's call."""
    trace.librarian_ms = facts.ms
    trace.librarian_text = _facts_note(facts)
    st = getattr(facts, "stats", None) or {}
    if st:
        trace.librarian_stats = (f"load {st.get('load_ms', 0)} ms · read {st.get('prompt_tokens', 0)} "
                                 f"tokens {st.get('prompt_eval_ms', 0)} ms · wrote "
                                 f"{st.get('gen_tokens', 0)} tokens {st.get('gen_ms', 0)} ms")


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
        prev = previous_question(tab, user_input)
        follow_up = is_follow_up(user_input) and bool(prev)
        # What the message is about, in their own words. One that names nothing
        # ("do you have pictures to demonstrate?") is about the last question.
        # Owner: "it doesn't remember the context of the last message at all" —
        # "what's the story of it?" was looked up on its own ("story"), found
        # nothing, and the speaker was told the library had nothing. A short
        # message that points back now carries the last question with it.
        about = (f"{prev} {user_input}" if prev and (not subject_words(user_input) or follow_up
                                                     or leans_on_last(user_input))
                 else user_input)
        search_q = (f"{prev} {user_input}" if follow_up else about)
        # Two models: the speaker writes the librarian a clear request first —
        # search words and the full question ("their missions" → which missions).
        # Not in an emergency: there the message is searched as written, and the
        # speaker reads the field-manual passages itself, word for word.
        use_librarian = self.librarian.enabled() and routing_plan.intent != Intent.EMERGENCY
        if trace and getattr(self.config, "two_models", False) and getattr(self.llm, "thrashing", False):
            trace.librarian_text = "(off for this run — the graphics card can't hold both models)"
        question = about
        # Low power: no separate request step — the librarian works from the
        # message as written (one model call fewer per question)
        low_power = getattr(self.config, "low_power_active", False)
        # The speaker's request (SEARCH words) only when the message leans on the
        # last one ("their missions", "pictures of that?"). For a message that
        # names its subject it did harm: "hemlock" → "hemlock tree forest",
        # "log shelter" → "materials construction safety" (straw-bale pages) —
        # and cost ~0.5 s every time.
        needs_brief = about != user_input
        if use_librarian and not low_power and needs_brief:
            if progress:
                progress("Checking the library")
            brief = self.librarian.brief(user_input, previous_question(tab, user_input),
                                         last_reply(tab))
            search_q = f"{brief.search} {search_q}"
            # The brief's QUESTION is NOT passed on: the speaker rewrote "How do
            # I make soap from fat?" as "…from coconut oil" and "what movies can
            # you tell me about" as "the latest releases". The librarian gets
            # their own words (with the last question when they name nothing).
            if trace:
                trace.brief_ms = brief.ms
                trace.brief_text = short(f"SEARCH {brief.search} | QUESTION {brief.question}", 300)
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

        # Step 7c: only passages that are on the subject go any further — to the
        # librarian, under the answer as "From:", as pictures. ("who is
        # confuscious" was being answered from the film "Your Name".)
        used = list(getattr(self.knowledge, "_last_used_chunks", None)
                    or raw_chunks[:max(1, getattr(self.knowledge, "prompt_passages", 3))])
        candidates = [("book", i, self.knowledge.scorer._source_label(r.get("source", ""), r.get("domain", "")),
                       r.get("content", "")) for i, r in enumerate(used)]
        if wiki_sources:
            candidates += [("wiki", None, label, text) for label, text in self._wiki_passages(search_q, 200)]
        on_subject = [c for c in candidates if relevant(about, f"{c[2]} {c[3]}")]
        # Step 7c+: no book on the subject, or a section you made yourself (the
        # Entertainment one has no books — it "never worked") → search inside
        # Wikipedia's articles, not just their titles
        if not routing_plan.is_strict and tab.id != "medical" and (
                getattr(tab, "custom", False) or not any(c[0] == "book" for c in on_subject)):
            have = {c[2] for c in candidates}
            extra = [("wiki", None, label, text) for label, text in self._wiki_search_passages(about)
                     if label not in have]
            extra = [c for c in extra if relevant(about, f"{c[2]} {c[3]}")]
            if extra:
                candidates += extra
                on_subject += extra
                if not use_librarian:
                    knowledge_context = (knowledge_context + "\n\n" if knowledge_context else "") + \
                        loose_block([(c[2], c[3]) for c in extra], user_input)
        shown = [c[1] for c in on_subject if c[0] == "book"]
        wiki_shown = [c[2] for c in on_subject if c[0] == "wiki"]

        # Step 7d: the librarian reads them and keeps only the facts that answer
        # the question; the speaker gets those instead of the passages
        if use_librarian and candidates and not subject_words(about):
            # Nothing to judge passages by ("list 50 movies", "tell me something
            # interesting") — passages would be whatever matched, OCR noise
            # included. No library for this one; the speaker just answers.
            knowledge_context = ""
            on_subject = []
            if trace:
                trace.librarian_text = "(not asked — the message names no subject)"
        elif use_librarian and candidates:
            if not on_subject:
                # Nothing on the subject: don't ask it at all (saves ~0.5 s)
                knowledge_context = facts_block(Facts("", False))
                if trace:
                    trace.librarian_text = "(not asked — nothing found was on the subject)"
            else:
                facts = self.librarian.extract(question, [(c[2], c[3]) for c in on_subject])
                if trace:
                    _trace_librarian(trace, facts)
                if facts.found:
                    knowledge_context = facts_block(facts)
                    cited = [on_subject[n - 1] for n in sorted(facts.cited()) if 0 < n <= len(on_subject)]
                    if cited:
                        shown = [c[1] for c in cited if c[0] == "book"]
                        wiki_shown = [c[2] for c in cited if c[0] == "wiki"]
                elif not facts.failed:
                    # "NOT FOUND" from a 1.2B model is often wrong — the passages
                    # are on the subject, so the speaker reads them itself
                    knowledge_context = loose_block([(c[2], c[3]) for c in on_subject], user_input)

        # Step 7e: pictures. Asked for one → the figure pages whose caption or
        # labels name the thing (find_pictures), not the page a text passage
        # happened to come from. Otherwise only pictures on the passages used.
        # Either way the speaker is told what's shown — it said "I don't have
        # pictures" with one right under its reply.
        images = list(dict.fromkeys(used[i]["image_path"] for i in shown if used[i].get("image_path")))
        picture_lines = [self._source_line(used[i]) for i in shown if used[i].get("image_path")]
        asked = wants_picture(user_input)
        if asked:
            images, picture_lines = self._pictures_for(about, images, picture_lines)
        else:
            # Owner: instructions and plants should come with their pictures
            # without asking — a figure whose caption names the subject
            # ("Fig. 9-5 Water hemlock", "Figure 7. Bow drill") goes with the answer
            from core.library.figures import find_pictures
            label = self.knowledge.scorer._source_label
            for f in find_pictures(about, limit=1):
                if f["in_caption"] >= min(f["wanted"], 2) and f["image"] not in images:
                    images.append(f["image"])
                    picture_lines.append(f"{label(f['source'], f['domain'])}, p. {f['page']}"
                                         + (f" — {f['shows']}" if f["shows"] else ""))
        note = picture_note(picture_lines, asked)
        if note:
            knowledge_context = (knowledge_context + "\n\n" if knowledge_context else "") + note

        # Step 7f: say what they're following on from, so the speaker keeps the
        # thread (owner: "memory is a huge issue … not remembering context")
        if about != user_input and prev:
            knowledge_context = (f'They\'re following on from their last question: "{prev}". '
                                 "Keep to that subject.\n\n" + (knowledge_context or "")).strip()

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

        sources = list(dict.fromkeys([self._source_line(used[i]) for i in shown] + wiki_shown +
                                     [l.split(" — ")[0] for l in picture_lines]))

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

    def _pictures_for(self, about: str, images: List[str], lines: List[str]):
        """
        A picture was asked for: the figure pages that show it, best first,
        then (if none of those) the pictures on the passages used.
        Returns (image paths, "Book, p. 12 — Fig. 3 Water hemlock" lines).
        """
        from core.library.figures import find_pictures
        found = find_pictures(about)
        if not found:
            return images, lines
        label = self.knowledge.scorer._source_label
        return ([f["image"] for f in found],
                [f"{label(f['source'], f['domain'])}, p. {f['page']}" +
                 (f" — {f['shows']}" if f["shows"] else "") for f in found])

    def _name_origin(self, user_input: str) -> str:
        """
        If they're asking about the assistant or its name, what that name comes
        from (owner: "it would stand to reason it knows the name it was given,
        and if it's based on someone from history or media, tell me about them").

        Step 1: is the message about it? — "who are you", "your name", "named
                after", "based on", or the name itself, even misspelt
        Step 2: the Wikipedia article closest to the name ("confuscious" →
                Confucius); nothing close → only the name itself
        """
        import difflib
        name = self.assistant_name()
        q = user_input.lower()
        words = re.findall(r"[a-z']+", q)
        says_name = bool(difflib.get_close_matches(name.lower(), words, n=1, cutoff=0.8))
        if not (says_name or re.search(r"\b(who|what) are you\b|\byour name\b|\bnamed after\b|"
                                       r"\bbased on\b|\bcalled that\b|\byourself\b", q)):
            return ""
        from core.library.wiki_lookup import closest_article, lead
        found = closest_article(name)
        if not found:
            return f"About you: your name is {name}."
        title, path = found
        return (f"About you: your name is {name}, after {title}. If they ask who you're named "
                f"after or who {title} is or was, tell them from this (your library's article "
                f"on {title}), in your own words:\n{lead(path, 120)}")

    def _source_line(self, chunk: Dict) -> str:
        """"Book title, p. 12" for one passage (as under every answer)."""
        label = self.knowledge.scorer._source_label(chunk.get("source", ""), chunk.get("domain", ""))
        return label + (f", p. {chunk['page_num']}" if chunk.get("page_num") else "")

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
        # Step 3c: about the assistant itself — "who is confuscious", "who are
        # you named after": what its name comes from, instead of a Wikipedia
        # search on the message (that found the film "Your Name")
        origin = self._name_origin(user_input)
        if origin:
            parts.append(origin)
        subject = self._subject_text(tab, user_input) if not own else user_input
        carried = subject != user_input
        wiki_notes, sources = ("", []) if origin else self._wikipedia_background(subject)
        sources = [f"Obsidian — {t}" for t, _ in own] + sources
        if wiki_notes and use_librarian:
            passages += self._wiki_passages(subject, 250)
        elif wiki_notes:
            parts.append(("Earlier in this chat they asked about this — use it only if they "
                          "still are.\n" if carried else "") + wiki_notes)
        elif not own and not passages and not origin:
            missing = self._not_in_library_note(subject)
            if missing and carried:
                missing = "If they're still on the same subject — " + missing
            if missing:
                parts.append(missing)

        # Step 4b: the librarian reads what was found and keeps only the facts
        # that answer them; the speaker may say nothing else about it
        question = (f"{user_input} (about: {subject})" if carried else user_input)
        if passages:
            # Only passages on the subject — in their own words if they named
            # one ("who is confuscious" got the film "Your Name" read to it)
            about = question if (carried or not subject_words(user_input)) else user_input
            dropped = [p[0] for p in passages if not relevant(about, f"{p[0]} {p[1]}")]
            passages = [p for p in passages if p[0] not in dropped]
            sources = [x for x in sources if x not in dropped]
            if not passages:
                if trace:
                    trace.librarian_text = "(not asked — nothing found was on the subject)"
                missing = self._not_in_library_note(user_input)
                if missing:
                    parts.append(missing)
        if passages:
            if progress:
                progress("Checking the library")
            facts = self.librarian.extract(question, passages)
            if trace:
                _trace_librarian(trace, facts)
            lead_in = "If they're still on the same subject — " if carried else ""
            if facts.failed:            # librarian unreachable: the speaker reads them itself
                parts.append("Background from the library — use only this for facts about it:\n" +
                             "\n\n".join(f"{label}: {' '.join(text.split()[:110])}"
                                           for label, text in passages))
            elif not facts.found:
                # Step 4c: the librarian said NOT FOUND, but the article is on the
                # subject (it did that with the Magic: The Gathering article)
                parts.append(lead_in + loose_block(passages, user_input, 90))
            else:
                parts.append(lead_in + facts_block(facts, "it"))

        # Step 4d: a picture asked for here too ("show me a picture of a bow
        # drill") — the figure page that shows it, from any book
        images = []
        if wants_picture(user_input):
            images, lines = self._pictures_for(
                user_input if subject_words(user_input) else question, [], [])
            parts.append(picture_note(lines, True))
            sources = sources + [l.split(" — ")[0] for l in lines]

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
            images=images,
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
                    r"good night|hey|hi|hello)\b", q) or \
                re.search(r"\b(who|what) are you\b|\byour (name|quest|purpose|job)\b|\byourself\b", q):
            # …and so do questions about the assistant ("who are you")
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
    def _wiki_search_passages(text: str, n: int = 2, words: int = 200):
        """
        [("Wikipedia — Title", opening)] for the best full-text matches of the
        message's subject words ("tell me about magic the gathering" → Magic:
        The Gathering). "May refer to" pages are skipped.
        """
        from core.ai.librarian import subject_words
        from core.library.wiki_lookup import search, lead, _is_disambiguation
        q = " ".join(subject_words(text))
        if not q:
            return []
        out = []
        try:
            for r in search(q, limit=n + 3):
                path = r["path"]
                if hasattr(path, "open") and _is_disambiguation(path):
                    continue
                out.append((f"Wikipedia — {r['title']}", lead(path, words)))
                if len(out) >= n:
                    break
        except Exception:
            return []
        return out

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
