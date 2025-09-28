# game_manager.py
from client.core.game_object import GameObject
from client.entities.remote_player import RemotePlayer


class GameManager:
    """Gestionnaire universel d'objets de jeu"""

    def __init__(self):
        self.game_objects = []
        self.objects_to_add = []  # Buffer pour les nouveaux objets

    def add_object(self, game_object):
        """Ajouter un objet au gestionnaire"""
        if isinstance(game_object, GameObject):
            self.objects_to_add.append(game_object)
        else:
            raise TypeError("L'objet doit hériter de GameObject")

    def remove_object(self, game_object):
        """Marquer un objet pour suppression"""
        game_object.mark_for_removal()

    def update_all(self, dt, *args, **kwargs):
        """Mettre à jour tous les objets actifs"""
        # Ajouter les nouveaux objets
        self.game_objects.extend(self.objects_to_add)
        self.objects_to_add.clear()


        # Mettre à jour tous les objets actifs
        for obj in self.game_objects:
            if isinstance(obj, RemotePlayer):
                pass
            if obj.active:
                obj.update(dt, *args, **kwargs)

        # Nettoyer les objets marqués pour suppression
        self.game_objects = [obj for obj in self.game_objects if not obj.to_remove]

    def draw_all(self, screen):
        """Dessiner tous les objets actifs"""
        for obj in self.game_objects:
            if obj.active:
                obj.draw(screen)

    def get_objects_by_type(self, object_type):
        """Récupérer tous les objets d'un type donné"""
        return [obj for obj in self.game_objects
                if isinstance(obj, object_type) and obj.active]

    def get_object_count(self):
        """Nombre total d'objets actifs"""
        return len([obj for obj in self.game_objects if obj.active])

    def get_remote_player(self, player_id):
        for remote_player in self.get_objects_by_type(RemotePlayer):
            if remote_player.player_id == player_id:
                return remote_player
        return None