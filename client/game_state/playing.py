import pygame

from client.entities.player import IN_BOARD, IN_DRAWING
#from client.ui.live_prediction_overlay import try_compute_prediction


# Throttle : ~10 Hz de prediction live (suffisant pour un feedback visuel fluide)
_PREDICTION_THROTTLE_FRAMES = 6


def playing(game, tick_rate):
    if game.start_time is None:
        game.start_time = pygame.time.get_ticks()

    current_time = pygame.time.get_ticks() / 1000.0

    inp = game.player.read_local_input()
    inp["seq"] = game.input_seq
    game.input_seq += 1

    game.send_input_if_needed(inp)

    game.player.apply_input(inp)
    game.player.save_input_for_reconciliation(inp)
    game.player.update(tick_rate)

    # player change maps ptdr t'as pas le droit de faire ça la ... du moins je pense comme je fini dans ma boucle de logique et forcement ça quoince je ne suis plus en playing
    

    game.game_manager.update_all(tick_rate, game.player, current_time)
