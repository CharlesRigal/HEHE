"""Overlay Grimoire : rendu pygame utilisant les assets PNG (Phase 7).

Couche UI du grimoire. La persistance et la liste des sorts sont dans
`client/magic/grimoire.py`. Cette classe ne fait que le rendu :
  - fond : Open_book.png (1088x816) centre a l'ecran
  - pages : 2 colonnes texte (slots 1-5 a gauche, 6-9 a droite)
  - icones optionnelles : Icons.png (sprite sheet 9x10 a 32x32)

API :
  overlay = GrimoireOverlay(grimoire)           # grimoire = client.magic.grimoire.Grimoire
  overlay.toggle()                               # G
  overlay.draw(screen, font)
  overlay.save_current(slot, name, resolved)     # 1..9 pendant sort en cache
  overlay.replay(slot) -> dict | None            # renvoie la spec reseau a envoyer

Formats d'assets attendus :
  client/assets/images/grimoire/PNG/Open_book.png          1088 x 816 (statique)
  client/assets/images/grimoire/PNG/Close_book.png         1088 x 816 (statique)
  client/assets/images/grimoire/PNG/book_content.png        336 x 448 (parchemin)
  client/assets/images/grimoire/PNG/Icons.png               288 x 320 (grille 9x10 @ 32px)

Les animations (Turning_pages_left.png, pages_apper.png) ne sont pas
utilisees ici car leur decoupage en frames n'est pas documente. Si tu veux
les inclure, donne le nombre de frames (colonnes x lignes) et je branche.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pygame

from client.magic.grimoire import Grimoire, GrimoireEntry
from client.magic.resolver.prediction import predict_archetype
from client.ui.live_prediction_overlay import (
    _draw_archetype_icon as _draw_phase6_icon,
    _ELEMENT_COLORS as _PHASE6_ELEMENT_COLORS,
)


_ASSETS = Path("client/assets/images/grimoire/PNG")

_OPEN_BOOK = _ASSETS / "Open_book.png"
_CLOSE_BOOK = _ASSETS / "Close_book.png"
_ICONS = _ASSETS / "Icons.png"

# Open_book.png : pages visibles a peu pres centrees, marges estimees
# empiriquement (le livre occupe ~1088x816 avec les pages effectives dans
# un rectangle plus petit).
_PAGE_LEFT_RECT  = (150, 150, 360, 520)   # (x, y, w, h) relatif au livre
_PAGE_RIGHT_RECT = (570, 150, 360, 520)

_SLOT_LH = 52
_SLOTS_PER_PAGE = 5
_ICON_SIZE = 32
_ICON_GRID = (9, 10)                      # colonnes x lignes dans Icons.png

_COL_TITLE = (60, 30, 10)
_COL_TEXT  = (40, 28, 18)
_COL_DIM   = (130, 100, 80)
_COL_SEL   = (170, 80, 20)


def _load_optional(path: Path) -> pygame.Surface | None:
    if not path.exists():
        logging.info(f"grimoire asset missing: {path}")
        return None
    try:
        return pygame.image.load(str(path)).convert_alpha()
    except Exception as e:
        logging.warning(f"grimoire: failed to load {path}: {e}")
        return None


class GrimoireOverlay:
    def __init__(self, grimoire: Grimoire):
        self._grimoire = grimoire
        self.visible = False
        self._selected_slot: str = "1"
        self._open_img: pygame.Surface | None = None
        self._close_img: pygame.Surface | None = None
        self._icons: pygame.Surface | None = None
        self._assets_loaded = False

    def _ensure_assets(self) -> None:
        if self._assets_loaded:
            return
        self._open_img = _load_optional(_OPEN_BOOK)
        self._close_img = _load_optional(_CLOSE_BOOK)
        self._icons = _load_optional(_ICONS)
        self._assets_loaded = True

    def toggle(self) -> None:
        self.visible = not self.visible

    def close(self) -> None:
        self.visible = False

    def select_slot(self, slot: str) -> None:
        self._selected_slot = slot

    # ── API persistence ────────────────────────────────────────

    def save_current(self, slot: str, name: str, params: dict[str, Any]) -> None:
        self._grimoire.save_params(slot, name, params)

    def replay(self, slot: str) -> dict[str, Any] | None:
        return self._grimoire.replay_network_spec(slot)

    def remove(self, slot: str) -> bool:
        return self._grimoire.remove(slot)

    # ── Rendu ──────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface, font_provider=None) -> None:
        if not self.visible:
            return
        self._ensure_assets()

        screen_w, screen_h = screen.get_size()

        if self._open_img is not None:
            book = self._open_img
            bw, bh = book.get_size()
            # Downscale si le livre est plus grand que l'ecran
            scale = min(1.0, screen_w * 0.9 / bw, screen_h * 0.9 / bh)
            if scale < 1.0:
                book = pygame.transform.smoothscale(book, (int(bw * scale), int(bh * scale)))
                bw, bh = book.get_size()
            bx = (screen_w - bw) // 2
            by = (screen_h - bh) // 2
            screen.blit(book, (bx, by))
        else:
            # Fallback : panneau opaque si asset manquant
            scale = 1.0
            bw, bh = min(900, screen_w - 40), min(600, screen_h - 40)
            bx = (screen_w - bw) // 2
            by = (screen_h - bh) // 2
            panel = pygame.Surface((bw, bh), pygame.SRCALPHA)
            panel.fill((40, 25, 15, 230))
            pygame.draw.rect(panel, (200, 160, 80), panel.get_rect(), width=2)
            screen.blit(panel, (bx, by))

        font = self._resolve_font(font_provider, 18)
        title_font = self._resolve_font(font_provider, 22)

        # Titre centre en haut
        title_surf = title_font.render("Grimoire", True, _COL_TITLE)
        screen.blit(title_surf, (bx + bw // 2 - title_surf.get_width() // 2, by + 60))

        # Liste entrees par page
        entries = {e.slot: e for e in self._grimoire.list_slots()}
        left_rect = self._scaled_rect(_PAGE_LEFT_RECT, scale, bx, by)
        right_rect = self._scaled_rect(_PAGE_RIGHT_RECT, scale, bx, by)

        self._draw_page(screen, font, left_rect, entries, slot_range=range(1, _SLOTS_PER_PAGE + 1))
        self._draw_page(
            screen, font, right_rect, entries,
            slot_range=range(_SLOTS_PER_PAGE + 1, 10),
        )

        # Bas de page : raccourcis
        hint = "G fermer | 1-9 selectionner | S sauver sort en cache | ENTREE rejouer | SUPPR effacer"
        hint_surf = font.render(hint, True, _COL_DIM)
        screen.blit(hint_surf, (bx + bw // 2 - hint_surf.get_width() // 2, by + bh - 40))

    # ── Helpers de rendu ───────────────────────────────────────

    def _draw_page(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        rect: tuple[int, int, int, int],
        entries: dict[str, GrimoireEntry],
        slot_range,
    ) -> None:
        x, y, w, h = rect
        for i, slot_num in enumerate(slot_range):
            slot = str(slot_num)
            row_y = y + i * _SLOT_LH
            entry = entries.get(slot)
            selected = slot == self._selected_slot

            # Indicateur de selection
            if selected:
                pygame.draw.rect(
                    screen, _COL_SEL,
                    (x - 4, row_y - 2, w + 8, _SLOT_LH - 4),
                    width=2,
                )

            # Icone : archetype procedural (Phase 6) pour les slots pleins,
            # sprite sheet fallback ou cercle gris pour les slots vides.
            icon_rect = pygame.Rect(x, row_y, _ICON_SIZE, _ICON_SIZE)
            if entry is not None:
                prediction = predict_archetype(entry.params)
                self._draw_slot_icon(screen, icon_rect, prediction)
            else:
                self._draw_empty_icon(screen, icon_rect, slot_num)

            # Numero de slot + nom
            label = f"{slot}. "
            if entry is None:
                label += "(vide)"
                color = _COL_DIM
            else:
                label += entry.name or "sort"
                color = _COL_SEL if selected else _COL_TEXT

            label_surf = font.render(label, True, color)
            screen.blit(label_surf, (x + _ICON_SIZE + 8, row_y + 2))

            # 2e ligne : archetype + element + top dominant
            if entry is not None:
                prediction = predict_archetype(entry.params)
                sub = f"[{prediction.archetype}] {prediction.element}"
                if prediction.dominants:
                    name, value = prediction.dominants[0]
                    sub += f"  \u2022 {name} {int(value * 100)}%"
                sub_surf = font.render(sub, True, _COL_DIM)
                screen.blit(sub_surf, (x + _ICON_SIZE + 8, row_y + 22))

    def _draw_slot_icon(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        prediction,
    ) -> None:
        """Dessine l'icone d'archetype sur le fond parchemin (via surface SRCALPHA)."""
        surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        color = _PHASE6_ELEMENT_COLORS.get(prediction.element, (200, 160, 90))
        local_rect = surface.get_rect()
        _draw_phase6_icon(surface, prediction.archetype, local_rect, color)
        screen.blit(surface, rect.topleft)

    def _draw_empty_icon(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        slot_num: int,
    ) -> None:
        """Fallback pour les slots vides : sprite sheet si dispo, sinon cercle gris."""
        if self._icons is not None:
            icon_idx = (slot_num - 1) % (_ICON_GRID[0] * _ICON_GRID[1])
            icon = self._get_icon(icon_idx)
            if icon is not None:
                # Rendu semi-transparent pour marquer le slot vide
                faded = icon.copy()
                faded.set_alpha(90)
                screen.blit(faded, rect.topleft)
                return
        pygame.draw.circle(
            screen, _COL_DIM,
            rect.center, rect.width // 2 - 2, width=1,
        )

    def _get_icon(self, index: int) -> pygame.Surface | None:
        if self._icons is None:
            return None
        cols, rows = _ICON_GRID
        col = index % cols
        row = index // cols
        if row >= rows:
            return None
        rect = pygame.Rect(col * _ICON_SIZE, row * _ICON_SIZE, _ICON_SIZE, _ICON_SIZE)
        icon = pygame.Surface((_ICON_SIZE, _ICON_SIZE), pygame.SRCALPHA)
        icon.blit(self._icons, (0, 0), rect)
        return icon

    @staticmethod
    def _scaled_rect(
        rect: tuple[int, int, int, int],
        scale: float,
        origin_x: int,
        origin_y: int,
    ) -> tuple[int, int, int, int]:
        x, y, w, h = rect
        return (
            origin_x + int(x * scale),
            origin_y + int(y * scale),
            int(w * scale),
            int(h * scale),
        )

    @staticmethod
    def _resolve_font(font_provider, size: int) -> pygame.font.Font:
        if font_provider is not None:
            try:
                return font_provider(size)
            except Exception:
                pass
        return pygame.font.SysFont("consolas", size)

    # ── Gestion clavier (utilitaire) ───────────────────────────

    def handle_key(self, event: pygame.event.Event, last_params: dict | None) -> dict | None:
        """Routeur clavier optionnel. Retourne une spec reseau a rejouer, ou None.

        Touches :
          G               toggle ouverture/fermeture
          1..9            selectionne un slot
          S               sauvegarde last_params dans le slot selectionne
          ENTREE          rejoue le slot selectionne (retourne la spec reseau)
          SUPPR / BACKSPACE  efface le slot selectionne
        """
        if event.type != pygame.KEYDOWN:
            return None

        if event.key == pygame.K_g:
            self.toggle()
            return None

        if not self.visible:
            return None

        if pygame.K_1 <= event.key <= pygame.K_9:
            self._selected_slot = str(event.key - pygame.K_0)
            return None

        if event.key == pygame.K_s and last_params:
            from client.magic.resolver.prediction import predict_archetype
            name = predict_archetype(last_params).archetype
            self.save_current(self._selected_slot, name, last_params)
            return None

        if event.key == pygame.K_RETURN:
            return self.replay(self._selected_slot)

        if event.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
            self.remove(self._selected_slot)
            return None

        return None


if __name__ == "__main__":
    import os
    import tempfile

    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1, 1))

    with tempfile.TemporaryDirectory() as tmp:
        g = Grimoire(path=Path(tmp) / "grim.json")
        # Panel d'archetypes : valide que chaque mini-icone passe dans _draw_slot_icon
        g.save_params("1", "projectile feu", {
            "element": "fire", "power": 0.6, "speed": 0.5, "compression": 0.3,
            "_dir_explicit": True, "dir_x": 1.0, "dir_y": 0.0,
        })
        g.save_params("2", "mur feu", {
            "element": "fire", "power": 0.5, "compression": 2.0,
            "axis_x": 1.0, "axis_y": 0.0, "elongation": 2.0,
        })
        g.save_params("3", "nappe glace", {
            "element": "ice", "power": 0.4, "spread": 0.5, "fade_rate": 0.5,
        })
        g.save_params("4", "zone plasma", {
            "element": "plasma", "power": 0.5, "spread": 0.4,
        })
        g.save_params("5", "eclair foudre", {
            "element": "lightning", "speed": 0.6, "split_count": 3,
        })
        g.save_params("6", "explosion enfer", {
            "element": "inferno", "speed": 0.2, "power": 0.6, "aoe_on_impact": True,
        })
        g.save_params("7", "lien tempete", {
            "element": "storm", "focused": True,
            "duration_bonus": 0.8, "power": 0.6,
        })
        g.save_params("8", "charge vent", {
            "element": "wind", "power": 0.5,
        })
        # slot 9 volontairement vide pour tester le fallback

        ui = GrimoireOverlay(g)
        ui.toggle()
        screen = pygame.Surface((1280, 720))
        ui.draw(screen)
        assert ui.visible

        # Chaque slot rempli rejoue OK
        for slot in ("1", "2", "3", "4", "5", "6", "7", "8"):
            spec = ui.replay(slot)
            assert spec is not None, f"slot {slot} replay returned None"
            assert spec["t"] == "s", f"slot {slot} bad envelope: {spec}"

        # Slot vide
        assert ui.replay("9") is None

        # Handle key S sauvegarde derniers params
        from pygame.event import Event
        ev = Event(pygame.KEYDOWN, {"key": pygame.K_1})
        ui.handle_key(ev, {})  # selectionne slot 1
        ev = Event(pygame.KEYDOWN, {"key": pygame.K_RETURN})
        replayed = ui.handle_key(ev, None)
        assert replayed is not None
        assert replayed["t"] == "s"

    print("grimoire ui: OK")
