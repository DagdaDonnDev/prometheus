"""
Training Path (v22)
===================
First-principles derivation for the deductive tabs
(electronics, chemistry, build, navigation).

  TrainingGraph     3-tier confidence DAG, persistence, lemma promotion
  DerivationEngine  KB anchors, derivation, validation, gap classification
  TrainingSession   user verdicts and lemma eligibility
"""

from core.training.graph import TrainingGraph
from core.training.engine import DerivationEngine
from core.training.session import TrainingSession, VERDICT_LABELS

__all__ = ["TrainingGraph", "DerivationEngine", "TrainingSession", "VERDICT_LABELS"]
