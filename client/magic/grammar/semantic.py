"""semantic.py -- resolveur semantique ParseNode -> SpellIntent.

Parcourt l'arbre grammatical et construit une liste de SpellPhase en
consultant la table de composition. Chaque cercle-phrase produit au plus
une phase ; les sous-cercles genrent des phases chainees via
TriggerDescriptor(type="on_expire", next_phase=i+1).

Si AUCUN cercle ne produit une combinaison reconnue par la table,
build_intent() renvoie None et l'appelant peut se rabattre sur le
resolver geometrique emergent.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from client.magic.grammar.composition_table import fuse_elements, lookup
from client.magic.grammar.parser import ParseNode
from client.magic.grammar.tokenizer import subject_element, verb_name
from client.magic.resolver.spell_intent import (
    FormDescriptor,
    SpellIntent,
    SpellPhase,
    SubstanceDescriptor,
    TriggerDescriptor,
)

if TYPE_CHECKING:
    pass


def build_intent(parse_root: ParseNode) -> SpellIntent | None:
    """Produit un SpellIntent a partir d'un ParseNode.  None si aucune
    combinaison reconnue."""
    phases: list[SpellPhase] = []
    debug_roles: dict[str, str] = {}

    _collect_phases(parse_root, phases, debug_roles)

    if not phases:
        return None

    # Chainage sequentiel : chaque phase -> phase suivante via on_expire.
    for i in range(len(phases) - 1):
        phases[i].trigger = TriggerDescriptor(
            trigger_type="on_expire",
            next_phase=i + 1,
        )

    power = sum(p.substance.intensity for p in phases) / len(phases)
    return SpellIntent(
        phases=phases,
        power=power,
        element=phases[0].substance.element,
        debug_roles=debug_roles,
    )


def _collect_phases(
    node: ParseNode,
    phases: list[SpellPhase],
    debug: dict[str, str],
) -> None:
    """Visite recursive : chaque cercle -> au plus une phase, sous-cercles
    chainent des phases suivantes."""
    # Racine virtuelle : chaque sous-cercle = phase independante chainee.
    if node.symbol_type == "root":
        for c in node.clauses:
            _collect_phases(c, phases, debug)
        return

    phase = _phase_for_circle(node, debug)
    if phase is not None:
        phases.append(phase)

    for sub in node.clauses:
        _collect_phases(sub, phases, debug)


def _phase_for_circle(
    node: ParseNode,
    debug: dict[str, str],
) -> SpellPhase | None:
    """Construit une phase a partir des sujets/verbes directs d'un cercle."""
    # Sujets directs
    elements = [subject_element(s.ast_node) for s in node.subjects]

    # Verbes directs (prendre le premier -> ordre gauche-droite)
    verb = verb_name(node.verbs[0].ast_node) if node.verbs else "none"

    # Sujet implicite : premier sous-cercle qui contient des runes
    if not elements and node.clauses:
        for c in node.clauses:
            inner = [subject_element(s.ast_node) for s in c.subjects]
            if inner:
                elements = inner
                break

    # Verbe implicite : premier sous-cercle qui contient un verbe
    if verb == "none":
        for c in node.clauses:
            if c.verbs:
                verb = verb_name(c.verbs[0].ast_node)
                break

    element = fuse_elements(elements)
    debug[node.ast_node.node_id] = f"{element}+{verb}"

    # Cercle totalement vide de sens grammatical -> pas de phase.
    if element == "neutral" and verb == "none":
        return None

    # "neutral" = absence de sujet dans la table de composition.
    lookup_element = None if element == "neutral" else element
    lookup_verb    = None if verb == "none" else verb
    entry = lookup(lookup_element, lookup_verb)

    # Element fusé (plasma, inferno, ...) sans ligne dédiée :
    # on retombe sur l'ingrédient primaire et on conserve l'élément fusé.
    if entry is None and lookup_element is not None:
        primary = next((e for e in elements if e and e != "neutral"), None)
        if primary and primary != lookup_element:
            fallback = lookup(primary, lookup_verb)
            if fallback is not None:
                f_form, f_effect, _f_elem, f_extra = fallback
                entry = (f_form, f_effect, lookup_element, f_extra)

    if entry is None:
        return None
    form_type, effect_type, final_element, extra = entry

    # Intensite : base 0.5, +0.1 par sujet direct, +0.05 par verbe.
    intensity = min(1.0, 0.5 + 0.1 * len(node.subjects) + 0.05 * len(node.verbs))

    # Forme : defauts par form_type.
    form = FormDescriptor(
        form_type=form_type,
        speed=0.5 if form_type == "projectile" else 0.0,
        spread=0.3 if form_type in ("aoe", "cone") else 0.0,
        radius=0.4,
        duration=1.0 if form_type in ("wall", "aoe") else 0.0,
    )
    substance = SubstanceDescriptor(
        effect_type=effect_type,
        element=final_element,
        intensity=intensity,
        extra=dict(extra),
    )
    return SpellPhase(form=form, substance=substance, trigger=None)


