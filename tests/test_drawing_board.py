"""Tableau de dessin et rendu du monde, sans fenetre."""
from __future__ import annotations

import math
import os
import time
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from client.graphics.world_renderer import WorldRenderer
from client.magic.drawing_board import DrawingBoard
from client.magic.templates import EMBLEM_GLYPHS


class _Camera:
    offset = pygame.Vector2(0, 0)

    def apply(self, position: pygame.Vector2) -> pygame.Vector2:
        return position - self.offset


def _event(kind, **attrs):
    return pygame.event.Event(kind, attrs)


class DrawingBoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def _trace(self, board, points):
        board.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=points[0]))
        for point in points[1:]:
            board.handle_event(_event(pygame.MOUSEMOTION, pos=point, rel=(0, 0), buttons=(1, 0, 0)))
        board.handle_event(_event(pygame.MOUSEBUTTONUP, button=1, pos=points[-1]))

    def _wait(self, board):
        deadline = time.time() + 10.0
        while time.time() < deadline:
            result = board.poll()
            if result is not None:
                return result
            time.sleep(0.01)
        self.fail("lecture trop longue")

    def test_closing_the_circle_casts_and_clears_the_board(self):
        board = DrawingBoard()
        self.assertFalse(board.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0))))
        board.handle_event(_event(pygame.MOUSEBUTTONDOWN, button=3, pos=(0, 0)))
        self.assertTrue(board.is_open)

        cx, cy = 300, 300
        for stroke in EMBLEM_GLYPHS["fire"]:
            dense = []
            for (x1, y1), (x2, y2) in zip(stroke, stroke[1:]):
                dense += [(cx + 18 * (x1 + (x2 - x1) * t / 8), cy + 18 * (y1 + (y2 - y1) * t / 8)) for t in range(9)]
            self._trace(board, dense)
        # Cercle presque ferme : rien ne part.
        arc = [(cx + 150 * math.cos(a / 60 * 1.9 * math.pi), cy + 150 * math.sin(a / 60 * 1.9 * math.pi)) for a in range(61)]
        self._trace(board, arc)
        self.assertIsNone(board.poll())
        # Dernier trait qui ferme le cercle (C1).
        closing = [(cx + 150 * math.cos(a), cy + 150 * math.sin(a)) for a in [1.85 * math.pi + i * 0.02 for i in range(35)]]
        self._trace(board, closing)

        result = self._wait(board)
        self.assertEqual(result.message["e"], "fire")
        self.assertAlmostEqual(result.message["R"], 150.0, delta=3.0)
        self.assertEqual(board.strokes, [])
        self.assertGreater(board.ink_used, 2 * math.pi * 150)
        board.close()

    def test_board_draws_only_when_open(self):
        board = DrawingBoard()
        surface = pygame.Surface((50, 50))
        board.draw(surface)
        self.assertEqual(surface.get_at((10, 10))[:3], (0, 0, 0))
        board.toggle()
        board.draw(surface)
        self.assertNotEqual(surface.get_at((10, 10))[:3], (0, 0, 0))
        board.close()


class WorldRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_water_and_ice_have_distinct_colors(self):
        renderer = WorldRenderer()
        # Cellule 0 : eau liquide. Cellule 3 : eau gelee (chaleur sous le seuil).
        renderer.load({"cs": 16, "cols": 4, "rows": 1, "cells": [
            [0, 2.0, 0, 0, 0, 0, 0],
            [3, 2.0, 0, 0, -3.0, 0, 0],
        ]})
        surface = pygame.Surface((64, 16))
        renderer.draw(surface, _Camera())
        water = surface.get_at((4, 8))
        ice = surface.get_at((60, 8))
        self.assertGreater(water.b, water.r)
        self.assertGreater(ice.r, water.r)

    def test_active_spell_ring_is_drawn(self):
        renderer = WorldRenderer()
        renderer.set_spells([{"x": 50, "y": 50, "R": 30, "e": "fire", "left": 2.0}])
        surface = pygame.Surface((100, 100))
        renderer.draw(surface, _Camera())
        self.assertNotEqual(surface.get_at((80, 50))[:3], (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
