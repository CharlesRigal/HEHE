"""Logger fichier pour le pipeline de sorts.

Crée debug_logs/spell_pipeline.log (rotation à 2 MB, 3 backups).
Chaque cast est loggé en texte structuré lisible.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from client.ui.spell_debug_overlay import SpellDebugData

_LOG_DIR  = "debug_logs"
_LOG_FILE = os.path.join(_LOG_DIR, "spell_pipeline.log")
_MAX_BYTES = 2 * 1024 * 1024   # 2 MB
_BACKUP_COUNT = 3


class SpellLogger:
    def __init__(self) -> None:
        os.makedirs(_LOG_DIR, exist_ok=True)
        self._logger = logging.getLogger("spell_pipeline")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False  # ne pas polluer le root logger

        if not self._logger.handlers:
            handler = RotatingFileHandler(
                _LOG_FILE,
                maxBytes=_MAX_BYTES,
                backupCount=_BACKUP_COUNT,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def log_cast(self, data: SpellDebugData) -> None:
        ts = datetime.datetime.fromtimestamp(data.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        lines: list[str] = []
        lines.append(f"[{ts}] === SPELL CAST ===")

        # Primitives
        prim_names = []
        for p in data.primitives:
            kind = getattr(p, "kind", type(p).__name__)
            conf = getattr(p, "confidence", None)
            prim_names.append(f"{kind}(conf={conf:.2f})" if conf is not None else kind)
        lines.append(f"Primitives ({len(data.primitives)}): {', '.join(prim_names) or '(aucune)'}")

        # Relations GraphGeo
        if data.spatial_relations:
            rel_strs = []
            for rel in data.spatial_relations:
                src = getattr(rel, "source_index", "?")
                tgt = getattr(rel, "target_index", "?")
                rtype = getattr(rel, "relation", "?")
                rel_strs.append(f"#{src}→#{tgt}[{rtype}]")
            lines.append(f"GraphGeo: {', '.join(rel_strs)}")
        else:
            lines.append("GraphGeo: (aucune relation)")

        # AST
        ast = data.ast
        lines.append(f"AST: depth={ast.depth} nodes={ast.node_count}")
        if ast.root is not None:
            self._format_node(ast.root, "", True, lines)

        # Pass1
        lines.append(f"Pass1 (bottom-up) — {len(data.pass1_bags)} nœud(s):")
        for node_id, bag in data.pass1_bags.items():
            entries = getattr(bag, "entries", [])
            entry_strs = [
                f"{e.tag.domain}.{e.tag.axis}.{e.tag.scope}={e.value:.3f}(w={e.weight:.3f})"
                for e in entries
            ]
            lines.append(f"  {node_id}: {', '.join(entry_strs) or '(vide)'}")

        # Pass2 (entrées propagées marquées)
        lines.append(f"Pass2 (top-down) — {len(data.pass2_bags)} nœud(s):")
        for node_id, bag in data.pass2_bags.items():
            entries = getattr(bag, "entries", [])
            entry_strs = []
            for e in entries:
                suffix = "[prop]" if e.source_node_id.endswith("_propagated") else ""
                entry_strs.append(
                    f"{e.tag.domain}.{e.tag.axis}.{e.tag.scope}={e.value:.3f}(w={e.weight:.3f}){suffix}"
                )
            lines.append(f"  {node_id}: {', '.join(entry_strs) or '(vide)'}")

        # Pass3
        if data.cross_entries:
            lines.append(f"Pass3 (cross-node) — {len(data.cross_entries)} entrée(s):")
            for e in data.cross_entries:
                lines.append(
                    f"  {e.tag.domain}.{e.tag.axis}.{e.tag.scope}={e.value:.3f}"
                    f"(w={e.weight:.3f}) src={e.source_node_id}"
                )
        else:
            lines.append("Pass3 (cross-node): (aucune interférence)")

        # Params résolus
        p = data.resolved_params
        param_strs = [f"{k}={v:.4f}" if isinstance(v, float) else f"{k}={v}" for k, v in sorted(p.items())]
        lines.append(f"Resolved: {' '.join(param_strs)}")

        # Spec réseau
        try:
            net_str = json.dumps(data.network_spec, ensure_ascii=False)
        except Exception:
            net_str = str(data.network_spec)
        lines.append(f"Network: {net_str}")
        lines.append("")  # ligne vide séparatrice

        self._logger.debug("\n".join(lines))

    def close(self) -> None:
        for handler in list(self._logger.handlers):
            handler.flush()
            handler.close()
            self._logger.removeHandler(handler)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_node(node: object, prefix: str, is_last: bool, lines: list[str]) -> None:
        connector = "└─" if is_last else "├─"
        sym = getattr(node, "symbol_type", "?")
        depth = getattr(node, "depth", 0)
        role = getattr(node, "spatial_role", "?")
        feats = getattr(node, "drawing_features", {}) or {}
        feat_str = "  " + "  ".join(f"{k}={v:.2f}" for k, v in list(feats.items())[:4])
        lines.append(f"  {prefix}{connector} {sym} (depth={depth}) [{role}]{feat_str}")
        children = getattr(node, "children", [])
        child_prefix = prefix + ("   " if is_last else "│  ")
        for i, child in enumerate(children):
            SpellLogger._format_node(child, child_prefix, i == len(children) - 1, lines)
