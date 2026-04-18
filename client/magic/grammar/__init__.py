"""Grammaire des sorts : cercle = phrase/fonction, runes = sujets, formes = verbes.

Un sort valide = un arbre enraciné sur un cercle.
Hors cercle = ignoré.
"""
from client.magic.grammar.parser import ParseNode, parse, describe
from client.magic.grammar.semantic import build_intent
from client.magic.grammar.tokenizer import TokenKind, classify, subject_element, verb_name

__all__ = [
    "ParseNode",
    "TokenKind",
    "build_intent",
    "classify",
    "describe",
    "parse",
    "subject_element",
    "verb_name",
]
