from abc import ABC, abstractmethod


class Damagable(ABC):
    """Contrat commun pour les entités qui ont des points de vie."""

    @abstractmethod
    def on_death(self):
        """Hook appelé quand la vie atteint 0."""
        pass

    def take_damage(self, damage):
        remaining_health = self.life.lose_health(damage)
        if self.life.is_dead():
            self.on_death()
        return remaining_health

    def heal(self, amount):
        return self.life.heal(amount)
