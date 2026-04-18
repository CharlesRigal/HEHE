"""composition_table.py -- table sujet x verbe -> phase de sort.

Chaque paire (element_name, verb_name) produit une Entry (form_type,
effect_type, element, extra_dict).  Element "none" = pas de sujet.
Verbe "none" = pas de verbe.  Si la cle n'est pas presente dans la
table, lookup() renvoie None : la grammaire ne reconnait pas la
combinaison et l'appelant peut se rabattre sur l'emergence geometrique.

Fusion elementaire : si un cercle contient plusieurs sujets (runes),
fuse_elements() combine les deux dominants via ELEMENT_FUSION (commutatif,
cle triee alphabetiquement).
"""
from __future__ import annotations

# (form_type, effect_type, element, extra)
Entry = tuple[str, str, str, dict]


COMPOSITION: dict[tuple[str, str], Entry] = {
    # ── Sujet seul : manifestation statique ─────────────────────────────────
    ("fire",      "none"): ("aoe", "damage",    "fire",      {}),
    ("ice",       "none"): ("aoe", "freeze",    "ice",       {}),
    ("lightning", "none"): ("aoe", "damage",    "lightning", {}),
    ("arcane",    "none"): ("aoe", "transmute", "arcane",    {"to_material": "dust"}),

    # ── Sujet + throw (fleche) : projectile ─────────────────────────────────
    ("fire",      "throw"): ("projectile", "damage",    "fire",      {}),
    ("ice",       "throw"): ("projectile", "freeze",    "ice",       {}),
    ("lightning", "throw"): ("projectile", "damage",    "lightning", {}),
    ("arcane",    "throw"): ("projectile", "transmute", "arcane",    {}),

    # ── Sujet + create (segment) : mur/terrain ──────────────────────────────
    ("fire",      "create"): ("wall", "damage", "fire",      {"terrain_type": "wall_of_fire"}),
    ("ice",       "create"): ("wall", "create", "ice",       {"terrain_type": "ice_bridge",
                                                              "traversable": True}),
    ("lightning", "create"): ("wall", "damage", "lightning", {"terrain_type": "barrier"}),
    ("arcane",    "create"): ("wall", "create", "arcane",    {"terrain_type": "arcane_barrier"}),

    # ── Sujet + pierce (triangle) : cone/rayon ──────────────────────────────
    ("fire",      "pierce"): ("cone", "damage",    "fire",      {}),
    ("ice",       "pierce"): ("cone", "freeze",    "ice",       {}),
    ("lightning", "pierce"): ("ray",  "damage",    "lightning", {}),
    ("arcane",    "pierce"): ("ray",  "transmute", "arcane",    {"to_material": "dust"}),

    # ── Sujet + scatter (zigzag) : dispersion ───────────────────────────────
    ("fire",      "scatter"): ("aoe", "damage", "fire",      {"scatter": True}),
    ("ice",       "scatter"): ("aoe", "freeze", "ice",       {"scatter": True}),
    ("lightning", "scatter"): ("aoe", "damage", "lightning", {"scatter": True, "chain": True}),
    ("arcane",    "scatter"): ("aoe", "transmute","arcane",  {"scatter": True}),

    # ── Verbe seul (cercle sans sujet) : effet cinetique neutre ─────────────
    ("none", "throw"):   ("projectile", "push",   "neutral", {}),
    ("none", "create"):  ("wall",       "create", "neutral", {"terrain_type": "bridge",
                                                              "traversable": True}),
    ("none", "pierce"):  ("cone",       "push",   "neutral", {}),
    ("none", "scatter"): ("aoe",        "push",   "neutral", {"scatter": True}),
}


# Fusion elementaire : (a, b) avec a < b alphabetiquement.
ELEMENT_FUSION: dict[tuple[str, str], str] = {
    ("fire", "ice"):         "plasma",
    ("fire", "lightning"):   "plasma",
    ("arcane", "fire"):      "inferno",
    ("ice", "lightning"):    "storm",
    ("arcane", "ice"):       "crystal",
    ("arcane", "lightning"): "arcane",
}


def fuse_elements(elements: list[str]) -> str:
    """Combine une liste d'elements en un element dominant.

    Vide ou que "neutral" -> "neutral".
    Un seul -> cet element.
    Deux ou plus -> ELEMENT_FUSION sur les deux premiers (trie alphabetique).
    """
    clean = [e for e in elements if e and e != "neutral"]
    if not clean:
        return "neutral"
    if len(clean) == 1:
        return clean[0]
    a, b = sorted(clean[:2])
    return ELEMENT_FUSION.get((a, b), clean[0])


def lookup(subject_element: str | None, verb: str | None) -> Entry | None:
    """Consulte COMPOSITION. None si la paire est absente."""
    return COMPOSITION.get((subject_element or "none", verb or "none"))


# ---------------------------------------------------------------------------
# Test de validation
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Lookups directs
    assert lookup("fire", "throw")     == ("projectile", "damage", "fire", {})
    assert lookup("ice",  "create")[0] == "wall"
    assert lookup("ice",  "create")[1] == "create"
    assert lookup(None,   "throw")     == ("projectile", "push", "neutral", {})
    assert lookup("fire", None)[0]     == "aoe"
    assert lookup("xxx",  "throw")     is None, "combo inconnue doit renvoyer None"
    print("[PASS] lookup direct")

    # Fusion elementaire
    assert fuse_elements([])                    == "neutral"
    assert fuse_elements(["fire"])              == "fire"
    assert fuse_elements(["fire", "ice"])       == "plasma"
    assert fuse_elements(["ice",  "fire"])      == "plasma", "commutatif"
    assert fuse_elements(["arcane", "fire"])    == "inferno"
    assert fuse_elements(["earth", "water"])    == "earth",  "fallback : premier element"
    assert fuse_elements(["neutral", "fire"])   == "fire"
    print("[PASS] fuse_elements")

    print("\nAll composition_table assertions passed.")
