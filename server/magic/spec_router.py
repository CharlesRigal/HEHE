from __future__ import annotations

from server.magic.spell_spec import ServerSpellSpec

# (element, behavior) → spell_id spécifique
_SPECIFIC: dict[tuple[str, str], str] = {
    ("fire", "projectile"):      "fire_projectile",
    ("lightning", "projectile"): "lightning_projectile",
    ("plasma", "projectile"):    "fire_projectile",   # fallback jusqu'à impl plasma
}

# element → spell_id par défaut (toute behavior non spécifique)
_FALLBACK: dict[str, str] = {
    "fire":      "fire_rune",
    "lightning": "lightning_rune",
    "plasma":    "fire_rune",
    "inferno":   "fire_rune",
    "storm":     "lightning_rune",
}


def route_spec(spec: ServerSpellSpec) -> str:
    element = spec.element or "fire"
    behavior = spec.behavior or "stationary"

    specific = _SPECIFIC.get((element, behavior))
    if specific:
        return specific

    return _FALLBACK.get(element, "fire_rune")
