"""Overlay de feedback temps reel pendant le dessin (Phase 6).

Affiche en haut-gauche l'archetype dominant calcule a la volee depuis les
strokes en cours. Pas de nom de sort, pas de pseudo-grammaire : uniquement
archetype + element + dominantes continues.

Protocole de consommation :
  overlay.update(prediction)    # ArchetypePrediction | None
  overlay.draw(screen)          # appele par la boucle de rendu

La logique de quand/comment calculer la prediction est faite dans l'appelant
(typiquement : throttle une fois toutes les N frames pendant le dessin).
"""
from __future__ import annotations

from typing import Any

import pygame

from client.magic.resolver.prediction import ArchetypePrediction


_BG = (8, 12, 18, 185)
_BORDER = (92, 170, 255, 200)
_TITLE = (255, 220, 80)
_TEXT = (230, 244, 255)
_DIM = (130, 150, 170)
_BAR = (120, 220, 120)
_ICON_FG = (200, 230, 255)
_ICON_ACCENT = (255, 200, 90)

_PANEL_W = 240
_PANEL_X = 12
_PANEL_Y = 12
_PAD = 8
_LH = 17
_ICON_SIZE = 36
_ICON_INSET = 6

_ELEMENT_COLORS = {
    "feu":      (255, 120,  40),
    "glace":    (180, 230, 255),
    "eau":      ( 80, 160, 240),
    "foudre":   (255, 240, 120),
    "plasma":   (220, 120, 255),
    "enfer":    (255, 100,  60),
    "tempete":  (180, 200, 255),
    "vent":     (200, 240, 220),
    "neutre":   (200, 200, 200),
}


class LivePredictionOverlay:
    def __init__(self, font_provider: Any = None):
        self._prediction: ArchetypePrediction | None = None
        self._font_provider = font_provider
        self._font_cache: pygame.font.Font | None = None

    def update(self, prediction: ArchetypePrediction | None) -> None:
        self._prediction = prediction

    def clear(self) -> None:
        self._prediction = None

    def _get_font(self) -> pygame.font.Font:
        if self._font_cache is not None:
            return self._font_cache
        if self._font_provider is not None:
            try:
                self._font_cache = self._font_provider(15)
                return self._font_cache
            except Exception:
                pass
        self._font_cache = pygame.font.SysFont("consolas", 14)
        return self._font_cache

    def draw(self, screen: pygame.Surface) -> None:
        if self._prediction is None or self._prediction.archetype == "neutre":
            return

        font = self._get_font()
        lines = self._prediction.to_display_lines()

        max_w = max((font.size(t)[0] for t in lines), default=120)
        panel_w = max(max_w + _PAD * 2 + _ICON_SIZE + _ICON_INSET, _PANEL_W)
        panel_h = max(len(lines) * _LH + _PAD * 2, _ICON_SIZE + _PAD * 2)

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill(_BG)
        pygame.draw.rect(panel, _BORDER, panel.get_rect(), width=1)

        # Icone de l'archetype dans le coin haut-droit
        icon_color = _ELEMENT_COLORS.get(self._prediction.element, _ICON_FG)
        icon_rect = pygame.Rect(
            panel_w - _ICON_SIZE - _ICON_INSET,
            _ICON_INSET,
            _ICON_SIZE,
            _ICON_SIZE,
        )
        _draw_archetype_icon(panel, self._prediction.archetype, icon_rect, icon_color)

        screen.blit(panel, (_PANEL_X, _PANEL_Y))

        tx = _PANEL_X + _PAD
        ty = _PANEL_Y + _PAD
        text_max_w = panel_w - _ICON_SIZE - _ICON_INSET * 2 - _PAD
        for i, text in enumerate(lines):
            if i == 0:
                color = _TITLE
            elif text.startswith("element:"):
                color = _TEXT
            elif "#" in text:
                color = _BAR
            else:
                color = _DIM
            surf = font.render(text, True, color)
            screen.blit(surf, (tx, ty))
            _ = text_max_w
            ty += _LH


# ─── Mini-icones par archetype ──────────────────────────────────────

