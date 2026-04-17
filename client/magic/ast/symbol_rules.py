"""
symbol_rules.py — Système émergent à rôles sémantiques.

Chaque type de symbole a une règle dédiée qui définit son RÔLE PRIMAIRE.
La géométrie calibre l'intensité — le type détermine la signification.
rule_geometric reste disponible comme fallback universel.

PropertyTag.axis  : axe de la propriété
PropertyTag.scope : portée ("self" | "parent" | "children")

Domains / axes disponibles :
  energy   : compression, spread, element
  motion   : velocity, direction
  space    : axis, elongation, scope_radius
  time     : duration, chaos
  semantic : role_zone, role_vector, role_vector_grounded, role_focus,
             role_barrier, role_chaos, role_element_mod, count

Rôles par symbole :
  circle          → ZONE      : spread + duration  (où et combien de temps)
  arrow           → VECTEUR   : velocity + direction (vers où, à quelle vitesse)
  arrow_with_base → CÔNE      : velocity + direction + spread (émane d'un point)
  triangle        → FOCUS     : compression + axis  (concentré, perce)
  segment         → BARRIÈRE  : compression + axis  (structure statique)
  zigzag          → CHAOS     : chaos + count       (combien de fois, imprévisible)
  rune_fire       → ÉLÉMENT   : element ×2          (surcharge l'élément dominant)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from client.magic.ast.ast import ASTNode


# ---------------------------------------------------------------------------
# Types de base
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PropertyTag:
    domain: str   # "energy" | "motion" | "space" | "time"
    axis: str     # "compression" | "spread" | "velocity" | "direction" | ...
    scope: str    # "self" | "parent" | "children"


@dataclass
class PropertyEntry:
    tag: PropertyTag
    value: float
    weight: float
    source_node_id: str


class PropertyBag:
    def __init__(self) -> None:
        self.entries: list[PropertyEntry] = []

    def add(self, tag: PropertyTag, value: float, weight: float, source_node_id: str) -> None:
        self.entries.append(PropertyEntry(tag=tag, value=value, weight=weight, source_node_id=source_node_id))

    def query(self, domain: str, axis: str = "*") -> list[PropertyEntry]:
        return [
            e for e in self.entries
            if e.tag.domain == domain and (axis == "*" or e.tag.axis == axis)
        ]

    def net(self, domain: str, axis: str) -> float:
        return sum(
            e.value * e.weight
            for e in self.entries
            if e.tag.domain == domain and e.tag.axis == axis
        )

    def merge(self, other: "PropertyBag") -> "PropertyBag":
        merged = PropertyBag()
        merged.entries = list(self.entries) + list(other.entries)
        return merged

    def __len__(self) -> int:
        return len(self.entries)

    def __repr__(self) -> str:
        return f"PropertyBag({len(self.entries)} entries)"


@dataclass
class ResolutionContext:
    node: Any
    depth: int
    child_bags: list[PropertyBag]

    @staticmethod
    def empty(node: Any, tree: Any = None) -> "ResolutionContext":
        return ResolutionContext(
            node=node,
            depth=getattr(node, "depth", 0),
            child_bags=[],
        )


class SymbolRule(Protocol):
    def __call__(self, node: "ASTNode", ctx: ResolutionContext) -> PropertyBag: ...


# ---------------------------------------------------------------------------
# Règle géométrique universelle
# ---------------------------------------------------------------------------

def rule_geometric(node: "ASTNode", ctx: ResolutionContext) -> PropertyBag:
    """
    Règle émergente unique. Toutes les propriétés viennent de la géométrie.

    Features attendues dans node.drawing_features (extraites par ast_builder) :
        compactness   [0,1]  — rondeur  (4π·A / P²)
        elongation    [1,∞]  — étirement (ratio PCA major/minor)
        closure       [0,1]  — fermeture (1=cycle fermé)
        linearity     [0,1]  — droiture  (dist_endpoints / périmètre)
        angularity    [0,1]  — densité de coins aigus
        area_n        [0,1]  — aire normalisée
        scale_n       [0,1]  — échelle (max(area_n, perimeter_n × 0.5))
        direction_n   [0,1]  — angle principal / 360°
        convexity     [0,1]  — fraction de virages cohérents
        is_directional [0,1] — 1 si la forme a une tête directionnelle (flèche)
        confidence    [0,1]  — confiance de la reconnaissance
    """
    bag = PropertyBag()
    nid = node.node_id
    f = node.drawing_features

    compactness    = float(f.get("compactness",    0.5))
    elongation     = max(1.0, float(f.get("elongation",    1.0)))
    closure        = float(f.get("closure",        0.0))
    linearity      = float(f.get("linearity",      0.0))
    angularity     = float(f.get("angularity",     0.3))
    area_n         = float(f.get("area_n",         0.2))
    scale_n        = float(f.get("scale_n",        area_n))
    direction_n    = float(f.get("direction_n",    0.0))
    convexity      = float(f.get("convexity",      0.8))
    is_directional = float(f.get("is_directional", 0.0))
    conf           = float(f.get("confidence",     1.0))

    # scope : "self" si nœud racine (cercle exécuteur), "parent" sinon
    scope = "self" if ctx.depth == 0 else "parent"

    # facteur d'étirement normalisé [0, 1)
    elonga_n = (elongation - 1.0) / elongation

    # poids de base : taille × confiance
    w = scale_n * conf + 0.05

    # ── Compression (énergie focalisée) ────────────────────────────────────
    # Anguleux × non-rond × allongé → focalisation static
    angular_cmp = angularity * (1.0 - compactness) * (1.0 + elonga_n)
    # Linéaire × allongé × NON directionnel → énergie statique comprimée (mur)
    static_cmp = linearity * elonga_n * (1.0 - is_directional) * 2.0
    compression = angular_cmp + static_cmp
    bag.add(PropertyTag("energy", "compression", scope), compression, w, nid)

    # ── Spread (diffusion spatiale) ────────────────────────────────────────
    # Rond × fermé × grand → énergie étalée
    spread = compactness * closure * area_n
    if spread > 0.01:
        bag.add(PropertyTag("energy", "spread", scope), spread, conf, nid)

    # ── Vélocité + direction ───────────────────────────────────────────────
    # Linéaire × allongé × directionnel → mouvement
    velocity = linearity * elonga_n * is_directional
    if velocity > 0.02:
        bag.add(PropertyTag("motion", "velocity", scope), velocity, w, nid)
        bag.add(PropertyTag("motion", "direction", scope), direction_n, conf, nid)

    # ── Durée (persistance) ────────────────────────────────────────────────
    # Fermé × grand → sort persistant
    if closure > 0.4:
        bag.add(PropertyTag("time", "duration", scope), closure * area_n, conf, nid)

    # ── Chaos (instabilité) ────────────────────────────────────────────────
    # Non-convexe × anguleux → sort instable
    chaos = (1.0 - convexity) * angularity
    if chaos > 0.05:
        bag.add(PropertyTag("time", "chaos", scope), chaos, conf, nid)

    # ── Axe spatial (orientation dominante) ───────────────────────────────
    if elongation > 1.3:
        bag.add(PropertyTag("space", "axis",       scope), direction_n, elonga_n * conf, nid)
        bag.add(PropertyTag("space", "elongation", scope), elongation,  conf,            nid)

    # ── Signature élémentaire (émergente) ─────────────────────────────────
    element_val = _element_from_geometry(angularity, linearity, compactness, closure, is_directional)
    bag.add(PropertyTag("energy", "element", scope), element_val, scale_n * 0.5 + 0.15, nid)

    return bag


def _element_from_geometry(
    angularity: float,
    linearity: float,
    compactness: float,
    closure: float,
    is_directional: float,
) -> float:
    """
    Projection géométrique → valeur élémentaire continue [0, 1].

    Géométrie  →  élément attendu
    ─────────────────────────────────────────────────────────────────────
    anguleux + ouvert          → feu      (>0.82): flamme, chaotique
    linéaire + directionnel    → foudre   (>0.65): arc, précis, rapide
    linéaire + non-directionnel→ arcane   (>0.42): neutre stable
    compact + fermé + lisse    → glace    (<0.22): cristal, contenu
    """
    # chaleur : anguleux + ouvert = instable = feu
    heat = angularity * (1.0 - closure)
    # précision : linéaire + directionnel = foudre
    precision = linearity * is_directional * (1.0 - angularity * 0.4)
    # axe neutre : linéaire + non-directionnel = arcane
    arcane = linearity * (1.0 - is_directional) * (1.0 - angularity)
    # froid : compact + fermé + lisse = glace
    cold = compactness * closure * (1.0 - angularity)

    val = 0.5 + heat * 0.5 + precision * 0.25 + arcane * 0.05 - cold * 0.4
    return max(0.0, min(1.0, val))


# ---------------------------------------------------------------------------
# Règles sémantiques par type de symbole
# ---------------------------------------------------------------------------

def rule_circle(node: "ASTNode", ctx: ResolutionContext) -> PropertyBag:
    """
    Cercle → Rôle : ZONE / PORTÉE
    Primaire : energy.spread (taille de zone), time.duration (persistance)
    Un cercle répond à « où » et « combien de temps ».

    Nesting : si container, distribue spread et durée vers les enfants
    pour qu'ils sachent qu'ils opèrent dans une zone.
    """
    bag = PropertyBag()
    nid = node.node_id
    f = node.drawing_features

    area_n      = float(f.get("area_n",      0.2))
    closure     = float(f.get("closure",     0.95))
    compactness = float(f.get("compactness", 0.90))
    scale_n     = float(f.get("scale_n",     0.5))
    conf        = float(f.get("confidence",  1.0))
    angularity  = float(f.get("angularity",  0.0))

    scope = "self" if ctx.depth == 0 else "parent"

    # PRIMAIRE : Spread — plus grand et fermé = zone plus vaste
    spread = compactness * closure * max(area_n, 0.1)
    bag.add(PropertyTag("energy", "spread", scope), spread, conf * 1.5, nid)

    # PRIMAIRE : Durée — cercle fermé = sort persistant
    duration = closure * (0.2 + area_n * 0.8)
    bag.add(PropertyTag("time", "duration", scope), duration, conf * 1.3, nid)

    # Rayon normalisé (taille réelle de la zone pour le serveur)
    bag.add(PropertyTag("space", "scope_radius", scope), scale_n, conf, nid)

    # Rôle sémantique (ne se propage pas vers parent ni children)
    bag.add(PropertyTag("semantic", "role_zone", "self"), 1.0, conf, nid)

    # Si container : distribue zone et durée vers les enfants
    # (les enfants savent qu'ils opèrent à l'intérieur d'une zone)
    if node.children:
        bag.add(PropertyTag("energy", "spread",   "children"), spread   * 0.5, conf * 0.7, nid)
        bag.add(PropertyTag("time",   "duration", "children"), duration * 0.4, conf * 0.7, nid)

    # Élément (signature légère — cercle neutre par défaut)
    element_val = _element_from_geometry(angularity, 0.0, compactness, closure, 0.0)
    bag.add(PropertyTag("energy", "element", scope), element_val, scale_n * 0.25, nid)

    return bag


def rule_arrow(node: "ASTNode", ctx: ResolutionContext) -> PropertyBag:
    """
    Flèche → Rôle : VECTEUR / MOUVEMENT
    Primaire : motion.velocity (force cinétique), motion.direction (angle exact)
    Une flèche répond à « dans quelle direction » et « à quelle vitesse ».
    """
    bag = PropertyBag()
    nid = node.node_id
    f = node.drawing_features

    linearity   = float(f.get("linearity",   0.9))
    elongation  = max(1.0, float(f.get("elongation", 4.0)))
    direction_n = float(f.get("direction_n", 0.0))
    scale_n     = float(f.get("scale_n",     0.2))
    conf        = float(f.get("confidence",  1.0))

    scope = "self" if ctx.depth == 0 else "parent"
    elonga_n = (elongation - 1.0) / elongation

    # PRIMAIRE : Vélocité — flèche longue et droite = rapide
    # Minimum 0.15 garanti : une flèche est TOUJOURS un vecteur de mouvement
    velocity = max(0.15, linearity * elonga_n)
    bag.add(PropertyTag("motion", "velocity",  scope), velocity,    conf * 1.5, nid)

    # PRIMAIRE : Direction — angle exact de la flèche (toujours explicite)
    bag.add(PropertyTag("motion", "direction", scope), direction_n, conf * 1.5, nid)

    # Rôle sémantique
    bag.add(PropertyTag("semantic", "role_vector", "self"), 1.0, conf, nid)

    # Élément (foudre par défaut : linéaire + directionnel = précis)
    element_val = _element_from_geometry(0.0, linearity, 0.0, 0.0, 1.0)
    bag.add(PropertyTag("energy", "element", scope), element_val, scale_n * 0.4, nid)

    return bag


def rule_arrow_with_base(node: "ASTNode", ctx: ResolutionContext) -> PropertyBag:
    """
    Flèche avec base → Rôle : CÔNE / VECTEUR ANCRÉ
    Hérite du rôle VECTEUR + ajoute un spread (émane d'un point fixe).
    Résultat naturel : behavior=aoe avec shp=cone.
    """
    # Base = tout ce qu'une flèche fait
    bag = rule_arrow(node, ctx)
    nid = node.node_id
    f = node.drawing_features

    area_n = float(f.get("area_n",     0.1))
    conf   = float(f.get("confidence", 1.0))
    scope  = "self" if ctx.depth == 0 else "parent"

    # Spread depuis la base (forme de cône directionnel)
    bag.add(PropertyTag("energy", "spread",                "children"), area_n * 0.4, conf * 0.8, nid)
    bag.add(PropertyTag("semantic", "role_vector_grounded", "self"),    1.0,           conf,       nid)

    return bag


def rule_triangle(node: "ASTNode", ctx: ResolutionContext) -> PropertyBag:
    """
    Triangle → Rôle : FOCUS / PERÇAGE
    Primaire : energy.compression (intensité concentrée), space.axis (direction de pointe)
    Un triangle répond à « quelle intensité focalisée » et « vers où ça pointe ».
    """
    bag = PropertyBag()
    nid = node.node_id
    f = node.drawing_features

    angularity  = float(f.get("angularity",  0.6))
    compactness = float(f.get("compactness", 0.4))
    elongation  = max(1.0, float(f.get("elongation", 2.0)))
    direction_n = float(f.get("direction_n", 0.0))
    scale_n     = float(f.get("scale_n",     0.3))
    conf        = float(f.get("confidence",  1.0))

    scope = "self" if ctx.depth == 0 else "parent"
    elonga_n = (elongation - 1.0) / elongation

    # PRIMAIRE : Compression — triangle pointu = énergie très concentrée
    # Minimum 0.2 garanti : un triangle est TOUJOURS une forme focalisée
    compression = max(0.2, angularity * (1.0 - compactness) * (1.0 + elonga_n))
    bag.add(PropertyTag("energy", "compression", scope), compression, conf * 1.5, nid)

    # PRIMAIRE : Axe de la pointe (direction du triangle)
    bag.add(PropertyTag("space", "axis",       scope), direction_n, elonga_n * conf * 1.5, nid)
    bag.add(PropertyTag("space", "elongation", scope), elongation,  conf,                  nid)

    # Rôle sémantique
    bag.add(PropertyTag("semantic", "role_focus", "self"), 1.0, conf, nid)

    # Élément (arcane/feu selon angularité — triangle = forme active)
    element_val = _element_from_geometry(angularity, 0.0, compactness, 0.3, 0.0)
    bag.add(PropertyTag("energy", "element", scope), element_val, scale_n * 0.4, nid)

    return bag


def rule_segment(node: "ASTNode", ctx: ResolutionContext) -> PropertyBag:
    """
    Segment → Rôle : BARRIÈRE / STRUCTURE STATIQUE
    Primaire : energy.compression (solidité), space.axis (orientation du mur)
    Un segment répond à « quelle structure statique » et « dans quel sens ».
    """
    bag = PropertyBag()
    nid = node.node_id
    f = node.drawing_features

    linearity   = float(f.get("linearity",   1.0))
    elongation  = max(1.0, float(f.get("elongation", 5.0)))
    direction_n = float(f.get("direction_n", 0.0))
    scale_n     = float(f.get("scale_n",     0.2))
    conf        = float(f.get("confidence",  1.0))

    scope = "self" if ctx.depth == 0 else "parent"
    elonga_n = (elongation - 1.0) / elongation

    # PRIMAIRE : Compression statique — segment long = mur solide
    # Minimum 0.3 garanti : un segment est TOUJOURS une structure
    static_cmp = max(0.3, linearity * elonga_n * 2.0)
    bag.add(PropertyTag("energy", "compression", scope), static_cmp, conf * 1.5, nid)

    # PRIMAIRE : Axe spatial — orientation exacte du mur
    bag.add(PropertyTag("space", "axis",       scope), direction_n, elonga_n * conf * 1.5, nid)
    bag.add(PropertyTag("space", "elongation", scope), elongation,  conf * 1.2,            nid)

    # Rôle sémantique
    bag.add(PropertyTag("semantic", "role_barrier", "self"), 1.0, conf, nid)

    # Élément (arcane par défaut — structure neutre/magique)
    element_val = _element_from_geometry(0.0, linearity, 0.0, 0.0, 0.0)
    bag.add(PropertyTag("energy", "element", scope), element_val, scale_n * 0.3, nid)

    return bag


def rule_zigzag(node: "ASTNode", ctx: ResolutionContext) -> PropertyBag:
    """
    ZigZag → Rôle : CHAOS / MULTIPLICATEUR
    Primaire : time.chaos (instabilité garantie), semantic.count (nombre de dents)
    Un zigzag répond à « combien de fois » et « avec quelle imprévisibilité ».

    Le nombre de dents encode directement le split_count côté resolver.
    """
    bag = PropertyBag()
    nid = node.node_id
    f = node.drawing_features

    angularity = float(f.get("angularity", 0.8))
    convexity  = float(f.get("convexity",  0.3))
    area_n     = float(f.get("area_n",     0.1))
    scale_n    = float(f.get("scale_n",    0.2))
    conf       = float(f.get("confidence", 1.0))

    scope = "self" if ctx.depth == 0 else "parent"

    # Compter les dents depuis le primitif (graceful fallback si None)
    prim = node.primitive
    if prim is not None and hasattr(prim, "vertices") and prim.vertices:
        n_verts = len(prim.vertices)
        # zigzag N dents ≈ N*2 vertices (pic + vallée alternés)
        teeth = max(2, n_verts // 2)
    else:
        teeth = 3  # fallback raisonnable

    # PRIMAIRE : Chaos — zigzag anguleux = instabilité garantie
    chaos = max(0.35, (1.0 - convexity) * angularity)
    bag.add(PropertyTag("time", "chaos", scope), chaos, conf * 1.5, nid)

    # PRIMAIRE : Compte (nombre de splits/répétitions, brut)
    # scope="self" car le count ne se propage pas — c'est une propriété locale
    bag.add(PropertyTag("semantic", "count", "self"), float(teeth), conf * 1.5, nid)

    # Rôles sémantiques
    bag.add(PropertyTag("semantic", "role_chaos", "self"), 1.0, conf, nid)

    # Spread secondaire (dispersion/explosion légère)
    spread = angularity * area_n * 0.5
    if spread > 0.01:
        bag.add(PropertyTag("energy", "spread", scope), spread, conf * 0.8, nid)

    # Élément (feu par défaut — chaos = chaleur, instabilité)
    element_val = _element_from_geometry(angularity, 0.0, 0.0, 0.0, 0.0)
    bag.add(PropertyTag("energy", "element", scope), element_val, scale_n * 0.5, nid)

    return bag


def rule_rune_fire(node: "ASTNode", ctx: ResolutionContext) -> PropertyBag:
    """
    RuneFire → Rôle : MODIFICATEUR ÉLÉMENTAIRE
    Primaire : energy.element avec poids ×2 (surcharge l'élément dominant du sort)
    Une rune répond à « de quel élément » — elle colore tout le reste.

    Placée à l'intérieur d'un cercle : l'élément de la zone prend sa valeur.
    Placée à l'intérieur d'un segment : le mur prend son élément.
    """
    bag = PropertyBag()
    nid = node.node_id
    f = node.drawing_features

    angularity  = float(f.get("angularity",  0.5))
    linearity   = float(f.get("linearity",   0.3))
    compactness = float(f.get("compactness", 0.3))
    closure     = float(f.get("closure",     0.5))
    scale_n     = float(f.get("scale_n",     0.2))
    conf        = float(f.get("confidence",  1.0))

    scope = "self" if ctx.depth == 0 else "parent"

    # PRIMAIRE : Élément avec poids doublé — la rune IMPOSE son élément
    element_val = _element_from_geometry(angularity, linearity, compactness, closure, 0.0)
    bag.add(PropertyTag("energy", "element", scope), element_val, conf * 2.0, nid)

    # Renforcement (une rune amplifie le sort)
    bag.add(PropertyTag("energy", "compression", scope), 0.2 * angularity, conf,       nid)

    # Persistance légère (la rune grave l'effet dans la durée)
    bag.add(PropertyTag("time",   "duration",    scope), 0.2 * closure,    conf * 0.8, nid)

    # Rôle sémantique
    bag.add(PropertyTag("semantic", "role_element_mod", "self"), 1.0, conf, nid)

    return bag