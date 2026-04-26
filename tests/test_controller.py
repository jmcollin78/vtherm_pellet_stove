"""Tests unitaires — PelletRegulationController (pellet/controller.py).

Couvre les scénarios fonctionnels 1–6, 8, 9 définis en §11.2 du document
d'architecture.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.vtherm_pellet_stove.pellet.controller import (
    PelletRegulationController,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime(2026, 1, 15, 20, 0, 0, tzinfo=timezone.utc)


def _make_ctrl(
    *,
    hysteresis_on: float = 0.5,
    hysteresis_off: float = 0.3,
    min_on_duration_min: int = 30,
    min_off_duration_min: int = 20,
    cooldown_duration_min: int = 5,
    safety_room_temp: float = 26.0,
    min_on_percent: float = 0.0,
    max_on_percent: float = 1.0,
    power_control_enabled: bool = True,
    power_levels: list[str] | None = None,
    power_default_level_index: int = 2,
    power_boost_enabled: bool = True,
    power_boost_duration_min: int = 15,
) -> PelletRegulationController:
    return PelletRegulationController(
        hysteresis_on=hysteresis_on,
        hysteresis_off=hysteresis_off,
        min_on_duration_min=min_on_duration_min,
        min_off_duration_min=min_off_duration_min,
        cooldown_duration_min=cooldown_duration_min,
        safety_room_temp=safety_room_temp,
        min_on_percent=min_on_percent,
        max_on_percent=max_on_percent,
        power_control_enabled=power_control_enabled,
        power_levels=power_levels or ["1", "2", "3", "4", "5"],
        power_default_level_index=power_default_level_index,
        power_boost_enabled=power_boost_enabled,
        power_boost_duration_min=power_boost_duration_min,
    )


# ---------------------------------------------------------------------------
# Scénario 1 — Allumage : current ≤ target − hysteresis_on
# ---------------------------------------------------------------------------


def test_scenario_1_ignition_below_threshold() -> None:
    """current ≤ target − hysteresis_on → on_percent = max, reason=below_on_threshold."""
    ctrl = _make_ctrl()
    now = _now()

    result = ctrl.calculate(
        target_temp=20.0,
        current_temp=19.4,  # 19.4 ≤ 20.0 − 0.5 = 19.5
        hvac_mode="heat",
        now=now,
    )

    assert result == pytest.approx(1.0)
    assert ctrl.last_reason == "below_on_threshold"
    assert ctrl.is_heating is True


def test_scenario_1_exactly_at_threshold() -> None:
    """current == target − hysteresis_on (= 19.5) → allumage."""
    ctrl = _make_ctrl()
    result = ctrl.calculate(
        target_temp=20.0,
        current_temp=19.5,
        hvac_mode="heat",
        now=_now(),
    )
    assert result == pytest.approx(1.0)
    assert ctrl.last_reason == "below_on_threshold"


# ---------------------------------------------------------------------------
# Scénario 2 — Extinction autorisée : min_on_duration écoulée
# ---------------------------------------------------------------------------


def test_scenario_2_turn_off_after_min_on_duration() -> None:
    """current ≥ target + hysteresis_off ET min_on écoulé → on_percent=0, reason=above_off_threshold."""
    ctrl = _make_ctrl(min_on_duration_min=30)
    now = _now()

    # Simuler un poêle en chauffe depuis 35 min
    ctrl._state.is_heating = True
    ctrl._state.last_on_at = now - timedelta(minutes=35)

    result = ctrl.calculate(
        target_temp=20.0,
        current_temp=20.4,  # ≥ 20.0 + 0.3 = 20.3
        hvac_mode="heat",
        now=now,
    )

    assert result == pytest.approx(0.0)
    assert ctrl.last_reason == "above_off_threshold"
    assert ctrl.is_heating is False


# ---------------------------------------------------------------------------
# Scénario 3 — Extinction bloquée : min_on_duration non écoulée
# ---------------------------------------------------------------------------


def test_scenario_3_turn_off_locked_min_on_not_elapsed() -> None:
    """Même condition mais min_on non écoulé → on_percent=max, reason=locked_on."""
    ctrl = _make_ctrl(min_on_duration_min=30)
    now = _now()

    # Poêle allumé depuis seulement 15 min
    ctrl._state.is_heating = True
    ctrl._state.last_on_at = now - timedelta(minutes=15)

    result = ctrl.calculate(
        target_temp=20.0,
        current_temp=20.4,  # dépasse le seuil OFF
        hvac_mode="heat",
        now=now,
    )

    assert result == pytest.approx(1.0)
    assert ctrl.last_reason == "locked_on"
    assert ctrl.is_heating is True


# ---------------------------------------------------------------------------
# Scénario 4 — Allumage bloqué : min_off + cooldown non écoulés
# ---------------------------------------------------------------------------


def test_scenario_4_turn_on_locked_min_off_not_elapsed() -> None:
    """current < target − hysteresis_on mais min_off + cooldown non écoulés → on_percent=0, reason=locked_off."""
    ctrl = _make_ctrl(min_off_duration_min=20, cooldown_duration_min=5)
    now = _now()

    # Poêle éteint depuis seulement 10 min (< 25 requis)
    ctrl._state.is_heating = False
    ctrl._state.last_off_at = now - timedelta(minutes=10)

    result = ctrl.calculate(
        target_temp=20.0,
        current_temp=19.0,  # bien en dessous du seuil ON
        hvac_mode="heat",
        now=now,
    )

    assert result == pytest.approx(0.0)
    assert ctrl.last_reason == "locked_off"
    assert ctrl.is_heating is False


# ---------------------------------------------------------------------------
# Scénario 5 — Sécurité : current ≥ safety_room_temp (override des garde-fous)
# ---------------------------------------------------------------------------


def test_scenario_5_safety_override_while_heating_locked() -> None:
    """current ≥ safety_room_temp → on_percent=0, reason=safety, même si locked_on."""
    ctrl = _make_ctrl(safety_room_temp=26.0, min_on_duration_min=60)
    now = _now()

    # Poêle allumé depuis 5 min seulement (min_on=60 → normalement locked_on)
    ctrl._state.is_heating = True
    ctrl._state.last_on_at = now - timedelta(minutes=5)

    result = ctrl.calculate(
        target_temp=20.0,
        current_temp=27.0,  # ≥ 26.0 = safety
        hvac_mode="heat",
        now=now,
    )

    assert result == pytest.approx(0.0)
    assert ctrl.last_reason == "safety"
    assert ctrl.is_heating is False


def test_scenario_5_safety_at_exact_threshold() -> None:
    """current == safety_room_temp → déclenche la sécurité."""
    ctrl = _make_ctrl(safety_room_temp=26.0)
    now = _now()
    ctrl._state.is_heating = True
    ctrl._state.last_on_at = now - timedelta(minutes=5)

    result = ctrl.calculate(
        target_temp=20.0,
        current_temp=26.0,
        hvac_mode="heat",
        now=now,
    )

    assert result == pytest.approx(0.0)
    assert ctrl.last_reason == "safety"


# ---------------------------------------------------------------------------
# Scénario 6 — HVAC mode OFF
# ---------------------------------------------------------------------------


def test_scenario_6_hvac_off_returns_min_on_percent() -> None:
    """hvac_mode == 'off' → on_percent=0, reason=hvac_off."""
    ctrl = _make_ctrl(min_on_percent=0.0)
    ctrl._state.is_heating = True

    result = ctrl.calculate(
        target_temp=20.0,
        current_temp=19.0,
        hvac_mode="off",
        now=_now(),
    )

    assert result == pytest.approx(0.0)
    assert ctrl.last_reason == "hvac_off"
    assert ctrl.is_heating is False


def test_scenario_6_hvac_off_case_insensitive() -> None:
    """hvac_mode est comparé en lowercase."""
    ctrl = _make_ctrl()
    result = ctrl.calculate(
        target_temp=20.0,
        current_temp=19.0,
        hvac_mode="OFF",
        now=_now(),
    )
    assert result == pytest.approx(0.0)
    assert ctrl.last_reason == "hvac_off"


# ---------------------------------------------------------------------------
# Scénario 8 — Pilotage de puissance : delta_T=+1.5, slope=+0.1
# ---------------------------------------------------------------------------


def test_scenario_8_power_level_penultimate() -> None:
    """delta_T=+1.5, slope=+0.1 → niveau avant-dernier (index 3 sur 5 niveaux)."""
    ctrl = _make_ctrl(
        power_control_enabled=True,
        power_levels=["1", "2", "3", "4", "5"],
        power_boost_enabled=False,  # pas de boost pour isoler le test
    )
    now = _now()

    # S'assurer que le guard ne bloque pas (jamais éteint)
    ctrl._state.is_heating = False
    ctrl._state.last_off_at = None

    result = ctrl.calculate(
        target_temp=21.5,
        current_temp=20.0,  # delta_T = 21.5 − 20.0 = 1.5
        slope=0.1,
        hvac_mode="heat",
        now=now,
    )

    assert result == pytest.approx(1.0)  # on_percent = max
    assert ctrl.current_level_index == 3  # avant-dernier sur 5


# ---------------------------------------------------------------------------
# Scénario 9 — Boost : hausse de consigne ≥ 0.5°C
# ---------------------------------------------------------------------------


def test_scenario_9_boost_triggers_on_setpoint_rise() -> None:
    """Hausse de consigne ≥ 0.5°C → niveau max pendant la durée du boost."""
    ctrl = _make_ctrl(
        power_control_enabled=True,
        power_levels=["1", "2", "3", "4", "5"],
        power_boost_enabled=True,
        power_boost_duration_min=15,
    )
    now = _now()

    # Premier appel avec consigne initiale
    ctrl.calculate(
        target_temp=20.0,
        current_temp=19.4,
        hvac_mode="heat",
        now=now,
    )

    # Deuxième appel avec hausse de consigne de +1°C
    result = ctrl.calculate(
        target_temp=21.0,  # +1.0 ≥ 0.5 → boost
        current_temp=19.4,
        hvac_mode="heat",
        now=now,
    )

    assert result == pytest.approx(1.0)
    # Le boost doit être actif → niveau maximal (index 4)
    assert ctrl.current_level_index == 4
    assert ctrl._state.boost_until is not None


def test_scenario_9_boost_expires_after_duration() -> None:
    """Après expiration du boost, retour au niveau normal."""
    ctrl = _make_ctrl(
        power_control_enabled=True,
        power_levels=["1", "2", "3", "4", "5"],
        power_boost_enabled=True,
        power_boost_duration_min=15,
    )
    now = _now()

    # Déclencher le boost
    ctrl.calculate(target_temp=20.0, current_temp=19.0, hvac_mode="heat", now=now)
    ctrl.calculate(target_temp=21.0, current_temp=19.0, hvac_mode="heat", now=now)

    # Avancer le temps de 20 min (> 15 min de boost)
    after_boost = now + timedelta(minutes=20)

    result = ctrl.calculate(
        target_temp=21.0,
        current_temp=19.0,  # delta_T = 2.0 → niveau max sans boost aussi
        hvac_mode="heat",
        now=after_boost,
    )

    assert result == pytest.approx(1.0)
    # Pas de boost actif
    assert not ctrl._boost_manager.is_boosting(after_boost, ctrl._state)


def test_scenario_9_no_boost_on_small_rise() -> None:
    """Hausse de consigne < 0.5°C → pas de boost."""
    ctrl = _make_ctrl(
        power_control_enabled=True,
        power_levels=["1", "2", "3", "4", "5"],
        power_boost_enabled=True,
        power_boost_duration_min=15,
    )
    now = _now()

    ctrl.calculate(target_temp=20.0, current_temp=19.0, hvac_mode="heat", now=now)
    ctrl.calculate(target_temp=20.3, current_temp=19.0, hvac_mode="heat", now=now)

    assert ctrl._state.boost_until is None


# ---------------------------------------------------------------------------
# Persistance de l'état (save / restore)
# ---------------------------------------------------------------------------


def test_save_restore_state_roundtrip() -> None:
    """save_state puis restore_state → état identique."""
    ctrl = _make_ctrl()
    now = _now()

    ctrl._state.is_heating = True
    ctrl._state.last_on_at = now - timedelta(minutes=10)
    ctrl._state.last_reason = "below_on_threshold"

    data = ctrl.save_state()

    ctrl2 = _make_ctrl()
    ctrl2.restore_state(data)

    assert ctrl2._state.is_heating is True
    assert ctrl2._state.last_reason == "below_on_threshold"
    assert ctrl2._state.last_on_at is not None


# ---------------------------------------------------------------------------
# Contrat prop_algorithm VTherm
# ---------------------------------------------------------------------------


def test_on_percent_and_calculated_on_percent_alias() -> None:
    """on_percent et calculated_on_percent retournent la même valeur."""
    ctrl = _make_ctrl()
    ctrl.calculate(target_temp=20.0, current_temp=19.0, hvac_mode="heat", now=_now())
    assert ctrl.on_percent == ctrl.calculated_on_percent


def test_calculate_positional_args_compat() -> None:
    """calculate(target, current) fonctionne sans kwargs (compat contrat VTherm)."""
    ctrl = _make_ctrl()
    result = ctrl.calculate(20.0, 19.0)
    assert isinstance(result, float)
