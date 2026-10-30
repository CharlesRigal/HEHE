"""Lecture du pentacle -> message reseau `s` (README L7).

Le centre n'est pas envoye : le sort agit autour du mage, la ou il se tient
a la fermeture du cercle (S1), et le serveur connait sa position.
"""
from __future__ import annotations

from client.magic.reader import PentacleReading


def build_spell_message(reading: PentacleReading) -> dict | None:
    """None si le sort est inerte : cercle mort (C1) ou pas d'emblème valide (E3)."""
    if reading.circle_quality <= 0.0 or reading.is_inert:
        return None
    return {
        "t": "s",
        "R": round(reading.radius, 1),
        "q": round(reading.circle_quality, 3),
        "e": reading.emblem.element,
        "eq": round(reading.emblem.score, 3),
        "ink": round(reading.ink, 1),
        "signs": [
            {
                "k": sign.kind,
                "r": round(sign.r, 3),
                "a": round(sign.angle, 4),
                "o": round(sign.orientation, 4),
                "s": round(sign.size, 3),
                "q": round(sign.score, 3),
            }
            for sign in reading.signs
            if sign.alive
        ],
    }