def _draw_archetype_icon(
    surface: pygame.Surface,
    archetype: str,
    rect: pygame.Rect,
    color: tuple[int, int, int],
) -> None:
    """Dessine une micro-representation geometrique de l'archetype.

    Purement visuel : le joueur reconnait la forme au lieu de lire un mot.
    Pas d'icone pour "neutre" (panneau masque de toute facon).
    """
    cx, cy = rect.center
    r = rect.width // 2 - 2

    if archetype == "projectile":
        # Fleche horizontale
        pygame.draw.line(surface, color, (rect.left + 2, cy), (rect.right - 6, cy), width=3)
        pygame.draw.polygon(surface, color, [
            (rect.right - 2, cy),
            (rect.right - 8, cy - 4),
            (rect.right - 8, cy + 4),
        ])
    elif archetype == "mur":
        # Rectangle allonge
        w = rect.width - 6
        h = 8
        rr = pygame.Rect(cx - w // 2, cy - h // 2, w, h)
        pygame.draw.rect(surface, color, rr, border_radius=2)
    elif archetype == "nappe":
        # Zone horizontale etalee avec trames
        for off in (-6, 0, 6):
            pygame.draw.line(surface, color, (rect.left + 2, cy + off), (rect.right - 2, cy + off), width=2)
    elif archetype == "zone":
        # Cercle plein (area)
        pygame.draw.circle(surface, color, (cx, cy), r)
    elif archetype == "explosion":
        # Etoile a 8 branches
        import math
        for i in range(8):
            a = i * math.pi / 4
            ex = cx + int(math.cos(a) * r)
            ey = cy + int(math.sin(a) * r)
            pygame.draw.line(surface, color, (cx, cy), (ex, ey), width=2)
    elif archetype == "eclair":
        # Zigzag
        pts = [
            (rect.left + 4, rect.top + 4),
            (cx - 4, cy - 2),
            (cx + 4, cy + 2),
            (rect.right - 4, rect.bottom - 4),
        ]
        pygame.draw.lines(surface, color, False, pts, width=3)
    elif archetype == "lien":
        # Deux points relies par un lien ondule
        p_a = (rect.left + 6, cy)
        p_b = (rect.right - 6, cy)
        pygame.draw.circle(surface, color, p_a, 4)
        pygame.draw.circle(surface, color, p_b, 4)
        pygame.draw.line(surface, _ICON_ACCENT, p_a, p_b, width=2)
    elif archetype == "charge":
        # Cercle plein + contour accent
        pygame.draw.circle(surface, color, (cx, cy), r - 2)
        pygame.draw.circle(surface, _ICON_ACCENT, (cx, cy), r, width=2)
    else:
        pygame.draw.circle(surface, color, (cx, cy), r, width=2)


def try_compute_prediction(
    game: Any,
    strokes: list,
) -> ArchetypePrediction | None:
    """Recalcule une prediction rapidement depuis des strokes partiels.

    En cas d'erreur (AST incomplet, primitives invalides, etc.) retourne None
    plutot que de planter : ce module est best-effort pour l'affichage live.
    """
    if not strokes:
        return None
    try:
        primitives = game.geometry_analyzer.analyze(strokes)
        if not primitives:
            return None
        if not isinstance(primitives, list):
            primitives = [primitives]

        # Le graph et l'AST doivent etre reconstruits a la volee. On ne
        # modifie pas l'etat persistant du MagicalDraw.
        from client.magic.graph_geo import GraphGeo
        graph = GraphGeo()
        for p in primitives:
            graph.add_node(p)

        ast = game.ast_builder.build(graph)
        resolved = game.ast_resolver.resolve(ast)

        from client.magic.resolver.prediction import predict_archetype
        prediction = predict_archetype(resolved.params)

        # Relations spatiales lisibles : prendre les plus pertinentes
        prediction.relations = _describe_relations(graph, primitives)
        return prediction
    except Exception:
        return None


def _describe_relations(graph: Any, primitives: list) -> list[str]:
    """Produit une description courte et lisible des relations spatiales.

    Ex : "cercle contient triangle", "fleche vers cercle", "segment pres cercle".
    """
    try:
        relations = graph.build_spatial_relations()
    except Exception:
        return []
    out: list[str] = []
    seen: set[tuple[int, int, str]] = set()
    for rel in relations:
        key = (rel.source_index, rel.target_index, rel.relation)
        if key in seen:
            continue
        seen.add(key)
        src = _short_name(primitives[rel.source_index]) if rel.source_index < len(primitives) else "?"
        tgt = _short_name(primitives[rel.target_index]) if rel.target_index < len(primitives) else "?"
        verb = _REL_VERB.get(rel.relation, rel.relation)
        out.append(f"{src} {verb} {tgt}")
        if len(out) >= 3:
            break
    return out


_REL_VERB = {
    "contains": "contient",
    "intersects": "croise",
    "near": "pres",
}


def _short_name(primitive: Any) -> str:
    name = type(primitive).__name__.lower()
    return {
        "circle": "cercle",
        "arrow": "fleche",
        "arrowwithbase": "fleche",
        "triangle": "triangle",
        "segment": "trait",
        "zigzag": "eclair",
        "runefire": "rune",
    }.get(name, name)


if __name__ == "__main__":
    import os
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1, 1))

    from client.magic.resolver.prediction import ArchetypePrediction

    overlay = LivePredictionOverlay()
    screen = pygame.Surface((640, 480), pygame.SRCALPHA)

    # Chaque archetype rendu sans crasher
    for arch in ("projectile", "mur", "nappe", "zone", "explosion",
                  "eclair", "lien", "charge"):
        overlay.update(ArchetypePrediction(
            archetype=arch, element="feu",
            dominants=[("vitesse", 0.6), ("puissance", 0.5)],
            confidence=0.7,
            relations=["cercle contient triangle", "fleche vers cercle"],
        ))
        screen.fill((0, 0, 0, 0))
        overlay.draw(screen)

    # neutre : pas de panneau
    overlay.update(ArchetypePrediction(
        archetype="neutre", element="neutre",
        dominants=[], confidence=0.0,
    ))
    screen.fill((0, 0, 0, 0))
    overlay.draw(screen)

    print("live_prediction_overlay: OK")
