"""Algebre d'interaction entre PropertyBags.

Fonctions pures pour calculer l'interference entre deux bags relies
par une relation spatiale. Pas de lookup table : tout est algebrique.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from client.magic.ast.symbol_rules import PropertyBag, PropertyEntry, PropertyTag

from client.magic.ast.symbol_rules import PropertyBag, PropertyEntry, PropertyTag


# ---------------------------------------------------------------------------
# Interference entre deux bags
# ---------------------------------------------------------------------------

def compute_interference(
    bag_a: PropertyBag,
    bag_b: PropertyBag,
    relation_type: str,
    spatial_angle: float,
) -> list[PropertyEntry]:
    """
    Pour chaque paire d'entries (a, b) avec meme domain+axis,
    calcule l'interference constructive ou destructive selon l'angle spatial.

    Formule : combined_value = a.value * cos(phase) + b.value * sin(phase)
    ou phase est derive de spatial_angle et du scope des entries.

    Multiplicateurs par type de relation :
        "intersects" : interference forte (weight * 1.5)
        "near"       : interference faible (weight * 0.5)
        "contains"/"inside" : pas d'interference cross-node (hierarchie)
    """
    if relation_type in ("contains", "inside"):
        return []

    # Multiplicateur de force selon la relation
    relation_mult = {
        "intersects": 1.5,
        "near": 0.5,
    }.get(relation_type, 0.8)

    # Indexer les entries de B par (domain, axis) pour matching rapide
    b_index: dict[tuple[str, str], list[PropertyEntry]] = {}
    for entry_b in bag_b.entries:
        key = (entry_b.tag.domain, entry_b.tag.axis)
        b_index.setdefault(key, []).append(entry_b)

    results: list[PropertyEntry] = []

    for entry_a in bag_a.entries:
        key = (entry_a.tag.domain, entry_a.tag.axis)
        matching_b = b_index.get(key)
        if not matching_b:
            continue

        for entry_b in matching_b:
            # Phase derivee de l'angle spatial et de la nature des scopes
            # Scopes identiques = en phase (constructif), differents = dephasage
            scope_offset = 0.0 if entry_a.tag.scope == entry_b.tag.scope else math.pi / 4.0
            phase = spatial_angle + scope_offset

            # Interference : combinaison trigonometrique
            combined_value = entry_a.value * math.cos(phase) + entry_b.value * math.sin(phase)

            # Poids combine (moyenne geometrique * multiplicateur de relation)
            combined_weight = math.sqrt(abs(entry_a.weight * entry_b.weight)) * relation_mult

            if abs(combined_value * combined_weight) < 1e-6:
                continue

            results.append(PropertyEntry(
                tag=PropertyTag(
                    domain=entry_a.tag.domain,
                    axis=entry_a.tag.axis,
                    scope="self",  # les interferences cross-node produisent des contributions "self"
                ),
                value=combined_value,
                weight=combined_weight,
                source_node_id=f"{entry_a.source_node_id}x{entry_b.source_node_id}",
            ))

    return results


# ---------------------------------------------------------------------------
# Poids gaussien par profondeur
# ---------------------------------------------------------------------------

def compute_depth_weight(source_depth: int, target_depth: int) -> float:
    """
    Poids gaussien selon la distance entre profondeurs.
    exp(-0.5 * (source_depth - target_depth)^2)
    Adjacent = fort, eloigne = faible.
    """
    return math.exp(-0.5 * (source_depth - target_depth) ** 2)


# ---------------------------------------------------------------------------
# Fusion de bags avec poids de profondeur
# ---------------------------------------------------------------------------

def accumulate_bag(bags: list[PropertyBag], depth_weights: list[float]) -> PropertyBag:
    """
    Fusionne N bags avec des poids de profondeur.
    Chaque entry.weight est multiplie par le depth_weight correspondant.
    Retourne un nouveau PropertyBag avec toutes les entries repondues.
    """
    merged = PropertyBag()
    for bag, dw in zip(bags, depth_weights):
        for entry in bag.entries:
            merged.entries.append(PropertyEntry(
                tag=entry.tag,
                value=entry.value,
                weight=entry.weight * dw,
                source_node_id=entry.source_node_id,
            ))
    return merged
