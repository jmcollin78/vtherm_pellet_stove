"""PelletState — état persistant du poêle à pellets.

Aucune dépendance envers Home Assistant : ce module est testable en pure Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite


@dataclass
class PelletState:
    """État interne persisté entre deux cycles de régulation et entre redémarrages HA."""

    #: True si le poêle est en chauffe (is_heating).
    is_heating: bool = False

    #: Index courant dans la liste ``power_levels`` (None = inconnu / non initialisé).
    current_level_index: int | None = None

    #: Horodatage du dernier allumage (None si jamais allumé depuis init).
    last_on_at: datetime | None = None

    #: Horodatage du dernier arrêt (None si jamais éteint depuis init).
    last_off_at: datetime | None = None

    #: Raison de la dernière décision de calcul.
    last_reason: str | None = None

    #: Datetime jusqu'à laquelle le boost est actif (None = pas de boost).
    boost_until: datetime | None = None

    observed_cycle: str | None = None
    observed_phase: str | None = None
    available: bool = False
    elapsed_on_sec: float = 0.0
    elapsed_off_sec: float = 0.0
    pending: str | None = None
    off_priority: bool = False
    command_error: str | None = None
    resume_reason: str = "missing"
    _active_at: float | None = field(default=None, repr=False)

    def observe(self, cycle: str | None, phase: str | None, now: float) -> None:
        """Reconcile observed cycles, counting only available monotonic time."""
        if self.available and self._active_at is not None:
            elapsed = max(0.0, now - self._active_at)
            if self.observed_cycle == "ON":
                self.elapsed_on_sec += elapsed
            elif self.observed_cycle == "OFF":
                self.elapsed_off_sec += elapsed
        self._active_at = now if cycle is not None else None
        self.available = cycle is not None
        self.observed_phase = phase
        if cycle is None:
            self.resume_reason = "unavailable"
            return
        if cycle != self.observed_cycle:
            self.resume_reason = "mismatch" if self.observed_cycle else self.resume_reason
            self.elapsed_on_sec = 0.0
            self.elapsed_off_sec = 0.0
            self.observed_cycle = cycle
        else:
            self.resume_reason = "matching"
        self.is_heating = cycle == "ON"
        if self.pending == cycle and phase not in ("Cleaning", "Eco idle"):
            self.pending = None
        elif self.pending == "OFF" and phase in ("Cleaning", "Eco idle"):
            self.pending = None

    @property
    def elapsed_cooldown_sec(self) -> float:
        """Cooling and minimum OFF share the same observed origin."""
        return self.elapsed_off_sec

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def save_state(self) -> dict:
        """Sérialise l'état pour le Store HA (valeurs JSON-sérialisables)."""
        return {
            "cycle_version": 1,
            "observed_cycle": self.observed_cycle,
            "observed_phase": self.observed_phase,
            "elapsed_on_sec": self.elapsed_on_sec,
            "elapsed_off_sec": self.elapsed_off_sec,
            "pending": self.pending,
            "off_priority": self.off_priority,
            "command_error": self.command_error,
            "is_heating": self.is_heating,
            "current_level_index": self.current_level_index,
            "last_on_at": self.last_on_at.isoformat() if self.last_on_at else None,
            "last_off_at": self.last_off_at.isoformat() if self.last_off_at else None,
            "last_reason": self.last_reason,
            "boost_until": self.boost_until.isoformat() if self.boost_until else None,
        }

    def restore_state(self, data: dict) -> None:
        """Recharge l'état depuis un dict issu du Store HA."""
        if not data:
            return
        self.available = False
        self._active_at = None
        self.resume_reason = "invalid"
        cycle = data.get("observed_cycle")
        counters = (data.get("elapsed_on_sec"), data.get("elapsed_off_sec"))
        if (
            data.get("cycle_version") == 1
            and cycle in ("ON", "OFF")
            and all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and isfinite(value)
                and value >= 0
                for value in counters
            )
        ):
            self.observed_cycle = cycle
            self.observed_phase = data.get("observed_phase")
            self.elapsed_on_sec, self.elapsed_off_sec = counters
            self.pending = data.get("pending") if data.get("pending") in ("ON", "OFF") else None
            self.off_priority = data.get("off_priority") is True
            self.command_error = data.get("command_error")
            self.resume_reason = "matching"
        self.is_heating = bool(data.get("is_heating", False))
        self.current_level_index = data.get("current_level_index")
        self.last_reason = data.get("last_reason")

        raw_on = data.get("last_on_at")
        self.last_on_at = _parse_iso(raw_on)

        raw_off = data.get("last_off_at")
        self.last_off_at = _parse_iso(raw_off)

        raw_boost = data.get("boost_until")
        self.boost_until = _parse_iso(raw_boost)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso(value: str | None) -> datetime | None:
    """Convertit une chaîne ISO 8601 en datetime aware, ou None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    # Rendre le datetime aware (UTC) si naive
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
