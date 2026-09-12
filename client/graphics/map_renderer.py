from importlib import resources
import logging
import pygame
import yaml


class MapRenderer:
    """Gestion du rendu, collisions et informations d'une map"""

    def __init__(self):
        self.current_map = None
        self.map_surface: pygame.Surface|None = None
        self.collision_objects = []


        # Charger la config sprites + backgrounds
        sprite_package = resources.files("client.assets")

        for sprite_list in sprite_package.iterdir():
            if sprite_list.is_file() and sprite_list.suffix in {".yaml", ".yml"}:
                file = yaml.safe_load(sprite_list.read_text())
                self.sprite_config = file.get("sprites", {})
                self.background_config = file.get("backgrounds", {})

        self.loaded_sprites = {}
        self.scaled_tiles = {}
        self.loaded_backgrounds = {}

    # --- Gestion sprites ---
    def _get_sprite(self, obj_type: str):
        conf = self.sprite_config.get(obj_type)
        if not conf:
            return None

        if "image" in conf:
            if obj_type not in self.loaded_sprites:
                asset_file = resources.files("client.assets.sprites") / conf["image"]
                try:
                    img = pygame.image.load(str(asset_file)).convert_alpha()
                except FileNotFoundError:
                    logging.warning(f"Sprite introuvable: {conf['image']}")
                    return None

                scale = conf.get("scale", 1.0)
                if scale != 1.0:
                    w, h = img.get_size()
                    img = pygame.transform.scale(img, (int(w * scale), int(h * scale)))

                self.loaded_sprites[obj_type] = img
                logging.info(f"Sprite chargé: {obj_type}")

            return self.loaded_sprites[obj_type]
        return None

    # --- Gestion backgrounds ---
    def _get_background(self, bg_name: str):
        # Les YAML de maps utilisent des identifiants numériques (1, 2),
        # tandis que les clés YAML de sprites sont des chaînes ("1", "2").
        bg_name = str(bg_name) if bg_name is not None else ""
        if not bg_name or bg_name not in self.background_config:
            return None

        if bg_name not in self.loaded_backgrounds:
            try:
                asset_file = resources.files("client.assets.backgrounds") / self.background_config[bg_name]
                img = pygame.image.load(str(asset_file)).convert()
            except FileNotFoundError:
                logging.warning(f"Background introuvable: {self.background_config[bg_name]}")
                return None

            self.loaded_backgrounds[bg_name] = img
            logging.info(f"Background chargé: {bg_name}")

        return self.loaded_backgrounds[bg_name]

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

        # Charger le background
        bg_name = self.current_map.get("background")
        bg = self._get_background(bg_name)

        if bg:
            bw, bh = bg.get_size()
            mw, mh = size

            # Tuilage du background si trop petit
            for x in range(0, mw, bw):
                for y in range(0, mh, bh):
                    self.map_surface.blit(bg, (x, y))
        else:
            # Fallback couleur
            self.map_surface.fill((50, 50, 50))
            logging.info("Aucun background trouvé, couleur grise appliquée")

        # Dessiner les objets
        for obj in self.collision_objects:
            self._draw_object(obj)

    def _draw_object(self, obj: dict):
        """Dessine un objet unique"""
        points = obj.get("points", [])
        if len(points) < 3:
            return  # Il faut au moins 3 points pour un polygone

        obj_type = obj.get("type", "default")
        sprite = self._get_sprite(obj_type)

        if sprite:
            sprite_conf = self.sprite_config.get(obj_type, {})
            tile_size = self._tile_size(sprite_conf, obj_type)
            if sprite_conf.get("tiling", False) or tile_size is not None:
                self._blit_tiled_sprite(sprite, points, tile_size)
            else:
                rect = sprite.get_rect()
                rect.topleft = points[0]
                self.map_surface.blit(sprite, rect)
        else:
            color = self._get_color(obj_type)
            pygame.draw.polygon(self.map_surface, color, points)

    def _tile_size(self, sprite_conf: dict, obj_type: str):
        """Retourne la taille de tuile imposée par ``repeat``, si présente."""
        repeat = sprite_conf.get("repeat")
        if repeat is None:
            return None
        if not isinstance(repeat, (list, tuple)) or len(repeat) != 2:
            logging.warning("repeat invalide pour le sprite %s: %r", obj_type, repeat)
            return None
        try:
            width, height = (int(repeat[0]), int(repeat[1]))
        except (TypeError, ValueError):
            logging.warning("repeat invalide pour le sprite %s: %r", obj_type, repeat)
            return None
        if width <= 0 or height <= 0:
            logging.warning("repeat doit être strictement positif pour le sprite %s", obj_type)
            return None
        return (width, height)

    def _blit_tiled_sprite(self, sprite: pygame.Surface, points: list, tile_size):
        """Répète un sprite dans le rectangle englobant d'un objet de map."""
        xs, ys = zip(*points)
        bounds = pygame.Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
        if bounds.width <= 0 or bounds.height <= 0:
            return

        if tile_size is None:
            tile = sprite
        else:
            cache_key = (id(sprite), tile_size)
            tile = self.scaled_tiles.get(cache_key)
            if tile is None:
                tile = pygame.transform.scale(sprite, tile_size)
                self.scaled_tiles[cache_key] = tile

        tile_width, tile_height = tile.get_size()
        previous_clip = self.map_surface.get_clip()
        self.map_surface.set_clip(bounds)
        try:
            for x in range(bounds.left, bounds.right, tile_width):
                for y in range(bounds.top, bounds.bottom, tile_height):
                    self.map_surface.blit(tile, (x, y))
        finally:
            self.map_surface.set_clip(previous_clip)

    def _get_color(self, obj_type: str):
        palette = {
            "rock": (100, 100, 100),
            "tree": (34, 139, 34),
            "water": (30, 144, 255),
            "wall": (139, 69, 19),
            "default": (128, 128, 128),
        }
        return palette.get(obj_type, palette["default"])

    def draw(self, screen: pygame.Surface, camera):
        if self.map_surface:
            screen.blit(self.map_surface, (-camera.offset.x, -camera.offset.y))

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

    def object_nearby(self,type,x,y,area_size=10,size=32):
        x1, x2 = x - size / 2, x + size / 2
        y1, y2 = y - size / 2, y + size / 2

        max_p_area = lambda x: max(x) + area_size
        min_p_area = lambda x: min(x) + area_size

        for obj in self.collision_objects:
            if obj.get("type") == type:
                pts = obj.get("points", [])
                if len(pts) >= 4:
                    xs, ys = zip(*pts)
                    if (x1 < max_p_area(xs) and x2 > min_p_area(xs) and
                            y1 < max_p_area(ys) and y2 > min_p_area(ys)):
                         return obj



    def get_spawn_points(self):
        return self.current_map.get("spawn_points", []) if self.current_map else []

    def reset(self):
        self.current_map = None
        self.map_surface = None
        self.collision_objects = []
