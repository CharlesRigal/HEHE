from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from client.magic.recognition.types import NormalizedStroke, Point, StrokeSample


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def euclidean_distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def path_length(points: Sequence[Point]) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for idx in range(1, len(points)):
        total += euclidean_distance(points[idx - 1], points[idx])
    return total


def bounding_box(points: Sequence[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def bbox_diagonal(bbox: tuple[float, float, float, float]) -> float:
    min_x, min_y, max_x, max_y = bbox
    return math.hypot(max_x - min_x, max_y - min_y)


def centroid(points: Sequence[Point]) -> Point:
    if not points:
        return (0.0, 0.0)
    sum_x = sum(p[0] for p in points)
    sum_y = sum(p[1] for p in points)
    return (sum_x / len(points), sum_y / len(points))


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_stroke_sample(raw: Any) -> StrokeSample | None:
    # Support dict extensible: {"point": [x, y], "time": t} ou {"x": x, "y": y, "t": t}
    if isinstance(raw, Mapping):
        if "point" in raw:
            point = raw.get("point")
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                x = _as_float(point[0])
                y = _as_float(point[1])
                t = _as_float(raw.get("time", raw.get("t")))
                if x is not None and y is not None:
                    return StrokeSample((x, y), t)
        if "x" in raw and "y" in raw:
            x = _as_float(raw.get("x"))
            y = _as_float(raw.get("y"))
            t = _as_float(raw.get("time", raw.get("t")))
            if x is not None and y is not None:
                return StrokeSample((x, y), t)
        return None

    # Support tuple horodate: ((x, y), t)
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        first, second = raw[0], raw[1]
        if isinstance(first, (list, tuple)) and len(first) >= 2:
            x = _as_float(first[0])
            y = _as_float(first[1])
            t = _as_float(second)
            if x is not None and y is not None:
                return StrokeSample((x, y), t)

        # Support (x, y) et (x, y, t)
        x = _as_float(raw[0])
        y = _as_float(raw[1])
        if x is not None and y is not None:
            t = _as_float(raw[2]) if len(raw) >= 3 else None
            return StrokeSample((x, y), t)

    return None


def normalize_stroke(
    raw_stroke: Sequence[Any],
    min_sample_distance: float = 2.0,
    closed_ratio: float = 0.08,
) -> NormalizedStroke | None:
    samples: list[StrokeSample] = []
    for raw in raw_stroke:
        parsed = parse_stroke_sample(raw)
        if parsed is not None:
            samples.append(parsed)

    if len(samples) < 2:
        return None

    points: list[Point] = [samples[0].point]
    times: list[float | None] = [samples[0].time]

    for sample in samples[1:]:
        if euclidean_distance(sample.point, points[-1]) >= min_sample_distance:
            points.append(sample.point)
            times.append(sample.time)

    if len(points) == 1:
        points.append(samples[-1].point)
        times.append(samples[-1].time)

    if len(points) < 2:
        return None

    stroke_path = path_length(points)
    if stroke_path <= 1e-6:
        return None

    bbox = bounding_box(points)
    diagonal = max(1e-6, bbox_diagonal(bbox))
    start_end = euclidean_distance(points[0], points[-1])
    closure_threshold = max(8.0, diagonal * closed_ratio)
    is_closed = len(points) >= 4 and start_end <= closure_threshold

    return NormalizedStroke(
        points=points,
        times=times,
        path_length=stroke_path,
        bbox=bbox,
        diagonal=diagonal,
        start_end_distance=start_end,
        is_closed=is_closed,
    )


def perpendicular_distance(point: Point, line_start: Point, line_end: Point) -> float:
    x0, y0 = point
    x1, y1 = line_start
    x2, y2 = line_end
    numerator = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1)
    denominator = math.hypot(y2 - y1, x2 - x1)
    return numerator / (denominator + 1e-9)


def rdp(points: Sequence[Point], epsilon: float) -> list[Point]:
    if len(points) < 3:
        return list(points)

    dmax = 0.0
    index = 0
    first = points[0]
    last = points[-1]

    for idx in range(1, len(points) - 1):
        dist = perpendicular_distance(points[idx], first, last)
        if dist > dmax:
            dmax = dist
            index = idx

    if dmax > epsilon:
        left = rdp(points[: index + 1], epsilon)
        right = rdp(points[index:], epsilon)
        return left[:-1] + right
    return [first, last]


def ensure_closed_contour(points: Sequence[Point]) -> list[Point]:
    contour = list(points)
    if contour and contour[0] != contour[-1]:
        contour.append(contour[0])
    return contour


def dedupe_consecutive(points: Sequence[Point], tolerance: float = 1e-9) -> list[Point]:
    if not points:
        return []
    result = [points[0]]
    for point in points[1:]:
        if euclidean_distance(point, result[-1]) > tolerance:
            result.append(point)
    return result


def _cyclic_distance(a: int, b: int, total: int) -> int:
    direct = abs(a - b)
    return min(direct, total - direct)


def _extract_strong_corners(points: Sequence[Point], target_vertices: int) -> list[Point] | None:
    contour = list(points)
    if len(contour) < target_vertices:
        return None

    scores: list[tuple[float, int]] = []
    total = len(contour)

    for idx in range(total):
        prev = contour[(idx - 1) % total]
        curr = contour[idx]
        nxt = contour[(idx + 1) % total]

        a1 = math.atan2(curr[1] - prev[1], curr[0] - prev[0])
        a2 = math.atan2(nxt[1] - curr[1], nxt[0] - curr[0])
        turn = abs((a2 - a1 + math.pi) % (2 * math.pi) - math.pi)
        scores.append((turn, idx))

    scores.sort(reverse=True, key=lambda item: item[0])
    min_gap = max(1, total // (target_vertices * 4))
    selected: list[int] = []

    for _, idx in scores:
        if all(_cyclic_distance(idx, chosen, total) > min_gap for chosen in selected):
            selected.append(idx)
        if len(selected) == target_vertices:
            break

    if len(selected) != target_vertices:
        return None

    selected.sort()
    return [tuple(contour[idx]) for idx in selected]


def simplify_to_vertices(points: Sequence[Point], target_vertices: int = 3) -> list[Point] | None:
    if len(points) < target_vertices:
        return None

    open_points = list(points)
    if open_points and open_points[0] == open_points[-1]:
        open_points = open_points[:-1]
    open_points = dedupe_consecutive(open_points)
    if len(open_points) < target_vertices:
        return None

    contour = ensure_closed_contour(open_points)
    perimeter = path_length(contour)
    if perimeter <= 0:
        return None

    best_over_target: list[Point] | None = None
    for factor in (0.02, 0.03, 0.04, 0.05, 0.07, 0.10):
        simplified = rdp(contour, epsilon=max(2.0, perimeter * factor))
        if len(simplified) > 1 and simplified[0] == simplified[-1]:
            simplified = simplified[:-1]
        simplified = dedupe_consecutive(simplified)
        if len(simplified) == target_vertices:
            return [tuple(p) for p in simplified]
        if len(simplified) > target_vertices:
            if best_over_target is None or len(simplified) < len(best_over_target):
                best_over_target = simplified

    if best_over_target is not None:
        corners = _extract_strong_corners(best_over_target, target_vertices=target_vertices)
        if corners is not None:
            return corners

    return _extract_strong_corners(open_points, target_vertices=target_vertices)


def resample(points: Sequence[Point], target_count: int) -> list[Point]:
    if not points:
        return []
    if target_count <= 1:
        return [points[0]]
    if len(points) == 1:
        return [points[0] for _ in range(target_count)]

    total_length = path_length(points)
    if total_length <= 1e-9:
        return [points[0] for _ in range(target_count)]

    step = total_length / (target_count - 1)
    accumulated = 0.0
    work = list(points)
    new_points = [work[0]]
    idx = 1

    while idx < len(work):
        previous = work[idx - 1]
        current = work[idx]
        segment_length = euclidean_distance(previous, current)

        if segment_length <= 1e-9:
            idx += 1
            continue

        if accumulated + segment_length >= step:
            ratio = (step - accumulated) / segment_length
            qx = previous[0] + ratio * (current[0] - previous[0])
            qy = previous[1] + ratio * (current[1] - previous[1])
            q = (qx, qy)
            new_points.append(q)
            work.insert(idx, q)
            accumulated = 0.0
            idx += 1
        else:
            accumulated += segment_length
            idx += 1

    if len(new_points) == target_count - 1:
        new_points.append(work[-1])

    while len(new_points) < target_count:
        new_points.append(work[-1])

    return new_points[:target_count]


def rotate_by(points: Sequence[Point], angle: float) -> list[Point]:
    c = centroid(points)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    rotated: list[Point] = []
    for x, y in points:
        dx = x - c[0]
        dy = y - c[1]
        rotated.append((dx * cos_a - dy * sin_a + c[0], dx * sin_a + dy * cos_a + c[1]))
    return rotated


def indicative_angle(points: Sequence[Point]) -> float:
    c = centroid(points)
    first = points[0]
    return math.atan2(c[1] - first[1], c[0] - first[0])


def scale_to_square(points: Sequence[Point], size: float) -> list[Point]:
    min_x, min_y, max_x, max_y = bounding_box(points)
    width = max_x - min_x
    height = max_y - min_y

    if width <= 1e-9 and height <= 1e-9:
        return [(0.0, 0.0) for _ in points]
    if width <= 1e-9:
        width = height
    if height <= 1e-9:
        height = width

    scaled: list[Point] = []
    for x, y in points:
        sx = ((x - min_x) / width) * size
        sy = ((y - min_y) / height) * size
        scaled.append((sx, sy))
    return scaled


def translate_to_origin(points: Sequence[Point]) -> list[Point]:
    c = centroid(points)
    return [(x - c[0], y - c[1]) for x, y in points]


def path_distance(a: Sequence[Point], b: Sequence[Point]) -> float:
    if not a or not b:
        return float("inf")
    count = min(len(a), len(b))
    total = 0.0
    for idx in range(count):
        total += euclidean_distance(a[idx], b[idx])
    return total / count


def distance_at_angle(points: Sequence[Point], template: Sequence[Point], angle: float) -> float:
    return path_distance(rotate_by(points, angle), template)


def distance_at_best_angle(
    points: Sequence[Point],
    template: Sequence[Point],
    angle_range: float,
    angle_precision: float,
) -> float:
    phi = 0.5 * (-1.0 + math.sqrt(5.0))
    a = -angle_range
    b = angle_range
    x1 = phi * a + (1 - phi) * b
    x2 = (1 - phi) * a + phi * b
    f1 = distance_at_angle(points, template, x1)
    f2 = distance_at_angle(points, template, x2)

    while abs(b - a) > angle_precision:
        if f1 < f2:
            b = x2
            x2 = x1
            f2 = f1
            x1 = phi * a + (1 - phi) * b
            f1 = distance_at_angle(points, template, x1)
        else:
            a = x1
            x1 = x2
            f1 = f2
            x2 = (1 - phi) * a + phi * b
            f2 = distance_at_angle(points, template, x2)

    return min(f1, f2)
