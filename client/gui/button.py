import pygame

class Button:
    def __init__(self, rect, text, font, color=(50,50,50), hover_color=(70,130,180), selected_color = (70, 130, 180), callback=None):
        self.on_click = callback
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.color = color
        self.hover_color = hover_color
        self.selected_color = selected_color
        self.is_hovered = False
        self.is_selected = False

    def draw(self, screen):

        if self.is_selected:
            color = self.selected_color
        elif self.is_hovered:
            color = self.hover_color
        else:
            color = self.color

        pygame.draw.rect(screen, color, self.rect, border_radius=5)
        pygame.draw.rect(screen, (100, 100, 100), self.rect, 2, border_radius=5)

        text_surface = self.font.render(self.text, True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=self.rect.center)
        screen.blit(text_surface, text_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.on_click:
                    self.on_click()
                return True
        return False