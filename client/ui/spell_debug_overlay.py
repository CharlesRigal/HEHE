"""Overlay de debug in-game pour le pipeline de sorts.

Touches :
  F5          — afficher / masquer l'overlay
  [           — vue précédente
  ]           — vue suivante

8 vues :
  1. PRIMITIVES   — primitives reconnues avec confidence
  2. GRAPH        — relations spatiales (GraphGeo)
  3. AST          — arbre de symboles indenté
  4. PASS1        — PropertyBags après passe bottom-up
  5. PASS2        — PropertyBags après passe top-down (entrées propagées marquées)
  6. PASS3        — Entrées cross-node (interférences)
  7. PARAMS       — Paramètres résolus finaux
  8. NETWORK      — Dict réseau envoyé au serveur
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pygame

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Dataclass centrale — capturée après chaque cast
# ---------------------------------------------------------------------------

@dataclass
class SpellDebugData:
    primitives: list
    spatial_relations: list
    ast: Any                            # SpellAST
    pass1_bags: dict[str, Any]          # dict[node_id, PropertyBag]
    pass2_bags: dict[str, Any]          # dict[node_id, PropertyBag]
    cross_entries: list                 # list[PropertyEntry]
    resolved_params: dict
    network_spec: dict
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Noms des 8 stages
# ---------------------------------------------------------------------------

STAGES = [
    "PRIMITIVES",
    "GRAPH",
    "AST",
    "PASS1 (bottom-up)",
    "PASS2 (top-down)",
    "PASS3 (cross-node)",
    "PARAMS",
    "NETWORK",
]
NUM_STAGES = len(STAGES)

# Couleurs
_BG       = (8,   12,  18,  185)
_BORDER   = (92,  170, 255, 210)
_TITLE    = (255, 220, 80)
_TEXT     = (230, 244, 255)
_DIM      = (150, 170, 190)
_ACTIVE   = (120, 220, 120)
_WARN     = (255, 160, 60)
_KEY_HINT = (100, 140, 180)

_PANEL_W  = 420
_PANEL_X  = 12   # à droite — calculé dynamiquement dans draw()
_PANEL_Y  = 12
_PAD      = 8
_LH       = 17   # line height
_MAX_LINES = 35  # nombre max de lignes affichées (scroll non implémenté)


class SpellDebugOverlay:
    def __init__(self, game: Any):
        self._game = game
        self.visible: bool = False
        self._stage: int = 0          # index dans STAGES
        self._data: SpellDebugData | None = None
        self._font_size = 15

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def toggle(self) -> None:
        self.visible = not self.visible

    def set_data(self, data: SpellDebugData) -> None:
        self._data = data

    def next_stage(self) -> None:
        self._stage = (self._stage + 1) % NUM_STAGES

    def prev_stage(self) -> None:
        self._stage = (self._stage - 1) % NUM_STAGES

    # ------------------------------------------------------------------
    # Rendu
    # ------------------------------------------------------------------

    def draw(self, screen: pygame.Surface) -> None:
        if not self.visible:
            return

        font = self._game._get_font(self._font_size)
        lines = self._build_lines()

        # Tronquer si trop long
        if len(lines) > _MAX_LINES:
            lines = lines[:_MAX_LINES] + [("...", _DIM)]

        # Calculer taille du panel
        max_text_w = max((font.size(text)[0] for text, _ in lines), default=200)
        panel_w = max(max_text_w + _PAD * 2, _PANEL_W)
        panel_h = len(lines) * _LH + _PAD * 2

        # Positionner à droite de l'écran
        screen_w = screen.get_width()
        panel_x = max(screen_w - panel_w - 12, 12)
        panel_y = _PANEL_Y

        # Surface semi-transparente
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill(_BG)
        pygame.draw.rect(panel, _BORDER, panel.get_rect(), width=1)
        screen.blit(panel, (panel_x, panel_y))

        # Texte
        tx = panel_x + _PAD
        ty = panel_y + _PAD
        for text, color in lines:
            surf = font.render(text, True, color)
            screen.blit(surf, (tx, ty))
            ty += _LH

    # ------------------------------------------------------------------
    # Construction du contenu par stage
    # ------------------------------------------------------------------

    def _build_lines(self) -> list[tuple[str, tuple]]:
        lines: list[tuple[str, tuple]] = []

        # ── En-tête ──
        stage_name = STAGES[self._stage]
        lines.append((f"SPELL DEBUG  F5:close  [:prev  ]:next", _KEY_HINT))
        lines.append((f"> {self._stage + 1}/{NUM_STAGES}  {stage_name} <", _TITLE))
        lines.append(("-" * 44, _DIM))

        if self._data is None:
            lines.append(("(aucun sort casté depuis le lancement)", _DIM))
            return lines

        import datetime
        ts = datetime.datetime.fromtimestamp(self._data.timestamp).strftime("%H:%M:%S")
        lines.append((f"cast @ {ts}", _DIM))
        lines.append(("", _TEXT))

        # ── Contenu selon le stage ──
        builders = [
            self._lines_primitives,
            self._lines_graph,
            self._lines_ast,
            self._lines_pass1,
            self._lines_pass2,
            self._lines_pass3,
            self._lines_params,
            self._lines_network,
        ]
        lines.extend(builders[self._stage]())
        return lines

    # ── Stage 1 : Primitives ──────────────────────────────────────────

    def _lines_primitives(self) -> list[tuple[str, tuple]]:
        lines = []
        primitives = self._data.primitives  # type: ignore[union-attr]
        if not primitives:
            lines.append(("(aucune primitive reconnue)", _DIM))
            return lines
        lines.append((f"{len(primitives)} primitive(s):", _TEXT))
        for i, p in enumerate(primitives):
            kind = getattr(p, "kind", type(p).__name__)
            conf = getattr(p, "confidence", None)
            meta = getattr(p, "meta", {})
            conf_str = f"conf={conf:.2f}" if conf is not None else ""
            # Quelques features clés selon le type
            feat_parts = []
            if kind == "circle":
                r = getattr(p, "radius", None)
                if r is not None:
                    feat_parts.append(f"r={r:.1f}")
            elif kind in ("arrow", "arrow_with_base"):
                tail = getattr(p, "tail", None)
                tip = getattr(p, "tip", None)
                if tail and tip:
                    import math
                    dx, dy = tip[0] - tail[0], tip[1] - tail[1]
                    ang = math.degrees(math.atan2(dy, dx))
                    feat_parts.append(f"angle={ang:.0f}°")
            elif kind == "triangle":
                verts = getattr(p, "vertices", None) or []
                feat_parts.append(f"verts={len(verts)}")
            elif kind == "zigzag":
                pts = getattr(p, "_points", None) or []
                feat_parts.append(f"segs={len(pts)}")
            elif kind == "rune_fire":
                cuts = meta.get("cut_count", "?")
                feat_parts.append(f"cuts={cuts}")

            feat_str = "  " + "  ".join(feat_parts) if feat_parts else ""
            color = _ACTIVE if conf is not None and conf > 0.7 else _WARN if conf is not None and conf < 0.5 else _TEXT
            lines.append((f"  [{i}] {kind}  {conf_str}{feat_str}", color))
        return lines

    # ── Stage 2 : Graph (relations spatiales) ─────────────────────────

    def _lines_graph(self) -> list[tuple[str, tuple]]:
        lines = []
        relations = self._data.spatial_relations  # type: ignore[union-attr]
        primitives = self._data.primitives  # type: ignore[union-attr]

        def _kind(idx: int) -> str:
            if 0 <= idx < len(primitives):
                return getattr(primitives[idx], "kind", f"#{idx}")
            return f"#{idx}"

        if not relations:
            lines.append(("(aucune relation spatiale)", _DIM))
            return lines
        lines.append((f"{len(relations)} relation(s):", _TEXT))
        for rel in relations:
            src = getattr(rel, "source_index", "?")
            tgt = getattr(rel, "target_index", "?")
            rtype = getattr(rel, "relation", "?")
            weight = getattr(rel, "weight", None)
            w_str = f"  w={weight:.2f}" if weight is not None else ""
            color = _ACTIVE if rtype == "contains" else _TEXT
            lines.append((f"  {_kind(src)} → {_kind(tgt)}  [{rtype}]{w_str}", color))
        return lines

    # ── Stage 3 : AST ─────────────────────────────────────────────────

    def _lines_ast(self) -> list[tuple[str, tuple]]:
        lines = []
        ast = self._data.ast  # type: ignore[union-attr]
        if ast.root is None:
            lines.append(("(AST vide — aucune primitive)", _DIM))
            return lines
        lines.append((f"depth={ast.depth}  nodes={ast.node_count}", _TEXT))
        lines.append(("", _TEXT))
        self._render_node(ast.root, "", True, lines)
        return lines

    def _render_node(self, node: Any, prefix: str, is_last: bool, lines: list) -> None:
        connector = "└─" if is_last else "├─"
        sym = node.symbol_type
        role = node.spatial_role
        feats = node.drawing_features or {}
        feat_str = "  " + "  ".join(f"{k}={v:.2f}" for k, v in list(feats.items())[:3])
        color = _TITLE if node.depth == 0 else _TEXT
        lines.append((f"{prefix}{connector} {sym} (d={node.depth} ord={node.ordinal}) [{role}]{feat_str}", color))
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, child in enumerate(node.children):
            self._render_node(child, child_prefix, i == len(node.children) - 1, lines)

    # ── Stage 4 : Pass1 bags (bottom-up) ──────────────────────────────

    def _lines_pass1(self) -> list[tuple[str, tuple]]:
        return self._lines_bags(self._data.pass1_bags, propagated_suffix=None)  # type: ignore[union-attr]

    # ── Stage 5 : Pass2 bags (top-down) ───────────────────────────────

    def _lines_pass2(self) -> list[tuple[str, tuple]]:
        return self._lines_bags(self._data.pass2_bags, propagated_suffix="_propagated")  # type: ignore[union-attr]

    def _lines_bags(self, bags: dict, propagated_suffix: str | None) -> list[tuple[str, tuple]]:
        lines = []
        if not bags:
            lines.append(("(aucune donnée)", _DIM))
            return lines
        for node_id, bag in bags.items():
            entries = getattr(bag, "entries", [])
            lines.append((f"{node_id}  ({len(entries)} entrées)", _TITLE))
            for e in entries:
                tag = e.tag
                label = f"    {tag.domain}.{tag.axis}.{tag.scope}"
                val_str = f"= {e.value:.3f}  w={e.weight:.3f}"
                is_prop = propagated_suffix and e.source_node_id.endswith(propagated_suffix)
                suffix = "  [prop]" if is_prop else ""
                color = _WARN if is_prop else _TEXT
                lines.append((f"{label}  {val_str}{suffix}", color))
        return lines

    # ── Stage 6 : Pass3 cross-node ────────────────────────────────────

    def _lines_pass3(self) -> list[tuple[str, tuple]]:
        lines = []
        entries = self._data.cross_entries  # type: ignore[union-attr]
        if not entries:
            lines.append(("(aucune interaction cross-node)", _DIM))
            return lines
        lines.append((f"{len(entries)} entrée(s) cross-node:", _TEXT))
        for e in entries:
            tag = e.tag
            lines.append((
                f"  {tag.domain}.{tag.axis}.{tag.scope}  = {e.value:.3f}  w={e.weight:.3f}",
                _ACTIVE,
            ))
            lines.append((f"    src: {e.source_node_id}", _DIM))
        return lines

    # ── Stage 7 : Params résolus ──────────────────────────────────────

    def _lines_params(self) -> list[tuple[str, tuple]]:
        lines = []
        params = self._data.resolved_params  # type: ignore[union-attr]
        if not params:
            lines.append(("(paramètres vides)", _DIM))
            return lines
        for k, v in sorted(params.items()):
            if isinstance(v, float):
                val_str = f"{v:.4f}"
                color = _ACTIVE if v > 0.5 else _TEXT
            elif isinstance(v, bool):
                val_str = str(v)
                color = _WARN if v else _DIM
            else:
                val_str = str(v)
                color = _TITLE if k in ("element", "behavior") else _TEXT
            lines.append((f"  {k:<20s} = {val_str}", color))
        return lines

    # ── Stage 8 : Network spec ────────────────────────────────────────

    def _lines_network(self) -> list[tuple[str, tuple]]:
        lines = []
        spec = self._data.network_spec  # type: ignore[union-attr]
        if not spec:
            lines.append(("(spec réseau vide)", _DIM))
            return lines
        for k, v in spec.items():
            if isinstance(v, float):
                val_str = f"{v:.4f}"
            elif isinstance(v, (list, tuple)):
                val_str = f"[{', '.join(f'{x:.3f}' for x in v)}]"
            else:
                val_str = str(v)
            color = _TITLE if k == "t" else _TEXT
            lines.append((f"  {k:<6s}: {val_str}", color))
        return lines
