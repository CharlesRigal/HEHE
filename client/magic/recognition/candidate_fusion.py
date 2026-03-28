from __future__ import annotations

from typing import Any

from client.magic.recognition.preprocessing import (
    clamp,
    dedupe_consecutive,
    euclidean_distance,
    rdp,
    turn_angle,
)
from client.magic.recognition.shape_registry import ShapeRegistry
from client.magic.recognition.types import NormalizedStroke, RecognitionConfig, RecognizerResult


class CandidateFusionPolicy:
    """
    Politique de fusion des candidats de reconnaissance.
    Isole les pondérations de sources et les garde-fous par forme.
    """

    FALLBACK_DOLLAR_FACTOR_WHEN_HEURISTIC_EXISTS = 0.60

    SEGMENT_PATH_RATIO_BLOCK = 1.12
    SEGMENT_PATH_RATIO_DAMP = 1.07
    SEGMENT_DAMP_FACTOR = 0.20

    TRIANGLE_BLOCK_TURN_COUNT = 5
    TRIANGLE_DAMP_TURN_COUNT = 4
    TRIANGLE_TURN_DAMP_FACTOR = 0.40
    TRIANGLE_PATH_DIAGONAL_DAMP_THRESHOLD = 3.0
    TRIANGLE_PATH_DIAGONAL_DAMP_FACTOR = 0.35

    TURN_ESTIMATION_EPSILON_RATIO = 0.03
    TURN_ESTIMATION_EPSILON_MIN = 2.0
    TURN_ESTIMATION_DEDUPE_TOL = 1.2
    TURN_ESTIMATION_CLOSED_DISTANCE_MIN = 6.0
    TURN_ESTIMATION_CLOSED_DISTANCE_RATIO = 0.08
    TURN_ESTIMATION_MIN_LEG_MIN = 6.0
    TURN_ESTIMATION_MIN_LEG_RATIO = 0.04
    TURN_ESTIMATION_MIN_ANGLE = 0.28

    def __init__(self, *, shape_registry: ShapeRegistry, config: RecognitionConfig) -> None:
        self.shape_registry = shape_registry
        self.config = config

    def merge(
        self,
        stroke: NormalizedStroke,
        heuristic_candidates: list[RecognizerResult],
        dollar_candidate: RecognizerResult | None,
    ) -> RecognizerResult | None:
        by_label: dict[str, dict[str, Any]] = {}
        raw_best_by_label: dict[str, RecognizerResult] = {}
        heuristic_labels: set[str] = set()

        for candidate in heuristic_candidates:
            canonical = self.shape_registry.canonical_label(candidate.label)
            if canonical is None:
                continue
            heuristic_labels.add(canonical)
            self._register_raw_best(raw_best_by_label, canonical, candidate)
            weight = self.config.get_source_weight(candidate.source, default=self.config.heuristic_weight)
            self._accumulate_candidate(by_label, canonical, candidate, weight)

        if dollar_candidate is not None:
            canonical = self.shape_registry.canonical_label(dollar_candidate.label)
            if canonical is not None:
                self._register_raw_best(
                    raw_best_by_label,
                    canonical,
                    RecognizerResult(
                        label=canonical,
                        score=dollar_candidate.score,
                        source="$1",
                        payload=dict(dollar_candidate.payload),
                    ),
                )

                has_heuristic_for_label = canonical in heuristic_labels
                default_dollar_weight = self.config.get_source_weight("$1", default=self.config.dollar_weight)
                if has_heuristic_for_label:
                    weight = default_dollar_weight
                elif heuristic_labels:
                    weight = default_dollar_weight * self.FALLBACK_DOLLAR_FACTOR_WHEN_HEURISTIC_EXISTS
                else:
                    weight = self.config.fallback_source_weight

                weight = self._apply_single_source_guardrails(
                    canonical=canonical,
                    stroke=stroke,
                    has_heuristic_for_label=has_heuristic_for_label,
                    weight=weight,
                )

                dollar_payload = {"dollar": dollar_candidate.payload} if dollar_candidate.payload else {}
                self._accumulate_candidate(
                    by_label,
                    canonical,
                    RecognizerResult(
                        label=canonical,
                        score=dollar_candidate.score,
                        source="$1",
                        payload=dollar_payload,
                    ),
                    weight,
                )

        if not by_label:
            return None

        for label, slot in by_label.items():
            shape = self.shape_registry.get(label)
            if shape is None:
                continue
            if len(set(slot["sources"])) >= 2:
                slot["score"] = min(1.0, slot["score"] + shape.multi_source_bonus)
            if shape.requires_closed is True and not stroke.is_closed:
                slot["score"] *= shape.open_penalty

        best_label, best_slot = max(by_label.items(), key=lambda item: item[1]["score"])
        shape = self.shape_registry.get(best_label)
        if shape is None:
            return None

        threshold = self.config.get_shape_threshold(best_label, shape.threshold)
        best_score = best_slot["score"]
        if best_score < threshold:
            fallback = raw_best_by_label.get(best_label)
            if fallback is not None and fallback.source == "heuristic" and fallback.score >= threshold:
                return RecognizerResult(
                    label=best_label,
                    score=fallback.score,
                    source=fallback.source,
                    payload=dict(fallback.payload),
                )
            return None

        source = "+".join(sorted(set(best_slot["sources"]))) or "unknown"
        return RecognizerResult(
            label=best_label,
            score=best_score,
            source=source,
            payload=best_slot["payload"],
        )

    def _apply_single_source_guardrails(
        self,
        *,
        canonical: str,
        stroke: NormalizedStroke,
        has_heuristic_for_label: bool,
        weight: float,
    ) -> float:
        if weight <= 0.0:
            return 0.0

        if canonical == "segment":
            straightness_ratio = stroke.path_length / max(stroke.start_end_distance, 1e-6)
            if straightness_ratio >= self.SEGMENT_PATH_RATIO_BLOCK:
                return 0.0
            if straightness_ratio >= self.SEGMENT_PATH_RATIO_DAMP:
                return weight * self.SEGMENT_DAMP_FACTOR
            return weight

        if canonical == "triangle" and not has_heuristic_for_label:
            turn_count = self._estimate_turn_count(stroke)
            if turn_count >= self.TRIANGLE_BLOCK_TURN_COUNT:
                return 0.0
            if turn_count == self.TRIANGLE_DAMP_TURN_COUNT:
                weight *= self.TRIANGLE_TURN_DAMP_FACTOR

            path_to_diagonal = stroke.path_length / max(stroke.diagonal, 1e-6)
            if path_to_diagonal >= self.TRIANGLE_PATH_DIAGONAL_DAMP_THRESHOLD:
                weight *= self.TRIANGLE_PATH_DIAGONAL_DAMP_FACTOR

        return weight

    @staticmethod
    def _accumulate_candidate(
        by_label: dict[str, dict[str, Any]],
        label: str,
        candidate: RecognizerResult,
        weight: float,
    ) -> None:
        if weight <= 0.0:
            return
        slot = by_label.setdefault(label, {"score": 0.0, "payload": {}, "sources": []})
        slot["score"] += candidate.score * weight
        if candidate.payload:
            slot["payload"].update(candidate.payload)
        slot["sources"].append(candidate.source)

    @staticmethod
    def _register_raw_best(
        raw_best_by_label: dict[str, RecognizerResult],
        label: str,
        candidate: RecognizerResult,
    ) -> None:
        current = raw_best_by_label.get(label)
        if current is None or candidate.score > current.score:
            raw_best_by_label[label] = RecognizerResult(
                label=label,
                score=candidate.score,
                source=candidate.source,
                payload=dict(candidate.payload),
            )

    def _estimate_turn_count(self, stroke: NormalizedStroke) -> int:
        points = dedupe_consecutive(
            rdp(
                stroke.points,
                epsilon=max(self.TURN_ESTIMATION_EPSILON_MIN, stroke.path_length * self.TURN_ESTIMATION_EPSILON_RATIO),
            ),
            tolerance=self.TURN_ESTIMATION_DEDUPE_TOL,
        )
        if len(points) < 3:
            return 0

        closed = stroke.is_closed or (
            euclidean_distance(points[0], points[-1])
            <= max(self.TURN_ESTIMATION_CLOSED_DISTANCE_MIN, stroke.diagonal * self.TURN_ESTIMATION_CLOSED_DISTANCE_RATIO)
        )

        contour = list(points)
        if closed and euclidean_distance(contour[0], contour[-1]) > self.TURN_ESTIMATION_DEDUPE_TOL:
            contour.append(contour[0])
        if len(contour) < 4:
            return 0

        min_leg = max(self.TURN_ESTIMATION_MIN_LEG_MIN, stroke.diagonal * self.TURN_ESTIMATION_MIN_LEG_RATIO)
        turns = 0

        if closed:
            base = contour[:-1]
            total = len(base)
            for idx in range(total):
                prev = base[(idx - 1) % total]
                curr = base[idx]
                nxt = base[(idx + 1) % total]
                if euclidean_distance(prev, curr) < min_leg or euclidean_distance(curr, nxt) < min_leg:
                    continue
                if turn_angle(prev, curr, nxt) >= self.TURN_ESTIMATION_MIN_ANGLE:
                    turns += 1
            return turns

        for idx in range(1, len(contour) - 1):
            prev = contour[idx - 1]
            curr = contour[idx]
            nxt = contour[idx + 1]
            if euclidean_distance(prev, curr) < min_leg or euclidean_distance(curr, nxt) < min_leg:
                continue
            if turn_angle(prev, curr, nxt) >= self.TURN_ESTIMATION_MIN_ANGLE:
                turns += 1

        return turns
