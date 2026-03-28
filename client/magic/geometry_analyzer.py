from __future__ import annotations

from typing import Any, Sequence

from client.magic.primitives import Arrow, Circle, RuneFire, Segment, Triangle
from client.magic.recognition.complex_composers import ComplexShapeComposer
from client.magic.recognition.pipeline import PrimitiveRecognitionEngine
from client.magic.recognition.types import (
    HeuristicDetector,
    Point,
    RecognitionConfig,
    ShapeDefinition,
)


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

    def register_shape(
        self,
        shape: ShapeDefinition,
        *,
        heuristic_detector: HeuristicDetector | None = None,
        dollar_templates: Sequence[Sequence[Point]] | None = None,
    ) -> None:
        self._engine.register_shape(
            shape,
            heuristic_detector=heuristic_detector,
            dollar_templates=dollar_templates,
        )

    def register_heuristic_rule(
        self,
        label: str,
        detector: HeuristicDetector,
        *,
        requires_closed: bool | None = None,
    ) -> None:
        self._engine.register_heuristic_rule(
            label=label,
            detector=detector,
            requires_closed=requires_closed,
        )

    def register_dollar_template(self, label: str, points: Sequence[Point]) -> None:
        self._engine.register_dollar_template(label, points)

    def register_complex_composer(self, label: str, composer: ComplexShapeComposer) -> None:
        self._engine.register_complex_composer(label, composer)


__all__ = [
    "GeometryAnalyzer",
    "Segment",
    "Circle",
    "Triangle",
    "Arrow",
    "RuneFire",
    "RecognitionConfig",
    "ShapeDefinition",
]
