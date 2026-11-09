"""
Query Trace
===========
Captures full observability data for every query across all decision layers.

Intent → Retrieval → Source Sufficiency → Decision Gate → Bounds → Generation

Exposed via:
  - Dev panel toggle in UI
  - Log file (memory/query_traces.jsonl)
  - In-memory ring buffer (last 100 traces)
"""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from pathlib import Path
from collections import deque


TRACE_LOG_PATH = Path("memory/query_traces.jsonl")
RING_BUFFER_SIZE = 100


@dataclass
class RetrievalTrace:
    tier1_chunks:   int = 0
    tier2_chunks:   int = 0
    tier3_chunks:   int = 0
    personal_chunks: int = 0
    total_chunks:   int = 0
    top_score:      float = 0.0
    avg_score:      float = 0.0
    min_score:      float = 0.0
    sources:        List[str] = field(default_factory=list)
    has_sources:    bool = False
    conflict:       bool = False


@dataclass
class SourceSufficiencyTrace:
    verdict:        str = "NONE"    # SUFFICIENT / WEAK / CONFLICTING / NONE
    chunk_count:    int = 0
    avg_confidence: float = 0.0
    source_diversity: int = 0
    agreement:      bool = True
    reason:         str = ""


@dataclass
class QueryTrace:
    # Identity
    trace_id:       str = ""
    timestamp:      float = 0.0
    tab_id:         str = ""
    query_preview:  str = ""        # first 80 chars only

    # Layer 1: Intent
    intent:         str = ""
    is_strict:      bool = False
    allow_discussion: bool = False

    # Layer 2: Retrieval
    retrieval:      RetrievalTrace = field(default_factory=RetrievalTrace)

    # Layer 3: Source sufficiency
    sufficiency:    SourceSufficiencyTrace = field(
                        default_factory=SourceSufficiencyTrace)

    # Layer 4: Decision gate
    gate_mode:      str = ""
    worst_case:     bool = False
    clarify_triggered: bool = False
    risk_domains:   List[str] = field(default_factory=list)

    # Layer 5: Generation
    prompt_chars:   int = 0
    response_chars: int = 0
    response_ms:    int = 0         # full completion time in ms (secondary)
    first_token_ms: int = 0         # speak-start: first token / TTS start (headline)
    # Where the wait comes from (v23)
    prep_ms:        int = 0         # retrieval + gates + prompt building, before the model call
    brief_ms:       int = 0         # speaker writing the librarian's request
    librarian_ms:   int = 0         # librarian pulling facts from the passages
    load_ms:        int = 0         # Ollama loading the model into memory (0 when already loaded)
    prompt_tokens:  int = 0         # tokens the model had to read before writing
    prompt_eval_ms: int = 0         # time spent reading them
    gen_tokens:     int = 0
    gen_ms:         int = 0
    # What each model said (shortened), so a saved log shows the whole exchange
    brief_text:     str = ""        # speaker → librarian: "SEARCH … | QUESTION …"
    librarian_text: str = ""        # librarian's facts, or NOT FOUND
    response_text:  str = ""        # the reply the person got
    images:         List[str] = field(default_factory=list)   # pictures shown with it

    def breakdown(self) -> str:
        """One line: where the time to the first word went."""
        lib = ""
        if self.brief_ms or self.librarian_ms:
            lib = f"(request {self.brief_ms} ms, librarian {self.librarian_ms} ms) "
        if not (self.prompt_tokens or self.load_ms):
            return f"prep {self.prep_ms} ms {lib}".strip()
        return (f"prep {self.prep_ms} ms {lib}· model load {self.load_ms} ms · "
                f"reading prompt {self.prompt_eval_ms} ms ({self.prompt_tokens} tokens) · "
                f"writing {self.gen_ms} ms ({self.gen_tokens} tokens)")
    llm_model:      str = ""

    # Query path (v22)
    path:            str = "knowledge"   # "knowledge" or "training"
    training_status: str = ""            # DERIVED / NEEDS_DATA / fallback reason
    training_concept: str = ""

    # Outcome signals
    safe_mode_triggered: bool = False
    redirect_suggested:  bool = False
    redirect_tab:        str = ""
    warnings_shown:      List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d

    def summary(self) -> str:
        """One-line summary for dev panel."""
        mode_emoji = {
            "emergency": "🚨",
            "safe_mode": "🛡",
            "clarify":   "❓",
            "cautious":  "⚠",
            "direct":    "✓",
        }.get(self.gate_mode, "?")

        suff_emoji = {
            "SUFFICIENT":  "✓",
            "WEAK":        "~",
            "CONFLICTING": "⚡",
            "NONE":        "✗",
        }.get(self.sufficiency.verdict, "?")

        return (
            f"{mode_emoji} {self.gate_mode.upper():<10} "
            f"| intent: {self.intent:<12} "
            f"| sources: {suff_emoji}{self.retrieval.total_chunks} "
            f"(top: {self.retrieval.top_score:.0f}%) "
            f"| 🔊 {self.first_token_ms}ms ✓ {self.response_ms}ms"
        )


