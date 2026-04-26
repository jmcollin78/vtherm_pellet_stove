"""Tests unitaires — PowerMapper (pellet/power_mapper.py).

Couvre la table de mapping delta_T/slope → index de niveau (scénario 8).
"""

from __future__ import annotations

import pytest

from custom_components.vtherm_pellet_stove.pellet.power_mapper import PowerMapper


LEVELS = ["1", "2", "3", "4", "5"]  # 5 niveaux


@pytest.fixture()
def mapper() -> PowerMapper:
    return PowerMapper(power_levels=LEVELS, default_level_index=2)


# ---------------------------------------------------------------------------
# Validation des paramètres
# ---------------------------------------------------------------------------


def test_empty_power_levels_raises() -> None:
    with pytest.raises(ValueError):
        PowerMapper(power_levels=[], default_level_index=0)


# ---------------------------------------------------------------------------
# Table de mapping (5 niveaux : index 0..4)
# ---------------------------------------------------------------------------
# idx_max=4, idx_penultimate=3, idx_mid=2, idx_mid_high=3, idx_mid_low=1, idx_min=0


def test_delta_t_above_2_returns_max(mapper: PowerMapper) -> None:
    """delta_T ≥ 2.0 → index 4 (max)."""
    assert mapper.choose_level_index(delta_t=2.0) == 4
    assert mapper.choose_level_index(delta_t=3.5) == 4


def test_delta_t_1_to_2_low_slope_returns_penultimate(mapper: PowerMapper) -> None:
    """delta_T ∈ [1.0, 2.0), slope < 0.3 → index 3 (avant-dernier)."""
    # Scénario 8 : delta_T = +1.5, slope = +0.1 → avant-dernier
    assert mapper.choose_level_index(delta_t=1.5, slope=0.1) == 3


def test_delta_t_1_to_2_high_slope_returns_mid_high(mapper: PowerMapper) -> None:
    """delta_T ∈ [1.0, 2.0), slope ≥ 0.3 → index 3 (médian sup, 5 niveaux)."""
    assert mapper.choose_level_index(delta_t=1.5, slope=0.5) == 3


def test_delta_t_03_to_1_low_slope_returns_mid(mapper: PowerMapper) -> None:
    """delta_T ∈ [0.3, 1.0), slope < 0.2 → index 2 (médian)."""
    assert mapper.choose_level_index(delta_t=0.6, slope=0.1) == 2


def test_delta_t_03_to_1_high_slope_returns_mid_low(mapper: PowerMapper) -> None:
    """delta_T ∈ [0.3, 1.0), slope ≥ 0.2 → index 1 (médian inf)."""
    assert mapper.choose_level_index(delta_t=0.6, slope=0.3) == 1


def test_delta_t_near_zero_returns_min(mapper: PowerMapper) -> None:
    """delta_T ∈ [-0.3, 0.3) → index 0 (minimum)."""
    assert mapper.choose_level_index(delta_t=0.0) == 0
    assert mapper.choose_level_index(delta_t=0.2) == 0
    assert mapper.choose_level_index(delta_t=-0.2) == 0


def test_delta_t_below_minus_03_returns_none(mapper: PowerMapper) -> None:
    """delta_T < -0.3 → None (poêle doit être éteint)."""
    assert mapper.choose_level_index(delta_t=-0.5) is None
    assert mapper.choose_level_index(delta_t=-2.0) is None


def test_slope_none_uses_zero(mapper: PowerMapper) -> None:
    """slope=None est traité comme 0 (slope < seuil)."""
    # delta_T=1.5, slope implicitement 0 < 0.3 → avant-dernier
    assert mapper.choose_level_index(delta_t=1.5, slope=None) == 3


# ---------------------------------------------------------------------------
# level_value
# ---------------------------------------------------------------------------


def test_level_value_returns_correct_string(mapper: PowerMapper) -> None:
    assert mapper.level_value(0) == "1"
    assert mapper.level_value(4) == "5"
    assert mapper.level_value(2) == "3"


def test_level_value_clamps_index(mapper: PowerMapper) -> None:
    assert mapper.level_value(-1) == "1"
    assert mapper.level_value(99) == "5"


# ---------------------------------------------------------------------------
# Cas limites avec 2 niveaux
# ---------------------------------------------------------------------------


def test_two_levels_mapping() -> None:
    """Avec 2 niveaux, les indices restent cohérents."""
    mapper2 = PowerMapper(power_levels=["low", "high"], default_level_index=0)
    assert mapper2.choose_level_index(delta_t=2.0) == 1  # max
    assert mapper2.choose_level_index(delta_t=0.0) == 0  # min
