from __future__ import annotations

import math
from typing import Any, Callable, Mapping, Sequence

from client.magic.circle_symbol_executor import CircleSubSymbolExecutionContext
from client.magic.default_runes import build_default_rune_registry
from client.magic.graph_geo import CircleReadingPlan, GraphGeo, SpatialRelation
from client.magic.primitives import Arrow, ArrowWithBase, Circle, Segment, Triangle, ZigZag
from client.magic.rune_abstractions import FunctionalModifierArchetype, ModifierArchetype
from client.magic.rune_registry import RuneDefinition, RuneRegistry
from client.magic.spell_types import OrderedSymbol, SpellDraft, SpellModifier, SpellModel


class SpellModifierEngine:
    """
    Moteur de modificateurs orienté registre.
    Chaque handler peut altérer les paramètres d'un sort, voire son identité.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[SpellModel, SpellModifier, GraphGeo | None], SpellModel]]] = {}
        self._register_defaults()

    def register(
        self,
        modifier_id: str,
        handler: Callable[[SpellModel, SpellModifier, GraphGeo | None], SpellModel],
    ) -> None:
        self._handlers.setdefault(modifier_id, []).append(handler)

    def apply(
        self,
        spell: SpellModel,
        modifiers: Sequence[SpellModifier],
        *,
        graph: GraphGeo | None = None,
    ) -> SpellModel:
        current = spell
        for modifier in modifiers:
            for handler in self._handlers.get(modifier.modifier_id, ()):
                current = handler(current, modifier, graph)
        return current

    def _register_defaults(self) -> None:
        self.register("power", self._handle_power_modifier)
        self.register("reach", self._handle_reach_modifier)
        self.register("volatility", self._handle_volatility_modifier)
        self.register("precision", self._handle_precision_modifier)
        self.register("stability", self._handle_stability_modifier)

    @staticmethod
    def _modifier_strength(modifier: SpellModifier, fallback: float = 1.0) -> float:
        raw = modifier.payload.get("strength", fallback)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = fallback
        return max(0.1, min(3.0, value))

    @staticmethod
    def _payload_float(
        modifier: SpellModifier,
        key: str,
        fallback: float = 0.0,
    ) -> float:
        raw = modifier.payload.get(key, fallback)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(fallback)

    def _handle_power_modifier(
        self,
        spell: SpellModel,
        modifier: SpellModifier,
        graph: GraphGeo | None,
    ) -> SpellModel:
        _ = graph
        strength = self._modifier_strength(modifier)
        base = spell.get_float("damage_per_tick", 12.0)
        spell.params["damage_per_tick"] = max(0.0, base * (1.0 + 0.22 * strength))
        return spell

    def _handle_reach_modifier(
        self,
        spell: SpellModel,
        modifier: SpellModifier,
        graph: GraphGeo | None,
    ) -> SpellModel:
        _ = graph
        strength = self._modifier_strength(modifier)
        current = spell.get_float("cast_distance_bonus", 0.0)
        spell.params["cast_distance_bonus"] = current + 18.0 * strength

        has_base = self._payload_float(modifier, "has_base", 0.0) >= 0.5
        base_score = max(0.0, min(1.0, self._payload_float(modifier, "base_score", 0.0)))
        base_length = max(0.0, self._payload_float(modifier, "base_length", 0.0))

        direction_x = self._payload_float(modifier, "direction_x", 0.0)
        direction_y = self._payload_float(modifier, "direction_y", 0.0)
        length = max(0.0, self._payload_float(modifier, "vector_length", 0.0))
        shape_pressure = max(0.0, self._payload_float(modifier, "shape_pressure", 0.0))
        speed_seed = max(0.0, self._payload_float(modifier, "speed_seed", 0.0))

        norm = math.hypot(direction_x, direction_y)
        if norm > 1e-6:
            direction_x /= norm
            direction_y /= norm

        base_factor = 1.0 + (0.22 * base_score if has_base else 0.0)
        pressure_factor = 1.0 + (0.18 * base_score if has_base else 0.0)
        speed_bonus = (length * 0.18 + speed_seed * 32.0) * strength
        if has_base:
            speed_bonus += (base_length * 0.10 + base_score * 24.0) * strength

        spell.params["motion_vector_x"] = spell.get_float("motion_vector_x", 0.0) + direction_x * strength * base_factor
        spell.params["motion_vector_y"] = spell.get_float("motion_vector_y", 0.0) + direction_y * strength * base_factor
        spell.params["shape_pressure"] = spell.get_float("shape_pressure", 0.0) + shape_pressure * strength * pressure_factor
        spell.params["move_speed_bonus"] = spell.get_float("move_speed_bonus", 0.0) + speed_bonus
        return spell

    def _handle_volatility_modifier(
        self,
        spell: SpellModel,
        modifier: SpellModifier,
        graph: GraphGeo | None,
    ) -> SpellModel:
        _ = graph
        strength = self._modifier_strength(modifier)
        tick_interval = spell.get_float("tick_interval", 0.20)
        duration = spell.get_float("duration", 2.4)
        spell.params["tick_interval"] = max(0.05, tick_interval * max(0.45, 1.0 - 0.10 * strength))
        spell.params["duration"] = max(0.15, duration * max(0.50, 1.0 - 0.08 * strength))
        return spell

    def _handle_precision_modifier(
        self,
        spell: SpellModel,
        modifier: SpellModifier,
        graph: GraphGeo | None,
    ) -> SpellModel:
        _ = graph
        strength = self._modifier_strength(modifier)
        hitbox = spell.get_float("hitbox_radius", 16.0)
        damage = spell.get_float("damage_per_tick", 12.0)
        spell.params["hitbox_radius"] = max(1.0, hitbox * max(0.65, 1.0 - 0.06 * strength))
        spell.params["damage_per_tick"] = max(0.0, damage * (1.0 + 0.08 * strength))
        return spell

    def _handle_stability_modifier(
        self,
        spell: SpellModel,
        modifier: SpellModifier,
        graph: GraphGeo | None,
    ) -> SpellModel:
        _ = graph
        strength = self._modifier_strength(modifier)
        duration = spell.get_float("duration", 2.4)
        tick_interval = spell.get_float("tick_interval", 0.20)
        size_scale = max(1.0, min(1.4, 1.0 + 0.14 * strength))
        spell.params["duration"] = max(0.15, duration * (1.0 + 0.14 * strength))
        spell.params["tick_interval"] = max(0.05, tick_interval * (1.0 + 0.05 * strength))
        hitbox_radius = max(1.0, spell.get_float("hitbox_radius", 16.0) * size_scale)
        spell.params["hitbox_radius"] = hitbox_radius
        spell.params["texture_radius"] = max(
            8.0,
            spell.get_float("texture_radius", hitbox_radius * 1.18) * size_scale,
        )
        if "hitbox_radius_x" in spell.params:
            spell.params["hitbox_radius_x"] = max(1.0, spell.get_float("hitbox_radius_x", hitbox_radius) * size_scale)
        if "hitbox_radius_y" in spell.params:
            spell.params["hitbox_radius_y"] = max(1.0, spell.get_float("hitbox_radius_y", hitbox_radius) * size_scale)
        return spell


class SpellBuilder:
    """
    Builder de sorts depuis une lecture de graphe.
    - construction d'un draft ordonné,
    - sélection d'une base de sort via registre,
    - extraction + application d'une chaîne de modificateurs.
    """

    def __init__(
        self,
        modifier_engine: SpellModifierEngine | None = None,
        rune_registry: RuneRegistry | None = None,
    ) -> None:
        self.modifier_engine = modifier_engine or SpellModifierEngine()
        self.rune_registry = rune_registry or build_default_rune_registry()
        self._modifier_archetypes: list[ModifierArchetype] = []
        self._register_default_factories()

    def register_spell_factory(
        self,
        primitive_type: type[Any],
        factory: Callable[[OrderedSymbol, SpellDraft], SpellModel | None],
        *,
        spell_id: str | None = None,
    ) -> None:
        resolved_spell_id = spell_id or str(getattr(primitive_type, "kind", primitive_type.__name__.lower()))
        self.rune_registry.register(
            RuneDefinition(
                spell_id=resolved_spell_id,
                primary_primitive_type=primitive_type,
                build_spell=factory,
            )
        )

    def register_modifier_factory(
        self,
        primitive_type: type[Any],
        factory: Callable[[OrderedSymbol], SpellModifier],
    ) -> None:
        modifier_id = str(getattr(primitive_type, "kind", primitive_type.__name__.lower()))
        self.register_modifier_archetype(
            FunctionalModifierArchetype(
                modifier_id=modifier_id,
                primitive_type=primitive_type,
                factory=factory,
            )
        )

    def register_modifier_archetype(self, archetype: ModifierArchetype) -> None:
        self._modifier_archetypes.append(archetype)

    def build_draft(
        self,
        plan: CircleReadingPlan,
        primitives: Sequence[Any],
        execution: Sequence[CircleSubSymbolExecutionContext],
    ) -> SpellDraft:
        ordered_symbols: list[OrderedSymbol] = []
        for context in execution:
            if context.symbol_index < 0 or context.symbol_index >= len(primitives):
                continue
            primitive = primitives[context.symbol_index]
            ordered_symbols.append(
                OrderedSymbol(
                    symbol_index=context.symbol_index,
                    primitive=primitive,
                    ordinal=context.ordinal,
                    total=context.total,
                    drawing_features=self._extract_symbol_features(primitive),
                )
            )
        drawing_features = self._aggregate_symbol_features(ordered_symbols)
        return SpellDraft(
            anchor_circle_index=plan.anchor_circle_index,
            center=plan.center,
            anchor_radius=plan.anchor_radius,
            ordered_symbols=ordered_symbols,
            drawing_features=drawing_features,
        )

    def create_spell(self, draft: SpellDraft, graph: GraphGeo | None = None) -> SpellModel | None:
        primary_symbol, primary_definition = self._select_primary_definition(draft.ordered_symbols)
        if primary_symbol is None or primary_definition is None:
            return None

        spell = primary_definition.build_spell(primary_symbol, draft)
        if spell is None:
            return None

        spell.modifiers = self._build_modifiers(
            draft,
            excluded_symbol_index=primary_symbol.symbol_index,
            primary_symbol_index=primary_symbol.symbol_index,
            graph=graph,
        )
        if not spell.drawing_features:
            spell.drawing_features = dict(draft.drawing_features)
        else:
            merged = dict(draft.drawing_features)
            merged.update(spell.drawing_features)
            spell.drawing_features = merged

        return self.modifier_engine.apply(spell, spell.modifiers, graph=graph)

    def _register_default_factories(self) -> None:
        self.register_modifier_factory(ArrowWithBase, self._build_reach_modifier)
        self.register_modifier_factory(Arrow, self._build_reach_modifier)
        self.register_modifier_factory(Triangle, self._build_power_modifier)
        self.register_modifier_factory(ZigZag, self._build_volatility_modifier)
        self.register_modifier_factory(Segment, self._build_precision_modifier)
        self.register_modifier_factory(Circle, self._build_stability_modifier)

    def _extract_symbol_features(self, primitive: Any) -> dict[str, float]:
        meta = getattr(primitive, "meta", None)
        if not isinstance(meta, Mapping):
            return {}

        features: dict[str, float] = {}
        for key, value in meta.items():
            if not isinstance(value, (int, float)):
                continue
            numeric = float(value)
            if key.startswith("drawing_"):
                features[key] = numeric
                continue
            if key in {
                "avg_speed",
                "max_speed",
                "speed_variability",
                "speed_norm",
                "avg_pressure",
                "max_pressure",
                "pressure_variability",
                "pressure_norm",
                "pressure_supported",
                "symmetry_score",
            }:
                features[f"drawing_{key}"] = numeric

        if "drawing_speed_norm" not in features and "drawing_avg_speed" in features:
            features["drawing_speed_norm"] = self._clamp(features["drawing_avg_speed"] / 680.0, 0.0, 1.0)
        if "drawing_pressure_norm" not in features and "drawing_avg_pressure" in features:
            features["drawing_pressure_norm"] = self._clamp(features["drawing_avg_pressure"], 0.0, 1.0)
        if "drawing_symmetry_score" in features:
            features["drawing_symmetry_score"] = self._clamp(features["drawing_symmetry_score"], 0.0, 1.0)
        return features

    def _aggregate_symbol_features(self, symbols: Sequence[OrderedSymbol]) -> dict[str, float]:
        if not symbols:
            return {}

        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for symbol in symbols:
            for key, value in symbol.drawing_features.items():
                if not isinstance(value, (int, float)):
                    continue
                numeric = float(value)
                sums[key] = sums.get(key, 0.0) + numeric
                counts[key] = counts.get(key, 0) + 1

        aggregated = {
            key: sums[key] / max(1, counts.get(key, 1))
            for key in sums
        }
        aggregated["drawing_symbol_count"] = float(len(symbols))
        return aggregated

    def _select_primary_definition(
        self,
        symbols: Sequence[OrderedSymbol],
    ) -> tuple[OrderedSymbol | None, RuneDefinition | None]:
        for symbol in symbols:
            for definition in self.rune_registry.iter_primary_matches(symbol.primitive):
                return symbol, definition
        return None, None

    def _build_modifiers(
        self,
        draft: SpellDraft,
        *,
        excluded_symbol_index: int,
        primary_symbol_index: int,
        graph: GraphGeo | None,
    ) -> list[SpellModifier]:
        modifiers: list[SpellModifier] = []
        spatial_relations = graph.build_spatial_relations() if graph is not None else None
        for symbol in draft.ordered_symbols:
            if symbol.symbol_index == excluded_symbol_index:
                continue
            modifier = self._build_modifier(symbol)
            modifiers.append(
                self._apply_modifier_context(
                    modifier,
                    symbol=symbol,
                    primary_symbol_index=primary_symbol_index,
                    graph=graph,
                    relations=spatial_relations,
                )
            )
        return modifiers

    def _apply_modifier_context(
        self,
        modifier: SpellModifier,
        *,
        symbol: OrderedSymbol,
        primary_symbol_index: int,
        graph: GraphGeo | None,
        relations: list[SpatialRelation] | None,
    ) -> SpellModifier:
        payload = dict(modifier.payload)
        base_strength = self._safe_float(payload.get("strength", 1.0), 1.0)
        order_factor = self._order_factor(symbol)
        placement_factor, relation = self._placement_factor(
            graph=graph,
            symbol_index=symbol.symbol_index,
            primary_symbol_index=primary_symbol_index,
            relations=relations,
        )
        strength = self._clamp(base_strength * order_factor * placement_factor, 0.1, 3.0)
        payload["strength"] = strength
        payload["order_factor"] = order_factor
        payload["placement_factor"] = placement_factor
        payload["relation"] = relation
        modifier.payload = payload
        return modifier

    def _placement_factor(
        self,
        *,
        graph: GraphGeo | None,
        symbol_index: int,
        primary_symbol_index: int,
        relations: list[SpatialRelation] | None,
    ) -> tuple[float, str]:
        if graph is None:
            return 1.0, "none"

        direct = graph.find_relations(
            source_index=symbol_index,
            target_index=primary_symbol_index,
            relations=relations,
        )
        reverse = graph.find_relations(
            source_index=primary_symbol_index,
            target_index=symbol_index,
            relations=relations,
        )
        scoped_relations = direct + reverse
        if not scoped_relations:
            return 0.95, "none"

        best_factor = 1.0
        best_relation = "none"
        for relation in scoped_relations:
            candidate_factor = 1.0
            if relation.relation == "intersects":
                candidate_factor = 1.24
            elif relation.relation in {"inside", "contains"}:
                candidate_factor = 1.16
            elif relation.relation == "near":
                near_weight = max(0.0, min(1.0, float(relation.weight)))
                candidate_factor = 1.04 + 0.14 * near_weight

            if candidate_factor > best_factor:
                best_factor = candidate_factor
                best_relation = relation.relation

        return self._clamp(best_factor, 0.80, 1.35), best_relation

    @staticmethod
    def _order_factor(symbol: OrderedSymbol) -> float:
        if symbol.total <= 1:
            return 1.0
        rank = symbol.ordinal / max(1, symbol.total - 1)
        # Les premiers symboles lus pèsent légèrement plus.
        return SpellBuilder._clamp(1.15 - 0.35 * rank, 0.80, 1.25)

    @staticmethod
    def _safe_float(value: object, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(fallback)

    def _build_modifier(self, symbol: OrderedSymbol) -> SpellModifier:
        for archetype in self._modifier_archetypes:
            if archetype.supports(symbol.primitive):
                return archetype.build(symbol)
        return SpellModifier(
            modifier_id=f"shape_{type(symbol.primitive).__name__.lower()}",
            source_symbol_index=symbol.symbol_index,
            ordinal=symbol.ordinal,
            total=symbol.total,
            payload={"strength": 1.0},
        )

    def _build_power_modifier(self, symbol: OrderedSymbol) -> SpellModifier:
        primitive = symbol.primitive
        strength = 1.0
        if isinstance(primitive, Triangle) and len(primitive.vertices) >= 3:
            strength = self._triangle_strength(primitive.vertices[:3])
        return SpellModifier(
            modifier_id="power",
            source_symbol_index=symbol.symbol_index,
            ordinal=symbol.ordinal,
            total=symbol.total,
            payload={"strength": strength},
        )

    def _build_reach_modifier(self, symbol: OrderedSymbol) -> SpellModifier:
        primitive = symbol.primitive
        strength = 1.0
        direction_x = 0.0
        direction_y = 0.0
        length = 0.0
        head_span = 0.0
        shape_pressure = 0.0
        speed_seed = 0.0
        has_base = 0.0
        base_score = 0.0
        base_length = 0.0
        base_start_x = 0.0
        base_start_y = 0.0
        base_end_x = 0.0
        base_end_y = 0.0
        if isinstance(primitive, (Arrow, ArrowWithBase)):
            dx = primitive.tip[0] - primitive.tail[0]
            dy = primitive.tip[1] - primitive.tail[1]
            length = math.hypot(dx, dy)
            strength = self._clamp(length / 120.0, 0.5, 2.4)
            if length > 1e-6:
                direction_x = dx / length
                direction_y = dy / length
            head_span = math.hypot(
                primitive.left_head[0] - primitive.right_head[0],
                primitive.left_head[1] - primitive.right_head[1],
            )
            shape_pressure = self._clamp(head_span / max(length, 1e-6), 0.12, 1.6)
            speed_seed = self._clamp(length / 95.0, 0.25, 3.0)
        if isinstance(primitive, ArrowWithBase):
            has_base = 1.0
            base_score = self._clamp(float(getattr(primitive, "confidence", 1.0)), 0.0, 1.0)
            base_length = math.hypot(
                primitive.base_end[0] - primitive.base_start[0],
                primitive.base_end[1] - primitive.base_start[1],
            )
            base_start_x = float(primitive.base_start[0])
            base_start_y = float(primitive.base_start[1])
            base_end_x = float(primitive.base_end[0])
            base_end_y = float(primitive.base_end[1])
            base_ratio = self._clamp(base_length / max(length, 1e-6), 0.12, 1.8)
            shape_pressure = max(shape_pressure, base_ratio) * (0.86 + 0.30 * base_score)
            speed_seed = speed_seed * (0.70 + 0.60 * base_score)
        return SpellModifier(
            modifier_id="reach",
            source_symbol_index=symbol.symbol_index,
            ordinal=symbol.ordinal,
            total=symbol.total,
            payload={
                "strength": strength,
                "direction_x": direction_x,
                "direction_y": direction_y,
                "vector_length": length,
                "head_span": head_span,
                "shape_pressure": shape_pressure,
                "speed_seed": speed_seed,
                "has_base": has_base,
                "base_score": base_score,
                "base_length": base_length,
                "base_start_x": base_start_x,
                "base_start_y": base_start_y,
                "base_end_x": base_end_x,
                "base_end_y": base_end_y,
            },
        )

    def _build_volatility_modifier(self, symbol: OrderedSymbol) -> SpellModifier:
        primitive = symbol.primitive
        strength = 1.0
        if isinstance(primitive, ZigZag):
            changes = max(1, len(primitive.vertices) - 1)
            strength = self._clamp(changes / 3.0, 0.5, 2.2)
        return SpellModifier(
            modifier_id="volatility",
            source_symbol_index=symbol.symbol_index,
            ordinal=symbol.ordinal,
            total=symbol.total,
            payload={"strength": strength},
        )

    def _build_precision_modifier(self, symbol: OrderedSymbol) -> SpellModifier:
        primitive = symbol.primitive
        strength = 1.0
        if isinstance(primitive, Segment):
            length = math.hypot(primitive.end[0] - primitive.start[0], primitive.end[1] - primitive.start[1])
            strength = self._clamp(length / 150.0, 0.4, 2.0)
        return SpellModifier(
            modifier_id="precision",
            source_symbol_index=symbol.symbol_index,
            ordinal=symbol.ordinal,
            total=symbol.total,
            payload={"strength": strength},
        )

    def _build_stability_modifier(self, symbol: OrderedSymbol) -> SpellModifier:
        primitive = symbol.primitive
        strength = 1.0
        if isinstance(primitive, Circle) and primitive.radius is not None:
            strength = self._clamp(float(primitive.radius) / 110.0, 0.4, 2.0)
        return SpellModifier(
            modifier_id="stability",
            source_symbol_index=symbol.symbol_index,
            ordinal=symbol.ordinal,
            total=symbol.total,
            payload={"strength": strength},
        )

    @staticmethod
    def _triangle_strength(vertices: Sequence[tuple[float, float]]) -> float:
        x1, y1 = vertices[0]
        x2, y2 = vertices[1]
        x3, y3 = vertices[2]
        area = abs((x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2)) * 0.5)
        return SpellBuilder._clamp(area / 2200.0, 0.5, 2.6)

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))


class EmergentResolver:
    """
    Résolution émergente d'un sort, pilotée par des règles enregistrables.
    Les règles par défaut exploitent:
    - les features de dessin (vitesse, pression, symétrie),
    - le contexte spatial du graphe (densité de relations).
    """

    def __init__(self) -> None:
        self._rules: list[tuple[str, Callable[[SpellModel, GraphGeo], SpellModel]]] = []
        self._register_default_rules()

    def register_rule(
        self,
        name: str,
        rule: Callable[[SpellModel, GraphGeo], SpellModel],
    ) -> None:
        normalized = (name or "").strip().lower()
        if not normalized:
            raise ValueError("Emergent rule name must not be empty")
        self._rules = [(rule_name, fn) for rule_name, fn in self._rules if rule_name != normalized]
        self._rules.append((normalized, rule))

    def resolve(self, spell_or_draft: Any, graph: GraphGeo) -> Any | None:
        if not isinstance(spell_or_draft, SpellModel):
            return None

        spell = spell_or_draft
        for _, rule in self._rules:
            spell = rule(spell, graph)
        return spell

    def _register_default_rules(self) -> None:
        self.register_rule("drawing_dynamics", self._apply_drawing_dynamics)
        self.register_rule("modifier_chain", self._apply_modifier_chain)
        self.register_rule("modifier_geometry", self._apply_modifier_geometry)
        self.register_rule("graph_dynamics", self._apply_graph_dynamics)

    def _apply_drawing_dynamics(self, spell: SpellModel, graph: GraphGeo) -> SpellModel:
        _ = graph
        speed_norm = self._feature(spell, "drawing_speed_norm", fallback_from="drawing_avg_speed", scale=680.0)
        pressure_supported = self._feature(spell, "drawing_pressure_supported", 0.0)
        pressure_norm = self._feature(
            spell,
            "drawing_pressure_norm",
            fallback_from="drawing_avg_pressure",
            scale=1.0,
        )
        symmetry_score = self._feature(spell, "drawing_symmetry_score", 0.5)
        speed_variability = self._feature(spell, "drawing_speed_variability", 0.0)

        speed_norm = self._clamp(speed_norm, 0.0, 1.0)
        symmetry_score = self._clamp(symmetry_score, 0.0, 1.0)
        speed_variability = self._clamp(speed_variability, 0.0, 1.0)

        if pressure_supported < 0.5:
            pressure_norm = 0.5
        pressure_norm = self._clamp(pressure_norm, 0.0, 1.0)

        damage_multiplier = 0.85 + 0.35 * pressure_norm + 0.18 * speed_norm
        duration_multiplier = 0.78 + 0.26 * symmetry_score + 0.12 * (1.0 - speed_norm)
        tick_interval_multiplier = 1.0 - 0.20 * speed_norm - 0.10 * pressure_norm + 0.08 * symmetry_score
        tick_interval_multiplier = self._clamp(tick_interval_multiplier, 0.55, 1.35)

        base_damage = spell.get_float("damage_per_tick", 12.0)
        base_duration = spell.get_float("duration", 2.4)
        base_tick_interval = spell.get_float("tick_interval", 0.20)
        base_cast_bonus = spell.get_float("cast_distance_bonus", 0.0)
        base_hitbox = spell.get_float("hitbox_radius", 18.0)

        spell.params["damage_per_tick"] = max(0.0, base_damage * damage_multiplier)
        spell.params["duration"] = max(0.15, base_duration * duration_multiplier)
        spell.params["tick_interval"] = max(0.05, base_tick_interval * tick_interval_multiplier)
        spell.params["cast_distance_bonus"] = max(0.0, base_cast_bonus + 36.0 * speed_norm)
        spell.params["hitbox_radius"] = max(1.0, base_hitbox * (0.92 + 0.16 * pressure_norm))
        spell.params["emergent_speed"] = speed_norm
        spell.params["emergent_pressure"] = pressure_norm
        spell.params["emergent_symmetry"] = symmetry_score
        spell.params["emergent_variability"] = speed_variability
        return spell

    def _apply_modifier_chain(self, spell: SpellModel, graph: GraphGeo) -> SpellModel:
        _ = graph
        modifiers = spell.modifiers
        if not modifiers:
            spell.params.setdefault("emergent_chain_intensity", 0.0)
            spell.params.setdefault("emergent_chain_synergy", 0.0)
            spell.params.setdefault("emergent_chain_diversity", 0.0)
            return spell

        strengths_by_id: dict[str, float] = {}
        strength_sum = 0.0
        order_sum = 0.0
        placement_sum = 0.0

        for modifier in modifiers:
            payload = modifier.payload
            strength = self._clamp(self._as_float(payload.get("strength"), 1.0), 0.1, 3.0)
            strength_sum += strength
            strengths_by_id[modifier.modifier_id] = strengths_by_id.get(modifier.modifier_id, 0.0) + strength
            order_sum += self._as_float(payload.get("order_factor"), 1.0)
            placement_sum += self._as_float(payload.get("placement_factor"), 1.0)

        count = float(len(modifiers))
        avg_strength = strength_sum / max(1.0, count)
        diversity = len(strengths_by_id) / max(1.0, count)
        order_mean = order_sum / max(1.0, count)
        placement_mean = placement_sum / max(1.0, count)
        order_norm = self._clamp((order_mean - 0.8) / 0.45, 0.0, 1.0)
        placement_norm = self._clamp((placement_mean - 0.8) / 0.55, 0.0, 1.0)

        chain_intensity = self._clamp((avg_strength / 1.4) * (0.75 + 0.45 * diversity), 0.0, 3.0)
        synergy = self._clamp(0.35 * diversity + 0.35 * order_norm + 0.30 * placement_norm, 0.0, 1.0)

        power_strength = strengths_by_id.get("power", 0.0)
        reach_strength = strengths_by_id.get("reach", 0.0)
        volatility_strength = strengths_by_id.get("volatility", 0.0)
        precision_strength = strengths_by_id.get("precision", 0.0)
        stability_strength = strengths_by_id.get("stability", 0.0)

        damage = spell.get_float("damage_per_tick", 12.0)
        duration = spell.get_float("duration", 2.4)
        tick_interval = spell.get_float("tick_interval", 0.20)

        damage_factor = self._clamp(
            1.0 + 0.08 * power_strength + 0.05 * precision_strength + 0.10 * chain_intensity * synergy,
            0.65,
            2.8,
        )
        duration_factor = self._clamp(
            1.0 + 0.06 * stability_strength - 0.04 * volatility_strength + 0.06 * chain_intensity * (1.0 - 0.4 * synergy),
            0.45,
            2.6,
        )
        tick_factor = self._clamp(
            1.0 - 0.05 * volatility_strength + 0.03 * stability_strength - 0.04 * chain_intensity * synergy,
            0.45,
            1.8,
        )

        spell.params["damage_per_tick"] = max(0.0, damage * damage_factor)
        spell.params["duration"] = max(0.15, duration * duration_factor)
        spell.params["tick_interval"] = max(0.05, tick_interval * tick_factor)

        reach_boost = max(0.0, reach_strength) * (22.0 + 18.0 * synergy)
        spell.params["cast_distance_bonus"] = max(0.0, spell.get_float("cast_distance_bonus", 0.0) + reach_boost)
        spell.params["move_speed_bonus"] = max(0.0, spell.get_float("move_speed_bonus", 0.0) + reach_boost * (0.55 + 0.35 * synergy))
        spell.params["shape_pressure"] = max(0.0, spell.get_float("shape_pressure", 0.0) + max(0.0, reach_strength) * 0.12 * synergy)
        spell.params["emergent_chain_intensity"] = chain_intensity
        spell.params["emergent_chain_synergy"] = synergy
        spell.params["emergent_chain_diversity"] = diversity
        return spell

    def _apply_modifier_geometry(self, spell: SpellModel, graph: GraphGeo) -> SpellModel:
        _ = graph
        motion_x = spell.get_float("motion_vector_x", 0.0)
        motion_y = spell.get_float("motion_vector_y", 0.0)
        shape_pressure = max(0.0, spell.get_float("shape_pressure", 0.0))
        move_speed_bonus = max(0.0, spell.get_float("move_speed_bonus", 0.0))

        base_radius = max(1.0, spell.get_float("hitbox_radius", 16.0))
        motion_magnitude = math.hypot(motion_x, motion_y)
        if motion_magnitude <= 1e-6:
            spell.params["shape"] = "circle"
            spell.params["hitbox_radius_x"] = base_radius
            spell.params["hitbox_radius_y"] = base_radius
            spell.params["ellipse_angle"] = 0.0
            spell.params["velocity_x"] = 0.0
            spell.params["velocity_y"] = 0.0
            return spell

        direction_x = motion_x / motion_magnitude
        direction_y = motion_y / motion_magnitude
        speed_norm = self._feature(spell, "drawing_speed_norm", 0.0)

        elongation = self._clamp(1.0 + 0.28 * shape_pressure + 0.22 * motion_magnitude, 1.0, 2.5)
        compression = self._clamp(1.0 / max(1.0, 0.22 * shape_pressure + 0.30 * motion_magnitude), 0.45, 1.0)
        radius_x = max(1.0, base_radius * elongation)
        radius_y = max(1.0, base_radius * compression)

        speed = move_speed_bonus + 90.0 * motion_magnitude + 120.0 * self._clamp(speed_norm, 0.0, 1.0)
        speed = self._clamp(speed, 0.0, 620.0)

        spell.params["shape"] = "ellipse"
        spell.params["hitbox_radius_x"] = radius_x
        spell.params["hitbox_radius_y"] = radius_y
        spell.params["ellipse_angle"] = math.atan2(direction_y, direction_x)
        spell.params["velocity_x"] = direction_x * speed
        spell.params["velocity_y"] = direction_y * speed
        return spell

    def _apply_graph_dynamics(self, spell: SpellModel, graph: GraphGeo) -> SpellModel:
        relations = graph.build_spatial_relations()
        primitives_count = max(1, len(graph.iter_primitives()))
        near_count = sum(1 for relation in relations if relation.relation == "near")
        intersects_count = sum(1 for relation in relations if relation.relation == "intersects")

        density = self._clamp((near_count + intersects_count * 1.5) / (primitives_count * 3.0), 0.0, 1.0)
        if density <= 0.0:
            spell.params.setdefault("emergent_graph_density", 0.0)
            return spell

        base_tick_interval = spell.get_float("tick_interval", 0.20)
        base_duration = spell.get_float("duration", 2.4)
        spell.params["tick_interval"] = max(0.05, base_tick_interval * (1.0 - 0.18 * density))
        spell.params["duration"] = max(0.15, base_duration * (1.0 - 0.10 * density))
        spell.params["emergent_graph_density"] = density
        return spell

    @staticmethod
    def _feature(
        spell: SpellModel,
        key: str,
        default: float = 0.0,
        *,
        fallback_from: str | None = None,
        scale: float = 1.0,
    ) -> float:
        raw = spell.drawing_features.get(key)
        if raw is None and fallback_from is not None:
            raw = spell.drawing_features.get(fallback_from)
            if raw is not None and scale > 1e-9:
                try:
                    return float(raw) / scale
                except (TypeError, ValueError):
                    return float(default)
        if raw is None:
            return float(default)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _as_float(value: object, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))


class GraphSpellPipeline:
    """
    Chaîne complète:
    graphe -> lecture ordonnée -> draft de sort -> résolution émergente.
    """

    def __init__(
        self,
        builder: SpellBuilder | None = None,
        resolver: EmergentResolver | None = None,
        rune_registry: RuneRegistry | None = None,
    ) -> None:
        self.builder = builder or SpellBuilder(rune_registry=rune_registry)
        self.resolver = resolver or EmergentResolver()

    def process_circle_plan(
        self,
        plan: CircleReadingPlan,
        primitives: Sequence[Any],
        execution: Sequence[CircleSubSymbolExecutionContext],
        graph: GraphGeo,
    ) -> Any | None:
        draft = self.builder.build_draft(plan, primitives, execution)
        spell = self.builder.create_spell(draft, graph=graph)
        base = spell if spell is not None else draft
        resolved = self.resolver.resolve(base, graph)
        return resolved if resolved is not None else base
