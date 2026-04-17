"""ResolvedSpell : resultat final du resolver, pret pour le serveur."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from client.magic.ast.ast import SpellAST
    from client.magic.ast.symbol_rules import PropertyEntry


@dataclass
class ResolvedSpell:
    params: dict[str, Any]
    ast: Any  # SpellAST
    property_snapshot: dict[str, list]  # node_id -> list[PropertyEntry] pour debug


def params_to_network_spec(resolved: ResolvedSpell) -> dict:
    """
    Serialise un ResolvedSpell vers le format reseau compact
    attendu par spec_from_network / ServerSpellSpec.

    Mapping params -> champs reseau :
        compression   -> cmp
        speed         -> spd
        power         -> pwr
        spread        -> spr
        duration_bonus -> dur
        intensity     -> intn
        element       -> e
        behavior      -> bh
        focused       -> foc
        fade_rate     -> fdr
        axis_x/axis_y -> ax  (magnitude encode elongation)
        dir_x/dir_y   -> dir (seulement si _dir_explicit)
    """
    p = resolved.params
    spec: dict[str, Any] = {"t": "s"}

    # Compression (nouveau champ central)
    compression = float(p.get("compression", 0.0))
    spec["cmp"] = round(compression, 4)

    # Element
    element = p.get("element")
    if element and element != "neutral":
        spec["e"] = element

    # Behavior (derive, pas hardcode dans les regles)
    behavior = p.get("behavior", "aoe")
    if behavior:
        spec["bh"] = behavior

    # Speed
    speed = float(p.get("speed", 0.0))
    if speed > 0.0:
        spec["spd"] = round(speed, 4)

    # Power
    power = p.get("power")
    if power is not None:
        spec["pwr"] = round(float(power), 4)

    # Spread
    spread = float(p.get("spread", 0.0))
    if spread > 0.0:
        spec["spr"] = round(spread, 4)

    # Duration bonus
    dur = float(p.get("duration_bonus", 0.0))
    if dur > 0.0:
        spec["dur"] = round(dur, 4)

    # Intensity
    intensity = float(p.get("intensity", 1.0))
    if intensity != 1.0:
        spec["intn"] = round(intensity, 4)

    # Focused
    if p.get("focused"):
        spec["foc"] = 1

    # Unstable
    if p.get("unstable"):
        spec["uns"] = 1

    # Fade rate
    fade_rate = float(p.get("fade_rate", 0.0))
    if fade_rate > 0.0:
        spec["fdr"] = round(fade_rate, 4)

    # Axis — la magnitude encode l'elongation pour que le serveur puisse la lire
    axis_x = float(p.get("axis_x", 0.0))
    axis_y = float(p.get("axis_y", 0.0))
    if abs(axis_x) > 1e-6 or abs(axis_y) > 1e-6:
        elongation = max(1.0, float(p.get("elongation", 1.0)))
        # Normaliser (cos,sin) puis multiplier par elongation
        mag = math.hypot(axis_x, axis_y)
        if mag > 1e-6:
            nx = axis_x / mag
            ny = axis_y / mag
        else:
            nx, ny = 1.0, 0.0
        spec["ax"] = [round(nx * elongation, 4), round(ny * elongation, 4)]

    # Direction — seulement si explicite (fleche standalone, pas propagee)
    if p.get("_dir_explicit"):
        dir_x = float(p.get("dir_x", 1.0))
        dir_y = float(p.get("dir_y", 0.0))
        if abs(dir_x) > 1e-6 or abs(dir_y) > 1e-6:
            spec["dir"] = [round(dir_x, 4), round(dir_y, 4)]

    # Shape cone : seulement si direction explicite ET aoe
    if behavior == "aoe" and spread > 0.05 and p.get("_dir_explicit"):
        spec["shp"] = "cone"

    # Split count (zigzag : nombre de sous-projectiles/répétitions)
    split_count = int(p.get("split_count", 0))
    if split_count > 0:
        spec["spl"] = split_count

    # ── Qualificateurs de composition ─────────────────────────────────────
    if p.get("pierce"):
        spec["prc"] = 1                     # perce les obstacles / solides

    if p.get("aoe_on_impact"):
        spec["aoi"] = 1                     # crée une zone à l'impact

    if p.get("split_on_impact") and split_count > 0:
        spec["spi"] = 1                     # se divise à l'impact (avec spl=N)

    if p.get("secondary_zone"):
        spec["szn"] = 1                     # effet secondaire différé

    scope_radius = float(p.get("scope_radius", 0.0))
    if scope_radius > 0.01:
        spec["rad"] = round(scope_radius, 4)  # rayon de zone normalisé

    return spec


def intent_to_network_spec(intent: "SpellIntent") -> dict:
    """Serialise un SpellIntent vers le format reseau s2 multi-phases."""
    from client.magic.resolver.spell_intent import SpellIntent

    if not intent.phases:
        return {"t": "s2", "phases": []}

    phases_out = []
    for phase in intent.phases:
        p: dict[str, Any] = {}

        # Form
        p["form"] = phase.form.form_type
        if phase.form.speed > 0.01:
            p["spd"] = round(phase.form.speed, 4)
        dx, dy = phase.form.direction
        if abs(dx) > 1e-6 or abs(dy) > 1e-6:
            p["dir"] = [round(dx, 4), round(dy, 4)]
        if phase.form.spread > 0.01:
            p["spr"] = round(phase.form.spread, 4)
        if phase.form.radius > 0.01:
            p["rad"] = round(phase.form.radius, 4)
        if phase.form.duration > 0.01:
            p["dur"] = round(phase.form.duration, 4)
        if phase.form.elongation > 1.1:
            ax, ay = phase.form.axis
            if abs(ax) > 1e-6 or abs(ay) > 1e-6:
                p["ax"] = [round(ax * phase.form.elongation, 4), round(ay * phase.form.elongation, 4)]

        # Substance
        p["sub"] = phase.substance.effect_type
        if phase.substance.element and phase.substance.element != "neutral":
            p["e"] = phase.substance.element
        p["pwr"] = round(phase.substance.intensity, 4)
        if phase.substance.extra:
            p["extra"] = phase.substance.extra

        # Trigger
        if phase.trigger is not None and phase.trigger.next_phase >= 0:
            t: dict[str, Any] = {"type": phase.trigger.trigger_type}
            if phase.trigger.delay > 0.01:
                t["delay"] = round(phase.trigger.delay, 4)
            if phase.trigger.count > 1:
                t["count"] = phase.trigger.count
            t["next"] = phase.trigger.next_phase
            p["trigger"] = t

        phases_out.append(p)

    return {
        "t": "s2",
        "pwr": round(intent.power, 4),
        "phases": phases_out,
    }
