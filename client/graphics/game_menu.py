from pathlib import Path
from typing import Dict, Optional, Literal

import pygame

from client.gui.button import Button


class GameMenu:
    def __init__(
        self,
        screen_width: int,
        screen_height: int,
        background_path: str = "client/assets/images/Une images de backgroud en pixel art composer de terre d'herbes vue du dessus.jpg",
    ):
        self.available_maps: Dict[str, str] = {}
        self.selected_map_id: Optional[str] = None
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)

        if not pygame.font.get_init():
            pygame.font.init()

        self.font = pygame.font.Font(None, 42)
        self.title_font = pygame.font.Font(None, 72)
        self.background_path = Path(background_path)
        self._background_source: Optional[pygame.Surface] = None
        self._background_scaled: Optional[pygame.Surface] = None
        self._background_missing = False

        self.play_button: Optional[Button] = None
        self.options_button: Optional[Button] = None
        self._create_buttons()

    def _create_buttons(self) -> None:
        button_width = 240
        button_height = 58
        left_margin = 30
        top_start = self.screen_height // 2 - 70
        spacing = 16

        self.play_button = Button(
            rect=(left_margin, top_start, button_width, button_height),
            text="Jouer",
            font=self.font,
        )
        self.options_button = Button(
            rect=(left_margin, top_start + button_height + spacing, button_width, button_height),
            text="Options",
            font=self.font,
        )

    def _load_background_source(self) -> None:
        if self._background_source is not None or self._background_missing:
            return

        try:
            self._background_source = pygame.image.load(str(self.background_path))
        except (FileNotFoundError, pygame.error):
            self._background_missing = True
            self._background_source = None

    def _refresh_background(self) -> None:
        if self._background_source is None:
            self._background_scaled = None
            return

        self._background_scaled = pygame.transform.smoothscale(
            self._background_source, (self.screen_width, self.screen_height)
        )

    def resize(self, screen_width: int, screen_height: int) -> None:
        self.screen_width = int(screen_width)
        self.screen_height = int(screen_height)
        self._create_buttons()
        self._refresh_background()

    def handle_hover(self, pos: tuple[int, int]) -> None:
        if self.play_button is not None:
            self.play_button.is_hovered = self.play_button.rect.collidepoint(pos)
        if self.options_button is not None:
            self.options_button.is_hovered = self.options_button.rect.collidepoint(pos)

    def handle_click(self, pos: tuple[int, int]) -> Optional[Literal["play", "options"]]:
        if self.play_button is not None and self.play_button.rect.collidepoint(pos):
            return "play"
        if self.options_button is not None and self.options_button.rect.collidepoint(pos):
            return "options"
        return None

    @staticmethod
    def handle_key(key: int) -> Optional[Literal["play", "options"]]:
        if key in (pygame.K_RETURN, pygame.K_SPACE):
            return "play"
        if key == pygame.K_o:
            return "options"
        return None

    def draw(self, screen: pygame.Surface) -> None:
        self._load_background_source()

        if screen.get_width() != self.screen_width or screen.get_height() != self.screen_height:
            self.resize(screen.get_width(), screen.get_height())

        if self._background_scaled is None and self._background_source is not None:
            self._refresh_background()

        if self._background_scaled is not None:
            screen.blit(self._background_scaled, (0, 0))
        else:
            screen.fill((0, 0, 0))

        title = self.title_font.render("Fala World", True, (255, 255, 255))
        screen.blit(title, (30, 60))

        mouse_pos = pygame.mouse.get_pos()
        self.handle_hover(mouse_pos)

        if self.play_button is not None:
            self.play_button.draw(screen)
        if self.options_button is not None:
            self.options_button.draw(screen)
