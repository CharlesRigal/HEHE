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
            import time
            from client.magic.resolver.resolved_spell import params_to_network_spec
            from client.ui.spell_debug_overlay import SpellDebugData
            ast = game.ast_builder.build(game.player.magical_draw._magical_graph)
            resolved = game.ast_resolver.resolve(ast)
            net_spec = params_to_network_spec(resolved)
            game.cast_ast_spell(net_spec)

            debug_data = SpellDebugData(
                primitives=list(primitives) if isinstance(primitives, list) else [primitives],
                spatial_relations=list(ast.spatial_relations),
                ast=ast,
                pass1_bags=dict(game.ast_resolver.last_pass1_bags),
                pass2_bags=dict(game.ast_resolver.last_pass2_bags),
                cross_entries=list(game.ast_resolver.last_cross_entries),
                resolved_params=dict(resolved.params),
                network_spec=dict(net_spec),
                timestamp=time.time(),
            )
            game.spell_debug_overlay.set_data(debug_data)
            game.spell_logger.log_cast(debug_data)

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
