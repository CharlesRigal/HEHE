import pygame
from typing import Dict, Optional

from client.gui.button import Button


class MapSelector:
    """Interface de sélection de map avant de rejoindre le jeu"""

    def __init__(self, screen_width: int = 1280, screen_height: int = 720):
        self.available_maps: Dict[str, str] = {}
        self.selected_map_id: Optional[str] = None
        self.screen_width = screen_width
        self.screen_height = screen_height

        # Interface
        self.font = pygame.font.Font(None, 36)
        #self.small_font = pygame.font.Font(None, 24)

        # État de l'interface
        self.map_buttons = []
        self.button_height = 50
        self.button_margin = 10

    def set_available_maps(self, maps: Dict[str, str]):
        """Met à jour la liste des maps disponibles"""
        self.available_maps = maps
        self.selected_map_id = None
        self._create_buttons()

        # Sélectionner automatiquement la première map
        if maps:
            self.selected_map_id = next(iter(maps.keys()))

    def _create_buttons(self):
        """Crée les boutons pour chaque map"""
        self.map_buttons = []
        start_y = self.screen_height // 2 - (len(self.available_maps) * (self.button_height + self.button_margin)) // 2

        for i, (map_id, map_name) in enumerate(self.available_maps.items()):
            y = start_y + i * (self.button_height + self.button_margin)
            rect = (self.screen_width // 2 - 200, y, 400, self.button_height)

            button = Button(rect, map_name, self.font)
            button.map_id = map_id
            self.map_buttons.append(button)

    def handle_click(self, event) -> Optional[str]:
        """Gère le clic de souris et retourne l'ID de la map sélectionnée"""
        for button in self.map_buttons:
            if button.handle_event(event):
                self.selected_map_id = button.map_id
                return button.map_id
        return None

    def handle_key(self, key: int) -> Optional[str]:
        """Gère les touches clavier pour la navigation"""
        if not self.available_maps:
            return None

        map_ids = list(self.available_maps.keys())

        if key == pygame.K_UP:
            if self.selected_map_id:
                current_index = map_ids.index(self.selected_map_id)
                new_index = (current_index - 1) % len(map_ids)
                self.selected_map_id = map_ids[new_index]

        elif key == pygame.K_DOWN:
            if self.selected_map_id:
                current_index = map_ids.index(self.selected_map_id)
                new_index = (current_index + 1) % len(map_ids)
                self.selected_map_id = map_ids[new_index]

        elif key == pygame.K_RETURN or key == pygame.K_SPACE:
            return self.selected_map_id

        return None

    def draw(self, screen: pygame.Surface):
        """Dessine l'interface de sélection"""
        # Fond semi-transparent
        overlay = pygame.Surface((self.screen_width, self.screen_height))
        overlay.set_alpha(200)
        overlay.fill((0, 0, 0))
        screen.blit(overlay, (0, 0))

        # Titre
        title = self.font.render("Sélectionnez une map", True, (255, 255, 255))
        title_rect = title.get_rect(center=(self.screen_width // 2, 150))
        screen.blit(title, title_rect)

        # Instructions
        instructions = [
            "Utilisez les flèches UP ou DOWN ou cliquez pour sélectionner",
            "Appuyez sur ENTRÉE ou ESPACE pour confirmer"
        ]

        for button in self.map_buttons:
            button.draw(screen)


    def get_selected_map(self) -> Optional[str]:
        """Retourne l'ID de la map actuellement sélectionnée"""
        return self.selected_map_id

    def handle_hover(self, pos):
        """Met à jour l'état hover des boutons en fonction de la souris"""
        for button in self.map_buttons:
            button.is_hovered = button.rect.collidepoint(pos)