# ---------------------------------------------------------------------------
# Test de validation
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from client.magic.ast.ast import ASTNode, SpellAST
    from client.magic.grammar.parser import parse

    def make(nid: str, sym: str, children=None) -> ASTNode:
        n = ASTNode(
            node_id=nid, symbol_type=sym, primitive=None,
            depth=0, ordinal=0, sibling_count=1,
        )
        if children:
            n.children = children
        return n

    # 1. (rune_fire) seul -> aoe damage fire
    rf = make("rf", "rune_fire")
    c = make("c", "circle", [rf])
    ast = SpellAST(root=c, all_nodes=[c, rf], depth=1, node_count=2, spatial_relations=[])
    intent = build_intent(parse(ast))
    assert intent is not None
    assert len(intent.phases) == 1
    assert intent.phases[0].form.form_type == "aoe"
    assert intent.phases[0].substance.effect_type == "damage"
    assert intent.phases[0].substance.element == "fire"
    print(f"[PASS] (feu) -> {intent.phases[0].form.form_type}/{intent.phases[0].substance.effect_type}/{intent.phases[0].substance.element}")

    # 2. (rune_fire, arrow) -> projectile damage fire
    rf2 = make("rf2", "rune_fire")
    a = make("a", "arrow")
    c2 = make("c2", "circle", [rf2, a])
    ast2 = SpellAST(root=c2, all_nodes=[c2, rf2, a], depth=1, node_count=3, spatial_relations=[])
    i2 = build_intent(parse(ast2))
    assert i2.phases[0].form.form_type == "projectile"
    assert i2.phases[0].substance.element == "fire"
    print(f"[PASS] (feu, fleche) -> projectile feu")

    # 3. (arrow) seul -> projectile push neutral
    ar = make("ar", "arrow")
    c3 = make("c3", "circle", [ar])
    ast3 = SpellAST(root=c3, all_nodes=[c3, ar], depth=1, node_count=2, spatial_relations=[])
    i3 = build_intent(parse(ast3))
    assert i3.phases[0].form.form_type == "projectile"
    assert i3.phases[0].substance.effect_type == "push"
    print(f"[PASS] (fleche seule) -> projectile push neutre")

    # 4. (rune_ice, segment) -> wall create ice
    ri = make("ri", "rune_ice")
    seg = make("seg", "segment")
    c4 = make("c4", "circle", [ri, seg])
    ast4 = SpellAST(root=c4, all_nodes=[c4, ri, seg], depth=1, node_count=3, spatial_relations=[])
    i4 = build_intent(parse(ast4))
    assert i4.phases[0].form.form_type == "wall"
    assert i4.phases[0].substance.effect_type == "create"
    assert i4.phases[0].substance.element == "ice"
    assert i4.phases[0].substance.extra.get("terrain_type") == "ice_bridge"
    print(f"[PASS] (glace, segment) -> pont de glace")

    # 5. Racine triangle (pas de cercle) -> parse None -> build impossible
    tri = make("tri", "triangle")
    ast5 = SpellAST(root=tri, all_nodes=[tri], depth=0, node_count=1, spatial_relations=[])
    assert parse(ast5) is None
    print("[PASS] triangle seul (hors cercle) -> rejete")

    # 6. Chainage : (rune_fire, arrow) > (rune_ice) -> 2 phases chainees
    rf6 = make("rf6", "rune_fire")
    a6 = make("a6", "arrow")
    ri6 = make("ri6", "rune_ice")
    inner = make("inner", "circle", [ri6])
    outer = make("outer", "circle", [rf6, a6, inner])
    ast6 = SpellAST(
        root=outer,
        all_nodes=[outer, rf6, a6, inner, ri6],
        depth=2, node_count=5, spatial_relations=[],
    )
    i6 = build_intent(parse(ast6))
    assert len(i6.phases) == 2
    assert i6.phases[0].form.form_type == "projectile"
    assert i6.phases[0].substance.element == "fire"
    assert i6.phases[1].form.form_type == "aoe"
    assert i6.phases[1].substance.effect_type == "freeze"
    # Phase 0 chainee sur phase 1
    assert i6.phases[0].trigger is not None
    assert i6.phases[0].trigger.trigger_type == "on_expire"
    assert i6.phases[0].trigger.next_phase == 1
    print(f"[PASS] (feu fleche (glace)) -> projectile feu -> zone glace")

    # 7. Fusion elementaire : (rune_fire, rune_ice) -> plasma
    rf7 = make("rf7", "rune_fire")
    ri7 = make("ri7", "rune_ice")
    c7 = make("c7", "circle", [rf7, ri7])
    ast7 = SpellAST(root=c7, all_nodes=[c7, rf7, ri7], depth=1, node_count=3, spatial_relations=[])
    i7 = build_intent(parse(ast7))
    assert i7.phases[0].substance.element == "plasma"
    print(f"[PASS] (feu+glace) -> plasma")

    # 8. Cercle vide -> pas de phase -> intent None
    c8 = make("c8", "circle")
    ast8 = SpellAST(root=c8, all_nodes=[c8], depth=0, node_count=1, spatial_relations=[])
    assert build_intent(parse(ast8)) is None
    print("[PASS] cercle vide -> intent None")

    print("\nAll semantic assertions passed.")
