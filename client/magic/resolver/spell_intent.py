"""
spell_intent.py — Structures de données pour le système de sorts par rôles.

Chaque sort est décrit comme une liste de phases temporelles.
Chaque phase a une Form (livraison), une Substance (effet) et un Trigger optionnel.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FormDescriptor:
    """Comment le sort se manifeste / se déplace."""
    form_type: str = "aoe"       # "projectile" | "cone" | "aoe" | "wall" | "ray" | "shield"
    speed: float = 0.0           # 0 = statique, >0 = mobile
    spread: float = 0.0          # angle pour cones, rayon relatif pour aoe
    direction: tuple[float, float] = (1.0, 0.0)
    axis: tuple[float, float] = (0.0, 0.0)
    elongation: float = 1.0
    radius: float = 0.3          # taille relative [0,1]
    duration: float = 0.0        # bonus durée


@dataclass
class SubstanceDescriptor:
    """Ce que le sort FAIT au contact / dans la zone."""
    effect_type: str = "damage"  # "damage" | "freeze" | "create" | "transmute" | "push" | "absorb"
    element: str = "neutral"     # "fire" | "ice" | "lightning" | "arcane" | "neutral"
    intensity: float = 0.5       # puissance relative [0,1]
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class TriggerDescriptor:
    """Connecteur temporel entre phases."""
    trigger_type: str = "on_expire"  # "on_impact" | "after_delay" | "on_expire" | "periodic"
    delay: float = 0.0               # secondes
    count: int = 1                   # nombre de spawns (split)
    next_phase: int = -1             # index dans SpellIntent.phases (-1 = pas de suite)


@dataclass
class SpellPhase:
    """Une phase temporelle du sort."""
    form: FormDescriptor = field(default_factory=FormDescriptor)
    substance: SubstanceDescriptor = field(default_factory=SubstanceDescriptor)
    trigger: TriggerDescriptor | None = None


@dataclass
class SpellIntent:
    """Description complète d'un sort multi-phases."""
    phases: list[SpellPhase] = field(default_factory=list)
    power: float = 0.5
    element: str = "neutral"     # élément dominant (Form level)
    debug_roles: dict[str, str] = field(default_factory=dict)  # node_id -> role
