"""
Bench — ask Prometheus a fixed set of real questions, with the real models,
and write down what happened. Run it after an update and send the report:
it shows in one go what used to take a dozen debug runs.

    python tools/bench.py             all questions (a few minutes)
    python tools/bench.py --quick     the 8 most telling ones
    python tools/bench.py --think     with "Think it through" on, to compare

Step 1: start the models the way the app does (its own Ollama if the models
        are in app\\models), and pick full or low power the same way
Step 2: load the library (meaning search + word search)
Step 3: each question goes through exactly what the window does — the same
        pipeline, the same chat history, the same prompt — in a fresh chat
        (your own chats and memory are never changed)
Step 4: check each reply: does it mention what it should, does it avoid what
        it shouldn't (copied instructions, file names, links), did a
        picture come with it, how long until it started speaking
Step 5: logs/bench_<date>_<time>.md — every question, every reply, the
        librarian's facts, the sources, the pictures and the timings

The questions come from the owner's own debug logs (the lye from wood ash,
the log shelter, Halo, "who is confuscious" …) plus follow-ups and memory.
"""

import copy
import json
import os
import re
import sys
import time
from pathlib import Path

# Run from anywhere: work in the app folder (one up from tools/)
ROOT_DIR = Path(__file__).resolve().parent.parent
os.chdir(ROOT_DIR)
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Phrases a reply should never contain: copied instructions, file names, links
NEVER = ["source status", "library facts", "from the library (answer", "behavioural",
         "retrieved knowledge", "http://", "https://", "example.com", "[1]", "[2]",
         "fm_3-05", "_survival_", ".pdf", "source:", "what the library says",
         "clarification needed", "the steps as the books give them"]

# name, section, quick?, turns: (question, any-of words expected, words to avoid, wants a picture)
CASES = [
    ("Purify water", "survival", True, [
        ("how do I purify water", ["boil", "filter", "chlorine", "bleach", "iodine", "minute"], [], False)]),
    ("Lye from wood ash", "chemistry", True, [
        ("How do I make lye from wood ash?", ["ash", "water", "leach", "drip"], ["sodium chloride"], False)]),
    ("Soap from fat", "chemistry", False, [
        ("How do I make soap from fat?", ["lye"], ["coconut", "lemon juice"], False)]),
    ("Not breathing", "medical", True, [
        ("he's not breathing what do i do", ["breath", "airway", "chest", "compress", "chin"], [], False)]),
    ("Deep cut", "medical", False, [
        ("how do I clean a deep cut", ["clean", "water", "bleed", "pressure", "wound"], [], False)]),
    ("Water hemlock picture", "survival", True, [
        ("can you show me a picture of water hemlock", ["hemlock", "picture"], ["can't show", "cannot show"], True)]),
    ("Bow drill", "survival", False, [
        ("how do I make a bow drill", ["spindle", "bow", "board", "socket", "drill"], [], True)]),
    ("Log shelter", "build", True, [
        ("How do I build a simple log shelter?", ["log", "roof", "wall", "notch"], ["straw bale", "source a"], False)]),
    ("Fast crops", "farming", False, [
        ("What can I plant now that grows fastest?", ["radish", "lettuce", "bean", "spinach", "seed", "grow"], [], False)]),
    ("North without a compass", "navigation", False, [
        ("how do I find north without a compass", ["shadow", "stick", "polaris", "north star", "stars"], [], False)]),
    ("Halo, then a follow-up", "entertainment", True, [
        ("tell me about halo the game", ["halo", "game", "chief", "bungie"], [], False),
        ("what's the story of it?", ["chief", "covenant", "halo", "ring"], ["what are you referring"], False)]),
    ("Magic: The Gathering", "entertainment", False, [
        ("tell me about magic the gathering", ["card", "game"], [], False),
        ("who made it?", ["garfield", "wizards"], [], False)]),
    ("Who are you", "prometheus", True, [
        ("who are you", ["{name}"], ["don't have a name", "do not have a name"], False)]),
    ("Its name's origin", "prometheus", False, [
        ("who are you named after?", ["{origin}"], ["don't have a name"], False)]),
    ("Remembers what you said", "prometheus", True, [
        ("my dog is called Biscuit and he hates thunder", [], [], False),
        ("what's my dog called?", ["biscuit"], [], False)]),
    ("Tell me something", "prometheus", False, [
        ("tell me something interesting", [], ["something interesting to you", "favorite kind of thing",
                                               "favourite kind of thing"], False)]),
    ("Go on", "chemistry", False, [
        ("give me every step to make soap from wood ash and fat, in detail", ["ash", "lye", "fat"], [], False),
        ("go on", [], ["continue from where it left off"], False)]),
]


def say(msg=""):
    print(msg, flush=True)


# ── Step 1 ──────────────────────────────────────────────────────────────────

