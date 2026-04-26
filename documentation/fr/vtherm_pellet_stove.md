# vtherm_pellet_stove — Guide utilisateur

> Plugin pour [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) qui apporte un algorithme de régulation adapté aux poêles à pellets (`pellet_regulation`) dans Home Assistant.

---

## Table des matières

- [vtherm\_pellet\_stove — Guide utilisateur](#vtherm_pellet_stove--guide-utilisateur)
  - [Table des matières](#table-des-matières)
  - [1. Prérequis](#1-prérequis)
  - [2. Installation](#2-installation)
    - [Via HACS (recommandé)](#via-hacs-recommandé)
    - [Installation manuelle](#installation-manuelle)
  - [Démarche — Mise en place en 5 étapes](#démarche--mise-en-place-en-5-étapes)
    - [Étape 1 — Installer Versatile Thermostat](#étape-1--installer-versatile-thermostat)
    - [Étape 2 — Installer vtherm\_pellet\_stove et créer la configuration par défaut](#étape-2--installer-vtherm_pellet_stove-et-créer-la-configuration-par-défaut)
    - [Étape 3 — Créer le VTherm de type `over_switch`](#étape-3--créer-le-vtherm-de-type-over_switch)
    - [Étape 4 — Ajouter les commandes personnalisées d'allumage et d'extinction](#étape-4--ajouter-les-commandes-personnalisées-dallumage-et-dextinction)
    - [Étape 5 — Relier vtherm\_pellet\_stove au VTherm](#étape-5--relier-vtherm_pellet_stove-au-vtherm)
  - [3. Fonctionnement](#3-fonctionnement)
  - [4. Configuration de Versatile Thermostat](#4-configuration-de-versatile-thermostat)
  - [5. Configuration du plugin](#5-configuration-du-plugin)
    - [5.1 Entrée de defaults globaux](#51-entrée-de-defaults-globaux)
    - [5.2 Entrée par thermostat](#52-entrée-par-thermostat)
    - [5.3 Options flow](#53-options-flow)
  - [6. Référence des paramètres](#6-référence-des-paramètres)
    - [Hystérésis](#hystérésis)
    - [Garde-fous pellet](#garde-fous-pellet)
    - [Pilotage du niveau de puissance (optionnel)](#pilotage-du-niveau-de-puissance-optionnel)
  - [7. Exemple complet — Poêle Duepi EVO](#7-exemple-complet--poêle-duepi-evo)
    - [Étape 1 — Installer le plugin](#étape-1--installer-le-plugin)
    - [Étape 2 — Créer le VTherm](#étape-2--créer-le-vtherm)
    - [Étape 3 — Configurer le plugin](#étape-3--configurer-le-plugin)
    - [Étape 4 — Vérifier](#étape-4--vérifier)
  - [8. Diagramme d'états](#8-diagramme-détats)
  - [9. Résolution des problèmes](#9-résolution-des-problèmes)
    - [Le poêle ne s'allume jamais](#le-poêle-ne-sallume-jamais)
    - [Le poêle s'allume mais le niveau de puissance reste par défaut](#le-poêle-sallume-mais-le-niveau-de-puissance-reste-par-défaut)
    - [Le poêle ne s'éteint pas malgré une pièce chaude](#le-poêle-ne-séteint-pas-malgré-une-pièce-chaude)
    - [HA a redémarré et l'état du poêle est incohérent](#ha-a-redémarré-et-létat-du-poêle-est-incohérent)

---

## 1. Prérequis

| Prérequis                                                                  | Version minimale |
| -------------------------------------------------------------------------- | ---------------- |
| Home Assistant                                                             | 2026.4           |
| [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) | 10.0             |
| HACS                                                                       | 1.34             |

Votre poêle à pellets **doit être déjà exposé comme entité `climate`** dans Home Assistant (via Duepi EVO, ESPHome, MCZ, EdilKamin, ou toute autre intégration). Ce plugin ne communique **pas** directement avec les poêles.

---

## 2. Installation

### Via HACS (recommandé)

[![Ajouter dans HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jmcollin78&repository=vtherm_pellet_stove&category=Integration)

1. Ouvrir HACS → **Intégrations** → menu **⋮** → **Dépôts personnalisés**.
2. Ajouter `https://github.com/jmcollin78/vtherm_pellet_stove` en tant qu'**Intégration**.
3. Rechercher **Versatile Thermostat Poêle à Pellets** et cliquer sur **Télécharger**.
4. Redémarrer Home Assistant.

### Installation manuelle

1. Télécharger la dernière version depuis les [Releases GitHub](https://github.com/jmcollin78/vtherm_pellet_stove/releases).
2. Copier le dossier `custom_components/vtherm_pellet_stove` dans le répertoire `config/custom_components/` de HA.
3. Redémarrer Home Assistant.

---

## Démarche — Mise en place en 5 étapes

Cette section guide pas à pas la configuration complète depuis zéro. Chaque étape renvoie à la section de référence détaillée correspondante.

### Étape 1 — Installer Versatile Thermostat

Si Versatile Thermostat n'est pas encore installé :

1. Ouvrir HACS → **Intégrations**.
2. Rechercher **Versatile Thermostat** et cliquer sur **Télécharger**.
3. Redémarrer Home Assistant.
4. Aller dans **Paramètres → Appareils et services → Ajouter une intégration**, rechercher **Versatile Thermostat** et finaliser la configuration initiale.

Se référer à la [documentation de Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) pour les détails.

### Étape 2 — Installer vtherm_pellet_stove et créer la configuration par défaut

1. Installer ce plugin en suivant le [§2 Installation](#2-installation).
2. Après le redémarrage, aller dans **Paramètres → Appareils et services**.
3. Cliquer sur **Ajouter une intégration** et sélectionner **Versatile Thermostat Poêle à Pellets**.
4. Une entrée de **defaults globaux** est créée automatiquement avec des valeurs par défaut raisonnables. Elle s'applique à tous les VTherm poêle à pellets n'ayant pas d'entrée par thermostat.
5. *(Optionnel)* Cliquer sur **Options** de l'entrée globale pour ajuster les paramètres par défaut (hystérésis, garde-fous, niveaux de puissance…) maintenant ou plus tard — voir [§6 Référence des paramètres](#6-référence-des-paramètres).

### Étape 3 — Créer le VTherm de type `over_switch`

1. Aller dans **Paramètres → Appareils et services → Versatile Thermostat → Ajouter**.
2. Choisir le type de thermostat **`over_switch`**.
3. Dans le champ **Entité sous-jacente**, sélectionner l'entité `climate` qui contrôle le poêle à pellets (ex. `climate.duepi_evo`).
4. Dans le champ **Fonction proportionnelle** (algorithme), sélectionner **`pellet_regulation`**.
5. Définir la durée du cycle (`cycle_min`) à `60` minutes.
6. Définir le **Délai d'activation minimal** à `1800` s (30 min) et le **Délai de désactivation minimal** à `1500` s (25 min) — ces valeurs doivent correspondre à `min_on_duration_min` et `min_off_duration_min + cooldown_duration_min`.
7. Compléter les autres paramètres VTherm (nom, capteur de température, etc.) et sauvegarder.

### Étape 4 — Ajouter les commandes personnalisées d'allumage et d'extinction

Le mode `over_switch` de VTherm communique avec le poêle via deux appels de service configurables. Ces commandes doivent être renseignées dans la **page de configuration du sous-jacent** du VTherm créé à l'étape précédente :

1. Ouvrir l'entité VTherm → **Options** → page **Entités sous-jacentes**.
2. Dans le champ **Commande d'allumage** (`vswitch_on`), saisir :
   ```
   set_hvac_mode/hvac_mode:heat
   ```
3. Dans le champ **Commande d'extinction** (`vswitch_off`), saisir :
   ```
   set_hvac_mode/hvac_mode:off
   ```
4. Sauvegarder. VTherm appellera désormais `climate.set_hvac_mode(hvac_mode=heat)` pour allumer le poêle et `climate.set_hvac_mode(hvac_mode=off)` pour l'éteindre.

> **Pourquoi ces commandes ?** Les poêles à pellets sont exposés comme entités `climate`, pas `switch`. La syntaxe `vswitch_on/off` permet à VTherm d'appeler n'importe quel service HA au format `nom_service/clé:valeur`.

### Étape 5 — Relier vtherm_pellet_stove au VTherm

Choisir l'une des deux options selon que des paramètres spécifiques à ce poêle sont nécessaires :

**Option A — Utiliser les defaults globaux (aucune action requise)**

Si les paramètres par défaut globaux conviennent à ce poêle, aucune étape supplémentaire n'est nécessaire. Le VTherm utilise automatiquement les defaults globaux car il est configuré avec l'algorithme `pellet_regulation`.

**Option B — Créer une entrée par thermostat (recommandé pour un réglage fin)**

1. Aller dans **Paramètres → Appareils et services → Versatile Thermostat Poêle à Pellets → Ajouter une entrée**.
2. Sélectionner l'entité `climate` VTherm créée à l'étape 3.
3. Ajuster les paramètres spécifiquement pour ce poêle (ex. `min_on_duration_min` différent, `power_levels` adaptés).
4. Sauvegarder. Cette entrée écrase les defaults globaux uniquement pour ce VTherm — voir [§5 Configuration du plugin](#5-configuration-du-plugin).

> Les valeurs par thermostat ont toujours la priorité sur les defaults globaux. Il est possible d'avoir une entrée par poêle.

---

## 3. Fonctionnement

`vtherm_pellet_stove` enregistre l'algorithme **`pellet_regulation`** dans l'API VTherm. Lorsqu'un VTherm en mode `over_switch` est configuré avec cet algorithme, le plugin :

1. **Calcule `on_percent`** — une valeur binaire 0 ou 1 dérivée d'une hystérésis paramétrable sur la température ambiante.
2. **Applique les garde-fous propres au pellet** — durées minimales de marche/arrêt et délai de refroidissement pour éviter les cycles d'allumage excessifs.
3. **Envoie les commandes ON/OFF** — le cycle scheduler de VTherm traduit `on_percent` en appels `set_hvac_mode` sur l'entité `climate` du poêle (via `vswitch_on` / `vswitch_off`).
4. **Ajuste optionnellement le niveau de puissance** — le plugin appelle `set_fan_mode` ou `set_preset_mode` en fonction de l'écart de température (ΔT) et de la pente.

```
Pièce trop froide                     Pièce à consigne
──────────────────────────────────────────────────────
current ≤ target − hysteresis_on      |
  → on_percent = 1                    |   maintien / arrêt
  → VTherm envoie vswitch_on ──────► climate.poele_pellets
                                           set_hvac_mode(heat)
```

---

## 4. Configuration de Versatile Thermostat

Créer un VTherm en mode **`over_switch`** avec les paramètres suivants :

| Option VTherm                      | Valeur                                                                                            |
| ---------------------------------- | ------------------------------------------------------------------------------------------------- |
| **Type de thermostat**             | `over_switch`                                                                                     |
| **Entité sous-jacente**            | `climate.<votre_poele>` (ex. `climate.duepi_evo`)                                                 |
| **Fonction proportionnelle**       | `pellet_regulation`                                                                               |
| **Commande `vswitch_on`**          | `set_hvac_mode/hvac_mode:heat`                                                                    |
| **Commande `vswitch_off`**         | `set_hvac_mode/hvac_mode:off`                                                                     |
| **Durée du cycle** (`cycle_min`)   | 60 (minutes)                                                                                      |
| **Délai d'activation minimal**     | 1800 (secondes, soit 30 min) — doit correspondre à `min_on_duration_min`                          |
| **Délai de désactivation minimal** | 1500 (secondes, soit 25 min) — doit correspondre à `min_off_duration_min + cooldown_duration_min` |

> **Pourquoi `over_switch` ?** Le mode `over_switch` de VTherm expose le point d'extension `InterfacePropAlgorithmFactory` qui permet aux plugins externes d'enregistrer des algorithmes de régulation personnalisés. Les options `vswitch_on/off` permettent de cibler n'importe quel domaine HA, y compris `climate`.

---

## 5. Configuration du plugin

### 5.1 Entrée de defaults globaux

Lors de la **première installation**, l'intégration crée automatiquement une entrée de **defaults globaux** (avec les valeurs par défaut du §6). Tous les thermostats VTherm qui utilisent `pellet_regulation` et qui n'ont pas d'entrée par thermostat hériteront de ces valeurs.

Aller dans **Paramètres → Appareils et services → Versatile Thermostat Poêle à Pellets** pour modifier ces defaults via le bouton **Options**.

### 5.2 Entrée par thermostat

Cliquer sur **Ajouter une entrée** pour créer une surcharge par thermostat :

1. Sélectionner l'entité `climate` VTherm à cibler.
2. Ajuster les paramètres souhaités — seul ce thermostat utilisera les valeurs surchargées.

Les valeurs par thermostat ont toujours la priorité sur les defaults globaux.

### 5.3 Options flow

Les deux types d'entrées (globale et par thermostat) exposent un bouton **Options** permettant de modifier les paramètres sans réinstaller. Les modifications sont appliquées immédiatement : les VTherm ciblés sont rechargés automatiquement.

---

## 6. Référence des paramètres

### Hystérésis

| Paramètre        | Défaut   | Description                                                             |
| ---------------- | -------- | ----------------------------------------------------------------------- |
| `hysteresis_on`  | `0,5 °C` | Allumage si `current_temp ≤ target − hysteresis_on`.                    |
| `hysteresis_off` | `0,3 °C` | Extinction si `current_temp ≥ target + hysteresis_off`.                 |
| `min_on_percent` | `0,0`    | Valeur `on_percent` envoyée au scheduler quand l'algorithme décide OFF. |
| `max_on_percent` | `1,0`    | Valeur `on_percent` envoyée au scheduler quand l'algorithme décide ON.  |

### Garde-fous pellet

| Paramètre               | Défaut    | Description                                                                                                               |
| ----------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------- |
| `min_on_duration_min`   | `30 min`  | Durée minimale de chauffe avant qu'une extinction soit autorisée. Protège la bougie.                                      |
| `min_off_duration_min`  | `20 min`  | Durée minimale d'arrêt avant qu'un rallumage soit autorisé.                                                               |
| `cooldown_duration_min` | `5 min`   | Délai de refroidissement supplémentaire ajouté après chaque extinction.                                                   |
| `safety_room_temp`      | `26,0 °C` | Température ambiante au-delà de laquelle le poêle est **immédiatement forcé à l'arrêt** (outrepasse tous les garde-fous). |

### Pilotage du niveau de puissance (optionnel)

| Paramètre                   | Défaut                  | Description                                                         |
| --------------------------- | ----------------------- | ------------------------------------------------------------------- |
| `power_control_enabled`     | `true`                  | Active/désactive le pilotage du niveau de puissance.                |
| `power_control_attribute`   | `fan_mode`              | Attribut HA utilisé : `fan_mode` ou `preset_mode`.                  |
| `power_levels`              | `["1","2","3","4","5"]` | Liste ordonnée des niveaux (du plus faible au plus fort).           |
| `power_default_level_index` | `2`                     | Index par défaut quand la pente de température est inconnue.        |
| `power_boost_enabled`       | `true`                  | Active un boost temporaire au maximum après une hausse de consigne. |
| `power_boost_duration_min`  | `15 min`                | Durée de la phase de boost.                                         |

---

## 7. Exemple complet — Poêle Duepi EVO

Cet exemple suppose que le poêle est exposé comme `climate.duepi_evo` avec `fan_modes` = `["1", "2", "3", "4", "5"]`.

### Étape 1 — Installer le plugin

Suivre le §2.

### Étape 2 — Créer le VTherm

Dans **Paramètres → Appareils et services → Versatile Thermostat → Ajouter** :

```yaml
# YAML équivalent pour référence (l'interface graphique est recommandée)
type: over_switch
heater: climate.duepi_evo
vswitch_on: "set_hvac_mode/hvac_mode:heat"
vswitch_off: "set_hvac_mode/hvac_mode:off"
proportional_function: pellet_regulation
cycle_min: 60
minimal_activation_delay: 1800
minimal_deactivation_delay: 1500
```

### Étape 3 — Configurer le plugin

Dans **Paramètres → Appareils et services → Versatile Thermostat Poêle à Pellets → Options** :

| Paramètre                  | Valeur recommandée      | Justification                                           |
| -------------------------- | ----------------------- | ------------------------------------------------------- |
| `hysteresis_on`            | `0,5`                   | Marge confortable pour éviter les allumages inutiles.   |
| `hysteresis_off`           | `0,3`                   | Plus étroit : une fois chaud, couper rapidement.        |
| `min_on_duration_min`      | `30`                    | Minimum recommandé par la documentation Duepi EVO.      |
| `min_off_duration_min`     | `20`                    | Permettre au poêle de refroidir avant le rallumage.     |
| `cooldown_duration_min`    | `5`                     | Marge supplémentaire pour l'évacuation des fumées.      |
| `safety_room_temp`         | `26,0`                  | Adapté à un salon ; à augmenter pour un garage.         |
| `power_control_enabled`    | `true`                  | Activer le pilotage automatique du niveau de puissance. |
| `power_control_attribute`  | `fan_mode`              | Le Duepi EVO utilise `fan_mode` pour la puissance.      |
| `power_levels`             | `["1","2","3","4","5"]` | Correspondre aux `fan_modes` du poêle.                  |
| `power_boost_duration_min` | `15`                    | Boost de 15 minutes après une hausse de consigne.       |

### Étape 4 — Vérifier

1. Vérifier que `climate.duepi_evo` passe à `hvac_mode: heat` quand le VTherm demande à chauffer.
2. Consulter les attributs du VTherm dans **Outils de développement → États** — rechercher le bloc d'attribut `pellet_regulation` :

```json
{
  "pellet_regulation": {
    "is_heating": true,
    "on_percent": 1.0,
    "current_level": "3",
    "elapsed_on_min": 12,
    "last_reason": "below_on_threshold"
  }
}
```

---

## 8. Diagramme d'états

Le poêle transite entre les états logiques suivants :

```
               ┌──────────────────────────────────────────┐
               ▼                                          │
           ┌───────┐  on_percent=1 (min_off+cooldown      │
           │  Arrêt │  écoulé)                            │
           └───┬───┘                                      │
               │                                          │
               ▼                                          │
          ┌───────────┐  min_on_duration                  │
          │ Allumage  │  non encore atteinte              │
          └─────┬─────┘                                   │
                │  min_on_duration atteinte               │
                ▼                                         │
          ┌─────────┐  on_percent=0 (min_on               │
          │ Chauffe │──écoulée OU sécurité) ──────────► Refroidissement
          └─────────┘                                     │
                                                          │
                                              min_off + cooldown écoulés
```

> `Allumage` et `Chauffe` sont des vues logiques de `is_heating=True`. `Refroidissement` correspond à `is_heating=False` tant que `min_off + cooldown` n'est pas écoulé.

---

## 9. Résolution des problèmes

### Le poêle ne s'allume jamais

- Vérifier que `vswitch_on = "set_hvac_mode/hvac_mode:heat"` est bien configuré sur le VTherm.
- Vérifier que `climate.<poele>` accepte `hvac_mode: heat` (tester manuellement dans Outils de développement → Services).
- Vérifier que `current_temperature` est disponible sur le VTherm et est inférieure à `target − hysteresis_on`.
- Vérifier que `min_off_duration_min + cooldown_duration_min` est bien écoulé depuis le dernier arrêt.

### Le poêle s'allume mais le niveau de puissance reste par défaut

- Vérifier que `power_control_enabled` est `true`.
- Vérifier que `power_levels` correspond aux `fan_modes` (ou `preset_modes`) remontés par l'entité poêle.
- Consulter les erreurs dans les logs HA pour `vtherm_pellet_stove`.

### Le poêle ne s'éteint pas malgré une pièce chaude

- Vérifier que `current_temperature ≥ target + hysteresis_off`.
- Vérifier que `min_on_duration_min` est écoulé depuis le dernier allumage.
- Si la température dépasse `safety_room_temp`, le poêle doit s'éteindre immédiatement quels que soient les garde-fous.

### HA a redémarré et l'état du poêle est incohérent

- Le plugin persiste son état dans le stockage HA (`.storage/vtherm_pellet_stove.*`). Si le fichier est absent ou corrompu, l'état se réinitialise à `is_heating=False`. Les garde-fous s'appliquent à partir de ce moment.
