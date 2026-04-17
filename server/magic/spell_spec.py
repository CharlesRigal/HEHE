from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ServerSpellSpec:
    element: str | None = None
    behavior: str | None = None
    direction: tuple[float, float] | None = None
    power: float | None = None
    shape: str | None = None
    focused: bool = False
    unstable: bool = False
    axis: tuple[float, float] | None = None
    intensity: float = 1.0
    speed: float = 0.0
    duration_bonus: float = 0.0
    spread: float = 0.0
    compression: float = 0.0
    fade_rate: float = 0.0
    # ── Qualificateurs issus de la composition de rôles (client) ──────────
    aoi: bool = False              # spawn une zone AOE au point d'impact
    split_count: int = 0          # nombre de fragments (zigzag)
    split_on_impact: bool = False  # True = split à l'impact, False = split à l'expiration


def spec_from_network(data: dict) -> ServerSpellSpec:
    """Désérialise le format compact réseau {"t":"s","e":"fire","bh":"area",...}."""
    spec = ServerSpellSpec()

    spec.element = data.get("e") or None
    spec.behavior = data.get("bh") or None
    spec.shape = data.get("shp") or None

    dir_raw = data.get("dir")
    if isinstance(dir_raw, (list, tuple)) and len(dir_raw) == 2:
        try:
            spec.direction = (float(dir_raw[0]), float(dir_raw[1]))
        except (TypeError, ValueError):
            pass

    pwr = data.get("pwr")
    if pwr is not None:
        try:
            spec.power = max(0.0, min(1.0, float(pwr)))
        except (TypeError, ValueError):
            pass

    spec.focused = bool(data.get("foc", 0))
    spec.unstable = bool(data.get("uns", 0))

    ax_raw = data.get("ax")
    if isinstance(ax_raw, (list, tuple)) and len(ax_raw) == 2:
        try:
            spec.axis = (float(ax_raw[0]), float(ax_raw[1]))
        except (TypeError, ValueError):
            pass

    intn = data.get("intn")
    if intn is not None:
        try:
            spec.intensity = max(0.0, float(intn))
        except (TypeError, ValueError):
            pass

    spd = data.get("spd")
    if spd is not None:
        try:
            spec.speed = max(0.0, min(1.0, float(spd)))
        except (TypeError, ValueError):
            pass

    dur = data.get("dur")
    if dur is not None:
        try:
            spec.duration_bonus = max(0.0, float(dur))
        except (TypeError, ValueError):
            pass

    spr = data.get("spr")
    if spr is not None:
        try:
            spec.spread = max(0.0, min(1.0, float(spr)))
        except (TypeError, ValueError):
            pass

    cmp = data.get("cmp")
    if cmp is not None:
        try:
            spec.compression = max(0.0, float(cmp))
        except (TypeError, ValueError):
            pass

    fdr = data.get("fdr")
    if fdr is not None:
        try:
            spec.fade_rate = max(0.0, min(1.0, float(fdr)))
        except (TypeError, ValueError):
            pass

    spec.aoi = bool(data.get("aoi", 0))

    spl = data.get("spl")
    if spl is not None:
        try:
            spec.split_count = max(0, int(spl))
        except (TypeError, ValueError):
            pass

    spec.split_on_impact = bool(data.get("spi", 0))

    return spec