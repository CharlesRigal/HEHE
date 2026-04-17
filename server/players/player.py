from __future__ import annotations

import math
import time


class Player:
    __slots__ = (
        "_id",
        "_x",
        "_y",
        "_vx",
        "_vy",
        "_facing_x",
        "_facing_y",
        "_health",
        "_max_health",
        "_alive",
        "_last_input_seq",
        "_last_update",
    )

    def __init__(
        self,
        id: str,
        x: float,
        y: float,
        vx: float = 0.0,
        vy: float = 0.0,
        facing_x: float = 1.0,
        facing_y: float = 0.0,
        health: float = 100.0,
        max_health: float = 100.0,
        alive: bool = True,
        last_input_seq: int = -1,
        last_update: float | None = None,
    ):
        self._id = id
        self._x = float(x)
        self._y = float(y)
        self._vx = float(vx)
        self._vy = float(vy)

        norm = math.hypot(facing_x, facing_y)
        if norm <= 1e-9:
            self._facing_x = 1.0
            self._facing_y = 0.0
        else:
            self._facing_x = float(facing_x) / norm
            self._facing_y = float(facing_y) / norm

        clamped_max_health = max(1.0, float(max_health))
        self._max_health = clamped_max_health
        self._health = max(0.0, min(float(health), clamped_max_health))
        self._alive = bool(alive) and self._health > 0.0
        self._last_input_seq = int(last_input_seq)
        self._last_update = time.time() if last_update is None else float(last_update)

    @property
    def id(self) -> str:
        return self._id

    @property
    def x(self) -> float:
        return self._x

    @property
    def y(self) -> float:
        return self._y

    @property
    def vx(self) -> float:
        return self._vx

    @property
    def vy(self) -> float:
        return self._vy

    @property
    def facing_x(self) -> float:
        return self._facing_x

    @property
    def facing_y(self) -> float:
        return self._facing_y

    @property
    def health(self) -> float:
        return self._health

    @property
    def max_health(self) -> float:
        return self._max_health

    @property
    def alive(self) -> bool:
        return self._alive

    @property
    def last_input_seq(self) -> int:
        return self._last_input_seq

    @property
    def last_update(self) -> float:
        return self._last_update

    def mark_updated(self) -> None:
        self._last_update = time.time()

    def is_alive(self) -> bool:
        return self._alive

    def is_dead(self) -> bool:
        return not self._alive

    def is_moving(self) -> bool:
        return abs(self._vx) > 1e-9 or abs(self._vy) > 1e-9

    def health_ratio(self) -> float:
        if self._max_health <= 1e-9:
            return 0.0
        return max(0.0, min(1.0, self._health / self._max_health))

    def position(self) -> tuple[float, float]:
        return self._x, self._y

    def velocity(self) -> tuple[float, float]:
        return self._vx, self._vy

    def facing(self) -> tuple[float, float]:
        return self._facing_x, self._facing_y

    def distance_sq_to(self, x: float, y: float) -> float:
        dx = self._x - float(x)
        dy = self._y - float(y)
        return dx * dx + dy * dy

    def can_receive_input(self) -> bool:
        return self._alive

    def record_input_seq(self, seq: int) -> bool:
        try:
            cast_seq = int(seq)
        except (TypeError, ValueError):
            return False
        if cast_seq <= self._last_input_seq:
            return False
        self._last_input_seq = cast_seq
        self.mark_updated()
        return True

    def set_facing_from_vector(self, vx: float, vy: float) -> bool:
        norm = math.hypot(vx, vy)
        if norm <= 1e-9:
            return False
        self._facing_x = float(vx) / norm
        self._facing_y = float(vy) / norm
        self.mark_updated()
        return True

    def set_motion(self, *, x: float, y: float, vx: float, vy: float) -> None:
        self._x = float(x)
        self._y = float(y)
        self._vx = float(vx)
        self._vy = float(vy)
        self.mark_updated()

    def stop(self) -> None:
        self._vx = 0.0
        self._vy = 0.0
        self.mark_updated()

    def take_damage(self, amount: float) -> bool:
        if amount <= 0.0 or not self._alive:
            return False

        self._health = max(0.0, self._health - float(amount))
        if self._health <= 0.0:
            self._alive = False
            self._vx = 0.0
            self._vy = 0.0

        self.mark_updated()
        return not self._alive

    def to_full_state(self) -> dict:
        return {
            "id": self._id,
            "x": self._x,
            "y": self._y,
            "vx": self._vx,
            "vy": self._vy,
            "facing_x": self._facing_x,
            "facing_y": self._facing_y,
            "health": self._health,
            "max_health": self._max_health,
            "alive": self._alive,
            "last_input_seq": self._last_input_seq,
            "last_update": self._last_update,
        }

    def to_update_state(self) -> dict:
        return {
            "x": self._x,
            "y": self._y,
            "health": self._health,
            "alive": self._alive,
            "last_input_seq": self._last_input_seq,
        }

    def can_cast_a_spell(self) -> bool:
        if self._alive:
            return True
        return False
