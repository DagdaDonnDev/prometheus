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


class TrainingWorker(QThread):
    """
    Runs the Training Path (first-principles derivation) off the UI thread.
    The derivation call can take up to 90 seconds on slow hardware —
    doing it on the Qt main thread froze the app (the v22 fix).

    Signals:
      derivation_done(dict)     DERIVED or NEEDS_DATA — show it
      fallback_requested(dict)  use the Knowledge Path instead (result has the reason)
      derivation_error(str)     engine or Ollama failed — also falls back
    """
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
            result = self.engine.run(self.query, self.tab_id)
        except Exception as e:
            self.derivation_error.emit(str(e))
            return

        if QueryPipeline.training_should_show(result):
            self.derivation_done.emit(result)
        else:
            self.fallback_requested.emit(result)


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
