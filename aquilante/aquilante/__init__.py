"""Aquilante — Adaptive Neural Learner Modeling Engine.

An adaptive system for modeling knowledge, retention and learning progression
from learning events. It answers one question: *what does this learner know
now, what are they starting to forget, and what should happen next?*

The package is organised as a pipeline —

    data (events, adapters) → features (sequences) → models (baselines, neural)
    → training → evaluation → inference (Learner, policy) → service

— and every layer works without the layers above it. Nothing here talks to
a language model; that is deliberate.
"""

from aquilante.data.schema import SCHEMA_VERSION, EventType, LearningEvent
from aquilante.inference.learner import Learner

__all__ = ["LearningEvent", "EventType", "SCHEMA_VERSION", "Learner"]
__version__ = "0.1.0"
