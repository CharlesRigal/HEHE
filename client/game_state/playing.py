import pygame


def playing(game, tick_rate):
    if game.start_time is None:
        game.start_time = pygame.time.get_ticks()

    current_time = pygame.time.get_ticks() / 1000.0

    inp = game.player.read_local_input()
    sent = game.send_input_if_needed(inp)
    inp["seq"] = game.input_seq

    game.player.apply_input(inp, tick_rate)
    game.player.save_input_for_reconciliation(inp, tick_rate)

    game.game_manager.update_all(tick_rate, game.player, current_time)