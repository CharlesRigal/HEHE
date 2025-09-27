import pygame


class MapRenderer:
    """Gestion du rendu, collisions et informations d'une map"""

    def __init__(self):
        self.current_map = None
        self.map_surface = None
        self.collision_objects = []

    # --- Chargement ---
    def load_map(self, map_data: dict):
        """Charge une map complète"""
        self.current_map = map_data
        self.collision_objects = map_data.get("objects", [])
        self._prepare_map_surface()

    def _prepare_map_surface(self):
        """Crée une surface pygame avec tous les objets statiques"""
        if not self.current_map:
            return

        size = self.current_map.get("size", [1280, 720])
        self.map_surface = pygame.Surface(size, pygame.SRCALPHA)

        for obj in self.collision_objects:
            self._draw_object(obj)

    def _draw_object(self, obj: dict):
        """Dessine un objet unique"""
        points = obj.get("points", [])
        if len(points) < 3:
            return

        obj_type = obj.get("type", "default")
        color = self._get_color(obj_type)

        pygame.draw.polygon(self.map_surface, color, points)
        border = tuple(max(0, c - 50) for c in color)
        pygame.draw.polygon(self.map_surface, border, points, 2)

    def _get_color(self, obj_type: str):
        palette = {
            "rock": (100, 100, 100),
            "tree": (34, 139, 34),
            "water": (30, 144, 255),
            "wall": (139, 69, 19),
            "default": (128, 128, 128),
        }
        return palette.get(obj_type, palette["default"])

    # --- Rendu ---
    def draw(self, screen: pygame.Surface, camera_offset=(0, 0)):
        if self.map_surface:
            screen.blit(self.map_surface, camera_offset)

    def draw_debug(self, screen: pygame.Surface, font: pygame.font.Font):
        if not self.current_map:
            return

        y = 10
        debug_lines = [
            f"Map: {self.current_map.get('name', 'Unknown')}",
            f"Size: {self.current_map.get('size', [0,0])[0]}x{self.current_map.get('size', [0,0])[1]}",
            f"Objects: {len(self.collision_objects)}",
        ]

        for line in debug_lines:
            text = font.render(line, True, (255, 255, 255))
            screen.blit(text, (10, y))
            y += 25

    # --- Collisions ---
    def check_collision(self, x, y, size=32) -> bool:
        """Collision joueur (AABB)"""
        x1, x2 = x - size / 2, x + size / 2
        y1, y2 = y - size / 2, y + size / 2

        for obj in self.collision_objects:
            pts = obj.get("points", [])
            if len(pts) >= 4:
                xs, ys = zip(*pts)
                if (x1 < max(xs) and x2 > min(xs) and
                        y1 < max(ys) and y2 > min(ys)):
                    return True
        return False

    def get_spawn_points(self):
        return self.current_map.get("spawn_points", []) if self.current_map else []
