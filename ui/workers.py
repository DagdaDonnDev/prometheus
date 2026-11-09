"""
Background worker threads.
Keeps UI responsive during LLM generation and initialization.
"""

from PySide6.QtCore import QThread, Signal

from core.llm import LLMEngine
from core.rag import KnowledgeBase
from core.stt import STTEngine
from core.config import Config
from core.pipeline import QueryPipeline


class LLMWorker(QThread):
    """Runs LLM generation in background thread, emits tokens as they arrive."""
    token_received = Signal(str)
    response_done  = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, llm: LLMEngine, messages: list,
                 system_prompt: str, tab_id: str = "", intent: str = ""):
        super().__init__()
        self.llm           = llm
        self.messages      = messages
        self.system_prompt = system_prompt
        self.tab_id        = tab_id
        self.intent        = intent

    def run(self):
        self.llm.stream(
            messages=self.messages,
            system_prompt=self.system_prompt,
            on_token=self.token_received.emit,
            on_done=self.response_done.emit,
            on_error=self.error_occurred.emit,
            tab_id=self.tab_id,
            intent=self.intent,
        )


class PrepareWorker(QThread):
    """
    Everything before the speaker talks (core/pipeline.prepare_knowledge),
    off the UI thread: with two models it asks the speaker for a library
    request and the librarian for the facts — each a short model call.
    """
    prepared = Signal(object)      # PreparedAnswer
    progress = Signal(str)
    failed   = Signal(str)

    def __init__(self, pipeline, tab, user_input, routing_plan, trace):
        super().__init__()
        self.args = (pipeline, tab, user_input, routing_plan, trace)

    def run(self):
        pipeline, tab, user_input, routing_plan, trace = self.args
        try:
            result = pipeline.prepare_knowledge(tab, user_input, routing_plan, trace,
                                                progress=self.progress.emit)
        except Exception as e:
            self.failed.emit(str(e))
            return
        self.prepared.emit(result)


class TrainingWorker(QThread):
    """
    Runs the Training Path (first-principles derivation) off the UI thread.
    The derivation call can take up to 90 seconds on slow hardware —
    doing it on the Qt main thread froze the app (the v22 fix).

    Signals:
      derivation_done(dict)     DERIVED or NEEDS_DATA — show it
      fallback_requested(dict)  use the Knowledge Path instead (result has the reason)
      derivation_error(str)     engine or Ollama failed — also falls back
      progress(str)             "Researching <topic>" as each step starts
    """
    progress           = Signal(str)
    derivation_done    = Signal(dict)
    fallback_requested = Signal(dict)
    derivation_error   = Signal(str)

    def __init__(self, engine, query: str, tab_id: str):
        super().__init__()
        self.engine = engine
        self.query  = query
        self.tab_id = tab_id

    def run(self):
        try:
            result = self.engine.run(self.query, self.tab_id, progress=self.progress.emit)
        except Exception as e:
            self.derivation_error.emit(str(e))
            return

        if QueryPipeline.training_should_show(result):
            self.derivation_done.emit(result)
        else:
            self.fallback_requested.emit(result)


class OllamaCheckWorker(QThread):
    """
    Checks Ollama off the UI thread (each try can wait several seconds).
    Emits a dict: {"reachable": bool, "error": str, "missing": [model, …]}
    """
    checked = Signal(dict)

    def __init__(self, llm: LLMEngine):
        super().__init__()
        self.llm = llm

    def run(self):
        # Step 1: if the model lives in prometheus/models, start our own Ollama
        # for it (port 11435) and give it a few seconds to come up
        from core import ollama_local
        ollama_local.start(wait=8)
        # Step 2: find whichever Ollama answers
        reachable = self.llm.is_available()
        self.checked.emit({
            "reachable": reachable,
            "error": getattr(self.llm, "last_error", ""),
            "missing": self.llm.missing_models() if reachable else [],
        })


class InitWorker(QThread):
    """Initializes heavy components (RAG, STT) in background."""
    status_update = Signal(str)
    finished = Signal()

    def __init__(self, knowledge: KnowledgeBase, stt: STTEngine, config: Config):
        super().__init__()
        self.knowledge = knowledge
        self.stt = stt
        self.config = config

    def run(self):
        # List Wikipedia's article titles now, in the background, so the first
        # chat message doesn't pay for it (can take seconds with ~200k files)
        try:
            from core import wiki_lookup
            n = wiki_lookup.article_count()
            if n:
                self.status_update.emit(f"Wikipedia: {n:,} articles ready")
        except Exception:
            pass

        # Initialize knowledge base
        self.knowledge.initialize_vector_db(
            status_callback=self.status_update.emit
        )

        # Initialize STT if enabled
        if self.config.stt_enabled:
            self.stt.initialize(
                status_callback=self.status_update.emit
            )

        self.finished.emit()
