"""Grimoire : sauvegarde et rejeu de sorts resolus (Phase 7).

Un sort, apres resolution, est un `ResolvedSpell.params` (dict). Le grimoire
stocke ces dicts dans des slots numerotes et permet de les rejouer sans
avoir a redessiner.

Persistance JSON simple (un slot par cle de slot). L'etat est charge au
demarrage du client et sauvegarde a chaque modification.

Limite : rejouer depuis un slot ne reproduit PAS la trace graphique ; seul
le comportement serveur est preserve. Le joueur qui veut archiver un
dessin devra le faire cote UI (hors scope Phase 7).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from client.magic.resolver.resolved_spell import ResolvedSpell, params_to_network_spec


_DEFAULT_PATH = Path.home() / ".hehe" / "grimoire.json"


@dataclass
class GrimoireEntry:
    slot: str
    name: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"slot": self.slot, "name": self.name, "params": self.params}

    @classmethod
    def from_dict(cls, data: dict) -> "GrimoireEntry":
        return cls(
            slot=str(data.get("slot", "?")),
            name=str(data.get("name", "")),
            params=dict(data.get("params", {})),
        )


class Grimoire:
    """Petite base locale de sorts appris. Un seul fichier JSON."""

    def __init__(self, path: Path | None = None):
        self._path = path or _DEFAULT_PATH
        self._entries: dict[str, GrimoireEntry] = {}
        self._load()

    # ── IO ──────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            for entry in raw.get("entries", []):
                e = GrimoireEntry.from_dict(entry)
                self._entries[e.slot] = e
        except Exception as e:
            logging.warning(f"grimoire: failed to load {self._path}: {e}")

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._path.open("w", encoding="utf-8") as f:
                json.dump(
                    {"entries": [e.to_dict() for e in self._entries.values()]},
                    f, indent=2, ensure_ascii=False,
                )
        except Exception as e:
            logging.warning(f"grimoire: failed to save {self._path}: {e}")

    # ── API ─────────────────────────────────────────────────────

    def save_resolved(self, slot: str, name: str, resolved: ResolvedSpell) -> None:
        """Stocke les params d'un ResolvedSpell dans un slot."""
        self._entries[slot] = GrimoireEntry(slot=slot, name=name, params=dict(resolved.params))
        self._save()

    def save_params(self, slot: str, name: str, params: dict[str, Any]) -> None:
        self._entries[slot] = GrimoireEntry(slot=slot, name=name, params=dict(params))
        self._save()

    def remove(self, slot: str) -> bool:
        if slot in self._entries:
            del self._entries[slot]
            self._save()
            return True
        return False

    def get(self, slot: str) -> GrimoireEntry | None:
        return self._entries.get(slot)

    def list_slots(self) -> list[GrimoireEntry]:
        return sorted(self._entries.values(), key=lambda e: e.slot)

    def replay_network_spec(self, slot: str) -> dict[str, Any] | None:
        """Retourne un dict reseau pret a envoyer {'t':'s',...} ou None."""
        entry = self._entries.get(slot)
        if entry is None:
            return None
        stub = ResolvedSpell(params=dict(entry.params), ast=None, property_snapshot={})
        return params_to_network_spec(stub)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "grim.json"
        g = Grimoire(path=path)
        assert g.list_slots() == []

        params = {
            "element": "fire", "power": 0.6, "speed": 0.5,
            "compression": 0.3, "_dir_explicit": True,
            "dir_x": 1.0, "dir_y": 0.0,
        }
        g.save_params("1", "Projectile feu", params)
        g.save_params("2", "Mur feu", {
            "element": "fire", "power": 0.5,
            "compression": 2.0, "axis_x": 1.0, "axis_y": 0.0,
            "elongation": 2.0,
        })
        assert len(g.list_slots()) == 2

        net = g.replay_network_spec("1")
        assert net is not None
        assert net["t"] == "s"
        assert net["e"] == "fire"
        assert net["spd"] > 0.0

        # Persistance
        g2 = Grimoire(path=path)
        assert len(g2.list_slots()) == 2
        assert g2.get("1").name == "Projectile feu"

        # Suppression
        assert g2.remove("1")
        assert not g2.remove("ghost")
        assert len(g2.list_slots()) == 1

    print("grimoire: OK")
