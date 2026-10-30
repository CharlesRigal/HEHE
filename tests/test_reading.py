"""Lecture du dessin cote client (README, « Lecture du dessin »)."""
from __future__ import annotations

import math
import random
import unittest

from client.magic.circle import find_circle, measure_loop
from client.magic.dollar_p import recognize, recognize_oriented
from client.magic.grouping import group_strokes
from client.magic.reader import PentacleReader
from client.magic.spell_message import build_spell_message
from client.magic.templates import EMBLEM_GLYPHS, SIGN_GLYPHS, emblem_templates, sign_templates

THICKNESS = 4.0
CENTER = (300.0, 300.0)


def _glyph(strokes, cx, cy, scale, rotation=0.0, noise=0.0, rng=None):
    """Place un glyphe : densifie, tourne, met a l'echelle, bruite."""
    rng = rng or random.Random(0)
    c, s = math.cos(rotation), math.sin(rotation)
    out = []
    for stroke in strokes:
        dense = []
        for (x1, y1), (x2, y2) in zip(stroke, stroke[1:]):
            for i in range(6):
                t = i / 6
                dense.append((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t))
        dense.append(stroke[-1])
        out.append([
            (cx + scale * (x * c - y * s) + rng.gauss(0, noise), cy + scale * (x * s + y * c) + rng.gauss(0, noise))
            for x, y in dense
        ])
    return out


def _arc(cx, cy, r, start, end, steps=90):
    return [(cx + r * math.cos(start + (end - start) * i / steps), cy + r * math.sin(start + (end - start) * i / steps))
            for i in range(steps + 1)]


def _circle(r=150.0, gap=0.0):
    """Cercle d'un trait, avec un trou de `gap` pixels."""
    gap_angle = gap / r
    return [_arc(*CENTER, r, -math.pi / 2 + gap_angle, 1.5 * math.pi)]


def _sign(kind, r_rel, angle, orientation, radius=150.0, scale=14.0, noise=0.6, seed=0):
    x = CENTER[0] + r_rel * radius * math.cos(angle)
    y = CENTER[1] + r_rel * radius * math.sin(angle)
    return _glyph(SIGN_GLYPHS[kind], x, y, scale, orientation, noise, random.Random(seed))


class GroupingTests(unittest.TestCase):
    def test_contact_follows_rendered_thickness(self):
        a = [(0.0, 0.0), (100.0, 0.0)]
        touching = [(50.0, THICKNESS), (50.0, 50.0)]
        apart = [(50.0, THICKNESS + 1.0), (50.0, 50.0)]
        self.assertEqual(len(group_strokes([a, touching], THICKNESS)), 1)
        self.assertEqual(len(group_strokes([a, apart], THICKNESS)), 2)

    def test_crossing_strokes_form_one_symbol(self):
        cross = [[(0.0, 0.0), (20.0, 20.0)], [(0.0, 20.0), (20.0, 0.0)]]
        self.assertEqual(len(group_strokes(cross, THICKNESS)), 1)


class CircleTests(unittest.TestCase):
    def test_gap_up_to_thickness_is_closed(self):
        closed = group_strokes(_circle(gap=THICKNESS * 0.8), THICKNESS)[0]
        opened = group_strokes(_circle(gap=THICKNESS * 3), THICKNESS)[0]
        self.assertTrue(measure_loop(closed, THICKNESS).closed)
        self.assertFalse(measure_loop(opened, THICKNESS).closed)

    def test_nearly_closed_circle_closed_by_a_last_stroke(self):
        r = 150.0
        strokes = [_arc(*CENTER, r, 0.0, 1.9 * math.pi)]
        self.assertIsNone(find_circle(group_strokes(strokes, THICKNESS), THICKNESS))
        strokes.append(_arc(*CENTER, r, 1.85 * math.pi, 2.05 * math.pi, steps=12))
        self.assertIsNotNone(find_circle(group_strokes(strokes, THICKNESS), THICKNESS))

    def test_spiral_and_triangle_are_not_circles(self):
        spiral = [[(CENTER[0] + 4 * t * math.cos(t), CENTER[1] + 4 * t * math.sin(t)) for t in
                   [i * 0.1 for i in range(10, 200)]]]
        triangle = _glyph(SIGN_GLYPHS["convergence"], *CENTER, 60.0)
        self.assertIsNone(find_circle(group_strokes(spiral, THICKNESS), THICKNESS))
        self.assertIsNone(find_circle(group_strokes(triangle, THICKNESS), THICKNESS))

    def test_irregular_loop_is_not_a_circle(self):
        squashed = [[(CENTER[0] + 150 * math.cos(t), CENTER[1] + 80 * math.sin(t))
                     for t in [i * 2 * math.pi / 120 for i in range(121)]]]
        self.assertIsNone(find_circle(group_strokes(squashed, THICKNESS), THICKNESS))


