"""PelletRegulationController — orchestration complète de la régulation pellet.

Aucune dépendance envers Home Assistant : ce module est testable en pure Python.

Ce contrôleur :
  1. expose le contrat ``prop_algorithm`` attendu par VTherm (§9.1),
  2. orchestre HysteresisDecider + CycleGuard + PowerMapper + BoostManager,
  3. met à jour PelletState après chaque décision.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .boost import BoostManager
from .cycle_guard import CycleGuard
from .hysteresis import HysteresisDecider
from .power_mapper import PowerMapper
from .state import PelletState

_LOGGER = logging.getLogger(__name__)

# Chaîne représentant le mode HVAC OFF dans VTherm / HA.
HVAC_MODE_OFF = "off"


@dataclass(frozen=True)
class PelletDecision:
    """Résultat d'un appel à :meth:`PelletRegulationController.calculate`."""

    #: Valeur retournée à VTherm (0.0 ou max_on_percent).
    on_percent: float
    #: Raison lisible de la décision.
    reason: str
    #: Index de puissance courant (None si non applicable).
    level_index: int | None = None


class PelletRegulationController:
    """Contrôleur de régulation pour poêle à pellets.

    Paramètres
    ----------
    hysteresis_on:
        Écart °C en dessous de la consigne pour allumer.
    hysteresis_off:
        Écart °C au-dessus de la consigne pour éteindre.
    min_on_percent:
        Valeur ``on_percent`` envoyée au scheduler quand le poêle est éteint.
    max_on_percent:
        Valeur ``on_percent`` envoyée au scheduler quand le poêle chauffe.
    min_on_duration_min:
        Durée minimale de chauffe (minutes).
    min_off_duration_min:
        Durée minimale d'arrêt (minutes).
    cooldown_duration_min:
        Cooldown supplémentaire après extinction (minutes).
    safety_room_temp:
        Température ambiante de sécurité (°C) → force OFF.
    power_control_enabled:
        Active le calcul du niveau de puissance.
    power_levels:
        Liste ordonnée des niveaux (ex. ``["1".."5"]``).
    power_default_level_index:
        Index par défaut quand la pente est inconnue.
    power_boost_enabled:
        Active le boost après hausse de consigne.
    power_boost_duration_min:
        Durée du boost (minutes).
    """

    def __init__(
        self,
        *,
        hysteresis_on: float,
        hysteresis_off: float,
        min_on_percent: float = 0.0,
        max_on_percent: float = 1.0,
        min_on_duration_min: int,
        min_off_duration_min: int,
        cooldown_duration_min: int,
        safety_room_temp: float,
        power_control_enabled: bool = True,
        power_levels: list[str] | None = None,
        power_default_level_index: int = 2,
        power_boost_enabled: bool = True,
        power_boost_duration_min: int = 15,
    ) -> None:
        self._min_on_percent = min_on_percent
        self._max_on_percent = max_on_percent
        self._safety_room_temp = safety_room_temp
        self._power_control_enabled = power_control_enabled

        # Sous-composants
        self._hysteresis = HysteresisDecider(
            hysteresis_on=hysteresis_on,
            hysteresis_off=hysteresis_off,
        )
        self._guard = CycleGuard(
            min_on_duration_min=min_on_duration_min,
            min_off_duration_min=min_off_duration_min,
            cooldown_duration_min=cooldown_duration_min,
        )
        self._power_mapper: PowerMapper | None = None
        if power_control_enabled and power_levels:
            self._power_mapper = PowerMapper(
                power_levels=power_levels,
                default_level_index=power_default_level_index,
            )

        self._boost_manager: BoostManager | None = None
        if power_boost_enabled:
            self._boost_manager = BoostManager(
                power_boost_duration_min=power_boost_duration_min,
            )

        # État persisté
        self._state: PelletState = PelletState()
        # Dernière décision calculée
        self._last_decision: PelletDecision = PelletDecision(
            on_percent=min_on_percent,
            reason="init",
        )
        # Suivi de la consigne précédente pour le boost
        self._previous_target: float | None = None

    # ------------------------------------------------------------------
    # Contrat VTherm prop_algorithm (§9.1)
    # ------------------------------------------------------------------

    @property
    def on_percent(self) -> float:
        """Valeur ``on_percent`` de la dernière décision."""
        return self._last_decision.on_percent

    @property
    def calculated_on_percent(self) -> float:
        """Alias de ``on_percent`` pour compatibilité avec le contrat VTherm."""
        return self.on_percent

    def calculate(
        self,
        target_temp: float,
        current_temp: float | None,
        *args: Any,
        slope: float | None = None,
        hvac_mode: str = "heat",
        now: datetime | None = None,
        **kwargs: Any,
    ) -> float:
        """Calcule l'``on_percent`` et met à jour l'état interne.

        Signature compatible avec le contrat ``prop_algorithm`` de VTherm qui
        appelle ``calculate(target_temp, current_temp, ...)``.

        Parameters
        ----------
        target_temp:
            Consigne de température (°C).
        current_temp:
            Température ambiante mesurée (°C). ``None`` si indisponible.
        slope:
            Pente de montée en température (°C/h). Utilisé pour le niveau de
            puissance. ``None`` si indisponible.
        hvac_mode:
            Mode HVAC courant du VTherm (``"heat"`` ou ``"off"``).
        now:
            Horodatage courant. Si ``None``, ``datetime.now(UTC)`` est utilisé.

        Returns
        -------
        float
            ``on_percent`` calculé (0.0 ou ``max_on_percent``).
        """
        if now is None:
            now = datetime.now(timezone.utc)

        decision = self._compute(
            target=target_temp,
            current=current_temp,
            slope=slope,
            hvac_mode=hvac_mode,
            now=now,
        )
        self._last_decision = decision
        self._state.last_reason = decision.reason
        self._state.current_level_index = decision.level_index

        _LOGGER.debug(
            "PelletRegulationController.calculate target=%.1f current=%s "
            "on_percent=%.1f reason=%s level_index=%s",
            target_temp,
            f"{current_temp:.1f}" if current_temp is not None else "N/A",
            decision.on_percent,
            decision.reason,
            decision.level_index,
        )
        return decision.on_percent

    def restore_state(self, data: dict | None) -> None:
        """Restaure l'état depuis les données du Store HA."""
        if data:
            self._state.restore_state(data)

    def save_state(self) -> dict:
        """Sérialise l'état pour le Store HA."""
        return self._state.save_state()

    async def on_cycle_started(
        self,
        on_time_sec: float,
        off_time_sec: float,
        on_percent: float,
        hvac_mode: str,
    ) -> None:
        """Callback appelé par le cycle scheduler au début d'un cycle."""
        # v0.1 : no-op (réservé pour mesure de puissance réalisée en v0.2+)

    async def on_cycle_completed(
        self,
        e_eff: float | None = None,
        elapsed_ratio: float = 1.0,
        cycle_duration_min: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Callback appelé par le cycle scheduler à la fin d'un cycle."""
        # v0.1 : no-op

    # ------------------------------------------------------------------
    # Propriétés d'état (lecture seule)
    # ------------------------------------------------------------------

    @property
    def state(self) -> PelletState:
        """État interne courant (lecture seule)."""
        return self._state

    @property
    def last_reason(self) -> str | None:
        """Raison de la dernière décision."""
        return self._state.last_reason

    @property
    def current_level_index(self) -> int | None:
        """Index de niveau de puissance courant."""
        return self._state.current_level_index

    @property
    def current_level_value(self) -> str | None:
        """Valeur du niveau de puissance courant (ex. ``"3"``), ou None."""
        if self._power_mapper is None or self._state.current_level_index is None:
            return None
        return self._power_mapper.level_value(self._state.current_level_index)

    @property
    def is_heating(self) -> bool:
        """True si le poêle est en chauffe selon l'état interne."""
        return self._state.is_heating

    # ------------------------------------------------------------------
    # Calcul interne
    # ------------------------------------------------------------------

    def _compute(
        self,
        *,
        target: float,
        current: float | None,
        slope: float | None,
        hvac_mode: str,
        now: datetime,
    ) -> PelletDecision:
        """Logique de régulation complète (§7.2 du document d'architecture)."""

        # ----------------------------------------------------------------
        # Boost : détecter une hausse de consigne avant tout calcul
        # ----------------------------------------------------------------
        if self._boost_manager is not None:
            self._boost_manager.maybe_trigger(
                previous_target=self._previous_target,
                new_target=target,
                now=now,
                state=self._state,
            )
        self._previous_target = target

        # ----------------------------------------------------------------
        # 1. Mode HVAC OFF → extinction immédiate
        # ----------------------------------------------------------------
        if hvac_mode.lower() == HVAC_MODE_OFF:
            if self._state.is_heating:
                self._state.last_off_at = now
            self._state.is_heating = False
            return PelletDecision(
                on_percent=self._min_on_percent,
                reason="hvac_off",
                level_index=None,
            )

        # ----------------------------------------------------------------
        # 2. Sécurité haute température → extinction forcée (override garde-fous)
        # ----------------------------------------------------------------
        if current is not None and current >= self._safety_room_temp:
            if self._state.is_heating:
                self._state.last_off_at = now
                self._state.is_heating = False
            return PelletDecision(
                on_percent=self._min_on_percent,
                reason="safety",
                level_index=None,
            )

        # ----------------------------------------------------------------
        # 3. Décision hystérésis brute
        # ----------------------------------------------------------------
        hyst = self._hysteresis.decide(
            is_heating=self._state.is_heating,
            current=current,
            target=target,
        )

        # ----------------------------------------------------------------
        # 4. Application des garde-fous anti-court-cycle
        # ----------------------------------------------------------------
        final_decision = hyst.decision
        final_reason = hyst.reason

        if hyst.decision == "OFF" and self._state.is_heating:
            if not self._guard.can_turn_off(now, self._state):
                final_decision = "ON"
                final_reason = "locked_on"

        elif hyst.decision == "ON" and not self._state.is_heating:
            if not self._guard.can_turn_on(now, self._state):
                final_decision = "OFF"
                final_reason = "locked_off"

        # ----------------------------------------------------------------
        # 5. Mise à jour de l'état et calcul du niveau de puissance
        # ----------------------------------------------------------------
        if final_decision == "ON":
            if not self._state.is_heating:
                self._state.last_on_at = now
            self._state.is_heating = True

            level_index = self._compute_level_index(
                target=target, current=current, slope=slope, now=now
            )
            return PelletDecision(
                on_percent=self._max_on_percent,
                reason=final_reason,
                level_index=level_index,
            )
        else:
            if self._state.is_heating:
                self._state.last_off_at = now
            self._state.is_heating = False
            return PelletDecision(
                on_percent=self._min_on_percent,
                reason=final_reason,
                level_index=None,
            )

    def _compute_level_index(
        self,
        *,
        target: float,
        current: float | None,
        slope: float | None,
        now: datetime,
    ) -> int | None:
        """Retourne l'index de niveau de puissance selon la situation."""
        if self._power_mapper is None:
            return None

        # Boost actif → niveau maximal
        if self._boost_manager is not None and self._boost_manager.is_boosting(
            now, self._state
        ):
            return len(self._power_mapper.power_levels) - 1

        if current is None:
            return self._power_mapper.default_level_index

        delta_t = target - current
        idx = self._power_mapper.choose_level_index(delta_t=delta_t, slope=slope)
        if idx is None:
            # Le mapper dit OFF → on retourne le niveau par défaut car le
            # contrôleur a déjà décidé ON (guard-rail ou hold).
            return self._power_mapper.default_level_index
        return idx
