"""
role_resolver.py — Résolution par rôle spatial.

La position dans l'AST donne un rôle sémantique :
  - Racine avec enfants       -> Form  (comment le sort se déplace)
  - Feuille                   -> Substance (ce que le sort fait)
  - Nœud intermédiaire        -> Trigger (quand/comment la phase suivante s'active)
  - Peer racine sans enfants  -> Form+Substance combiné (sort simple)

Chaque rôle a son propre resolver qui produit un descripteur typé.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from client.magic.resolver.spell_intent import (
    FormDescriptor,
    SpellIntent,
    SpellPhase,
    SubstanceDescriptor,
    TriggerDescriptor,
)

if TYPE_CHECKING:
    from client.magic.ast.ast import ASTNode, SpellAST


# ---------------------------------------------------------------------------
# Élément émergent (réutilise la logique de symbol_rules)
# ---------------------------------------------------------------------------

def _element_from_features(f: dict) -> str:
    angularity = float(f.get("angularity", 0.3))
    linearity = float(f.get("linearity", 0.0))
    compactness = float(f.get("compactness", 0.5))
    closure = float(f.get("closure", 0.0))
    is_directional = float(f.get("is_directional", 0.0))

    heat = angularity * (1.0 - closure)
    precision = linearity * is_directional * (1.0 - angularity * 0.4)
    arcane = linearity * (1.0 - is_directional) * (1.0 - angularity)
    cold = compactness * closure * (1.0 - angularity)

    val = 0.5 + heat * 0.5 + precision * 0.25 + arcane * 0.05 - cold * 0.4
    val = max(0.0, min(1.0, val))

    if val > 0.82:
        return "fire"
    elif val > 0.65:
        return "lightning"
    elif val > 0.42:
        return "arcane"
    elif val < 0.22:
        return "ice"
    return "neutral"


# ---------------------------------------------------------------------------
# Form resolver
# ---------------------------------------------------------------------------

def resolve_form(node: "ASTNode") -> FormDescriptor:
    """Géométrie du nœud racine -> type de livraison."""
    f = node.drawing_features
    compactness = float(f.get("compactness", 0.5))
    elongation = max(1.0, float(f.get("elongation", 1.0)))
    closure = float(f.get("closure", 0.0))
    linearity = float(f.get("linearity", 0.0))
    angularity = float(f.get("angularity", 0.3))
    area_n = float(f.get("area_n", 0.2))
    direction_n = float(f.get("direction_n", 0.0))
    is_directional = float(f.get("is_directional", 0.0))

    angle_rad = direction_n * 2.0 * math.pi
    dir_x = math.cos(angle_rad)
    dir_y = math.sin(angle_rad)

    # Ancres discrètes avec seuils stables
    if linearity > 0.5 and is_directional > 0.5:
        form_type = "projectile"
        speed = 0.3 + linearity * 0.5
    elif elongation > 2.5 and linearity > 0.4 and is_directional < 0.5:
        form_type = "wall"
        speed = 0.0
    elif angularity > 0.35 and is_directional > 0.3:
        form_type = "cone"
        speed = 0.0
    elif compactness > 0.6 and closure > 0.6:
        if area_n > 0.25:
            form_type = "aoe"
        else:
            form_type = "shield"
        speed = 0.0
    else:
        form_type = "aoe"
        speed = 0.0

    elonga_n = (elongation - 1.0) / elongation if elongation > 1.0 else 0.0
    ax_x = math.cos(angle_rad) * elonga_n
    ax_y = math.sin(angle_rad) * elonga_n

    return FormDescriptor(
        form_type=form_type,
        speed=speed,
        spread=compactness * closure * area_n,
        direction=(dir_x, dir_y),
        axis=(ax_x, ax_y),
        elongation=elongation,
        radius=area_n,
        duration=closure * area_n,
    )


# ---------------------------------------------------------------------------
# Substance resolver
# ---------------------------------------------------------------------------

def resolve_substance(node: "ASTNode") -> SubstanceDescriptor:
    """Géométrie + élément du nœud feuille -> type d'effet."""
    f = node.drawing_features
    element = _element_from_features(f)

    compactness = float(f.get("compactness", 0.5))
    elongation = max(1.0, float(f.get("elongation", 1.0)))
    closure = float(f.get("closure", 0.0))
    linearity = float(f.get("linearity", 0.0))
    angularity = float(f.get("angularity", 0.3))
    area_n = float(f.get("area_n", 0.2))
    is_directional = float(f.get("is_directional", 0.0))

    # Poids d'intensité basé sur la taille et l'angularité
    intensity = max(0.1, angularity * 0.4 + area_n * 0.3 + compactness * 0.3)

    extra: dict = {}

    # Élément + géométrie -> type d'effet
    # Gel : froid + compact + fermé
    if element == "ice" and compactness > 0.5 and closure > 0.5:
        effect_type = "freeze"
        extra["freeze_duration"] = 2.0 + area_n * 6.0

    # Création de terrain : linéaire + allongé + pas directionnel (segment)
    elif elongation > 2.0 and linearity > 0.4 and is_directional < 0.5:
        effect_type = "create"
        extra["terrain_type"] = "bridge"
        extra["traversable"] = True
        extra["width"] = 20.0 + elongation * 10.0
        extra["length"] = 40.0 + elongation * 30.0

    # Transmutation : arcane + anguleux
    elif element in ("arcane", "neutral") and angularity > 0.3 and compactness < 0.5:
        effect_type = "transmute"
        extra["to_material"] = "dust"

    # Poussée : directionnel + rapide
    elif is_directional > 0.5 and linearity > 0.5:
        effect_type = "push"
        angle_rad = float(f.get("direction_n", 0.0)) * 2.0 * math.pi
        extra["push_x"] = math.cos(angle_rad)
        extra["push_y"] = math.sin(angle_rad)
        extra["push_force"] = linearity * 200.0

    # Dégât : fallback (anguleux = destruction, feu = brûlure, etc.)
    else:
        effect_type = "damage"

    return SubstanceDescriptor(
        effect_type=effect_type,
        element=element,
        intensity=intensity,
        extra=extra,
    )


