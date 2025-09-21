class Life:
    def __init__(self, life_max):
        self.life_max = life_max
        self.life_current = life_max  # Vie actuelle séparée de la vie max

    def lose_health(self, damage_amount):
        """Fait perdre de la vie"""
        if damage_amount < 0:
            raise ValueError("Les dégâts ne peuvent pas être négatifs")

        self.life_current -= damage_amount
        if self.life_current < 0:
            self.life_current = 0

        return self.life_current  # Retourne la vie restante

    def heal(self, heal_amount):
        """Soigne l'entité"""
        if heal_amount < 0:
            raise ValueError("Les soins ne peuvent pas être négatifs")

        self.life_current += heal_amount
        if self.life_current > self.life_max:
            self.life_current = self.life_max

        return self.life_current

    def is_dead(self):
        """Vérifie si l'entité est morte"""
        return self.life_current <= 0

    def is_full_health(self):
        """Vérifie si l'entité a toute sa vie"""
        return self.life_current >= self.life_max

    def get_health_percentage(self):
        """Retourne le pourcentage de vie (utile pour les barres de vie)"""
        if self.life_max == 0:
            return 0
        return (self.life_current / self.life_max) * 100

    def reset_health(self):
        """Remet la vie au maximum"""
        self.life_current = self.life_max

    def set_max_health(self, new_max):
        """Change la vie maximum (pour les upgrades par exemple)"""
        ratio = self.life_current / self.life_max if self.life_max > 0 else 1
        self.life_max = new_max
        self.life_current = min(new_max, self.life_current)  # Garde la vie actuelle ou la cap au nouveau max

    def __str__(self):
        """Pour le debugging"""
        return f"Life: {self.life_current}/{self.life_max}"

    def __repr__(self):
        return f"Life(current={self.life_current}, max={self.life_max})"

    def get_health(self):
        return  self.life_current

    def get_max_health(self):
        return self.life_max