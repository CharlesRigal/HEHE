import pygame


class PlayerHealthBar:
    """UI pour la barre de vie du joueur local."""

    COLOR = (0xAC, 0x32, 0x32)
    MARGIN = (20, 20)
    PADDING = 4

    def __init__(self, frame_path="client/assets/ui/heal_bare.png", margin=None, fill_color=None):
        self.frame = pygame.image.load(frame_path).convert_alpha()
        self.frame_rect = self.frame.get_rect()
        self.margin = margin or self.MARGIN
        self.fill_color = fill_color or self.COLOR

    def draw(self, screen: pygame.Surface, current_health: float, max_health: float):
        if not max_health:
            return

        percent = max(0.0, min(1.0, current_health / max_health))
        screen_width, screen_height = screen.get_size()
        x = self.margin[0]
        y = screen_height - self.frame_rect.height - self.margin[1]

        fill_width = max(0, self.frame_rect.width - 2 * self.PADDING)
        fill_height = max(0, self.frame_rect.height - 2 * self.PADDING)
        fill_length = int(fill_width * percent)

        if fill_length > 0:
            fill_rect = pygame.Rect(
                x + self.PADDING,
                y + self.PADDING,
                fill_length,
                fill_height
            )
            pygame.draw.rect(screen, self.fill_color, fill_rect)

        screen.blit(self.frame, (x, y))
