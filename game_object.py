from abc import ABC, abstractmethod

class GameObject(ABC):
    """Interface que tous les objets du jeu doivent implémenter"""

    def __init__(self):
        self.active = True  # Pour marquer les objets à supprimer
        self.to_remove = False
        self.game_manager = None

    @abstractmethod
    def update(self, dt, *args, **kwargs):
        """Mise à jour obligatoire - chaque objet définit sa logique"""
        pass

    @abstractmethod
    def draw(self, screen):
        """Rendu obligatoire - chaque objet se dessine"""
        pass

    def set_game_manager(self, game_manager):
        self.game_manager = game_manager

    def mark_for_removal(self):
        """Marquer l'objet pour suppression au prochain cycle"""
        self.to_remove = True
        self.active = False