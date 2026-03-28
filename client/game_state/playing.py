import pygame

from client.entities.player import IN_BOARD, IN_DRAWING


def playing(game, tick_rate):
    if game.start_time is None:
        game.start_time = pygame.time.get_ticks()

    current_time = pygame.time.get_ticks() / 1000.0

    inp = game.player.read_local_input()
    inp["seq"] = game.input_seq
    game.input_seq += 1

    board_pressed = bool(inp.get("k") & IN_BOARD)
    drawing_pressed = bool(inp.get("k") & IN_DRAWING)

    if board_pressed:
        game.player.magical_draw.cancel_clear()
        if drawing_pressed:
            game.player.magical_draw.add_point(pygame.mouse.get_pos(), current_time)
        else:
            game.player.magical_draw.validate_points_to_board()
    elif game.prev_board_pressed:
        game.player.magical_draw.validate_points_to_board()
        primitives = game.geometry_analyzer.analyze(game.player.magical_draw.get_strokes())
        has_primitive = False
        if primitives:
            if isinstance(primitives, list):
                for primitive in primitives:
                    game.player.magical_draw.add_node(primitive)
                has_primitive = len(primitives) > 0
            else:
                game.player.magical_draw.add_node(primitives)
                has_primitive = True

        if has_primitive:
            # Dès qu'une primitive est reconnue, on retire les traits bruts.
            game.player.magical_draw.clear_board()
            game.player.magical_draw.cancel_clear()
        else:
            game.player.magical_draw.schedule_clear(current_time)

    game.prev_board_pressed = board_pressed

    if game.net_connected and game.net is not None:
        msg = {"t": "in", "seq": inp["seq"], "k": inp["k"]}
        if game.last_sid_ack is not None:
            msg["ack"] = game.last_sid_ack
        game.net.send(msg)

    game.player.apply_input(inp)
    game.player.save_input_for_reconciliation(inp)
    game.player.update(tick_rate)

    game.game_manager.update_all(tick_rate, game.player, current_time)