def start_models(config):
    from core.ai import ollama_local
    from core.ai.llm import LLMEngine
    from core.app import hardware
    say("Starting the models…")
    ollama_local.start(wait=20)
    llm = LLMEngine(config)
    if not llm.is_available():
        say(f"[X] Ollama isn't answering: {getattr(llm, 'last_error', '')}")
        return None
    missing = llm.missing_models()
    if missing:
        say(f"[X] Not installed: {', '.join(missing)} — run setup, or python -m core.ai.ollama_local --pull NAME")
        return None
    llm.warm_up()
    if config.two_models and config.librarian_model != config.speaker_model:
        llm.warm_up(model=config.librarian_model)      # both loaded, as the app does
    if config.power_mode == "auto":
        hw = hardware.detect()
        choice, why = hardware.recommend(hw, hardware.ollama_on_gpu(llm.base_url))
        config.low_power_active, config.power_reason = choice == "low", why
        config.hardware_summary = hw.summary()
    else:
        config.low_power_active = config.power_mode == "low"
    say(f"  Ollama: {llm.base_url} · speaker {config.speaker_model} · librarian "
        f"{config.librarian_model if config.two_models else '(off)'} · "
        f"{'low power' if config.low_power_active else 'full power'}")
    return llm


# ── Step 2 ──────────────────────────────────────────────────────────────────

def load_library():
    from core.library.rag import KnowledgeBase
    say("Loading the library…")
    kb = KnowledgeBase()
    kb.initialize_vector_db(status_callback=lambda m: say("  " + m))
    kb.ensure_index(status_callback=lambda m: say("  " + m))
    return kb


# ── Step 3 ──────────────────────────────────────────────────────────────────

def fresh_tab(tab_id: str):
    """A copy of a section with an empty chat — nothing of yours is touched."""
    from core.you.tabs import DEFAULT_TABS, Tab
    if tab_id == "entertainment":
        return Tab(id="custom_entertainment_bench", name="Entertainment", icon="", domains=["general"],
                   system_prompt="You are Prometheus, focused on: films, games, books and music.",
                   custom=True)
    for t in DEFAULT_TABS:
        if t.id == tab_id:
            tab = copy.deepcopy(t)
            tab.history, tab.summary, tab.chats = [], "", []
            return tab
    raise ValueError(tab_id)


def ask(pipeline, context_mgr, llm, tab, question: str) -> dict:
    """One message, exactly as the window sends it. Returns what happened."""
    from core.answers.pipeline import with_turn_context
    from core.answers.tracer import QueryTrace
    tab.add_message("user", question)
    trace = QueryTrace(query_preview=question[:80], tab_id=tab.id, timestamp=time.time())
    started = time.time()
    plan = pipeline.route(question, tab.id, trace)
    prepared = pipeline.prepare_knowledge(tab, question, plan, trace)
    prep_ms = int((time.time() - started) * 1000)
    if prepared.clarify_text:
        reply, first_ms = prepared.clarify_text, prep_ms
    else:
        reserve = len(prepared.system_prompt or "") + len(prepared.turn_context or "")
        messages = with_turn_context(context_mgr.messages_for(tab, reserve), prepared.turn_context)
        out, first = [], []

        def token(t):
            if not first:
                first.append(time.time())
            out.append(t)
        errors = []
        llm.last_stats = {}
        llm.__dict__.pop("_bench_final", None)
        llm.stream(messages, prepared.system_prompt, token,
                   lambda full: llm.__dict__.__setitem__("_bench_final", full), errors.append,
                   tab_id=tab.id, intent=prepared.intent)
        reply = "".join(out) if out else ("(error: " + "; ".join(errors) + ")")
        if out:
            # what the stream finally kept (a repeated step at the end is cut)
            reply = llm.__dict__.get("_bench_final", reply)
        first_ms = int(((first[0] if first else time.time()) - started) * 1000)
    total_ms = int((time.time() - started) * 1000)
    tab.add_message("assistant", reply)
    return {"question": question, "reply": reply, "prep_ms": prep_ms, "first_ms": first_ms,
            "total_ms": total_ms, "mode": getattr(prepared.mode, "value", str(prepared.mode)),
            "intent": prepared.intent, "librarian": trace.librarian_text, "search_ms": getattr(trace, "search_ms", 0),
            "librarian_stats": getattr(trace, "librarian_stats", ""),
            "sources": list(prepared.sources or []),
            "pictures": [Path(p).name for p in (prepared.images or [])],
            "speaker_stats": dict(getattr(llm, "last_stats", {}) or {}),
            "training": bool(getattr(plan, "use_training_path", False))}


# ── Step 4 ──────────────────────────────────────────────────────────────────

def check(result: dict, expect, avoid, wants_picture, name: str, origin: str) -> list:
    """What went wrong with one reply ([] = fine)."""
    text = result["reply"].lower()
    problems = []
    words = [w.replace("{name}", name.lower()).replace("{origin}", (origin or name).lower()) for w in expect]
    if words and not any(w in text for w in words):
        problems.append("mentions none of: " + ", ".join(words))
    for bad in list(avoid) + NEVER:
        if bad.lower() in text:
            problems.append(f'contains "{bad}"')
    if wants_picture and not result["pictures"]:
        problems.append("no picture (fine if your library has none of this — "
                        "or run python tools/ingest.py --figures)")
    if result["reply"].startswith("(error"):
        problems.append("the model didn't answer")
    seen = set()
    for line in result["reply"].lower().splitlines():
        key = " ".join(re.sub(r"^[\W\d]*", "", line).split())
        if len(key) >= 30 and key in seen:
            problems.append("repeats itself")
            break
        seen.add(key)
    return problems


