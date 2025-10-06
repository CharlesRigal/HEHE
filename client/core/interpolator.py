import pygame

class Interpolator:
    def __init__(self, start_pos: pygame.Vector2, speed: float = 10.0):
        self.current = start_pos.copy()
        self.target = start_pos.copy()
        self.speed = speed  # pixels par seconde

    def set_target(self, new_target: pygame.Vector2):
        self.target = new_target.copy()

    def update(self, dt: float):
        direction = self.target - self.current
        distance = direction.length()

        if distance > 0:
            # Limite la vitesse pour éviter les overshoots
            max_step = self.speed * dt
            if distance > max_step:
                direction.scale_to_length(max_step)
            self.current += direction

        return self.current
