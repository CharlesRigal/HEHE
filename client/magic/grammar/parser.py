"""parser.py -- parser grammatical.

Transforme un SpellAST en arbre grammatical (ParseNode).

Regle d'or : la racine DOIT etre un cercle. Sinon parse() renvoie None et
l'appelant doit rejeter le sort ("hors cercle = ignore").

Un cercle (CONTAINER) se decompose en :
  subjects  : list[ParseNode]   -- runes elementaires enfants directs
  verbs     : list[ParseNode]   -- formes d'action enfants directs
  clauses   : list[ParseNode]   -- sous-cercles (sous-phrases)
  modifiers : list[ParseNode]   -- modificateurs lexicaux
Les enfants UNKNOWN sont ignores silencieusement.

La racine virtuelle "root" (creee par ast_builder quand plusieurs formes
top-level existent) est acceptee si au moins un de ses enfants est un
cercle. Les non-cercles de niveau racine sont ignores.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from client.magic.grammar.tokenizer import (
    TokenKind,
    classify,
    subject_element,
    verb_name,
)

if TYPE_CHECKING:
    from client.magic.ast.ast import ASTNode, SpellAST


@dataclass
class ParseNode:
    """Noeud de l'arbre grammatical."""
    kind: TokenKind
    symbol_type: str
    ast_node: "ASTNode"
    subjects:  list["ParseNode"] = field(default_factory=list)
    verbs:     list["ParseNode"] = field(default_factory=list)
    clauses:   list["ParseNode"] = field(default_factory=list)
    modifiers: list["ParseNode"] = field(default_factory=list)


def parse(ast: "SpellAST") -> ParseNode | None:
    """Parse un SpellAST. Renvoie None si la racine n'est pas un cercle valide."""
    root = ast.root
    if root is None:
        return None

    if root.symbol_type == "root":
        # Racine virtuelle : n'accepter que les cercles top-level.
        circle_children = [c for c in root.children if c.symbol_type == "circle"]
        if not circle_children:
            return None
        if len(circle_children) == 1:
            return _parse_circle(circle_children[0])
        # Plusieurs cercles freres -> phrases sequentielles.
        virtual = ParseNode(
            kind=TokenKind.CONTAINER,
            symbol_type="root",
            ast_node=root,
        )
        for c in circle_children:
            virtual.clauses.append(_parse_circle(c))
        return virtual

    if root.symbol_type != "circle":
        return None
    return _parse_circle(root)


def _parse_circle(circle_node: "ASTNode") -> ParseNode:
    """Parse le contenu d'un cercle -> ParseNode (CONTAINER)."""
    node = ParseNode(
        kind=TokenKind.CONTAINER,
        symbol_type=circle_node.symbol_type,
        ast_node=circle_node,
    )
    for child in circle_node.children:
        kind = classify(child)
        if kind is TokenKind.SUBJECT:
            node.subjects.append(
                ParseNode(kind=kind, symbol_type=child.symbol_type, ast_node=child)
            )
        elif kind is TokenKind.VERB:
            node.verbs.append(
                ParseNode(kind=kind, symbol_type=child.symbol_type, ast_node=child)
            )
        elif kind is TokenKind.CONTAINER:
            node.clauses.append(_parse_circle(child))
        elif kind is TokenKind.MODIFIER:
            node.modifiers.append(
                ParseNode(kind=kind, symbol_type=child.symbol_type, ast_node=child)
            )
        # UNKNOWN -> ignore
    return node


