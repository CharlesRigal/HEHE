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

    return spec