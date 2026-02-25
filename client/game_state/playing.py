import pygame

from client.entities.magical_draw import MagicalDraw
from client.entities.player import IN_BOARD, IN_DRAWING


def playing(game, tick_rate):
    if game.start_time is None:
        game.start_time = pygame.time.get_ticks()

    current_time = pygame.time.get_ticks() / 1000.0

    inp = game.player.read_local_input()
    inp["seq"] = game.input_seq
    game.input_seq += 1

    if inp.get("k") & IN_BOARD:
        if inp.get("k") & IN_DRAWING:
            game.player.magical_board.add_point(pygame.mouse.get_pos())
        else:
            game.player.magical_board.validate_points_to_board()

    if game.net_connected and game.net is not None:
        msg = {"t": "in", "seq": inp["seq"], "k": inp["k"]}
        if game.last_sid_ack is not None:
            msg["ack"] = game.last_sid_ack
        game.net.send(msg)

    game.player.apply_input(inp)
    game.player.save_input_for_reconciliation(inp)
    game.player.update(tick_rate)

    game.game_manager.update_all(tick_rate, game.player, current_time)