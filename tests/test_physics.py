"""Tests du contrat physique, sans reseau ni client pygame."""
from __future__ import annotations

import unittest

from server.entities.components import Entity, EntityBody
from server.game_instance import GameInstance


class PhysicsTests(unittest.TestCase):
    def _world(self, objects=None):
        return GameInstance("physics", {"size": [800, 600], "objects": objects or []}, None)

    def test_same_force_accelerates_light_body_more(self):
        world = self._world()
        light = Entity("light", "crate", EntityBody(x=100, y=100, mass=1))
        heavy = Entity("heavy", "crate", EntityBody(x=200, y=100, mass=2))
        world.entities.extend([light, heavy])
        world.apply_force("light", 120, 0)
        world.apply_force("heavy", 120, 0)
        world._physics_system.tick(world, 1 / 60, 0)
        self.assertGreater(light.body.x - 100, heavy.body.x - 200)

    def test_static_body_ignores_force(self):
        world = self._world()
        wall = Entity("wall", "crate", EntityBody(x=100, y=100, static=True))
        world.entities.append(wall)
        self.assertTrue(world.apply_force("wall", 1000, 0))
        world._physics_system.tick(world, 1 / 60, 0)
        self.assertEqual((wall.body.x, wall.body.y), (100, 100))

    def test_force_zone_hits_player_and_entity(self):
        world = self._world()
        player = world.create_player("mage", 100, 100)
        crate = Entity("crate", "crate", EntityBody(x=130, y=100))
        world.entities.append(crate)
        hit = world.apply_force_in_radius(100, 100, 50, 600, 0)
        self.assertEqual(set(hit), {"mage", "crate"})
        world._physics_system.tick(world, 1 / 60, 0)
        self.assertGreater(player.x, 100)
        self.assertGreater(crate.body.x, 130)

    def test_wall_collision_slides_on_free_axis(self):
        wall = {"points": [[200, 0], [220, 0], [220, 600], [200, 600]]}
        world = self._world([wall])
        crate = Entity("crate", "crate", EntityBody(x=170, y=100, radius=10))
        world.entities.append(crate)
        world._move_body_with_collision(crate.body, 40, 30)
        self.assertEqual(crate.body.x, 170)
        self.assertEqual(crate.body.y, 130)

    def test_force_is_bounded_and_expires(self):
        world = self._world()
        crate = Entity("crate", "crate", EntityBody(x=100, y=100))
        world.entities.append(crate)
        world.apply_force("crate", 1_000_000, 0, duration=0)
        world._physics_system.tick(world, 1 / 60, 0)
        self.assertLessEqual(crate.body.velocity_x, world._physics_system.MAX_SPEED)
        self.assertEqual(world._physics_system.active_forces, [])


if __name__ == "__main__":
    unittest.main()
