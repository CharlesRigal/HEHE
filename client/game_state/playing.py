import pygame


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

    game.game_manager.update_all(tick_rate, game.player, current_time)