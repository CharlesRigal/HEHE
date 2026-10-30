"""Tableau de dessin : capture des traits et lancement a la fermeture du cercle.

Clic droit : ouvre ou ferme le tableau. Clic gauche maintenu : trace un trait.
Apres chaque trait, seul un test de fermeture du cercle est fait (C1, L1) :
pas de retour en temps reel. Quand le cercle se ferme, la lecture complete
tourne en arriere-plan, puis le tableau s'efface.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

import pygame

from client.magic.geometry import Stroke, path_length
from client.magic.reader import PentacleReader, PentacleReading
from client.magic.spell_message import build_spell_message

# Epaisseur du trait rendu. Elle fixe aussi le seuil de contact (L2).
STROKE_THICKNESS = 4
MIN_POINT_SPACING = 2.0

_INK = (30, 18, 60)
_INK_DONE = (90, 70, 140)
_PAPER = (244, 236, 214, 150)


@dataclass
class CastResult:
    message: dict | None          # None : sort inerte, rien a envoyer
    reading: PentacleReading
    status: str


class DrawingBoard:
    def __init__(self, reader: PentacleReader | None = None) -> None:
        self.reader = reader or PentacleReader()
        self.is_open = False
        self.strokes: list[Stroke] = []
        self._current: Stroke | None = None
        self._pending: Future | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pentacle")
        self.ink_used = 0.0       # S3 : chaque trait compte, mort ou non

    # ── Entrees ───────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> bool:
        """True si l'evenement a ete consomme par le tableau."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self.toggle()
            return True
        if not self.is_open or self._pending is not None:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._current = [tuple(map(float, event.pos))]
            return True
        if event.type == pygame.MOUSEMOTION and self._current is not None:
            x, y = map(float, event.pos)
            lx, ly = self._current[-1]
            if (x - lx) ** 2 + (y - ly) ** 2 >= MIN_POINT_SPACING ** 2:
                self._current.append((x, y))
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._current is not None:
            self._finish_stroke()
            return True
        return False

    def toggle(self) -> None:
        self.is_open = not self.is_open
        if not self.is_open:
            self.clear()

    def clear(self) -> None:
        self.strokes = []
        self._current = None

    def _finish_stroke(self) -> None:
        stroke, self._current = self._current, None
        self.strokes.append(stroke)
        self.ink_used += path_length(stroke)
        if self.reader.circle_closed(self.strokes, STROKE_THICKNESS):
            strokes = list(self.strokes)
            self._pending = self._executor.submit(self._read, strokes)

    def _read(self, strokes: list[Stroke]) -> CastResult:
        reading = self.reader.read(strokes, STROKE_THICKNESS)
        message = build_spell_message(reading)
        if message is None:
            status = "Sort inerte : pas d'emblème lisible."
        else:
            alive = len(message["signs"])
            dead = len(reading.signs) - alive
            status = f"Sort {reading.emblem.element} : {alive} signe(s)" + (f", {dead} mort(s)" if dead else "")
        return CastResult(message, reading, status)

    def poll(self) -> CastResult | None:
        """Resultat de la lecture une fois prete ; le tableau est alors efface."""
        if self._pending is None or not self._pending.done():
            return None
        future, self._pending = self._pending, None
        self.clear()
        return future.result()

    def debug_snapshot(self) -> dict:
        return {
            "open": self.is_open,
            "strokes": len(self.strokes),
            "reading": self._pending is not None,
            "ink": round(self.ink_used),
        }

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ── Rendu ─────────────────────────────────────────────────────

    def draw(self, screen: pygame.Surface) -> None:
        if not self.is_open:
            return
        paper = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        paper.fill(_PAPER)
        screen.blit(paper, (0, 0))
        color = _INK_DONE if self._pending is not None else _INK
        for stroke in self.strokes + ([self._current] if self._current else []):
            if len(stroke) == 1:
                pygame.draw.circle(screen, color, stroke[0], STROKE_THICKNESS / 2)
            else:
                pygame.draw.lines(screen, color, False, stroke, STROKE_THICKNESS)