# ---------------------------------------------------------------------------
# Trigger resolver
# ---------------------------------------------------------------------------

def resolve_trigger(node: "ASTNode") -> TriggerDescriptor:
    """Nœud intermédiaire -> connecteur temporel."""
    f = node.drawing_features
    compactness = float(f.get("compactness", 0.5))
    angularity = float(f.get("angularity", 0.3))
    area_n = float(f.get("area_n", 0.2))
    closure = float(f.get("closure", 0.0))
    convexity = float(f.get("convexity", 0.8))
    is_directional = float(f.get("is_directional", 0.0))

    # Triangle / anguleux -> split (on_impact ou on_expire)
    if angularity > 0.3 and compactness < 0.6:
        count = 3 if angularity > 0.5 else 2
        if is_directional > 0.3:
            trigger_type = "on_impact"
        else:
            trigger_type = "on_expire"
        delay = 0.0
    # Cercle intermédiaire -> délai temporel (taille = durée)
    elif compactness > 0.5 and closure > 0.5:
        trigger_type = "after_delay"
        delay = 1.0 + area_n * 5.0  # 1-6 secondes selon la taille
        count = 1
    # Zigzag / non-convexe -> périodique
    elif convexity < 0.5 and angularity > 0.2:
        trigger_type = "periodic"
        delay = 0.5 + (1.0 - angularity) * 2.0  # intervalle
        count = 1
    # Fallback : on_expire
    else:
        trigger_type = "on_expire"
        delay = 0.0
        count = 1

    return TriggerDescriptor(
        trigger_type=trigger_type,
        delay=delay,
        count=count,
        next_phase=-1,  # sera rempli par l'assembleur de phases
    )


# ---------------------------------------------------------------------------
# Rôle assignment + assemblage de phases
# ---------------------------------------------------------------------------

ROLE_FORM = "form"
ROLE_SUBSTANCE = "substance"
ROLE_TRIGGER = "trigger"
ROLE_FORM_SUBSTANCE = "form+substance"


