"""HysteresisDecider — décision binaire ON/OFF pour poêle à pellets.

Aucune dépendance envers Home Assistant : ce module est testable en pure Python.

Principe : deux seuils indépendants évitent les oscillations rapides :
  • On allume si  current ≤ target − hysteresis_on
  • On éteint si  current ≥ target + hysteresis_off
  • Sinon, on maintient l'état courant (« hold in band »).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DecisionType = Literal["ON", "OFF"]


@dataclass(frozen=True)
class HysteresisDecision:
    """Résultat brut de l'hystérésis, avant application des garde-fous."""

    decision: DecisionType
    reason: str
    #: True si la décision est un changement d'état (transition), False si maintien.
    is_hold: bool = False


class HysteresisDecider:
    """Double-seuil hystérésis paramétrable.

    Paramètres
    ----------
    hysteresis_on:
        Écart (°C) en dessous de la consigne pour déclencher l'allumage.
        Allumage si ``current ≤ target − hysteresis_on``.
    hysteresis_off:
        Écart (°C) au-dessus de la consigne pour déclencher l'extinction.
        Extinction si ``current ≥ target + hysteresis_off``.
    """

    def __init__(self, hysteresis_on: float, hysteresis_off: float) -> None:
        if hysteresis_on < 0:
            raise ValueError(f"hysteresis_on must be ≥ 0, got {hysteresis_on}")
        if hysteresis_off < 0:
            raise ValueError(f"hysteresis_off must be ≥ 0, got {hysteresis_off}")
        self._hysteresis_on = hysteresis_on
        self._hysteresis_off = hysteresis_off

    # ------------------------------------------------------------------
    # Propriétés
    # ------------------------------------------------------------------

    @property
    def hysteresis_on(self) -> float:
        """Seuil d'allumage (°C en dessous de la consigne)."""
        return self._hysteresis_on

    @hysteresis_on.setter
    def hysteresis_on(self, value: float) -> None:
        if value < 0:
            raise ValueError(f"hysteresis_on must be ≥ 0, got {value}")
        self._hysteresis_on = value

    @property
    def hysteresis_off(self) -> float:
        """Seuil d'extinction (°C au-dessus de la consigne)."""
        return self._hysteresis_off

    @hysteresis_off.setter
    def hysteresis_off(self, value: float) -> None:
        if value < 0:
            raise ValueError(f"hysteresis_off must be ≥ 0, got {value}")
        self._hysteresis_off = value

    # ------------------------------------------------------------------
    # Décision
    # ------------------------------------------------------------------

    def decide(
        self,
        *,
        is_heating: bool,
        current: float | None,
        target: float,
    ) -> HysteresisDecision:
        """Calcule la décision hystérésis brute (sans garde-fous pellet).

        Si ``current`` est None (capteur indisponible), l'état courant est
        maintenu (hold).

        Parameters
        ----------
        is_heating:
            État courant du poêle (True = en chauffe).
        current:
            Température ambiante mesurée (°C). None si non disponible.
        target:
            Consigne de température (°C).

        Returns
        -------
        HysteresisDecision
            `decision` vaut "ON" ou "OFF".
            `is_hold` est True si on maintient l'état sans changement.
        """
        if current is None:
            # Pas de mesure → maintien sécuritaire de l'état courant.
            hold_decision: DecisionType = "ON" if is_heating else "OFF"
            return HysteresisDecision(
                decision=hold_decision,
                reason="hold_in_band",
                is_hold=True,
            )

        if is_heating:
            if current >= target + self._hysteresis_off:
                return HysteresisDecision(
                    decision="OFF",
                    reason="above_off_threshold",
                    is_hold=False,
                )
            # Maintien de la chauffe dans la bande.
            return HysteresisDecision(
                decision="ON",
                reason="hold_in_band",
                is_hold=True,
            )
        else:
            if current <= target - self._hysteresis_on:
                return HysteresisDecision(
                    decision="ON",
                    reason="below_on_threshold",
                    is_hold=False,
                )
            # Maintien de l'arrêt dans la bande.
            return HysteresisDecision(
                decision="OFF",
                reason="hold_in_band",
                is_hold=True,
            )
