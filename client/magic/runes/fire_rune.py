from __future__ import annotations

import math
from typing import Any

from client.entities.fire_rune_area_effect import FireRuneAreaEffect
from client.magic.primitives import RuneFire
from client.magic.rune_abstractions import RuneArchetype
from client.magic.rune_registry import RuneDefinition
from client.magic.spell_types import OrderedSymbol, SpellDraft, SpellModel


class FireRuneArchetype(RuneArchetype):
    @property
    def spell_id(self) -> str:
        return "fire_rune"

    @property
    def primary_primitive_type(self) -> type[Any]:
        return RuneFire

    def has_client_executor(self) -> bool:
        return True

    def build_spell(self, symbol: OrderedSymbol, draft: SpellDraft) -> SpellModel | None:
        rune = symbol.primitive
        if not isinstance(rune, RuneFire):
            return None

        center = self._compute_rune_center(rune)
        rune_extent = self._compute_rune_extent(rune, center)
        anchor_radius = max(0.0, float(draft.anchor_radius))
        texture_radius = self._compute_texture_radius_from_geometry(rune_extent, anchor_radius)
        hitbox_radius = max(1.0, texture_radius * 0.78)
        return SpellModel(
            spell_id=self.spell_id,
            anchor_circle_index=draft.anchor_circle_index,
            center=center,
            params={
                "texture_radius": float(texture_radius),
                "hitbox_radius": float(hitbox_radius),
                "hitbox_radius_x": float(hitbox_radius),
                "hitbox_radius_y": float(hitbox_radius),
                "ellipse_angle": 0.0,
                "velocity_x": 0.0,
                "velocity_y": 0.0,
                "shape": "circle",
                "damage_per_tick": 12.0,
                "tick_interval": 0.20,
                "duration": 2.4,
                "cast_distance_bonus": 0.0,
                "rune_extent": float(rune_extent),
                "anchor_circle_radius": float(anchor_radius),
            },
            modifiers=[],
            ordered_symbols=list(draft.ordered_symbols),
            drawing_features=dict(draft.drawing_features),
        )

    def execute_client(self, game: Any, spell: SpellModel) -> None:
        texture_radius = max(8.0, spell.get_float("texture_radius", 16.0))
        hitbox_radius = max(1.0, spell.get_float("hitbox_radius", texture_radius * 0.78))
        hitbox_radius_x = max(1.0, spell.get_float("hitbox_radius_x", hitbox_radius))
        hitbox_radius_y = max(1.0, spell.get_float("hitbox_radius_y", hitbox_radius))
        texture_radius = max(
            texture_radius,
            hitbox_radius * 1.06,
            hitbox_radius_x * 1.04,
            hitbox_radius_y * 1.04,
        )
        ellipse_angle = spell.get_float("ellipse_angle", 0.0)
        velocity_x = spell.get_float("velocity_x", 0.0)
        velocity_y = spell.get_float("velocity_y", 0.0)
        damage_per_tick = max(0.0, spell.get_float("damage_per_tick", 12.0))
        tick_interval = max(0.05, spell.get_float("tick_interval", 0.20))
        duration = max(0.05, spell.get_float("duration", 2.4))
        cast_distance_bonus = max(0.0, spell.get_float("cast_distance_bonus", 0.0))

        cast_hitbox = max(hitbox_radius, hitbox_radius_x, hitbox_radius_y)
        cast_center = game._compute_forward_cast_center(
            hitbox_radius=cast_hitbox,
            fallback_center=spell.center,
            distance_bonus=cast_distance_bonus,
        )

        effect = FireRuneAreaEffect(
            center=cast_center,
            texture_radius=texture_radius,
            hitbox_radius=hitbox_radius,
            hitbox_radius_x=hitbox_radius_x,
            hitbox_radius_y=hitbox_radius_y,
            ellipse_angle=ellipse_angle,
            velocity=(velocity_x, velocity_y),
            damage_per_tick=damage_per_tick,
            tick_interval=tick_interval,
            duration=duration,
            owner_player_id=getattr(game, "client_id", None),
        )
        game.game_manager.add_object(effect)

        if not getattr(game, "net_connected", False):
            return
        net = getattr(game, "net", None)
        if net is None:
            return

        message = spell.to_cast_message()
        message["spell"] = spell.spell_id  # compat backward avec anciens serveurs
        message["x"] = float(cast_center[0])
        message["y"] = float(cast_center[1])
        payload = dict(message.get("payload", {}))
        payload["texture_radius"] = float(texture_radius)
        payload["hitbox_radius"] = float(hitbox_radius)
        payload["hitbox_radius_x"] = float(hitbox_radius_x)
        payload["hitbox_radius_y"] = float(hitbox_radius_y)
        payload["ellipse_angle"] = float(ellipse_angle)
        payload["velocity_x"] = float(velocity_x)
        payload["velocity_y"] = float(velocity_y)
        payload["damage_per_tick"] = float(damage_per_tick)
        payload["tick_interval"] = float(tick_interval)
        payload["duration"] = float(duration)
        payload["cast_distance_bonus"] = float(cast_distance_bonus)
        message["payload"] = payload
        net.send(message)

    @staticmethod
    def _compute_rune_center(rune: RuneFire) -> tuple[float, float]:
        if rune.vertices:
            cx = sum(point[0] for point in rune.vertices) / len(rune.vertices)
            cy = sum(point[1] for point in rune.vertices) / len(rune.vertices)
            return (float(cx), float(cy))
        if rune._points:
            cx = sum(point[0] for point in rune._points) / len(rune._points)
            cy = sum(point[1] for point in rune._points) / len(rune._points)
            return (float(cx), float(cy))
        return (0.0, 0.0)

    @staticmethod
    def _compute_rune_extent(rune: RuneFire, center: tuple[float, float]) -> float:
        points = [tuple(point) for point in rune.vertices]
        for start, end in rune.cuts:
            points.append(tuple(start))
            points.append(tuple(end))
        if not points and rune._points:
            points = [tuple(point) for point in rune._points]
        if not points:
            return 0.0

        return max(math.hypot(point[0] - center[0], point[1] - center[1]) for point in points)

    @staticmethod
    def _compute_texture_radius_from_geometry(rune_extent: float, anchor_radius: float) -> float:
        rune_scale = FireRuneArchetype._clamp(rune_extent / 42.0, 0.15, 3.0)
        circle_scale = FireRuneArchetype._clamp(anchor_radius / 110.0, 0.15, 3.5)
        combined_scale = 0.60 * (rune_scale ** 1.30) + 0.55 * (circle_scale ** 1.25)
        return FireRuneArchetype._clamp(7.0 + 12.0 * combined_scale, 8.0, 220.0)

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))


FIRE_RUNE = FireRuneArchetype()


def build_fire_rune_spell(symbol: OrderedSymbol, draft: SpellDraft) -> SpellModel | None:
    return FIRE_RUNE.build_spell(symbol, draft)


def execute_fire_rune(game: Any, spell: SpellModel) -> None:
    FIRE_RUNE.execute_client(game, spell)


FIRE_RUNE_DEFINITION: RuneDefinition = FIRE_RUNE.to_definition()
