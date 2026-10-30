"""Monde simule : grille d'elements, sorts actifs, forces (README, « Le monde »)."""
from __future__ import annotations

import math
import unittest

import numpy as np

from server.config import TICK_INTERVAL
from server.entities.components import Entity, EntityBody
from server.game_instance import GameInstance
from server.players.player import Player
from server.world.grid import WorldGrid
from server.world.spell import ActiveSpell, SignSpec, SpellSpec, combine_flows, parse_spell_message


def _ring(kind: str, r: float, count: int = 3, inward: bool = True, size: float = 0.25) -> list[SignSpec]:
    """`count` signes regulierement repartis, tete vers le centre (ou l'exterieur)."""
    signs = []
    for i in range(count):
        angle = -math.pi / 2 + i * 2 * math.pi / count
        orientation = angle + (math.pi if inward else 0.0)
        signs.append(SignSpec(kind, r, angle, orientation, size, 1.0))
    return signs


def _run(grid: WorldGrid, spells: list[ActiveSpell], seconds: float) -> None:
    for _ in range(int(seconds / TICK_INTERVAL)):
        grid.step(TICK_INTERVAL, combine_flows(grid, spells))
        for spell in spells:
            spell.advance(TICK_INTERVAL)
        spells[:] = [s for s in spells if not s.is_over()]


def _amount_within(grid: WorldGrid, field: str, x: float, y: float, radius: float) -> float:
    mask = (grid.center_x - x) ** 2 + (grid.center_y - y) ** 2 <= radius ** 2
    return float(grid.fields[field][mask].sum())


class WorldGridTests(unittest.TestCase):
    def test_diffusion_conserves_water(self):
        grid = WorldGrid(320, 320)
        grid.add_disc("water", 160, 160, 30, total=20.0)
        _run(grid, [], 2.0)
        self.assertAlmostEqual(grid.total("water"), 20.0, places=6)

    def test_cold_water_is_ice_and_does_not_move(self):
        grid = WorldGrid(320, 320)
        grid.add_disc("water", 160, 160, 30, total=20.0)
        grid.fields["heat"][:] = -3.0
        before = grid.fields["water"].copy()
        grid.step(TICK_INTERVAL)
        self.assertTrue(grid.ice_mask().any())
        np.testing.assert_allclose(before, grid.fields["water"])

    def test_heat_states_are_thresholds_only(self):
        grid = WorldGrid(64, 64)
        grid.fields["water"][0, 0] = 1.0
        grid.fields["earth"][0, 1] = 1.0
        grid.fields["heat"][0, :2] = 5.0
        self.assertTrue(grid.vapor_mask()[0, 0])
        self.assertTrue(grid.lava_mask()[0, 1])

    def test_walls_block_matter(self):
        grid = WorldGrid(320, 320, walls=[(150, 0, 170, 320)])
        grid.add_rect("water", 0, 0, 140, 320, 2.0)
        _run(grid, [], 3.0)
        right = grid.fields["water"][:, grid.cell_of(180, 0)[1]:]
        self.assertEqual(float(right.sum()), 0.0)


