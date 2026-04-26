# Versatile Thermostat Poêle à Pellets
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/jmcollin78/vtherm_pellet_stove.svg)](https://github.com/jmcollin78/vtherm_pellet_stove/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[Read the English version](README.md)

<p align="center">
  <img src="custom_components/vtherm_pellet_stove/brand/logo.png" alt="Logo Poêle à Pellets" width="300" />
</p>

<p align="center">
  <strong>Plugin de régulation pour poêle à pellets — Versatile Thermostat</strong>
</p>

<p align="center">
  Pilotez votre poêle à pellets avec un algorithme de régulation adapté à ses contraintes physiques : temps d'allumage long, niveaux de puissance, protection anti-court-cycle et coupure de sécurité.
</p>

---

## Qu'est-ce que vtherm_pellet_stove ?

`vtherm_pellet_stove` enregistre un nouvel algorithme proportionnel nommé **`pellet_regulation`** dans l'API publique de [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) (VTherm). Il étend les thermostats VTherm configurés en mode `over_switch` ciblant une entité `climate` (ex. Duepi EVO, poêle ESPHome, MCZ, EdilKamin, …).

Fonctionnalités principales :

- **Hystérésis paramétrable** — seuils `hysteresis_on` / `hysteresis_off` configurables.
- **Protection anti-court-cycle** — durées minimales de marche/arrêt et délai de refroidissement pour protéger la bougie.
- **Coupure de sécurité** — force l'extinction si la température ambiante dépasse un seuil configurable.
- **Pilotage optionnel du niveau de puissance** — ajuste `fan_mode` ou `preset_mode` du poêle en fonction de ΔT et de la pente de température.
- **Boost** — hausse temporaire au niveau maximal après une augmentation de consigne.
- **État persistant** — survit aux redémarrages de Home Assistant.
- **Compatible HACS** — entrée de defaults globaux + surcharges par thermostat.

## Intégration avec Versatile Thermostat

Le plugin utilise l'API publique [vtherm_api](https://github.com/KipK/vtherm_api). Une fois installé :

1. Configurer Versatile Thermostat en mode **`over_switch`**.
2. Définir l'entité sous-jacente comme l'entité `climate.*` du poêle.
3. Configurer `vswitch_on = "set_hvac_mode/hvac_mode:heat"` et `vswitch_off = "set_hvac_mode/hvac_mode:off"`.
4. Sélectionner **`pellet_regulation`** comme fonction proportionnelle.

## Installation

### Via HACS (recommandé)

[![Ouvrir votre instance Home Assistant et ouvrir un dépôt dans HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jmcollin78&repository=vtherm_pellet_stove&category=Integration)

1. Ajouter ce dépôt dans HACS comme intégration personnalisée.
2. Installer **Versatile Thermostat Poêle à Pellets**.
3. Redémarrer Home Assistant.
4. Ajouter l'intégration depuis **Paramètres → Appareils et services**.

### Installation manuelle

1. Copier `custom_components/vtherm_pellet_stove` dans le dossier `custom_components` de HA.
2. Redémarrer Home Assistant.
3. Ajouter l'intégration depuis **Paramètres → Appareils et services**.

## Documentation

- 🇬🇧 [User documentation](documentation/en/vtherm_pellet_stove.md)
- �🇧 [Technical documentation](documentation/en/technical_doc.md)
- 🇫🇷 [Documentation utilisateur](documentation/fr/vtherm_pellet_stove.md)
- 🇫🇷 [Documentation technique](documentation/fr/technical_doc.md)

## Architecture

Voir [tech-docs/plugin-architecture.md](tech-docs/plugin-architecture.md) pour le document d'architecture détaillé.

## Auteur

- [@jmcollin78](https://github.com/jmcollin78)

## Licence

MIT — voir [LICENSE](LICENSE).
