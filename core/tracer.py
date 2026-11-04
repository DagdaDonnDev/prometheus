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
    response_ms:    int = 0         # generation time in ms
    llm_model:      str = ""

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
            f"| {self.response_ms}ms"
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

    def finish(self, response: str, model: str):
        """Finalise trace after generation."""
        if not self._current:
            return

        t = self._current
        t.response_chars = len(response)
        t.llm_model = model
        t.response_ms = int((time.time() - t.timestamp) * 1000)

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
        return {
            "total_queries":           total,
            "safe_mode_rate":          sum(1 for t in traces if t.safe_mode_triggered) / total,
            "clarify_rate":            sum(1 for t in traces if t.clarify_triggered) / total,
            "no_sources_rate":         sum(1 for t in traces if not t.retrieval.has_sources) / total,
            "weak_sources_rate":       sum(1 for t in traces if t.sufficiency.verdict == "WEAK") / total,
            "conflict_rate":           sum(1 for t in traces if t.retrieval.conflict) / total,
            "tier3_usage_rate":        sum(1 for t in traces if t.retrieval.tier3_chunks > 0) / total,
            "avg_response_ms":         sum(t.response_ms for t in traces) / total,
            "avg_top_confidence":      sum(t.retrieval.top_score for t in traces) / total,
            "emergency_count":         sum(1 for t in traces if t.intent == "emergency"),
            "redirect_rate":           sum(1 for t in traces if t.redirect_suggested) / total,
        }


# ── Global tracer instance ─────────────────────────────────────────────────

tracer = QueryTracer()
