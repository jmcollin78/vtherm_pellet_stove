"""BoostManager — montée temporaire au niveau de puissance maximal.

Aucune dépendance envers Home Assistant : ce module est testable en pure Python.

Quand la consigne VTherm augmente d'au moins ``MIN_SETPOINT_RISE`` °C, le
poêle passe au niveau max pendant ``power_boost_duration_min`` minutes pour
atteindre rapidement la nouvelle température cible.

Le champ ``boost_until`` de :class:`~pellet.state.PelletState` stocke la fin
du boost (datetime aware) ou ``None`` si aucun boost n'est actif.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

#: Variation minimale de consigne (°C) pour déclencher le boost.
MIN_SETPOINT_RISE: float = 0.5


class BoostManager:
    """Gère le boost temporaire de puissance après hausse de consigne.

    Paramètres
    ----------
    power_boost_duration_min:
        Durée du boost en minutes.
    """

    def __init__(self, *, power_boost_duration_min: int) -> None:
        self._power_boost_duration_min = power_boost_duration_min

    # ------------------------------------------------------------------
    # Propriétés
    # ------------------------------------------------------------------

    @property
    def power_boost_duration_min(self) -> int:
        """Durée du boost (minutes)."""
        return self._power_boost_duration_min

    @power_boost_duration_min.setter
    def power_boost_duration_min(self, value: int) -> None:
        self._power_boost_duration_min = value

    # ------------------------------------------------------------------
    # Interface
    # ------------------------------------------------------------------

    def maybe_trigger(
        self,
        *,
        previous_target: float | None,
        new_target: float,
        now: datetime,
        state,
    ) -> bool:
        """Déclenche le boost si la consigne a suffisamment augmenté.

        Paramètres
        ----------
        previous_target:
            Consigne précédente (°C). ``None`` si premier appel.
        new_target:
            Nouvelle consigne (°C).
        now:
            Horodatage courant.
        state:
            Instance de :class:`~pellet.state.PelletState` (modifié en place).

        Returns
        -------
        bool
            ``True`` si le boost vient d'être déclenché.
        """
        if previous_target is None:
            return False
        delta = new_target - previous_target
        if delta >= MIN_SETPOINT_RISE:
            state.boost_until = _make_aware(now) + timedelta(
                minutes=self._power_boost_duration_min
            )
            return True
        return False

    def is_boosting(self, now: datetime, state) -> bool:
        """Retourne ``True`` si le boost est actif à l'instant ``now``."""
        if state.boost_until is None:
            return False
        return _make_aware(now) < state.boost_until

    def cancel(self, state) -> None:
        """Annule le boost en cours."""
        state.boost_until = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_aware(dt: datetime) -> datetime:
    """Rend le datetime aware (UTC) s'il est naïf."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
