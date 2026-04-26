"""Tests unitaires — CycleGuard (pellet/cycle_guard.py).

Couvre can_turn_off, can_turn_on et les helpers de diagnostic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.vtherm_pellet_stove.pellet.cycle_guard import CycleGuard
from custom_components.vtherm_pellet_stove.pellet.state import PelletState


def _now() -> datetime:
    return datetime(2026, 1, 15, 20, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def guard() -> CycleGuard:
    """Garde-fous standard : min_on=30min, min_off=20min, cooldown=5min."""
    return CycleGuard(
        min_on_duration_min=30,
        min_off_duration_min=20,
        cooldown_duration_min=5,
    )


# ---------------------------------------------------------------------------
# can_turn_off
# ---------------------------------------------------------------------------


def test_can_turn_off_never_on(guard: CycleGuard) -> None:
    """Jamais allumé → extinction autorisée immédiatement."""
    state = PelletState()
    assert guard.can_turn_off(_now(), state) is True


def test_can_turn_off_duration_elapsed(guard: CycleGuard) -> None:
    """Durée min atteinte → extinction autorisée."""
    state = PelletState(last_on_at=_now() - timedelta(minutes=31))
    assert guard.can_turn_off(_now(), state) is True


def test_can_turn_off_exactly_at_min(guard: CycleGuard) -> None:
    """Exactement 30 min → extinction autorisée."""
    state = PelletState(last_on_at=_now() - timedelta(minutes=30))
    assert guard.can_turn_off(_now(), state) is True


def test_can_turn_off_duration_not_elapsed(guard: CycleGuard) -> None:
    """Durée min non atteinte → extinction refusée."""
    state = PelletState(last_on_at=_now() - timedelta(minutes=15))
    assert guard.can_turn_off(_now(), state) is False


# ---------------------------------------------------------------------------
# can_turn_on
# ---------------------------------------------------------------------------


def test_can_turn_on_never_off(guard: CycleGuard) -> None:
    """Jamais éteint → allumage autorisé immédiatement."""
    state = PelletState()
    assert guard.can_turn_on(_now(), state) is True


def test_can_turn_on_duration_elapsed(guard: CycleGuard) -> None:
    """min_off + cooldown atteints → allumage autorisé."""
    # 20 + 5 = 25 min requis
    state = PelletState(last_off_at=_now() - timedelta(minutes=26))
    assert guard.can_turn_on(_now(), state) is True


def test_can_turn_on_exactly_at_required(guard: CycleGuard) -> None:
    """Exactement 25 min → allumage autorisé."""
    state = PelletState(last_off_at=_now() - timedelta(minutes=25))
    assert guard.can_turn_on(_now(), state) is True


def test_can_turn_on_duration_not_elapsed(guard: CycleGuard) -> None:
    """min_off + cooldown non atteints → allumage refusé."""
    state = PelletState(last_off_at=_now() - timedelta(minutes=10))
    assert guard.can_turn_on(_now(), state) is False


# ---------------------------------------------------------------------------
# Helpers de diagnostic
# ---------------------------------------------------------------------------


def test_seconds_until_can_turn_on_returns_zero_when_allowed(guard: CycleGuard) -> None:
    state = PelletState(last_off_at=_now() - timedelta(minutes=30))
    assert guard.seconds_until_can_turn_on(_now(), state) == 0.0


def test_seconds_until_can_turn_on_returns_remaining(guard: CycleGuard) -> None:
    state = PelletState(last_off_at=_now() - timedelta(minutes=10))
    # 25 min requis − 10 min écoulées = 15 min restantes = 900 secondes
    assert guard.seconds_until_can_turn_on(_now(), state) == pytest.approx(900.0)


def test_seconds_until_can_turn_off_returns_zero_when_allowed(guard: CycleGuard) -> None:
    state = PelletState(last_on_at=_now() - timedelta(minutes=35))
    assert guard.seconds_until_can_turn_off(_now(), state) == 0.0


def test_seconds_until_can_turn_off_returns_remaining(guard: CycleGuard) -> None:
    state = PelletState(last_on_at=_now() - timedelta(minutes=15))
    # 30 min requis − 15 min écoulées = 15 min restantes = 900 secondes
    assert guard.seconds_until_can_turn_off(_now(), state) == pytest.approx(900.0)
