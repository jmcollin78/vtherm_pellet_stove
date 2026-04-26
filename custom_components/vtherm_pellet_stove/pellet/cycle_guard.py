"""CycleGuard — garde-fous anti-court-cycle pour poêle à pellets.

Aucune dépendance envers Home Assistant : ce module est testable en pure Python.

Logique :
  • ``can_turn_off`` : l'extinction n'est autorisée que si le poêle a chauffé
    au minimum ``min_on_duration_min`` minutes depuis le dernier allumage.
  • ``can_turn_on``  : le rallumage n'est autorisé que si le poêle a été arrêté
    depuis au moins ``min_off_duration_min + cooldown_duration_min`` minutes.
  • La sécurité haute (``safety_room_temp``) **outrepasse** ``can_turn_off``
    (cf. controller.py qui applique ce cas avant d'interroger le guard).
"""

from __future__ import annotations

from datetime import datetime


class CycleGuard:
    """Contrôleur des durées minimales marche/arrêt d'un poêle à pellets.

    Paramètres
    ----------
    min_on_duration_min:
        Durée minimale de chauffe avant qu'une extinction soit autorisée.
    min_off_duration_min:
        Durée minimale d'arrêt avant qu'un allumage soit autorisé.
    cooldown_duration_min:
        Délai de cooldown supplémentaire ajouté à ``min_off_duration_min``
        après chaque extinction.
    """

    def __init__(
        self,
        *,
        min_on_duration_min: int,
        min_off_duration_min: int,
        cooldown_duration_min: int,
    ) -> None:
        self._min_on_duration_min = min_on_duration_min
        self._min_off_duration_min = min_off_duration_min
        self._cooldown_duration_min = cooldown_duration_min

    # ------------------------------------------------------------------
    # Propriétés
    # ------------------------------------------------------------------

    @property
    def min_on_duration_min(self) -> int:
        """Durée minimale de marche (minutes)."""
        return self._min_on_duration_min

    @min_on_duration_min.setter
    def min_on_duration_min(self, value: int) -> None:
        self._min_on_duration_min = value

    @property
    def min_off_duration_min(self) -> int:
        """Durée minimale d'arrêt (minutes)."""
        return self._min_off_duration_min

    @min_off_duration_min.setter
    def min_off_duration_min(self, value: int) -> None:
        self._min_off_duration_min = value

    @property
    def cooldown_duration_min(self) -> int:
        """Délai de cooldown ajouté à l'arrêt (minutes)."""
        return self._cooldown_duration_min

    @cooldown_duration_min.setter
    def cooldown_duration_min(self, value: int) -> None:
        self._cooldown_duration_min = value

    # ------------------------------------------------------------------
    # Décisions
    # ------------------------------------------------------------------

    def can_turn_off(self, now: datetime, state) -> bool:
        """Indique si l'extinction est autorisée selon la durée de chauffe.

        Paramètres
        ----------
        now:
            Horodatage courant (datetime aware recommandé).
        state:
            Instance de :class:`~pellet.state.PelletState`.

        Returns
        -------
        bool
            ``True`` si l'extinction est autorisée (durée min atteinte ou
            jamais allumé), ``False`` si le poêle doit continuer à chauffer.
        """
        if state.last_on_at is None:
            return True
        elapsed_min = _elapsed_minutes(state.last_on_at, now)
        return elapsed_min >= self._min_on_duration_min

    def can_turn_on(self, now: datetime, state) -> bool:
        """Indique si le rallumage est autorisé selon la durée d'arrêt.

        Paramètres
        ----------
        now:
            Horodatage courant (datetime aware recommandé).
        state:
            Instance de :class:`~pellet.state.PelletState`.

        Returns
        -------
        bool
            ``True`` si le rallumage est autorisé (durée min + cooldown
            atteints ou jamais éteint), ``False`` si le poêle doit rester
            éteint.
        """
        if state.last_off_at is None:
            return True
        elapsed_min = _elapsed_minutes(state.last_off_at, now)
        required = self._min_off_duration_min + self._cooldown_duration_min
        return elapsed_min >= required

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def seconds_until_can_turn_on(self, now: datetime, state) -> float:
        """Secondes restantes avant que le rallumage soit autorisé.

        Retourne 0 si déjà autorisé.
        """
        if state.last_off_at is None:
            return 0.0
        elapsed_min = _elapsed_minutes(state.last_off_at, now)
        required = self._min_off_duration_min + self._cooldown_duration_min
        remaining_min = required - elapsed_min
        return max(0.0, remaining_min * 60)

    def seconds_until_can_turn_off(self, now: datetime, state) -> float:
        """Secondes restantes avant que l'extinction soit autorisée.

        Retourne 0 si déjà autorisé.
        """
        if state.last_on_at is None:
            return 0.0
        elapsed_min = _elapsed_minutes(state.last_on_at, now)
        remaining_min = self._min_on_duration_min - elapsed_min
        return max(0.0, remaining_min * 60)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _elapsed_minutes(since: datetime, now: datetime) -> float:
    """Retourne le nombre de minutes écoulées entre *since* et *now*."""
    return (now - since).total_seconds() / 60
