"""Tests de fluidite de l'interpolation client sans ouvrir de fenetre pygame."""
from __future__ import annotations

import unittest

import pygame

from client.core.interpolator import Interpolator


class InterpolatorTests(unittest.TestCase):
    def test_moves_in_regular_steps_without_overshoot(self):
        interpolator = Interpolator(pygame.Vector2(0, 0), speed=100)
        interpolator.set_target(pygame.Vector2(100, 0))

        positions = [interpolator.update(0.1).x for _ in range(10)]

        self.assertEqual(positions, [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0])
        self.assertEqual(interpolator.update(0.1).x, 100.0)

    def test_new_snapshot_keeps_motion_bounded_and_smooth(self):
        interpolator = Interpolator(pygame.Vector2(0, 0), speed=100)
        interpolator.set_target(pygame.Vector2(100, 0))
        first_position = interpolator.update(0.1).x
        interpolator.set_target(pygame.Vector2(25, 0))
        second_position = interpolator.update(0.1).x

        self.assertEqual(first_position, 10.0)
        self.assertEqual(second_position, 20.0)
        self.assertLessEqual(abs(second_position - first_position), 100 * 0.1)
        self.assertLessEqual(second_position, 25.0)


if __name__ == "__main__":
    unittest.main()
