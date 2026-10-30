"""Glyphes des emblèmes et des signes.

PROVISOIRES : le README laisse les glyphes a dessiner. Ceux-ci servent a
faire tourner la chaine de lecture ; ils seront remplaces par les vrais.

Contraintes (README) :
- chaque glyphe est d'un seul tenant (ses traits se touchent, L3) ;
- chaque signe a un seul axe et une base et une tete distinguables (F0) ;
- aucun glyphe n'est une boucle ronde, sinon il passerait pour un cercle.

Repere : x a droite, y en bas. Les signes sont dessines tete vers +x.
Convergence et Dispersion sont un seul glyphe : le sens radial decide (F6).
"""
from __future__ import annotations

import math

from client.magic.dollar_p import Template


# ── Emblèmes (element du sort) ───────────────────────────────────

EMBLEM_GLYPHS: dict[str, list[list[tuple[float, float]]]] = {
    # Flamme : chevron vers le haut traverse par une tige.
    "fire": [[(-1.0, 1.0), (0.0, -1.0), (1.0, 1.0)], [(0.0, -1.0), (0.0, 1.0)]],
    # Flocon : trois droites croisees.
    "ice": [
        [(-1.0, 0.0), (1.0, 0.0)],
        [(-0.5, -0.87), (0.5, 0.87)],
        [(0.5, -0.87), (-0.5, 0.87)],
    ],
    # Vague : une sinusoide.
    "water": [[(x / 8.0 - 1.0, 0.5 * math.sin((x / 8.0 - 1.0) * 2.0 * math.pi)) for x in range(17)]],
    # Tourbillon : spirale.
    "wind": [[
        (0.15 * t * math.cos(t), 0.15 * t * math.sin(t))
        for t in [i * 0.25 for i in range(1, 27)]
    ]],
    # Montagne : deux pics poses sur un sol.
    "earth": [[(-1.0, 0.6), (-0.4, -0.6), (0.0, 0.1), (0.4, -0.9), (1.0, 0.6)], [(-1.0, 0.6), (1.0, 0.6)]],
    # Eclair : zigzag vertical.
    "lightning": [[(-0.3, -1.0), (0.35, -0.2), (-0.35, 0.2), (0.3, 1.0)]],
    # Soleil : croix droite.
    "light": [[(-1.0, 0.0), (1.0, 0.0)], [(0.0, -1.0), (0.0, 1.0)]],
}

# ── Signes (tete vers +x) ────────────────────────────────────────

_SHAFT = [(-1.0, 0.0), (1.0, 0.0)]
_HEAD = [(0.55, -0.4), (1.0, 0.0), (0.55, 0.4)]

SIGN_GLYPHS: dict[str, list[list[tuple[float, float]]]] = {
    # Fleche simple.
    "direction": [_SHAFT, _HEAD],
    # Fleche ouverte, triangle superpose a la hampe (README).
    "traction": [_SHAFT, _HEAD, [(-0.45, -0.4), (0.05, 0.0), (-0.45, 0.4), (-0.45, -0.4)]],
    # Triangle isocele, pointe = tete (README).
    "convergence": [[(-0.6, -0.55), (0.9, 0.0), (-0.6, 0.55), (-0.6, -0.55)]],
    # Fleche ouverte avec base (README).
    "suspension": [_SHAFT, _HEAD, [(-1.0, -0.45), (-1.0, 0.45)]],
    # T : la barre est la tete (README).
    "column": [[(-1.0, 0.0), (0.8, 0.0)], [(0.8, -0.7), (0.8, 0.7)]],
    # Hampe et deux chevrons empiles.
    "repetition": [_SHAFT, _HEAD, [(0.1, -0.4), (0.55, 0.0), (0.1, 0.4)]],
}

SIGN_HEAD = (1.0, 0.0)
SIGN_BASE = (-1.0, 0.0)


def emblem_templates() -> list[Template]:
    return [Template.from_strokes(label, strokes) for label, strokes in EMBLEM_GLYPHS.items()]


def sign_templates() -> list[Template]:
    return [
        Template.from_strokes(label, strokes, head=SIGN_HEAD, base=SIGN_BASE)
        for label, strokes in SIGN_GLYPHS.items()
    ]
