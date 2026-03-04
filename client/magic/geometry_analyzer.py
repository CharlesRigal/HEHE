import math
import numpy as np

def is_closed(stroke, threshold=15):
    if len(stroke) < 3:
        return False
    dx = stroke[0][0] - stroke[-1][0]
    dy = stroke[0][1] - stroke[-1][1]
    return dx*dx + dy*dy < threshold*threshold

def _as_unique_closed_points(points):
    if not points:
        return []
    pts = [tuple(p) for p in points]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts

def detect_circle(points, tolerance=0.18, min_points=8):
    pts_list = _as_unique_closed_points(points)
    if len(pts_list) < min_points:
        return None

    pts = np.array(pts_list, dtype=float)
    center = pts.mean(axis=0)

    distances = np.linalg.norm(pts - center, axis=1)
    radius = distances.mean()
    variance = distances.std()

    if tolerance <= 0 or radius <= 1:
        return None

    radial_error = variance / radius
    if radial_error >= tolerance:
        return None

    # Evite de classer un simple arc comme cercle: il faut couvrir
    # une grande partie de l'angle autour du centre.
    angles = np.mod(np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0]), 2 * math.pi)
    angles.sort()
    gaps = np.diff(np.concatenate([angles, [angles[0] + 2 * math.pi]]))
    coverage = 2 * math.pi - float(np.max(gaps))
    if coverage < 1.7 * math.pi:
        return None

    # Un cercle dessiné doit rester proche d'un bbox quasi carré.
    bbox_w = float(np.max(pts[:, 0]) - np.min(pts[:, 0]))
    bbox_h = float(np.max(pts[:, 1]) - np.min(pts[:, 1]))
    if bbox_w <= 0 or bbox_h <= 0:
        return None
    aspect = bbox_w / bbox_h
    if aspect < 0.6 or aspect > 1.4:
        return None

    return center, radius

def _simplify_closed_shape(points, epsilon):
    contour = [tuple(p) for p in points]
    if len(contour) < 3:
        return contour

    if contour[0] != contour[-1]:
        contour = contour + [contour[0]]

    simplified = rdp(contour, epsilon)
    if len(simplified) > 1 and simplified[0] == simplified[-1]:
        simplified = simplified[:-1]
    return simplified

def detect_triangle(points):
    pts_list = _as_unique_closed_points(points)
    if len(pts_list) < 3:
        return None

    pts_np = np.array(pts_list, dtype=float)
    perimeter = float(np.sum(np.linalg.norm(pts_np - np.roll(pts_np, -1, axis=0), axis=1)))
    diag = float(np.linalg.norm(
        [np.max(pts_np[:, 0]) - np.min(pts_np[:, 0]), np.max(pts_np[:, 1]) - np.min(pts_np[:, 1])]
    ))
    if perimeter <= 0 or diag <= 0:
        return None

    # On augmente progressivement epsilon pour converger vers 3 sommets.
    factors = [0.02, 0.03, 0.04, 0.05, 0.07]
    candidate = None
    for factor in factors:
        simp = _simplify_closed_shape(pts_list, epsilon=max(3.0, perimeter * factor))
        if len(simp) == 3:
            candidate = simp
            break

    if candidate is None:
        return None

    a, b, c = [np.array(p, dtype=float) for p in candidate]
    area2 = abs(np.cross(b - a, c - a))
    if area2 < (diag * diag * 0.02):
        return None

    lengths = [
        float(np.linalg.norm(b - a)),
        float(np.linalg.norm(c - b)),
        float(np.linalg.norm(a - c)),
    ]
    if min(lengths) < diag * 0.15:
        return None

    return [tuple(p) for p in candidate]

def rdp(points, epsilon):
    if len(points) < 3:
        return points

    def perpendicular_distance(pt, line_start, line_end):
        x0, y0 = pt
        x1, y1 = line_start
        x2, y2 = line_end

        num = abs((y2 - y1)*x0 - (x2 - x1)*y0 + x2*y1 - y2*x1)
        den = math.hypot(y2 - y1, x2 - x1)
        return num / (den + 1e-6)

    dmax = 0
    index = 0

    for i in range(1, len(points) - 1):
        d = perpendicular_distance(points[i], points[0], points[-1])
        if d > dmax:
            index = i
            dmax = d

    if dmax > epsilon:
        left = rdp(points[:index+1], epsilon)
        right = rdp(points[index:], epsilon)
        return left[:-1] + right
    else:
        return [points[0], points[-1]]

class Segment:
    def __init__(self, start, end):
        self.start = start
        self.end = end



class Circle:
    def __init__(self, points, center=None, radius=None):
        self._points = points
        self.center = center
        self.radius = radius


class Triangle:
    def __init__(self, points, vertices):
        self._points = points
        self.vertices = vertices


class GeometryAnalyzer:
    def analyze(self, strokes):
        primitives = []
        for stroke in strokes:
            primitive = self._analyze_stroke(stroke)
            if primitive:
                primitives.append(primitive)
        return primitives

    @staticmethod
    def _analyze_stroke(stroke):
        if len(stroke) < 2:
            return None

        simplified = rdp(stroke, epsilon=5)
        if len(simplified) == 2:
            return Segment(simplified[0], simplified[1])

        if is_closed(stroke):
            circle_data = detect_circle(stroke)
            if circle_data:
                center, radius = circle_data
                return Circle(stroke, center=tuple(center.tolist()), radius=float(radius))

            triangle_vertices = detect_triangle(stroke)
            if triangle_vertices:
                return Triangle(stroke, triangle_vertices)

        return None
