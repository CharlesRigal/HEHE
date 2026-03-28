# game_manager.py
from client.core.game_object import GameObject
from client.entities.remote_enemy import RemoteEnemy
from client.entities.remote_player import RemotePlayer


class GameManager:
    """Gestionnaire universel d'objets de jeu"""

    def __init__(self):
        self.game_objects = []
        self.objects_to_add = []

    def add_object(self, game_object):
        """Ajouter un objet au gestionnaire"""
        if not isinstance(game_object, GameObject):
            raise TypeError("L'objet doit hériter de GameObject")

        if isinstance(game_object, RemotePlayer) and self.get_remote_player(game_object.player_id):
            return
        if isinstance(game_object, RemoteEnemy) and self.get_remote_enemy(game_object.enemy_id):
            return

        self.objects_to_add.append(game_object)

    def _all_objects(self):
        # Inclut les objets en attente d'ajout pour éviter les doublons réseau
        return self.game_objects + self.objects_to_add

    def remove_object(self, game_object):
        """Marquer un objet pour suppression"""
        if game_object is not None:
            game_object.mark_for_removal()

    def update_all(self, dt, *args, **kwargs):
        """Mettre à jour tous les objets actifs"""
        # Ajouter les nouveaux objets
        self.game_objects.extend(self.objects_to_add)
        self.objects_to_add.clear()

        for obj in self.game_objects:
            if obj.active:
                obj.update(dt, *args, **kwargs)

        self.game_objects = [obj for obj in self.game_objects if not obj.to_remove]

    def draw_all(self, screen, camera=None):
        for obj in self.game_objects:
            if obj.active:
                obj.draw(screen, camera)

    def get_objects_by_type(self, object_type):
        """Récupérer tous les objets d'un type donné"""
        return [obj for obj in self.game_objects
                if isinstance(obj, object_type) and obj.active]

    def get_objects_by_type_including_pending(self, object_type):
        return [obj for obj in self._all_objects()
                if isinstance(obj, object_type) and obj.active]

    def get_object_count(self):
        """Nombre total d'objets actifs"""
        return len([obj for obj in self.game_objects if obj.active])

    def get_remote_player(self, player_id):
        for remote_player in self.get_objects_by_type_including_pending(RemotePlayer):
            if remote_player.player_id == player_id:
                return remote_player
        return None

    def get_remote_enemy(self, enemy_id):
        for remote_enemy in self.get_objects_by_type_including_pending(RemoteEnemy):
            if remote_enemy.enemy_id == enemy_id:
                return remote_enemy
        return None