# ── Tracer ─────────────────────────────────────────────────────────────────

class QueryTracer:
    """
    Singleton tracer. Records all query traces.
    Exposes ring buffer for dev panel.
    Appends to log file for post-analysis.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._buffer: deque = deque(maxlen=RING_BUFFER_SIZE)
        self._enabled = True
        self._current: Optional[QueryTrace] = None
        TRACE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    def start(self, query: str, tab_id: str) -> QueryTrace:
        """Start a new trace for a query."""
        import hashlib
        trace_id = hashlib.md5(
            f"{tab_id}{query}{time.time()}".encode()
        ).hexdigest()[:8]

        self._current = QueryTrace(
            trace_id     = trace_id,
            timestamp    = time.time(),
            tab_id       = tab_id,
            query_preview = query[:80],
        )
        return self._current

    def get_current(self) -> Optional[QueryTrace]:
        return self._current

    def record_first_token(self):
        """
        Mark speak-start: the moment the first token arrives.
        Tokens stream straight into Piper TTS, so this is when the
        user starts hearing the answer. Only the first call counts.
        """
        t = self._current
        if t and not t.first_token_ms:
            t.first_token_ms = max(1, int((time.time() - t.timestamp) * 1000))

    def discard(self):
        """Drop the current trace (generation was force-stopped)."""
        self._current = None

    def finish(self, response: str, model: str):
        """Finalise trace after generation."""
        if not self._current:
            return

        t = self._current
        t.response_chars = len(response)
        t.response_text = short(response, 600)
        t.llm_model = model
        t.response_ms = int((time.time() - t.timestamp) * 1000)
        if not t.first_token_ms:
            t.first_token_ms = t.response_ms   # whole reply arrived at once

        self._buffer.append(t)

        if self._enabled:
            self._write_log(t)

        self._current = None

    def _write_log(self, trace: QueryTrace):
        try:
            with open(TRACE_LOG_PATH, "a") as f:
                f.write(json.dumps(trace.to_dict()) + "\n")
        except Exception:
            pass

    def recent_traces(self, n: int = 20) -> List[QueryTrace]:
        return list(self._buffer)[-n:]

    def clear(self):
        self._buffer.clear()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    # ── Pattern detection ──────────────────────────────────────────────────

    def analyse_patterns(self) -> Dict[str, Any]:
        """
        Analyse recent traces for concerning patterns.
        Returns dict of pattern name → count/rate.
        """
        traces = list(self._buffer)
        if not traces:
            return {}

        total = len(traces)
        timed = [t for t in traces if t.first_token_ms]
        return {
            "total_queries":           total,
            "safe_mode_rate":          sum(1 for t in traces if t.safe_mode_triggered) / total,
            "clarify_rate":            sum(1 for t in traces if t.clarify_triggered) / total,
            "no_sources_rate":         sum(1 for t in traces if not t.retrieval.has_sources) / total,
            "weak_sources_rate":       sum(1 for t in traces if t.sufficiency.verdict == "WEAK") / total,
            "conflict_rate":           sum(1 for t in traces if t.retrieval.conflict) / total,
            "tier3_usage_rate":        sum(1 for t in traces if t.retrieval.tier3_chunks > 0) / total,
            "avg_first_token_ms":      (sum(t.first_token_ms for t in timed) / len(timed)) if timed else 0,
            "slow_speak_start_rate":   (sum(1 for t in timed if t.first_token_ms > 800) / len(timed)) if timed else 0,
            "avg_response_ms":         sum(t.response_ms for t in traces) / total,
            "training_path_rate":      sum(1 for t in traces if t.path == "training") / total,
            "avg_prompt_tokens":       (sum(t.prompt_tokens for t in traces if t.prompt_tokens) /
                                        max(1, sum(1 for t in traces if t.prompt_tokens))),
            "avg_load_ms":             (sum(t.load_ms for t in traces) / total),
            "avg_top_confidence":      sum(t.retrieval.top_score for t in traces) / total,
            "emergency_count":         sum(1 for t in traces if t.intent == "emergency"),
            "redirect_rate":           sum(1 for t in traces if t.redirect_suggested) / total,
        }


# ── Global tracer instance ─────────────────────────────────────────────────

tracer = QueryTracer()


# ── Summary for logs: python -m core.answers.tracer [N] ────────────────────────────

def short(text: str, limit: int) -> str:
    """One line, at most limit characters."""
    t = " ".join((text or "").split())
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + " …"


def print_recent(n: int = 10):
    """
    Print the last n replies from memory/query_traces.jsonl, one line each:
    tab, mode, speak-start, and where the wait came from. Used by
    debug_run.bat so a saved log shows why replies were fast or slow.
    """
    if not TRACE_LOG_PATH.exists():
        print("No replies recorded yet (memory/query_traces.jsonl not found).")
        return
    lines = TRACE_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    if not lines:
        print("No replies recorded yet.")
        return
    print(f"Last {len(lines)} replies (oldest first):")
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = QueryTrace(**{k: v for k, v in d.items()
                          if k in QueryTrace.__dataclass_fields__
                          and k not in ("retrieval", "sufficiency")})
        when = time.strftime("%H:%M:%S", time.localtime(t.timestamp))
        print(f"  {when}  {t.tab_id:<11} {t.path:<9} {t.gate_mode or '-':<9} "
              f"model={t.llm_model or '-'}  🔊 {t.first_token_ms} ms  ✓ {t.response_ms} ms")
        print(f"            {t.breakdown()}")
        if t.training_status:
            print(f"            training path: {t.training_status} ({t.training_concept or 'no concept'})")
        print(f"            \"{t.query_preview}\"")
        # Step: what each model said
        if t.brief_text:
            print(f"            speaker asked the librarian: {t.brief_text}")
        if t.librarian_text:
            print(f"            librarian found: {t.librarian_text}")
        if t.response_text:
            print(f"            reply: {t.response_text}")
        if t.images:
            print(f"            pictures: {', '.join(t.images)}")

    # Why the Training Path's last attempts didn't verify (one line per method)
    hist_path = Path("memory/training/history.json")
    if hist_path.exists():
        try:
            history = json.loads(hist_path.read_text(encoding="utf-8"))[-3:]
        except Exception:
            history = []
        if history:
            print()
            print("Last Training Path attempts (what the self-check objected to):")
            for h in history:
                when = time.strftime("%H:%M:%S", time.localtime(h.get("time", 0)))
                print(f"  {when}  {h.get('concept')}: {h.get('verified', 0)} of "
                      f"{h.get('methods', 0)} methods verified")
                for i, probs in enumerate(h.get("problems", []), 1):
                    print(f"            method {i}: {', '.join(probs) or 'ok'}")
                if h.get("raw"):
                    print("            model output (start): " + h["raw"][:300].replace("\n", " | "))


if __name__ == "__main__":
    import sys
    print_recent(int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10)
