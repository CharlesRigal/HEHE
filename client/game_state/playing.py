import pygame

from client.entities.player import IN_BOARD, IN_DRAWING
from client.ui.live_prediction_overlay import try_compute_prediction


# Throttle : ~10 Hz de prediction live (suffisant pour un feedback visuel fluide)
_PREDICTION_THROTTLE_FRAMES = 6


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

        # Phase 6 : recalcule la prediction live, throttle.
        game._prediction_frame_counter += 1
        if game._prediction_frame_counter >= _PREDICTION_THROTTLE_FRAMES:
            game._prediction_frame_counter = 0
            strokes = game.player.magical_draw.get_strokes()
            game.live_prediction.update(try_compute_prediction(game, strokes))
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

            # Phase 7 : memorise les params pour sauvegarde dans le grimoire (touche S).
            game._last_resolved_params = dict(resolved.params)

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
            game.live_prediction.clear()
        else:
            game.player.magical_draw.schedule_clear(current_time)
            game.live_prediction.clear()

    if not board_pressed and game.prev_board_pressed:
        # Releve de la planche : on efface le feedback live.
        game.live_prediction.clear()

    game.prev_board_pressed = board_pressed

    game.send_input_if_needed(inp)

    game.player.apply_input(inp)
    game.player.save_input_for_reconciliation(inp)
    game.player.update(tick_rate)

    game.game_manager.update_all(tick_rate, game.player, current_time)
