"""Scenarios deterministes couvrant les regles essentielles du jeu.

Ces tests ne demarrent ni fenetre pygame ni serveur websocket : ils testent
la simulation autoritaire qui decide du deplacement, des combats et puzzles.
"""
from __future__ import annotations

import unittest
from collections import deque
import math
import statistics
import time

from server.config import PLAYER_SPEED, TICK_INTERVAL
from server.entities.components import EnemyAI, Entity, EntityBody, EntityCombat
from server.entities.interactive import apply_state_change_to_entity, build_entity, entity_public_state
from server.game_instance import GameInstance
from server.players.player import Player
from server.systems.enemy_ai_system import EnemyAISystem
from server.systems.movement_system import MovementSystem
from server.systems.proximity_system import ProximitySystem


class GameplayTests(unittest.TestCase):
    def test_player_damage_stops_input_at_death(self):
        player = Player("mage", 10, 10, health=25, max_health=100)

        self.assertFalse(player.take_damage(24))
        self.assertEqual(player.health, 1)
        self.assertTrue(player.is_alive())
        self.assertTrue(player.take_damage(1))
        self.assertFalse(player.can_receive_input())
        self.assertEqual(player.health, 0)

    def test_input_sequence_rejects_stale_movement(self):
        world = GameInstance("test", {"size": [500, 500]}, None)
        player = Player("mage", 100, 100)

        world.process_input(player, {"seq": 2, "k": 8})  # droite
        x_after_new_input = player.x
        world.process_input(player, {"seq": 1, "k": 4})  # gauche, trop ancien

        self.assertGreater(x_after_new_input, 100)
        self.assertEqual(player.x, x_after_new_input)
        self.assertEqual(player.last_input_seq, 2)

    def test_player_cannot_cross_map_object(self):
        wall = {"points": [[110, 0], [130, 0], [130, 500], [110, 500]]}
        world = GameInstance("test", {"size": [500, 500], "objects": [wall]}, None)
        player = Player("mage", 95, 100)

        world.process_input(player, {"seq": 1, "k": 8})

        self.assertEqual(player.position(), (95.0, 100.0))
        self.assertFalse(player.is_moving())

    def test_player_movement_is_smooth_and_diagonal_speed_is_normalized(self):
        """Chaque tick produit un pas identique : pas de teleportation ni d'acceleration."""
        world = GameInstance("test", {"size": [5000, 5000]}, None)
        player = Player("mage", 1000, 1000)
        expected_step = PLAYER_SPEED * TICK_INTERVAL

        positions = []
        for seq in range(1, 11):
            world.process_input(player, {"seq": seq, "k": 8})  # droite
            positions.append(player.x)

        steps = [after - before for before, after in zip(positions, positions[1:])]
        self.assertTrue(all(abs(step - expected_step) < 1e-9 for step in steps))
        self.assertAlmostEqual(positions[-1] - 1000, expected_step * 10)

        diagonal = Player("diagonal", 1000, 1000)
        world.process_input(diagonal, {"seq": 1, "k": 2 | 8})  # bas-droite
        diagonal_distance = ((diagonal.x - 1000) ** 2 + (diagonal.y - 1000) ** 2) ** 0.5
        self.assertAlmostEqual(diagonal_distance, expected_step)

    def test_player_stays_inside_each_map_edge(self):
        world = GameInstance("test", {"size": [100, 100]}, None)
        half_hitbox = world.player_collision_size / 2
        cases = (
            ("left", (half_hitbox, 50), 4),
            ("right", (100 - half_hitbox, 50), 8),
            ("top", (50, half_hitbox), 1),
            ("bottom", (50, 100 - half_hitbox), 2),
        )

        for name, (x, y), key in cases:
            with self.subTest(edge=name):
                player = Player(name, x, y)
                world.process_input(player, {"seq": 1, "k": key})
                self.assertGreaterEqual(player.x, half_hitbox)
                self.assertLessEqual(player.x, 100 - half_hitbox)
                self.assertGreaterEqual(player.y, half_hitbox)
                self.assertLessEqual(player.y, 100 - half_hitbox)
                self.assertFalse(player.is_moving())

    def test_player_cannot_cut_through_an_obstacle_corner(self):
        block = {"points": [[110, 110], [150, 110], [150, 150], [110, 150]]}
        world = GameInstance("test", {"size": [500, 500], "objects": [block]}, None)
        player = Player("mage", 97, 97)

        world.process_input(player, {"seq": 1, "k": 2 | 8})

        self.assertEqual(player.position(), (97.0, 97.0))
        self.assertFalse(player.is_moving())

    def test_invalid_or_duplicate_input_sequences_are_ignored(self):
        world = GameInstance("test", {"size": [500, 500]}, None)
        player = Player("mage", 100, 100)
        world.process_input(player, {"seq": 3, "k": 8})
        accepted_position = player.position()

        for invalid_input in (
            {"k": 4},
            {"seq": None, "k": 4},
            {"seq": "not-a-number", "k": 4},
            {"seq": -1, "k": 4},
            {"seq": 3, "k": 4},
            {"seq": 2, "k": 4},
        ):
            world.process_input(player, invalid_input)
            self.assertEqual(player.position(), accepted_position)
            self.assertEqual(player.last_input_seq, 3)

    def test_input_processing_is_limited_per_tick(self):
        world = GameInstance("test", {"size": [5000, 5000]}, None)
        player = Player("mage", 1000, 1000)
        world.players[player.id] = player
        world.pending_inputs[player.id] = deque(
            {"seq": sequence, "k": 8}
            for sequence in range(1, GameInstance.MAX_INPUTS_PER_TICK + 2)
        )

        world._process_pending_inputs()

        self.assertEqual(world.inputs_processed, GameInstance.MAX_INPUTS_PER_TICK)
        self.assertEqual(player.last_input_seq, GameInstance.MAX_INPUTS_PER_TICK)
        self.assertEqual(len(world.pending_inputs[player.id]), 1)

    def test_enemy_state_limits_and_attack_cooldown(self):
        class World:
            map_data = {"size": [1000, 1000]}
            player_attack_hurtbox_w = 18.0
            player_attack_hurtbox_h = 18.0
            def _check_collision_with_objects(self, x, y, size):
                return False

        world = World()
        player = Player("mage", 100, 100)
        world.players = {player.id: player}
        enemy = Entity(
            "enemy", "enemy", EntityBody(x=100, y=100),
            combat=EntityCombat(), ai=EnemyAI(attack_cooldown=1.1),
        )
        world.entities = [enemy]
        system = EnemyAISystem()

        enemy.states.set("frozen", True)
        system.tick(world, TICK_INTERVAL, 1.09)
        self.assertEqual(enemy.body.velocity_x, 0)
        self.assertEqual(player.health, 100)

        enemy.states.set("frozen", False)
        enemy.states.set("speed_multiplier", 0.0)
        system.tick(world, TICK_INTERVAL, 1.09)
        self.assertEqual(enemy.body.velocity_x, 0)

        enemy.states.set("speed_multiplier", 0.01)
        player.set_motion(x=500, y=100, vx=0, vy=0)
        system.tick(world, TICK_INTERVAL, 1.09)
        self.assertGreater(enemy.body.velocity_x, 0)

        player.set_motion(x=100, y=100, vx=0, vy=0)
        enemy.states.set("speed_multiplier", 1.0)
        system.tick(world, TICK_INTERVAL, 1.1)
        self.assertEqual(player.health, 88)
        system.tick(world, TICK_INTERVAL, 2.19)
        self.assertEqual(player.health, 88)
        system.tick(world, TICK_INTERVAL, 2.2)
        self.assertEqual(player.health, 76)

    def test_proximity_activates_at_exact_effective_radius(self):
        class World:
            def _on_entity_state_changed(self, entity):
                pass

        altar = build_entity({"id": "altar", "type": "altar", "position": [100, 100], "radius": 20})
        crystal = build_entity({"id": "crystal", "type": "crystal", "position": [140, 100], "radius": 16})
        world = World()
        world.entities = [altar, crystal]

        ProximitySystem().tick(world, TICK_INTERVAL, 0)

        self.assertTrue(altar.states.get("powered"))

    def test_multiplayer_reordered_packets_keep_each_player_consistent(self):
        world = GameInstance("test", {"size": [1000, 1000]}, None)
        first = Player("first", 100, 100)
        second = Player("second", 300, 300)
        world.players = {first.id: first, second.id: second}

        # Le paquet seq=1 de first arrive apres seq=2 : il doit etre ignore.
        world.add_input(first.id, {"seq": 2, "k": 8})
        world.add_input(first.id, {"seq": 1, "k": 4})
        world.add_input(second.id, {"seq": 1, "k": 1})
        world.add_input(second.id, {"seq": 2, "k": 8})
        world._process_pending_inputs()

        step = PLAYER_SPEED * TICK_INTERVAL
        self.assertEqual(first.last_input_seq, 2)
        self.assertAlmostEqual(first.x, 100 + step)
        self.assertEqual(second.last_input_seq, 2)
        self.assertAlmostEqual(second.x, 300 + step)
        self.assertAlmostEqual(second.y, 300 - step)

    def test_ten_minutes_of_simulation_stays_finite_and_in_bounds(self):
        """Test de stabilite deterministe : 36 000 ticks a 60 Hz, sans attente reelle."""
        world = GameInstance("stability", {"size": [800, 600]}, None)
        left_player = Player("left", 100, 300)
        right_player = Player("right", 700, 300)
        world.players = {left_player.id: left_player, right_player.id: right_player}
        enemy = Entity(
            "enemy", "enemy", EntityBody(x=400, y=300, radius=12),
            combat=EntityCombat(), ai=EnemyAI(speed=180),
        )
        world.entities.append(enemy)

        for tick in range(1, 36_001):
            # Les deux joueurs essaient alternativement de sortir de la carte;
            # les clamps sont donc exerces pendant toute la simulation.
            world.process_input(left_player, {"seq": tick, "k": 4 if tick % 2 else 8})
            world.process_input(right_player, {"seq": tick, "k": 8 if tick % 2 else 4})
            now = tick * TICK_INTERVAL
            world._enemy_ai_system.tick(world, TICK_INTERVAL, now)
            world._movement_system.tick(world, TICK_INTERVAL, now)
            world._proximity_system.tick(world, TICK_INTERVAL, now)

        for player in world.players.values():
            self.assertTrue(math.isfinite(player.x) and math.isfinite(player.y))
            self.assertGreaterEqual(player.x, world.player_collision_size / 2)
            self.assertLessEqual(player.x, 800 - world.player_collision_size / 2)
            self.assertGreaterEqual(player.y, world.player_collision_size / 2)
            self.assertLessEqual(player.y, 600 - world.player_collision_size / 2)
        self.assertTrue(math.isfinite(enemy.body.x) and math.isfinite(enemy.body.y))
        self.assertGreaterEqual(enemy.body.x, enemy.body.radius)
        self.assertLessEqual(enemy.body.x, 800 - enemy.body.radius)

    def test_server_tick_p95_fits_the_frame_budget(self):
        """Alerte si la logique serveur seule depasse le budget d'un tick a 60 Hz."""
        world = GameInstance("performance", {"size": [800, 600]}, None)
        player = Player("mage", 100, 300)
        world.players = {player.id: player}
        world.entities.append(Entity(
            "enemy", "enemy", EntityBody(x=400, y=300, radius=12),
            combat=EntityCombat(), ai=EnemyAI(speed=180),
        ))
        durations = []

        for tick in range(300):
            start = time.perf_counter()
            now = tick * TICK_INTERVAL
            world._enemy_ai_system.tick(world, TICK_INTERVAL, now)
            world._movement_system.tick(world, TICK_INTERVAL, now)
            world._effect_tick_system.tick(world, TICK_INTERVAL, now)
            world._proximity_system.tick(world, TICK_INTERVAL, now)
            durations.append(time.perf_counter() - start)

        p95 = statistics.quantiles(durations, n=100)[94]
        self.assertLess(
            p95,
            TICK_INTERVAL,
            f"p95 de tick {p95 * 1000:.2f} ms > budget {TICK_INTERVAL * 1000:.2f} ms",
        )

    def test_enemy_moves_once_per_simulation_tick(self):
        class World:
            map_data = {"size": [1000, 1000]}
            player_attack_hurtbox_w = 18.0
            player_attack_hurtbox_h = 18.0
            def _check_collision_with_objects(self, x, y, size):
                return False

        world = World()
        world.players = {"mage": Player("mage", 500, 100)}
        enemy = Entity(
            id="enemy", type="enemy",
            body=EntityBody(x=100, y=100, radius=12),
            combat=EntityCombat(), ai=EnemyAI(speed=180),
        )
        world.entities = [enemy]

        EnemyAISystem().tick(world, TICK_INTERVAL, now=10.0)
        MovementSystem().tick(world, TICK_INTERVAL, now=10.0)

        self.assertAlmostEqual(enemy.body.x, 100 + 180 * TICK_INTERVAL)
        self.assertEqual(enemy.body.y, 100)
        self.assertGreater(enemy.body.velocity_x, 0)

    def test_enemy_is_blocked_by_terrain(self):
        class World:
            map_data = {"size": [1000, 1000]}
            player_attack_hurtbox_w = 18.0
            player_attack_hurtbox_h = 18.0
            def _check_collision_with_objects(self, x, y, size):
                return True

        world = World()
        world.players = {"mage": Player("mage", 500, 100)}
        enemy = Entity("enemy", "enemy", EntityBody(x=100, y=100), combat=EntityCombat(), ai=EnemyAI())
        world.entities = [enemy]

        EnemyAISystem().tick(world, TICK_INTERVAL, now=10.0)

        self.assertEqual(enemy.body.velocity_x, 0)
        self.assertEqual((enemy.body.x, enemy.body.y), (100, 100))

    def test_fire_lights_torch_only_above_threshold(self):
        torch = build_entity({"id": "torch", "type": "torch", "position": [10, 10]})

        self.assertFalse(apply_state_change_to_entity(torch, "fire", 0.05))
        self.assertTrue(apply_state_change_to_entity(torch, "fire", 0.2))
        self.assertTrue(torch.states.get("lit"))
        self.assertNotIn("_reactions", entity_public_state(torch)["state"])

    def test_crystal_proximity_powers_and_unpowers_altar(self):
        class World:
            entities = []
            def __init__(self):
                self.changed = []
            def _on_entity_state_changed(self, entity):
                self.changed.append(entity.id)

        world = World()
        altar = build_entity({"id": "altar", "type": "altar", "position": [100, 100], "radius": 20})
        crystal = build_entity({"id": "crystal", "type": "crystal", "position": [300, 100], "radius": 16})
        world.entities = [altar, crystal]
        system = ProximitySystem()

        system.tick(world, TICK_INTERVAL, 0)
        self.assertFalse(altar.states.get("powered"))
        crystal.body.x = 130
        system.tick(world, TICK_INTERVAL, 0)
        self.assertTrue(altar.states.get("powered"))
        crystal.body.x = 300
        system.tick(world, TICK_INTERVAL, 0)
        self.assertFalse(altar.states.get("powered"))
        self.assertEqual(world.changed, ["altar", "altar"])


if __name__ == "__main__":
    unittest.main()