class RecognizerTests(unittest.TestCase):
    def test_each_emblem_is_recognized_with_noise(self):
        templates = emblem_templates()
        rng = random.Random(3)
        for label, glyph in EMBLEM_GLYPHS.items():
            with self.subTest(emblem=label):
                match = recognize(_glyph(glyph, 0, 0, 20.0, rng.uniform(-0.15, 0.15), 1.0, rng), templates)
                self.assertEqual(match.label, label)

    def test_each_sign_is_recognized_at_any_rotation_with_its_orientation(self):
        templates = sign_templates()
        rng = random.Random(5)
        for label, glyph in SIGN_GLYPHS.items():
            for _ in range(3):
                rotation = rng.uniform(-math.pi, math.pi)
                with self.subTest(sign=label, rotation=round(math.degrees(rotation))):
                    match = recognize_oriented(_glyph(glyph, 0, 0, 18.0, rotation, 0.8, rng), templates)
                    self.assertEqual(match.label, label)
                    error = math.atan2(math.sin(match.orientation - rotation), math.cos(match.orientation - rotation))
                    self.assertLess(abs(math.degrees(error)), 8.0)
                    self.assertGreater(match.score - match.flip_score, 0.08)

    def test_symmetric_shape_has_no_distinct_head(self):
        """F0 : un losange se lit pareil dans les deux sens, base et tete indistinguables."""
        diamond = [[(-1.0, 0.0), (0.0, -0.5), (1.0, 0.0), (0.0, 0.5), (-1.0, 0.0)]]
        match = recognize_oriented(_glyph(diamond, 0, 0, 18.0), sign_templates())
        self.assertLess(match.score - match.flip_score, 0.08)


class PentacleTests(unittest.TestCase):
    reader = PentacleReader()

    def _pentacle(self):
        """Exemple du README : eau, traction / convergence / suspension en triangles."""
        strokes = _glyph(EMBLEM_GLYPHS["water"], *CENTER, 18.0, noise=0.5)
        for ring, (kind, r_rel) in enumerate((("traction", 0.82), ("convergence", 0.55), ("suspension", 0.3))):
            for i in range(3):
                angle = -math.pi / 2 + i * 2 * math.pi / 3 + ring * math.pi / 3
                strokes += _sign(kind, r_rel, angle, angle + math.pi, scale=12.0 if ring == 2 else 14.0, seed=ring * 3 + i)
        return strokes

    def test_open_circle_is_not_read(self):
        strokes = self._pentacle() + _circle(gap=30.0)
        self.assertIsNone(self.reader.read(strokes, THICKNESS))

    def test_full_pentacle_is_read(self):
        strokes = self._pentacle() + _circle()
        reading = self.reader.read(strokes, THICKNESS)
        self.assertIsNotNone(reading)
        self.assertAlmostEqual(reading.radius, 150.0, delta=2.0)
        self.assertEqual(reading.emblem.element, "water")
        self.assertTrue(reading.emblem.alive)
        kinds = sorted(sign.kind for sign in reading.signs if sign.alive)
        self.assertEqual(kinds, ["convergence"] * 3 + ["suspension"] * 3 + ["traction"] * 3)
        for sign in reading.signs:
            # Tete vers le centre : composante radiale negative.
            radial = math.cos(sign.orientation - sign.angle)
            self.assertLess(radial, -0.9)

        message = build_spell_message(reading)
        self.assertEqual(message["t"], "s")
        self.assertEqual(message["e"], "water")
        self.assertEqual(len(message["signs"]), 9)
        self.assertGreater(message["ink"], 2 * math.pi * 150)

    def test_dispersion_is_convergence_pointing_outward(self):
        strokes = _glyph(EMBLEM_GLYPHS["fire"], *CENTER, 18.0) + _circle()
        strokes += _sign("convergence", 0.6, 0.0, 0.0)          # tete vers l'exterieur
        sign = self.reader.read(strokes, THICKNESS).signs[0]
        self.assertEqual(sign.kind, "convergence")
        self.assertGreater(math.cos(sign.orientation - sign.angle), 0.9)

    def test_symbol_touching_the_circle_kills_the_spell(self):
        strokes = self._pentacle() + _circle()
        strokes.append([(CENTER[0], CENTER[1] - 130.0), (CENTER[0], CENTER[1] - 160.0)])
        self.assertIsNone(self.reader.read(strokes, THICKNESS))

    def test_emblem_is_the_symbol_nearest_the_center(self):
        strokes = _circle() + _glyph(EMBLEM_GLYPHS["fire"], CENTER[0] + 15, CENTER[1], 16.0)
        strokes += _sign("direction", 0.7, 0.0, 0.0)
        reading = self.reader.read(strokes, THICKNESS)
        self.assertEqual(reading.emblem.element, "fire")
        self.assertEqual([s.kind for s in reading.signs], ["direction"])

    def test_symbols_outside_the_circle_are_ignored(self):
        strokes = _circle() + _glyph(EMBLEM_GLYPHS["fire"], *CENTER, 16.0)
        strokes += _sign("direction", 1.4, 0.0, 0.0)
        reading = self.reader.read(strokes, THICKNESS)
        self.assertEqual(reading.ignored, 1)
        self.assertEqual(reading.signs, [])

    def test_circle_without_emblem_is_inert(self):
        reading = self.reader.read(_circle(), THICKNESS)
        self.assertTrue(reading.is_inert)
        self.assertIsNone(build_spell_message(reading))

    def test_scribble_sign_is_dead(self):
        rng = random.Random(9)
        scribble = [[(CENTER[0] + 90 + rng.uniform(-12, 12), CENTER[1] + rng.uniform(-12, 12)) for _ in range(25)]]
        strokes = _circle() + _glyph(EMBLEM_GLYPHS["fire"], *CENTER, 16.0) + scribble
        sign = self.reader.read(strokes, THICKNESS).signs[0]
        self.assertFalse(sign.alive)
        self.assertEqual(build_spell_message(self.reader.read(strokes, THICKNESS))["signs"], [])


if __name__ == "__main__":
    unittest.main()