def describe(node: ParseNode, indent: int = 0) -> str:
    """Representation lisible de l'arbre grammatical (debug)."""
    pad = "  " * indent
    lines = [f"{pad}{node.kind.value.upper()}: {node.symbol_type}"]
    for s in node.subjects:
        lines.append(
            f"{pad}  SUBJECT: {s.symbol_type} "
            f"(element={subject_element(s.ast_node)})"
        )
    for v in node.verbs:
        lines.append(
            f"{pad}  VERB: {v.symbol_type} (action={verb_name(v.ast_node)})"
        )
    for c in node.clauses:
        lines.append(describe(c, indent + 1))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Test de validation
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from client.magic.ast.ast import ASTNode, SpellAST

    def make(nid: str, sym: str, depth: int = 0, children=None) -> ASTNode:
        n = ASTNode(
            node_id=nid, symbol_type=sym, primitive=None,
            depth=depth, ordinal=0, sibling_count=1,
        )
        if children:
            n.children = children
        return n

    # 1. Racine = cercle avec rune_fire + arrow
    rune = make("n_rf", "rune_fire", 1)
    arrow = make("n_a", "arrow", 1)
    circle = make("n_c", "circle", 0, [rune, arrow])
    ast1 = SpellAST(
        root=circle, all_nodes=[circle, rune, arrow],
        depth=1, node_count=3, spatial_relations=[],
    )
    p1 = parse(ast1)
    assert p1 is not None,                 "parse(circle) doit reussir"
    assert p1.kind is TokenKind.CONTAINER
    assert len(p1.subjects) == 1
    assert p1.subjects[0].symbol_type == "rune_fire"
    assert len(p1.verbs) == 1
    assert p1.verbs[0].symbol_type == "arrow"
    print("[PASS] parse cercle+rune+arrow")

    # 2. Racine = triangle seul (non-cercle) -> rejet
    tri = make("n_t", "triangle", 0)
    ast2 = SpellAST(
        root=tri, all_nodes=[tri],
        depth=0, node_count=1, spatial_relations=[],
    )
    assert parse(ast2) is None, "racine triangle doit etre rejetee"
    print("[PASS] parse triangle racine -> None")

    # 3. Racine virtuelle avec un cercle -> OK, aplati
    c = make("n_c3", "circle", 0)
    vroot = make("n_root", "root", 0, [c])
    ast3 = SpellAST(
        root=vroot, all_nodes=[vroot, c],
        depth=0, node_count=2, spatial_relations=[],
    )
    p3 = parse(ast3)
    assert p3 is not None and p3.symbol_type == "circle"
    print("[PASS] parse virtual root (1 cercle) -> cercle aplati")

    # 4. Racine virtuelle sans cercle -> rejet
    s = make("n_s", "segment", 0)
    z = make("n_z", "zigzag", 0)
    vroot2 = make("n_root2", "root", 0, [s, z])
    ast4 = SpellAST(
        root=vroot2, all_nodes=[vroot2, s, z],
        depth=0, node_count=3, spatial_relations=[],
    )
    assert parse(ast4) is None, "root virtuel sans cercle doit etre rejete"
    print("[PASS] parse virtual root sans cercle -> None")

    # 5. Cercle imbrique : cercle avec (rune_fire, cercle_interne(rune_ice))
    rf = make("n_rf2", "rune_fire", 2)
    ri = make("n_ri", "rune_ice", 2)
    inner = make("n_ci", "circle", 1, [ri])
    outer = make("n_co", "circle", 0, [rf, inner])
    ast5 = SpellAST(
        root=outer, all_nodes=[outer, rf, inner, ri],
        depth=2, node_count=4, spatial_relations=[],
    )
    p5 = parse(ast5)
    assert p5 is not None
    assert len(p5.subjects) == 1 and p5.subjects[0].symbol_type == "rune_fire"
    assert len(p5.clauses) == 1 and p5.clauses[0].symbol_type == "circle"
    assert p5.clauses[0].subjects[0].symbol_type == "rune_ice"
    print("[PASS] parse cercle imbrique")

    # 6. describe produit une chaine non vide
    text = describe(p1)
    assert "SUBJECT" in text and "VERB" in text
    print(f"[PASS] describe():\n{text}")

    print("\nAll parser assertions passed.")
