"""Tests unitaires — HysteresisDecider (pellet/hysteresis.py).

Couvre les décisions ON, OFF et hold, avec capteur disponible ou absent.
"""

from __future__ import annotations

import pytest

from custom_components.vtherm_pellet_stove.pellet.hysteresis import HysteresisDecider


@pytest.fixture()
def decider() -> HysteresisDecider:
    """Hystérésis standard : on=0.5°C, off=0.3°C."""
    return HysteresisDecider(hysteresis_on=0.5, hysteresis_off=0.3)


# ---------------------------------------------------------------------------
# Validation des paramètres
# ---------------------------------------------------------------------------


def test_negative_hysteresis_on_raises() -> None:
    with pytest.raises(ValueError):
        HysteresisDecider(hysteresis_on=-0.1, hysteresis_off=0.3)


def test_negative_hysteresis_off_raises() -> None:
    with pytest.raises(ValueError):
        HysteresisDecider(hysteresis_on=0.5, hysteresis_off=-0.1)


# ---------------------------------------------------------------------------
# Décisions en chauffe (is_heating=True)
# ---------------------------------------------------------------------------


def test_heating_above_off_threshold_returns_off(decider: HysteresisDecider) -> None:
    """current ≥ target + hysteresis_off → OFF (above_off_threshold)."""
    result = decider.decide(is_heating=True, current=20.4, target=20.0)
    assert result.decision == "OFF"
    assert result.reason == "above_off_threshold"
    assert result.is_hold is False


def test_heating_exactly_at_off_threshold_returns_off(decider: HysteresisDecider) -> None:
    """current == target + hysteresis_off → OFF."""
    result = decider.decide(is_heating=True, current=20.3, target=20.0)
    assert result.decision == "OFF"


def test_heating_below_off_threshold_holds_on(decider: HysteresisDecider) -> None:
    """current < target + hysteresis_off → maintien ON (hold_in_band)."""
    result = decider.decide(is_heating=True, current=20.1, target=20.0)
    assert result.decision == "ON"
    assert result.reason == "hold_in_band"
    assert result.is_hold is True


# ---------------------------------------------------------------------------
# Décisions à l'arrêt (is_heating=False)
# ---------------------------------------------------------------------------


def test_not_heating_below_on_threshold_returns_on(decider: HysteresisDecider) -> None:
    """current ≤ target − hysteresis_on → ON (below_on_threshold)."""
    result = decider.decide(is_heating=False, current=19.5, target=20.0)
    assert result.decision == "ON"
    assert result.reason == "below_on_threshold"
    assert result.is_hold is False


def test_not_heating_exactly_at_on_threshold_returns_on(decider: HysteresisDecider) -> None:
    """current == target − hysteresis_on → ON."""
    result = decider.decide(is_heating=False, current=19.5, target=20.0)
    assert result.decision == "ON"


def test_not_heating_above_on_threshold_holds_off(decider: HysteresisDecider) -> None:
    """current > target − hysteresis_on → maintien OFF (hold_in_band)."""
    result = decider.decide(is_heating=False, current=19.8, target=20.0)
    assert result.decision == "OFF"
    assert result.reason == "hold_in_band"
    assert result.is_hold is True


# ---------------------------------------------------------------------------
# Capteur indisponible (current=None)
# ---------------------------------------------------------------------------


def test_no_sensor_heating_holds_on(decider: HysteresisDecider) -> None:
    """Capteur absent en chauffe → maintien ON sécuritaire."""
    result = decider.decide(is_heating=True, current=None, target=20.0)
    assert result.decision == "ON"
    assert result.is_hold is True


def test_no_sensor_not_heating_holds_off(decider: HysteresisDecider) -> None:
    """Capteur absent à l'arrêt → maintien OFF sécuritaire."""
    result = decider.decide(is_heating=False, current=None, target=20.0)
    assert result.decision == "OFF"
    assert result.is_hold is True