class SpellFieldTests(unittest.TestCase):
    def test_emblem_creates_element_in_proportion_to_circle_area(self):
        small, large = WorldGrid(640, 640), WorldGrid(640, 640)
        ActiveSpell(SpellSpec(50, 1.0, "water", 1.0), 320, 320, small)
        ActiveSpell(SpellSpec(100, 1.0, "water", 1.0), 320, 320, large)
        self.assertAlmostEqual(large.total("water") / small.total("water"), 4.0, places=6)

    def test_ice_emblem_creates_negative_heat(self):
        grid = WorldGrid(320, 320)
        ActiveSpell(SpellSpec(80, 1.0, "ice", 1.0), 160, 160, grid)
        self.assertLess(grid.total("heat"), 0.0)

    def test_inward_traction_gathers_existing_water(self):
        grid = WorldGrid(640, 640)
        grid.add_rect("water", 0, 0, 640, 640, 0.5)
        before = _amount_within(grid, "water", 320, 320, 110)
        spell = ActiveSpell(SpellSpec(120, 1.0, "water", 1.0, _ring("traction", 0.8)), 320, 320, grid)
        created = grid.total("water") - 0.5 * grid.rows * grid.cols
        _run(grid, [spell], 2.0)
        # Dehors agit dehors (F5) : l'eau du voisinage est ramenee jusqu'a la bande du signe.
        self.assertGreater(_amount_within(grid, "water", 320, 320, 110), before + created)

    def test_outward_traction_pushes_water_away(self):
        grid = WorldGrid(640, 640)
        spell = ActiveSpell(SpellSpec(120, 1.0, "water", 1.0, _ring("direction", 0.5, inward=False)), 320, 320, grid)
        start = _amount_within(grid, "water", 320, 320, 40)
        _run(grid, [spell], 1.0)
        self.assertLess(_amount_within(grid, "water", 320, 320, 40), start * 0.5)

    def test_suspension_holds_element_against_diffusion(self):
        free, held = WorldGrid(640, 640), WorldGrid(640, 640)
        free_spell = ActiveSpell(SpellSpec(120, 1.0, "water", 1.0), 320, 320, free)
        held_spell = ActiveSpell(SpellSpec(120, 1.0, "water", 1.0, _ring("suspension", 0.15, size=0.4)), 320, 320, held)
        _run(free, [free_spell], 2.0)
        _run(held, [held_spell], 2.0)
        self.assertGreater(
            _amount_within(held, "water", 320, 320, 40),
            _amount_within(free, "water", 320, 320, 40),
        )

    def test_water_bubble_example_from_readme(self):
        """Traction, convergence, suspension en triangles : l'eau reste groupee au centre."""
        signs = _ring("traction", 0.85) + _ring("convergence", 0.55) + _ring("suspension", 0.25)
        grid = WorldGrid(640, 640)
        grid.add_rect("water", 0, 0, 640, 640, 0.3)
        spell = ActiveSpell(SpellSpec(150, 1.0, "water", 1.0, signs), 320, 320, grid)
        _run(grid, [spell], 2.0)
        center = _amount_within(grid, "water", 320, 320, 45)
        ring = _amount_within(grid, "water", 320, 320, 150) - center
        self.assertGreater(center, ring)

    def test_spell_only_moves_its_own_element(self):
        grid = WorldGrid(640, 640)
        grid.add_disc("heat", 320, 320, 30, total=10.0)
        before = grid.fields["heat"].copy()
        spell = ActiveSpell(SpellSpec(120, 1.0, "water", 1.0, _ring("direction", 0.5, inward=False)), 320, 320, grid)
        flows = combine_flows(grid, [spell])
        self.assertEqual(set(flows), {"water"})
        grid.step(TICK_INTERVAL, flows)
        reference = WorldGrid(640, 640)
        reference.fields["heat"] = before
        reference.step(TICK_INTERVAL)
        np.testing.assert_allclose(grid.fields["heat"], reference.fields["heat"])

    def test_repetition_extends_only_its_band(self):
        grid = WorldGrid(640, 640)
        spell = ActiveSpell(SpellSpec(120, 1.0, "wind", 1.0, _ring("repetition", 0.8, count=6)), 320, 320, grid)
        outer = grid.cell_of(320, 320 - 0.8 * 120)
        self.assertGreater(spell.cell_duration[outer], spell.cell_duration[grid.cell_of(320, 320)])

    def test_release_spreads_element_after_spell_ends(self):
        grid = WorldGrid(640, 640)
        spells = [ActiveSpell(SpellSpec(120, 1.0, "water", 1.0, _ring("suspension", 0.15, size=0.4)), 320, 320, grid)]
        _run(grid, spells, spells[0].duration + TICK_INTERVAL)
        self.assertEqual(spells, [])
        held = _amount_within(grid, "water", 320, 320, 40)
        _run(grid, spells, 2.0)
        self.assertLess(_amount_within(grid, "water", 320, 320, 40), held)


class SpellMessageTests(unittest.TestCase):
    def test_spell_without_emblem_is_inert(self):
        with self.assertRaises(ValueError):
            parse_spell_message({"t": "s", "R": 100, "signs": []})

    def test_unknown_signs_are_dropped(self):
        spec = parse_spell_message({
            "t": "s", "R": 100, "e": "fire",
            "signs": [{"k": "traction", "r": 0.5, "a": 0, "o": 3.14}, {"k": "?", "r": 0.5, "a": 0, "o": 0}],
        })
        self.assertEqual([s.kind for s in spec.signs], ["traction"])

    def test_power_grows_with_circle_area(self):
        small = parse_spell_message({"R": 50, "e": "fire"})
        large = parse_spell_message({"R": 100, "e": "fire"})
        self.assertAlmostEqual(large.power / small.power, 4.0)


class WorldInGameTests(unittest.TestCase):
    def _instance(self) -> GameInstance:
        world = GameInstance("test", {"size": [960, 960]}, None)
        world.players["mage"] = Player("mage", 480, 480)
        return world

    def test_cast_is_centered_on_the_mage(self):
        world = self._instance()
        spell = world.add_spell_cast_from_spec("mage", {"t": "s", "R": 80, "e": "water"})
        self.assertEqual((spell.x, spell.y), (480.0, 480.0))
        self.assertGreater(world.world_grid.total("water"), 0.0)

    def test_wind_pushes_light_body_more_than_heavy_one(self):
        world = self._instance()
        light = Entity("light", "crystal", EntityBody(x=480, y=420, mass=1.0, radius=10))
        heavy = Entity("heavy", "crystal", EntityBody(x=480, y=540, mass=5.0, radius=10))
        world.entities = [light, heavy]
        signs = [
            {"k": "direction", "r": 0.5, "a": -math.pi / 2, "o": -math.pi / 2, "s": 0.4, "q": 1.0},
            {"k": "direction", "r": 0.5, "a": math.pi / 2, "o": math.pi / 2, "s": 0.4, "q": 1.0},
        ]
        world.add_spell_cast_from_spec("mage", {"t": "s", "R": 120, "e": "wind", "signs": signs})
        for _ in range(20):
            world._world_system.tick(world, TICK_INTERVAL, 0.0)
            world._physics_system.tick(world, TICK_INTERVAL, 0.0)
        self.assertLess(light.body.y, 420)       # pousse vers le haut, loin du centre
        self.assertGreater(heavy.body.y, 540)    # pousse vers le bas
        self.assertGreater(420 - light.body.y, heavy.body.y - 540)

    def test_spell_without_living_mage_is_ignored(self):
        world = self._instance()
        self.assertIsNone(world.add_spell_cast_from_spec("ghost", {"t": "s", "R": 80, "e": "water"}))


if __name__ == "__main__":
    unittest.main()
