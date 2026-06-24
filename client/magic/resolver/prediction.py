"""Prediction d'archetype (Phase 6).

A partir d'un dict params (partiel ou complet) produit par le resolver, genere
une description courte de l'archetype pour affichage en temps reel pendant le
dessin. Aucun nom de sort, uniquement des dominantes continues.

Vocabulaire d'archetype :
  - projectile     : speed eleve
  - mur            : compression + axis
  - nappe          : spread + fade (stationnaire)
  - zone           : spread seul, stationnaire
  - explosion      : power + aoe_on_impact
  - eclair         : speed + split
  - lien           : focused + duration_bonus (Phase 5 binding)
  - neutre         : aucun trait dominant

La fonction NE depend PAS du resolver : elle accepte n'importe quel dict,
y compris partiel (utile pour un rendu incremental pendant que le joueur
dessine).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ArchetypePrediction:
    archetype: str                     # "projectile" | "mur" | "nappe" | "lien" | ...
    element: str                       # dominant element ou "neutre"
    dominants: list[tuple[str, float]] # ("feu", 0.6), ("vitesse", 0.5), ...
    confidence: float                  # 0..1 : force de la signature
    relations: list[str] = field(default_factory=list)  # "cercle -> contient -> triangle"

    def to_display_lines(self) -> list[str]:
        """Representation lisible pour un overlay."""
        lines = [f"[{self.archetype}]"]
        if self.element != "neutre":
            lines.append(f"element: {self.element}")
        for name, value in self.dominants[:4]:
            bar = "#" * max(1, int(value * 8))
            lines.append(f"{name:>8} {bar}")
        for rel in self.relations[:3]:
            lines.append(f"  {rel}")
        return lines


_ELEMENT_FR = {
    "fire": "feu",
    "ice": "glace",
    "water": "eau",
    "lightning": "foudre",
    "plasma": "plasma",
    "inferno": "enfer",
    "storm": "tempete",
    "wind": "vent",
    "neutral": "neutre",
    None: "neutre",
}


def _f(p: dict, key: str, default: float = 0.0) -> float:
    v = p.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def predict_archetype(params: dict[str, Any]) -> ArchetypePrediction:
    """Classe continue en archetype reconnaissable pour le feedback joueur."""
    speed = _f(params, "speed")
    compression = _f(params, "compression")
    spread = _f(params, "spread")
    fade_rate = _f(params, "fade_rate")
    power = _f(params, "power")
    duration_bonus = _f(params, "duration_bonus")
    axis_x = _f(params, "axis_x")
    axis_y = _f(params, "axis_y")
    split_count = int(params.get("split_count", 0) or 0)
    aoe_on_impact = bool(params.get("aoe_on_impact"))
    focused = bool(params.get("focused"))
    has_axis = (abs(axis_x) + abs(axis_y)) > 1e-3

    element = params.get("element") or "neutral"
    element_fr = _ELEMENT_FR.get(element, element)

    # Classification (seuils alignes sur server/effects/producers.py).
    # Lien (binding) en priorite car il peut coexister avec speed modere.
    if focused and duration_bonus >= 0.5 and power >= 0.3:
        archetype = "lien"
        confidence = min(1.0, 0.4 + duration_bonus * 0.4 + power * 0.2)
    elif compression > 1.5 and has_axis:
        archetype = "mur"
        confidence = min(1.0, 0.4 + compression * 0.2)
    elif speed > 0.05 and aoe_on_impact:
        archetype = "explosion"
        confidence = min(1.0, 0.5 + speed * 0.5)
    elif speed > 0.05 and split_count >= 2:
        archetype = "eclair"
        confidence = min(1.0, 0.5 + speed * 0.3 + split_count * 0.05)
    elif speed > 0.05:
        archetype = "projectile"
        confidence = min(1.0, 0.4 + speed * 0.6)
    elif spread > 0.3 and fade_rate > 0.0:
        archetype = "nappe"
        confidence = min(1.0, 0.4 + spread * 0.4 + fade_rate * 0.2)
    elif spread > 0.05:
        archetype = "zone"
        confidence = min(1.0, 0.3 + spread * 0.7)
    elif power > 0.3:
        archetype = "charge"
        confidence = power
    else:
        archetype = "neutre"
        confidence = 0.0

    # Dominantes : triees par amplitude
    raw = [
        ("vitesse", speed),
        ("compression", min(1.0, compression / 2.0)),
        ("diffusion", spread),
        ("estompe", fade_rate),
        ("puissance", power),
        ("duree", min(1.0, duration_bonus)),
    ]
    dominants = [(n, v) for n, v in raw if v > 0.05]
    dominants.sort(key=lambda kv: kv[1], reverse=True)

    return ArchetypePrediction(
        archetype=archetype,
        element=element_fr,
        dominants=dominants,
        confidence=confidence,
    )


if __name__ == "__main__":
    # Projectile feu
    p = predict_archetype({"element": "fire", "speed": 0.5, "power": 0.6, "compression": 0.3})
    assert p.archetype == "projectile"
    assert p.element == "feu"
    assert p.confidence > 0.5

    # Mur
    p = predict_archetype({"element": "fire", "compression": 2.0, "axis_x": 50.0, "power": 0.5})
    assert p.archetype == "mur"

    # Nappe
    p = predict_archetype({"element": "fire", "spread": 0.5, "fade_rate": 0.5, "power": 0.4})
    assert p.archetype == "nappe"

    # Partiel (seulement element, rien d'autre)
    p = predict_archetype({"element": "ice"})
    assert p.archetype == "neutre"
    assert p.element == "glace"

    # Lien (Phase 5 binding archetype)
    p = predict_archetype({
        "element": "storm", "focused": True,
        "duration_bonus": 0.8, "power": 0.6,
    })
    assert p.archetype == "lien", f"got {p.archetype}"
    assert p.confidence > 0.5

    # Lien vs projectile : focused sans duration = projectile
    p = predict_archetype({
        "element": "storm", "focused": True, "speed": 0.5,
        "duration_bonus": 0.1, "power": 0.6,
    })
    assert p.archetype == "projectile"

    # Display
    p = predict_archetype({"element": "fire", "speed": 0.5, "power": 0.6})
    lines = p.to_display_lines()
    assert lines[0] == "[projectile]"

    print("prediction: OK")
