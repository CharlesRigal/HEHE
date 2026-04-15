"""
playing.py — Boucle de jeu principale.

Sorts disponibles (hardcodé) :
    Cercle seul  →  Boule de feu vers la direction du joueur.
"""
import math

import pygame

from client.entities.player import IN_BOARD, IN_DRAWING
from client.magic.primitives import Circle


# ---------------------------------------------------------------------------
# Patterns hardcodés — (condition) → spec réseau
# ---------------------------------------------------------------------------

def _fireball_spec(game) -> dict:
    """Boule de feu simple dans la direction du joueur."""
    facing = None
    if hasattr(game.player, "get_facing_vector"):
        try:
            facing = game.player.get_facing_vector()
        except Exception:
            pass

    if facing is not None and hasattr(facing, "x"):
        dx, dy = float(facing.x), float(facing.y)
    else:
        dx, dy = 1.0, 0.0

    mag = math.hypot(dx, dy)
    if mag > 1e-6:
        dx /= mag
        dy /= mag

    return {
        "t":   "s",
        "e":   "fire",
        "bh":  "projectile",
        "spd": 0.4,
        "pwr": 1.0,
        "dir": [round(dx, 4), round(dy, 4)],
    }


def _match_pattern(primitives: list) -> dict | None:
    """
    Retourne le spec réseau si un pattern est reconnu, None sinon.

    Patterns :
        Cercle  →  boule de feu
    """
    types = {type(p) for p in primitives}
    if Circle in types:
        return "fireball"
    return None


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def playing(game, tick_rate):
    if game.start_time is None:
        game.start_time = pygame.time.get_ticks()

    current_time = pygame.time.get_ticks() / 1000.0

    inp = game.player.read_local_input()
    inp["seq"] = game.input_seq
    game.input_seq += 1

    board_pressed  = bool(inp.get("k") & IN_BOARD)
    drawing_pressed = bool(inp.get("k") & IN_DRAWING)

    if board_pressed:
        game.player.magical_draw.cancel_clear()
        if drawing_pressed:
            game.player.magical_draw.add_point(
                pygame.mouse.get_pos(),
                current_time,
                pressure=inp.get("pressure"),
            )
        else:
            game.player.magical_draw.validate_points_to_board()

    elif game.prev_board_pressed:
        game.player.magical_draw.validate_points_to_board()
        primitives = game.geometry_analyzer.analyze(game.player.magical_draw.get_strokes())

        primitives_list = []
        if primitives:
            if isinstance(primitives, list):
                for p in primitives:
                    game.player.magical_draw.add_node(p)
                primitives_list = primitives
            else:
                game.player.magical_draw.add_node(primitives)
                primitives_list = [primitives]

        if primitives_list:
            pattern = _match_pattern(primitives_list)

            if pattern == "fireball":
                spec = _fireball_spec(game)
                game.cast_spell(spec)

            game.player.magical_draw.clear_board()
            game.player.magical_draw.cancel_clear()
        else:
            game.player.magical_draw.schedule_clear(current_time)

    game.prev_board_pressed = board_pressed

    game.send_input_if_needed(inp)
    game.player.apply_input(inp)
    game.player.save_input_for_reconciliation(inp)
    game.player.update(tick_rate)
    game.game_manager.update_all(tick_rate, game.player, current_time)