def assign_roles(root: "ASTNode") -> dict[str, str]:
    """Assigne un rôle à chaque nœud selon sa position dans l'arbre."""
    roles: dict[str, str] = {}
    _assign_roles_recursive(root, roles, is_root=True)
    return roles


def _assign_roles_recursive(
    node: "ASTNode",
    roles: dict[str, str],
    is_root: bool,
) -> None:
    has_children = len(node.children) > 0

    if node.symbol_type == "root":
        # Nœud virtuel : pas de rôle, juste propagation
        roles[node.node_id] = "virtual_root"
        for child in node.children:
            _assign_roles_recursive(child, roles, is_root=True)
        return

    if is_root and has_children:
        roles[node.node_id] = ROLE_FORM
    elif is_root and not has_children:
        roles[node.node_id] = ROLE_FORM_SUBSTANCE
    elif not is_root and not has_children:
        roles[node.node_id] = ROLE_SUBSTANCE
    elif not is_root and has_children:
        roles[node.node_id] = ROLE_TRIGGER
    else:
        roles[node.node_id] = ROLE_FORM_SUBSTANCE

    for child in node.children:
        _assign_roles_recursive(child, roles, is_root=False)


def resolve_intent(ast: "SpellAST") -> SpellIntent:
    """Point d'entrée principal : AST -> SpellIntent multi-phases."""
    if ast.root is None:
        return SpellIntent(phases=[], power=0.0)

    roles = assign_roles(ast.root)

    # Collecter les chemins racine->feuille
    paths: list[list["ASTNode"]] = []
    _collect_paths(ast.root, [], paths, roles)

    if not paths:
        return SpellIntent(phases=[], power=0.0)

    # Construire les phases depuis les chemins
    phases: list[SpellPhase] = []
    element_dominant = "neutral"

    for path in paths:
        form_node = None
        substance_node = None
        trigger_node = None

        for node in path:
            role = roles.get(node.node_id, "")
            if role == ROLE_FORM:
                form_node = node
            elif role == ROLE_SUBSTANCE:
                substance_node = node
            elif role == ROLE_TRIGGER:
                trigger_node = node
            elif role == ROLE_FORM_SUBSTANCE:
                form_node = node
                substance_node = node

        # Résoudre chaque composant
        form = resolve_form(form_node) if form_node else FormDescriptor()
        substance = resolve_substance(substance_node) if substance_node else SubstanceDescriptor()

        trigger = None
        if trigger_node is not None:
            trigger = resolve_trigger(trigger_node)

        # L'élément dominant vient de la Form
        if form_node and element_dominant == "neutral":
            element_dominant = _element_from_features(form_node.drawing_features)

        phases.append(SpellPhase(form=form, substance=substance, trigger=trigger))

    # Relier les triggers aux phases suivantes
    for i, phase in enumerate(phases):
        if phase.trigger is not None and phase.trigger.next_phase == -1:
            if i + 1 < len(phases):
                phase.trigger.next_phase = i + 1

    # Power = moyenne des intensités des substances
    intensities = [p.substance.intensity for p in phases]
    power = sum(intensities) / len(intensities) if intensities else 0.5

    # Adapter form_type si substance l'exige
    # Ex: substance=create + form=aoe -> le form reste aoe (placement de terrain)
    # Ex: substance=freeze + form=aoe -> ok
    # Ex: substance=push + form=projectile -> ok
    for phase in phases:
        if phase.substance.effect_type == "create" and phase.form.form_type == "wall":
            # Un wall-form avec substance create = on place un mur/pont
            pass
        if phase.substance.effect_type == "create" and phase.form.form_type == "projectile":
            # Projectile de création -> on force aoe au point d'impact
            phase.form.form_type = "aoe"
            phase.form.speed = 0.0

    return SpellIntent(
        phases=phases,
        power=power,
        element=element_dominant,
        debug_roles=roles,
    )