# ── Step 5 ──────────────────────────────────────────────────────────────────

def report(rows, config, started, think: bool) -> Path:
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(started))
    path = Path("logs") / f"bench_{stamp}.md"
    path.parent.mkdir(exist_ok=True)
    passed = sum(1 for r in rows if not r["problems"])
    firsts = sorted(r["first_ms"] for r in rows)
    median = firsts[len(firsts) // 2] if firsts else 0
    lines = [f"# Prometheus bench — {stamp}", "",
             f"- Speaker: {config.speaker_model} · librarian: "
             f"{config.librarian_model if config.two_models else 'off'} · "
             f"{'low' if getattr(config, 'low_power_active', False) else 'full'} power"
             + (" · think it through: on" if think else ""),
             f"- This computer: {getattr(config, 'hardware_summary', '') or 'not checked'}",
             f"- **{passed} of {len(rows)} replies passed** · started speaking after "
             f"{median} ms (median), slowest {max(firsts) if firsts else 0} ms", "",
             "| | Section | Question | Speaks after | Problems |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {'✓' if not r['problems'] else '✗'} | {r['tab']} | {r['question']} | "
                     f"{r['first_ms']} ms | {'; '.join(r['problems']) or '—'} |")
    lines.append("")
    for r in rows:
        lines += [f"## {'✓' if not r['problems'] else '✗'} {r['case']} — “{r['question']}”", "",
                  f"*{r['tab']} · {r['intent']} · {r['mode']} · prep {r['prep_ms']} ms (library search {r.get('search_ms', 0)} ms) · "
                  f"speaks after {r['first_ms']} ms · done {r['total_ms']} ms*"
                  + (" · *(this question goes to the Training Path in the app)*" if r["training"] else ""), ""]
        if r["problems"]:
            lines += ["**Problems:** " + "; ".join(r["problems"]), ""]
        lines += ["**Reply:**", "", "> " + r["reply"].replace("\n", "\n> "), ""]
        st = r.get("speaker_stats") or {}
        if st:
            lines += [f"*Speaker: load {st.get('load_ms', 0)} ms · read {st.get('prompt_tokens', 0)} tokens "
                      f"{st.get('prompt_eval_ms', 0)} ms · wrote {st.get('gen_tokens', 0)} tokens "
                      f"{st.get('gen_ms', 0)} ms*", ""]
        if r["librarian"]:
            lines += [f"**Librarian:** {r['librarian']}" +
                      (f" ({r['librarian_stats']})" if r["librarian_stats"] else ""), ""]
        if r["sources"]:
            lines += ["**From:** " + "; ".join(r["sources"]), ""]
        if r["pictures"]:
            lines += ["**Pictures:** " + ", ".join(r["pictures"]), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv) -> int:
    from core.app.config import Config
    from core.ai.context_manager import ContextManager
    from core.answers.pipeline import QueryPipeline
    from core.you.memory import Memory
    from core.library.wiki_lookup import closest_article

    quick, think = "--quick" in argv, "--think" in argv
    started = time.time()
    config = Config.load()
    config.think_hard = think
    llm = start_models(config)
    if llm is None:
        return 1
    kb = load_library()
    pipeline = QueryPipeline(Memory(), kb, llm)
    context_mgr = ContextManager(llm)
    name = pipeline.assistant_name()
    origin_hit = closest_article(name)
    origin = origin_hit[0] if origin_hit else ""

    cases = [c for c in CASES if c[2] or not quick]
    say(f"\nAsking {sum(len(c[3]) for c in cases)} questions…")
    rows = []
    for case, tab_id, _, turns in cases:
        tab = fresh_tab(tab_id)
        for question, expect, avoid, picture in turns:
            try:
                result = ask(pipeline, context_mgr, llm, tab, question)
            except Exception as e:                      # keep going; note it
                result = {"question": question, "reply": f"(error: {e})", "prep_ms": 0, "first_ms": 0,
                          "total_ms": 0, "mode": "", "intent": "", "librarian": "", "librarian_stats": "",
                          "sources": [], "pictures": [], "training": False}
            result.update(case=case, tab=tab_id,
                          problems=check(result, expect, avoid, picture, name, origin))
            rows.append(result)
            say(f"  {'✓' if not result['problems'] else '✗'} {tab_id:<13} {result['first_ms']:>6} ms  "
                f"{question[:60]}" + (f"   — {result['problems'][0]}" if result["problems"] else ""))
    from core.ai import ollama_local
    ollama_local.stop()
    path = report(rows, config, started, think)
    passed = sum(1 for r in rows if not r["problems"])
    say(f"\n{passed} of {len(rows)} passed. Report: {path.resolve()}")
    say("Send that file — it has every reply in full.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
