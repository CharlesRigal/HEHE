from __future__ import annotations

from typing import Any, Sequence

from client.magic.primitives import Circle, Segment, Triangle
from client.magic.recognition.dollar_one import DollarOneRecognizer
from client.magic.recognition.heuristic import HeuristicPrimitiveRecognizer
from client.magic.recognition.preprocessing import centroid, euclidean_distance, normalize_stroke, simplify_to_vertices
from client.magic.recognition.types import NormalizedStroke, RecognitionConfig, RecognizerResult


class PrimitiveRecognitionEngine:
    """
    Orchestrateur de reconnaissance:
    - normalisation des strokes
    - reconnaissance géométrique heuristique
    - reconnaissance $1 (template matching)
    - fusion et décision finale
    """

    def __init__(
        self,
        config: RecognitionConfig | None = None,
        heuristic: HeuristicPrimitiveRecognizer | None = None,
        dollar_one: DollarOneRecognizer | None = None,
    ):
        self.config = config or RecognitionConfig()
        self.heuristic = heuristic or HeuristicPrimitiveRecognizer()
        self.dollar_one = dollar_one or DollarOneRecognizer()
        self._thresholds = {
            "segment": self.config.segment_threshold,
            "circle": self.config.circle_threshold,
            "triangle": self.config.triangle_threshold,
        }
        self._dollar_label_map = {
            "line": "segment",
            "segment": "segment",
            "circle": "circle",
            "triangle": "triangle",
        }

    def recognize_strokes(self, strokes: Sequence[Sequence[Any]]) -> list[Any]:
        primitives: list[Any] = []
        for stroke in strokes:
            primitive = self.recognize_stroke(stroke)
            if primitive is not None:
                primitives.append(primitive)
        return primitives

    def recognize_stroke(self, raw_stroke: Sequence[Any]) -> Any | None:
        stroke = normalize_stroke(
            raw_stroke,
            min_sample_distance=self.config.min_sample_distance,
            closed_ratio=self.config.closed_ratio,
        )
        if stroke is None:
            return None

        heuristic_candidates = self.heuristic.recognize(stroke)
        dollar_candidate = self.dollar_one.recognize(stroke.points)
        merged = self._merge_candidates(stroke, heuristic_candidates, dollar_candidate)
        if merged is None:
            return None

        return self._build_primitive(stroke, merged)

    def _merge_candidates(
        self,
        stroke: NormalizedStroke,
        heuristic_candidates: list[RecognizerResult],
        dollar_candidate: RecognizerResult | None,
    ) -> RecognizerResult | None:
        by_label: dict[str, dict[str, Any]] = {}

        for candidate in heuristic_candidates:
            slot = by_label.setdefault(candidate.label, {"score": 0.0, "payload": {}, "sources": []})
            slot["score"] += candidate.score * self.config.heuristic_weight
            if candidate.payload:
                slot["payload"] = candidate.payload
            slot["sources"].append("heuristic")

        if dollar_candidate is not None:
            mapped = self._dollar_label_map.get(dollar_candidate.label.lower())
            if mapped is not None:
                slot = by_label.setdefault(mapped, {"score": 0.0, "payload": {}, "sources": []})
                has_heuristic_for_label = "heuristic" in slot["sources"]
                if has_heuristic_for_label:
                    slot["score"] += dollar_candidate.score * self.config.dollar_weight
                else:
                    # Si l'heuristique n'a rien trouvé, on permet à $1
                    # de décider seul avec un poids fort.
                    slot["score"] += dollar_candidate.score * 0.90
                slot["sources"].append("$1")
                slot["payload"].setdefault("dollar", dollar_candidate.payload)

        if not by_label:
            return None

        for label, slot in by_label.items():
            sources = set(slot["sources"])
            if {"heuristic", "$1"}.issubset(sources):
                slot["score"] = min(1.0, slot["score"] + 0.08)

            if label in {"circle", "triangle"} and not stroke.is_closed:
                slot["score"] *= 0.65

        best_label, best_slot = max(by_label.items(), key=lambda item: item[1]["score"])
        threshold = self._thresholds.get(best_label, 0.65)
        best_score = best_slot["score"]

        if best_score < threshold:
            return None

        source = "+".join(sorted(set(best_slot["sources"]))) or "unknown"
        return RecognizerResult(
            label=best_label,
            score=best_score,
            source=source,
            payload=best_slot["payload"],
        )

    def _build_primitive(self, stroke: NormalizedStroke, winner: RecognizerResult) -> Any | None:
        label = winner.label
        payload = winner.payload or {}
        points = list(stroke.points)

        if label == "segment":
            start = payload.get("start", points[0])
            end = payload.get("end", points[-1])
            return Segment(
                start=tuple(start),
                end=tuple(end),
                confidence=float(winner.score),
                source=winner.source,
            )

        if label == "circle":
            center = payload.get("center", centroid(points))
            radius = payload.get("radius")
            if radius is None:
                radius = self._mean_radius(points, center)
            return Circle(
                _points=points,
                center=tuple(center),
                radius=float(radius),
                confidence=float(winner.score),
                source=winner.source,
            )

        if label == "triangle":
            vertices = payload.get("vertices")
            if not vertices:
                vertices = simplify_to_vertices(points, target_vertices=3)
            if not vertices:
                return None
            return Triangle(
                _points=points,
                vertices=[tuple(v) for v in vertices],
                confidence=float(winner.score),
                source=winner.source,
            )

        return None

    @staticmethod
    def _mean_radius(points: list[tuple[float, float]], center: tuple[float, float]) -> float:
        if not points:
            return 0.0
        return sum(euclidean_distance(point, center) for point in points) / len(points)
