import pygame

class Interpolator:
    def __init__(self, start_pos: pygame.Vector2, speed: float = 0.1):
        self.current = start_pos
        self.target = start_pos
        self.speed = speed

    def set_target(self, new_target: pygame.Vector2):
        self.target = new_target

    def update(self, dt: float):
        # interpolation linéaire
        self.current.x += (self.target.x - self.current.x) * self.speed * dt
        self.current.y += (self.target.y - self.current.y) * self.speed * dt
        return self.current
