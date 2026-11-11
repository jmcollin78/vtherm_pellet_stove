"""PelletState — état persistant du poêle à pellets.

Aucune dépendance envers Home Assistant : ce module est testable en pure Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


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

    # ------------------------------------------------------------------
    # Sérialisation
    # ------------------------------------------------------------------

    def save_state(self) -> dict:
        """Sérialise l'état pour le Store HA (valeurs JSON-sérialisables)."""
        return {
            "is_heating": self.is_heating,
            "current_level_index": self.current_level_index,
            "last_on_at": self.last_on_at.isoformat() if self.last_on_at else None,
            "last_off_at": self.last_off_at.isoformat() if self.last_off_at else None,
            "last_reason": self.last_reason,
            "boost_until": self.boost_until.isoformat() if self.boost_until else None,
        }

    def restore_state(
        self,
        data: dict,
        *,
        tolerate_invalid_dates: bool = False,
        now: datetime | None = None,
    ) -> None:
        """Recharge l'état depuis un dict issu du Store HA."""

        if not data:
            return
        self.is_heating = bool(data.get("is_heating", False))
        self.current_level_index = data.get("current_level_index")
        self.last_reason = data.get("last_reason")

        raw_on = data.get("last_on_at")
        parse_date = _parse_iso_tolerant if tolerate_invalid_dates else _parse_iso
        self.last_on_at = parse_date(raw_on)

        raw_off = data.get("last_off_at")
        self.last_off_at = parse_date(raw_off)

        if tolerate_invalid_dates:
            reference = _to_utc(now or datetime.now(timezone.utc))
            if self.last_on_at is not None and self.last_on_at > reference:
                self.last_on_at = None
            if self.last_off_at is not None and self.last_off_at > reference:
                self.last_off_at = None

        raw_boost = data.get("boost_until")
        self.boost_until = parse_date(raw_boost)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_iso(value: str | None) -> datetime | None:
    """Convertit une chaîne ISO 8601 en datetime aware, ou None."""
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    # Rendre le datetime aware (UTC) si naive
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_iso_tolerant(value: str | None) -> datetime | None:
    """Parse a switch history date, returning None for malformed values."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return _to_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def _to_utc(value: datetime) -> datetime:
    """Normalize an aware or naive datetime to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
