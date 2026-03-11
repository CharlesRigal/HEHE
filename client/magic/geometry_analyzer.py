from __future__ import annotations

from typing import Any, Sequence

from client.magic.primitives import Circle, Segment, Triangle
from client.magic.recognition.pipeline import PrimitiveRecognitionEngine
from client.magic.recognition.types import RecognitionConfig


class GeometryAnalyzer:
    """
    Façade publique pour la reconnaissance de primitives.
    Garde l'API historique `analyze(strokes)` et délègue à une pipeline
    extensible basée sur heuristiques + $1 recognizer.
    """

    def __init__(self, config: RecognitionConfig | None = None):
        self._engine = PrimitiveRecognitionEngine(config=config)

    def analyze(self, strokes: Sequence[Sequence[Any]]) -> list[Any]:
        return self._engine.recognize_strokes(strokes)


__all__ = ["GeometryAnalyzer", "Segment", "Circle", "Triangle", "RecognitionConfig"]
