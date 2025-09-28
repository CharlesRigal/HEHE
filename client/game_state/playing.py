import pygame


def playing(game, dt=None):
    game.map_renderer.draw(game.screen)
    if game.start_time is None:
        game.start_time = pygame.time.get_ticks()

    elapsed = (pygame.time.get_ticks() - game.start_time) / 1000
    current_time = pygame.time.get_ticks() / 1000.0

    inp = game.player.read_local_input()
    game.player.apply_input(inp, dt)
    game.send_input_if_needed(inp)

    # Mettre à jour tous les objets gérés
    game.game_manager.update_all(dt, game.player, current_time)

    # Vérifier les collisions
    game.check_collisions()