def _collect_paths(
    node: "ASTNode",
    current_path: list["ASTNode"],
    paths: list[list["ASTNode"]],
    roles: dict[str, str],
) -> None:
    """Collecte tous les chemins racine->feuille."""
    role = roles.get(node.node_id, "")

    if role == "virtual_root":
        for child in node.children:
            _collect_paths(child, [], paths, roles)
        return

    current_path = current_path + [node]

    if not node.children:
        paths.append(current_path)
    else:
        for child in node.children:
            _collect_paths(child, current_path, paths, roles)


# ---------------------------------------------------------------------------
# Test de validation
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from client.magic.ast.ast import ASTNode, SpellAST

    def make_node(nid, symbol, depth, feats, children=None):
        node = ASTNode(
            node_id=nid, symbol_type=symbol, primitive=None,
            depth=depth, ordinal=0, sibling_count=1,
            spatial_role="peer", drawing_features=feats,
        )
        if children:
            node.children = children
        return node

    CIRCLE_FEATS = {
        "compactness": 0.95, "elongation": 1.05, "closure": 0.98,
        "linearity": 0.01, "angularity": 0.0, "area_n": 0.4,
        "scale_n": 0.6, "direction_n": 0.0, "convexity": 1.0,
        "is_directional": 0.0, "confidence": 1.0,
    }
    SMALL_CIRCLE_FEATS = {
        **CIRCLE_FEATS, "area_n": 0.15, "scale_n": 0.2,
    }
    ARROW_FEATS = {
        "compactness": 0.0, "elongation": 10.0, "closure": 0.0,
        "linearity": 1.0, "angularity": 0.0, "area_n": 0.0,
        "scale_n": 0.15, "direction_n": 0.0, "convexity": 1.0,
        "is_directional": 1.0, "confidence": 1.0,
    }
    SEGMENT_FEATS = {
        "compactness": 0.0, "elongation": 8.0, "closure": 0.0,
        "linearity": 1.0, "angularity": 0.0, "area_n": 0.0,
        "scale_n": 0.12, "direction_n": 0.25, "convexity": 1.0,
        "is_directional": 0.0, "confidence": 1.0,
    }
    TRIANGLE_FEATS = {
        "compactness": 0.5, "elongation": 1.3, "closure": 0.8,
        "linearity": 0.2, "angularity": 0.65, "area_n": 0.2,
        "scale_n": 0.25, "direction_n": 0.0, "convexity": 0.7,
        "is_directional": 0.4, "confidence": 1.0,
    }
    ZIGZAG_FEATS = {
        "compactness": 0.05, "elongation": 2.0, "closure": 0.05,
        "linearity": 0.3, "angularity": 0.8, "area_n": 0.05,
        "scale_n": 0.2, "direction_n": 0.0, "convexity": 0.3,
        "is_directional": 0.0, "confidence": 1.0,
    }

    # ── Test 1 : Triangle seul -> cone + damage ──────────────────────
    tri = make_node("n0_tri", "triangle", 0, TRIANGLE_FEATS)
    ast1 = SpellAST(root=tri, all_nodes=[tri], depth=0, node_count=1, spatial_relations=[])
    intent1 = resolve_intent(ast1)
    assert len(intent1.phases) == 1
    p = intent1.phases[0]
    print(f"Triangle seul: form={p.form.form_type} sub={p.substance.effect_type} element={p.substance.element}")
    assert p.form.form_type == "cone", f"Expected cone, got {p.form.form_type}"
    print("[PASS] Triangle seul -> cone")

    # ── Test 2 : Cercle > Petit cercle (ice) -> aoe + freeze ─────────
    inner = make_node("n1_circle", "circle", 1, SMALL_CIRCLE_FEATS)
    outer = make_node("n0_circle", "circle", 0, CIRCLE_FEATS, children=[inner])
    ast2 = SpellAST(root=outer, all_nodes=[outer, inner], depth=1, node_count=2, spatial_relations=[])
    intent2 = resolve_intent(ast2)
    assert len(intent2.phases) == 1
    p2 = intent2.phases[0]
    print(f"Cercle>Cercle: form={p2.form.form_type} sub={p2.substance.effect_type} element={p2.substance.element}")
    assert p2.form.form_type == "aoe", f"Expected aoe, got {p2.form.form_type}"
    assert p2.substance.effect_type == "freeze", f"Expected freeze, got {p2.substance.effect_type}"
    assert p2.substance.element == "ice", f"Expected ice, got {p2.substance.element}"
    print("[PASS] Cercle > Cercle -> aoe + freeze")

    # ── Test 3 : Cercle > Segment -> aoe + create(bridge) ────────────
    seg = make_node("n1_seg", "segment", 1, SEGMENT_FEATS)
    outer3 = make_node("n0_circle", "circle", 0, CIRCLE_FEATS, children=[seg])
    ast3 = SpellAST(root=outer3, all_nodes=[outer3, seg], depth=1, node_count=2, spatial_relations=[])
    intent3 = resolve_intent(ast3)
    p3 = intent3.phases[0]
    print(f"Cercle>Segment: form={p3.form.form_type} sub={p3.substance.effect_type} extra={p3.substance.extra}")
    assert p3.substance.effect_type == "create", f"Expected create, got {p3.substance.effect_type}"
    assert p3.substance.extra.get("terrain_type") == "bridge"
    print("[PASS] Cercle > Segment -> aoe + create(bridge)")

    # ── Test 4 : Arrow > Triangle > ZigZag -> projectile, trigger split, lightning ──
    zz = make_node("n2_zz", "zigzag", 2, ZIGZAG_FEATS)
    tri_mid = make_node("n1_tri", "triangle", 1, TRIANGLE_FEATS, children=[zz])
    arrow_root = make_node("n0_arrow", "arrow", 0, ARROW_FEATS, children=[tri_mid])
    ast4 = SpellAST(
        root=arrow_root,
        all_nodes=[arrow_root, tri_mid, zz],
        depth=2, node_count=3, spatial_relations=[],
    )
    intent4 = resolve_intent(ast4)
    assert len(intent4.phases) == 1  # un seul chemin racine->feuille
    p4 = intent4.phases[0]
    print(f"Arrow>Triangle>ZigZag: form={p4.form.form_type} trigger={p4.trigger.trigger_type if p4.trigger else None} "
          f"count={p4.trigger.count if p4.trigger else 0} sub={p4.substance.effect_type}")
    assert p4.form.form_type == "projectile", f"Expected projectile, got {p4.form.form_type}"
    assert p4.trigger is not None, "Expected trigger"
    assert p4.trigger.count >= 2, f"Expected count >= 2, got {p4.trigger.count}"
    print("[PASS] Arrow > Triangle > ZigZag -> projectile + split trigger")

    # ── Test 5 : Cercle > Triangle (anguleux) -> aoe + transmute ─────
    tri_sub = make_node("n1_tri", "triangle", 1, {
        **TRIANGLE_FEATS, "angularity": 0.6, "compactness": 0.3,
    })
    outer5 = make_node("n0_circle", "circle", 0, CIRCLE_FEATS, children=[tri_sub])
    ast5 = SpellAST(root=outer5, all_nodes=[outer5, tri_sub], depth=1, node_count=2, spatial_relations=[])
    intent5 = resolve_intent(ast5)
    p5 = intent5.phases[0]
    print(f"Cercle>Triangle: form={p5.form.form_type} sub={p5.substance.effect_type} extra={p5.substance.extra}")
    assert p5.substance.effect_type == "transmute", f"Expected transmute, got {p5.substance.effect_type}"
    print("[PASS] Cercle > Triangle -> aoe + transmute")

    # ── Test 6 : Arrow seul -> projectile + damage ────────────────────
    arrow_solo = make_node("n0_arrow", "arrow", 0, ARROW_FEATS)
    ast6 = SpellAST(root=arrow_solo, all_nodes=[arrow_solo], depth=0, node_count=1, spatial_relations=[])
    intent6 = resolve_intent(ast6)
    p6 = intent6.phases[0]
    print(f"Arrow seul: form={p6.form.form_type} sub={p6.substance.effect_type}")
    assert p6.form.form_type == "projectile"
    assert p6.substance.effect_type == "push", f"Expected push, got {p6.substance.effect_type}"
    print("[PASS] Arrow seul -> projectile + push")

    print("\nAll role_resolver assertions passed.")
