"""PowerMapper — sélection du niveau de puissance du poêle à pellets.

Aucune dépendance envers Home Assistant : ce module est testable en pure Python.

La table de mapping (§7.4 du document d'architecture) traduit un couple
(delta_T, slope) en un index dans la liste ``power_levels`` fournie par la
configuration :

+---------------------------+-------------+--------------------+
| delta_T = target − current| slope (°C/h)| Index niveau       |
+===========================+=============+====================+
| ≥ +2.0                    | n'importe   | dernier (max)      |
+---------------------------+-------------+--------------------+
| +1.0 .. +2.0              | < +0.3      | avant-dernier      |
+---------------------------+-------------+--------------------+
| +1.0 .. +2.0              | ≥ +0.3      | médian sup.        |
+---------------------------+-------------+--------------------+
| +0.3 .. +1.0              | < +0.2      | médian             |
+---------------------------+-------------+--------------------+
| +0.3 .. +1.0              | ≥ +0.2      | médian inf.        |
+---------------------------+-------------+--------------------+
| -0.3 .. +0.3              | n'importe   | premier (min)      |
+---------------------------+-------------+--------------------+
| < -0.3                    | n'importe   | None (poêle OFF)   |
+---------------------------+-------------+--------------------+

Le niveau effectif est ``power_levels[index]``.
"""

from __future__ import annotations


class PowerMapper:
    """Convertit (delta_T, slope) en index dans la liste des niveaux de puissance.

    Paramètres
    ----------
    power_levels:
        Liste ordonnée des valeurs de niveau (du plus faible au plus fort),
        ex. ``["1", "2", "3", "4", "5"]``.
    default_level_index:
        Index par défaut quand ``slope`` est None ou la situation est
        indéterminée.
    """

    def __init__(
        self,
        *,
        power_levels: list[str],
        default_level_index: int = 2,
    ) -> None:
        if not power_levels:
            raise ValueError("power_levels must not be empty")
        self._power_levels = list(power_levels)
        self._default_level_index = default_level_index

    # ------------------------------------------------------------------
    # Propriétés
    # ------------------------------------------------------------------

    @property
    def power_levels(self) -> list[str]:
        """Liste ordonnée des niveaux de puissance."""
        return list(self._power_levels)

    @power_levels.setter
    def power_levels(self, value: list[str]) -> None:
        if not value:
            raise ValueError("power_levels must not be empty")
        self._power_levels = list(value)

    @property
    def default_level_index(self) -> int:
        """Index de niveau par défaut."""
        return self._default_level_index

    @default_level_index.setter
    def default_level_index(self, value: int) -> None:
        self._default_level_index = value

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    def choose_level_index(
        self,
        delta_t: float,
        slope: float | None = None,
    ) -> int | None:
        """Retourne l'index du niveau de puissance adapté.

        Paramètres
        ----------
        delta_t:
            Différence ``target − current`` (°C). Positif = il faut chauffer.
        slope:
            Pente de montée en température (°C/h). None si non disponible.

        Returns
        -------
        int | None
            Index dans ``power_levels``, ou ``None`` si le poêle devrait être
            éteint (``delta_t < −0.3``).
        """
        n = len(self._power_levels)
        # Indices dérivés de la longueur de la liste
        idx_max = n - 1
        idx_penultimate = max(0, n - 2)
        idx_mid = n // 2
        idx_mid_high = min(n - 1, (n // 2) + 1) if n > 2 else idx_mid
        idx_mid_low = max(0, (n // 2) - 1) if n > 2 else idx_mid
        idx_min = 0

        effective_slope = slope if slope is not None else 0.0

        if delta_t >= 2.0:
            return idx_max

        if 1.0 <= delta_t < 2.0:
            if effective_slope < 0.3:
                return idx_penultimate
            return idx_mid_high

        if 0.3 <= delta_t < 1.0:
            if effective_slope < 0.2:
                return idx_mid
            return idx_mid_low

        if -0.3 <= delta_t < 0.3:
            return idx_min

        # delta_t < -0.3 : poêle doit être OFF
        return None

    def level_value(self, index: int) -> str:
        """Retourne la valeur du niveau à l'index donné (ex. ``"3"``).

        L'index est clamped à ``[0, len(power_levels) − 1]``.
        """
        clamped = max(0, min(index, len(self._power_levels) - 1))
        return self._power_levels[clamped]
