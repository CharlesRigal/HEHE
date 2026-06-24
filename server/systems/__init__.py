"""Systems : iterent sur un sous-ensemble d'entites selon leurs composants.

Contrat : chaque System expose `tick(world, dt, now)`. `world` est un objet
avec au moins un attribut `entities: list[Entity]` et `players: dict[str, Player]`.
Ordre conseille (appele par GameInstance.game_loop) :

  1. EnemyAISystem       (lit les players, calcule intent + vx/vy des ennemis)
  2. MovementSystem      (integre EntityBody non static)
  3. EffectTickSystem    (tick_all + detect_reactions)
  4. ProximitySystem     (reactions entite-entite par distance : altar, etc.)

L'ordre importe : les ennemis decident -> bougent -> subissent les effets
-> puis les reactions de proximite lisent les positions finales du frame.
"""
from server.systems.enemy_ai_system import EnemyAISystem
from server.systems.movement_system import MovementSystem
from server.systems.effect_tick_system import EffectTickSystem
from server.systems.proximity_system import ProximitySystem

__all__ = [
    "EnemyAISystem",
    "MovementSystem",
    "EffectTickSystem",
    "ProximitySystem",
]
