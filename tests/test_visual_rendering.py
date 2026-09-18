"""Tests de regression visuelle pygame, executables sans fenetre."""
from __future__ import annotations

import hashlib
import os
import unittest

# Doit etre configure avant l'import de pygame, y compris en CI Linux.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from client.entities.interactive_entity_renderer import InteractiveEntityRenderer


class _Camera:
    offset = pygame.Vector2(0, 0)

    def apply(self, position: pygame.Vector2) -> pygame.Vector2:
        return position - self.offset


class VisualRenderingTests(unittest.TestCase):
    """Capture de reference d'une scene representative des objets interactifs."""

    # Mise a jour volontaire uniquement si le rendu voulu a change.
    EXPECTED_SCENE_SHA256 = "7fa599fc571ca84aa6edbc2767770c411ad1ba466c2cec38f474cb5467d5c0ee"

    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    @staticmethod
    def _render_scene(torch_lit: bool = True, altar_powered: bool = True) -> pygame.Surface:
        surface = pygame.Surface((240, 160), pygame.SRCALPHA)
        surface.fill((12, 18, 30, 255))
        InteractiveEntityRenderer().draw(surface, [
            {"id": "torch", "type": "torch", "x": 45, "y": 86, "r": 20,
             "state": {"lit": torch_lit}},
            {"id": "altar", "type": "altar", "x": 120, "y": 86, "r": 24,
             "state": {"powered": altar_powered}},
            {"id": "crystal", "type": "crystal", "x": 195, "y": 86, "r": 20,
             "state": {"lifted": False}},
        ], _Camera())
        return surface

    def test_interactive_scene_matches_visual_baseline(self):
        """Detecte toute modification non validee de la scene rendue."""
        pixels = pygame.image.tobytes(self._render_scene(), "RGBA")
        actual_hash = hashlib.sha256(pixels).hexdigest()
        self.assertEqual(actual_hash, self.EXPECTED_SCENE_SHA256)

    def test_lit_and_powered_states_have_visible_effects(self):
        """Evite les regressions ou un changement d'etat ne se voit plus."""
        inactive = pygame.image.tobytes(self._render_scene(False, False), "RGBA")
        active = pygame.image.tobytes(self._render_scene(True, True), "RGBA")

        changed_pixels = sum(
            inactive[index:index + 4] != active[index:index + 4]
            for index in range(0, len(active), 4)
        )
        self.assertGreater(changed_pixels, 100)


if __name__ == "__main__":
    unittest.main()
