from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from client.magic.graph_geo import GraphGeo
from client.magic.primitive_emitters import emit_spell_spec
from client.magic.spell_spec import SpellSpec, merge_spec_into


@dataclass
class SpellChainNode:
    parallel_specs: list[SpellSpec]   # primitives sœurs fusionnées en parallèle
    next: SpellChainNode | None = None

    def resolve_parallel(self) -> SpellSpec | None:
        """Fusionne tous les parallel_specs simultanément."""
        if not self.parallel_specs:
            return None
        
        result = self.parallel_specs[0]
        for spec in self.parallel_specs[1:]:
            result = merge_spec_into(result, spec)
        
        return result


class SpellChainBuilder:
    """Construit une chaîne de SpellChainNode depuis un GraphGeo."""
    
    def build(self, graph: GraphGeo) -> SpellChainNode | None:
        """Construit la chaîne de nœuds depuis le GraphGeo."""
        anchor_index = graph.get_anchor_circle_index()
        if anchor_index is None:
            # Pas de cercle ancre, traiter toutes les primitives en parallèle
            return self._build_single_node_chain(graph)
        
        # Utiliser la lecture par cercles avec anneaux de distance
        ordered_indices = graph.get_contained_clockwise_indices(
            circle_index=anchor_index,
            radial_step_ratio=0.20  # Tolérance pour les anneaux parallèles
        )
        
        # Grouper par anneaux de distance
        rings = self._group_by_distance_rings(graph, anchor_index, ordered_indices)
        
        # Ajouter le cercle ancre comme propriétés globales (appliquées à la fin)
        anchor_primitive = graph.iter_primitives()[anchor_index]
        anchor_spec = emit_spell_spec(anchor_primitive)
        
        # Construire la chaîne
        chain_head = self._build_chain_from_rings(graph, rings)
        
        # Si on a un cercle ancre avec des propriétés, l'ajouter comme nœud final
        if anchor_spec is not None:
            if chain_head is None:
                # Seulement le cercle ancre
                return SpellChainNode(parallel_specs=[anchor_spec])
            else:
                # Ajouter le cercle à la fin de la chaîne
                current = chain_head
                while current.next is not None:
                    current = current.next
                current.next = SpellChainNode(parallel_specs=[anchor_spec])
        
        return chain_head
    
    def _build_single_node_chain(self, graph: GraphGeo) -> SpellChainNode | None:
        """Construit un nœud unique avec toutes les primitives en parallèle."""
        primitives = graph.iter_primitives()
        specs = []
        
        for primitive in primitives:
            spec = emit_spell_spec(primitive)
            if spec is not None:
                specs.append(spec)
        
        if not specs:
            return None
            
        return SpellChainNode(parallel_specs=specs)
    
    def _group_by_distance_rings(self, graph: GraphGeo, anchor_index: int, ordered_indices: list[int]) -> list[list[int]]:
        """Groupe les indices par anneaux de distance depuis le centre du cercle ancre."""
        anchor = graph.iter_primitives()[anchor_index]
        if not hasattr(anchor, 'center') or not hasattr(anchor, 'radius'):
            return [ordered_indices]  # Fallback: tout en un anneau
        
        center = anchor.center
        radius = anchor.radius
        ring_tolerance = radius * 0.20  # Tolérance pour considérer les primitives dans le même anneau
        
        primitives = graph.iter_primitives()
        rings: list[list[int]] = []
        
        for idx in ordered_indices:
            primitive = primitives[idx]
            primitive_center = graph._primitive_center(primitive)
            distance = graph._distance(center, primitive_center)
            
            # Calculer l'anneau (bucket) pour cette distance
            ring_bucket = int(distance / max(1.0, ring_tolerance))
            
            # Étendre la liste des anneaux si nécessaire
            while len(rings) <= ring_bucket:
                rings.append([])
            
            rings[ring_bucket].append(idx)
        
        # Filtrer les anneaux vides
        return [ring for ring in rings if ring]
    
    def _build_chain_from_rings(self, graph: GraphGeo, rings: list[list[int]]) -> SpellChainNode | None:
        """Construit la chaîne de nœuds depuis les anneaux."""
        if not rings:
            return None
        
        primitives = graph.iter_primitives()
        head = None
        current = None
        
        for ring in rings:
            # Créer les specs pour ce ring (parallèles)
            ring_specs = []
            for idx in ring:
                primitive = primitives[idx]
                spec = emit_spell_spec(primitive)
                if spec is not None:
                    ring_specs.append(spec)
            
            if not ring_specs:
                continue  # Ignorer les anneaux sans specs valides
            
            # Créer le nœud pour cet anneau
            node = SpellChainNode(parallel_specs=ring_specs)
            
            if head is None:
                head = node
                current = node
            else:
                current.next = node
                current = node
        
        return head
    
    def resolve(self, head: SpellChainNode | None) -> SpellSpec | None:
        """Résout la chaîne complète en une SpellSpec finale."""
        if head is None:
            return None
        
        current = head
        result = None
        
        while current is not None:
            ring_spec = current.resolve_parallel()
            if ring_spec is not None:
                if result is None:
                    result = ring_spec
                else:
                    result = merge_spec_into(result, ring_spec)
            current = current.next
        
        return result