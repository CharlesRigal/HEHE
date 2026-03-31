from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from client.magic.graph_geo import CircleReadingPlan


@dataclass(slots=True)
class CircleSubSymbolExecutionContext:
    anchor_circle_index: int
    symbol_index: int
    ordinal: int
    total: int


class CircleSubSymbolExecutor:
    """
    Exécuteur dédié aux sous-symboles contenus dans un cercle.
    Le hook `execute_symbol` reste volontairement vide:
    le câblage d'ordre de lecture est prêt, l'effet gameplay sera ajouté plus tard.
    """

    def execute_reading_plan(
        self,
        plan: CircleReadingPlan,
        primitives: Sequence[Any],
    ) -> list[CircleSubSymbolExecutionContext]:
        executed: list[CircleSubSymbolExecutionContext] = []
        if not plan.ordered_subsymbol_indices:
            return executed

        total = len(plan.ordered_subsymbol_indices)
        for ordinal, symbol_index in enumerate(plan.ordered_subsymbol_indices):
            if symbol_index < 0 or symbol_index >= len(primitives):
                continue
            primitive = primitives[symbol_index]
            context = CircleSubSymbolExecutionContext(
                anchor_circle_index=plan.anchor_circle_index,
                symbol_index=symbol_index,
                ordinal=ordinal,
                total=total,
            )
            self.execute_symbol(primitive, context)
            executed.append(context)
        return executed

    def execute_symbol(self, primitive: Any, context: CircleSubSymbolExecutionContext) -> None:
        _ = primitive
        _ = context
        # Hook volontairement vide.
        return None
