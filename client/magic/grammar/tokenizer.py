"""tokenizer.py -- classification grammaticale des noeuds AST.

Chaque ASTNode recoit une categorie grammaticale :
  CONTAINER : cercle (phrase / fonction / zone de lecture)
  SUBJECT   : rune elementaire (nom -> sujet)
  VERB      : forme d'action (verbe)
  MODIFIER  : modificateur lexical (point, petit cercle, ...)
  UNKNOWN   : hors vocabulaire -- sera ignore
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from client.magic.ast.ast import ASTNode


class TokenKind(Enum):
    CONTAINER = "container"
    SUBJECT   = "subject"
    VERB      = "verb"
    MODIFIER  = "modifier"
    UNKNOWN   = "unknown"


# symbol_type -> categorie grammaticale.
# Tout symbole commencant par "rune_" est traite comme SUBJECT (rune elementaire).
_KIND_TABLE: dict[str, TokenKind] = {
    "circle":          TokenKind.CONTAINER,
    "root":            TokenKind.CONTAINER,
    "arrow":           TokenKind.VERB,
    "arrow_with_base": TokenKind.VERB,
    "segment":         TokenKind.VERB,
    "triangle":        TokenKind.VERB,
    "zigzag":          TokenKind.VERB,
}


def classify(node: "ASTNode") -> TokenKind:
    """Renvoie la categorie grammaticale d'un noeud AST."""
    sym = node.symbol_type
    if sym.startswith("rune_"):
        return TokenKind.SUBJECT
    return _KIND_TABLE.get(sym, TokenKind.UNKNOWN)


def subject_element(node: "ASTNode") -> str:
    """Nom d'element (fire/ice/lightning/...) pour un SUBJECT. Neutre sinon."""
    sym = node.symbol_type
    if sym.startswith("rune_"):
        return sym[len("rune_"):]
    return "neutral"


def verb_name(node: "ASTNode") -> str:
    """Nom canonique du verbe associe a un VERB."""
    sym = node.symbol_type
    if sym in ("arrow", "arrow_with_base"):
        return "throw"
    if sym == "segment":
        return "create"
    if sym == "triangle":
        return "pierce"
    if sym == "zigzag":
        return "scatter"
    return "noop"


# ---------------------------------------------------------------------------
# Test de validation
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from client.magic.ast.ast import ASTNode

    def make(sym: str) -> ASTNode:
        return ASTNode(
            node_id=f"n_{sym}", symbol_type=sym, primitive=None,
            depth=0, ordinal=0, sibling_count=1,
        )

    assert classify(make("circle")) is TokenKind.CONTAINER
    assert classify(make("root"))   is TokenKind.CONTAINER
    assert classify(make("arrow"))  is TokenKind.VERB
    assert classify(make("triangle")) is TokenKind.VERB
    assert classify(make("segment")) is TokenKind.VERB
    assert classify(make("zigzag"))  is TokenKind.VERB
    assert classify(make("rune_fire")) is TokenKind.SUBJECT
    assert classify(make("rune_ice"))  is TokenKind.SUBJECT
    assert classify(make("xxx"))    is TokenKind.UNKNOWN

    assert subject_element(make("rune_fire")) == "fire"
    assert subject_element(make("rune_lightning")) == "lightning"
    assert subject_element(make("circle")) == "neutral"

    assert verb_name(make("arrow"))    == "throw"
    assert verb_name(make("segment"))  == "create"
    assert verb_name(make("triangle")) == "pierce"
    assert verb_name(make("zigzag"))   == "scatter"
    assert verb_name(make("circle"))   == "noop"

    print("[PASS] tokenizer assertions OK")
