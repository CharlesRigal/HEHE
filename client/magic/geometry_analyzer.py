import math
import numpy as np

def is_closed(stroke, threshold=15):
    dx = stroke[0][0] - stroke[-1][0]
    dy = stroke[0][1] - stroke[-1][1]
    return dx*dx + dy*dy < threshold*threshold

def detect_circle(points, tolerance=0.2):

    pts = np.array(points)
    center = pts.mean(axis=0)

    distances = np.linalg.norm(pts - center, axis=1)
    radius = distances.mean()

    variance = distances.std()

    if variance / radius < tolerance:
        return center, radius

    return None

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
    def __init__(self, points):
        self._points = points


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
        simplified = rdp(stroke, epsilon=5)
        if len(simplified) == 2:
            return Segment(simplified[0], simplified[1])

        if is_closed(simplified):
            detect_circle(simplified)
            return Circle(simplified)
        return None


