import pygame


def playing(game, dt=None):
    game.map_renderer.draw(game.screen)
    if game.start_time is None:
        game.start_time = pygame.time.get_ticks()

    elapsed = (pygame.time.get_ticks() - game.start_time) / 1000
    current_time = pygame.time.get_ticks() / 1000.0

    # ===== CLIENT-SIDE PREDICTION =====
    # 1. Lire l'input local
    inp = game.player.read_local_input()

    # 2. Ajouter le numéro de séquence
    inp["seq"] = game.input_seq

    # 3. Appliquer immédiatement localement (prédiction)
    game.player.apply_input(inp, dt)

    # 4. Sauvegarder pour réconciliation future
    game.player.save_input_for_reconciliation(inp, dt)

    # 5. Envoyer au serveur
    game.send_input_if_needed(inp)

    # 6. Incrémenter le séquence
    game.input_seq += 1

    # Mettre à jour tous les objets gérés (ennemis, projectiles, etc.)
    game.game_manager.update_all(dt, game.player, current_time)