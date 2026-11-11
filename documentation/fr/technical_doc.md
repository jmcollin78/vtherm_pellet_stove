# vtherm_pellet_stove — Documentation technique

> Référence d'architecture interne pour les développeurs et mainteneurs du plugin.
> Pour le document de conception complet, voir [tech-docs/plugin-architecture.md](../../tech-docs/plugin-architecture.md).

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Structure du dépôt](#2-structure-du-dépôt)
3. [Responsabilités des composants](#3-responsabilités-des-composants)
4. [Modèle de données](#4-modèle-de-données)
5. [Algorithme de régulation](#5-algorithme-de-régulation)
6. [Cycle de vie HA](#6-cycle-de-vie-ha)
7. [Interface de configuration](#7-interface-de-configuration)
8. [État persistant](#8-état-persistant)
9. [Pilotage du niveau de puissance](#9-pilotage-du-niveau-de-puissance)
10. [Stratégie de tests](#10-stratégie-de-tests)
11. [Observabilité — Logs et entité de débogage](#11-observabilité--logs-et-entité-de-débogage)
12. [Ajouter une nouvelle fonctionnalité](#12-ajouter-une-nouvelle-fonctionnalité)

---

## 1. Vue d'ensemble

`vtherm_pellet_stove` est une **intégration HA distribuable via HACS** qui s'enregistre comme algorithme proportionnel externe (`pellet_regulation`) dans l'interface publique [vtherm_api](https://github.com/KipK/vtherm_api).

Il est conçu pour les thermostats VTherm en mode `over_switch`; la configuration du plugin cible toujours le `climate` VTherm, dont le sous-jacent peut être l'entité `climate` du poêle ou un contact sec `switch`. Le cycle scheduler de VTherm gère les demandes ON/OFF; ce plugin calcule `on_percent` et n'ajuste la puissance que pour un sous-jacent `climate`.

```
┌────────────────────────────────────┐
│         Home Assistant             │
│                                    │
│  ┌──────────────┐  register        │
│  │  vtherm_     │──────────────►   │
│  │  pellet_stove│                  │
│  │  (ce dépôt)  │  create handler  │
│  │              │◄─────────────    │
│  └──────┬───────┘                  │
│         │ calculate / start_cycle  │
│         ▼                          │
│  ┌──────────────┐  vswitch_on/off  │
│  │  VTherm      │────────────────► climate.poele
│  │ over_switch  │                  │
│  └──────────────┘                  │
└────────────────────────────────────┘
```

---

## 2. Structure du dépôt

```
custom_components/vtherm_pellet_stove/
├── __init__.py          # setup / teardown, factory, propagation live et plateforme sensor
├── manifest.json        # manifeste HA (dépendance : versatile_thermostat)
├── config_flow.py       # ConfigFlow (global + par thermostat) + OptionsFlow
├── const.py             # DOMAIN, constantes CONF_*, DEFAULT_OPTIONS
├── factory.py           # PelletRegulationFactory (InterfacePropAlgorithmFactory)
├── handler.py           # PelletRegulationHandler (InterfacePropAlgorithmHandler)
├── sensor.py            # PelletDebugSensor — entité de débogage (DIAGNOSTIC)
└── pellet/              # Logique métier pure Python (sans dépendance HA)
    ├── __init__.py
    ├── controller.py    # PelletRegulationController — orchestration + logs INFO/WARNING
    ├── state.py         # PelletState — dataclass persisté
    ├── hysteresis.py    # HysteresisDecider — décision binaire ON/OFF
    ├── cycle_guard.py   # CycleGuard — durées min marche/arrêt + cooldown
    ├── power_mapper.py  # PowerMapper — ΔT/pente → index de niveau
    └── boost.py         # BoostManager — boost temporaire au niveau max
```

---

## 3. Responsabilités des composants

### `__init__.py`

- Appelle `VThermAPI.register_prop_algorithm(PelletRegulationFactory())` au `async_setup` / `async_setup_entry`.
- Appelle `VThermAPI.unregister_prop_algorithm("pellet_regulation")` seulement après suppression réelle de la dernière entrée, pas lors d'un unload/reload.
- Applique Options et Reconfigurer aux handlers vivants du plugin, sans recharger ni modifier les entrées VTherm.
- Pour l'entrée globale uniquement, forward la plateforme `sensor` (`async_forward_entry_setups`) permettant la création dynamique des capteurs de débogage.
- Après unload/reload de la plateforme globale, détache les anciennes références et réenregistre les capteurs des handlers vivants.

### `factory.py` — `PelletRegulationFactory`

Factory simple : `name = "pellet_regulation"`, `create(thermostat) → PelletRegulationHandler`.

### `handler.py` — `PelletRegulationHandler`

Adaptateur au cycle de vie HA. Implémente `InterfacePropAlgorithmHandler` :

| Méthode               | Responsabilité                                                                                                                                                                                                                                                                  |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `init_algorithm`      | Résoudre les options effectives (`_resolve_options`), construire `PelletRegulationController`, créer le `Store`.                                                                                                                                                                |
| `async_added_to_hass` | Charger l'état persistant depuis le `Store`, appeler `controller.restore_state`.                                                                                                                                                                                                |
| `async_startup`       | Pour un switch, adopter son premier état connu sans dater de transition; attendre s'il est inconnu. Pour le parcours climate, déclencher `on_state_changed(True)` comme avant.                                                                                                      |
| `remove`              | Planifier `store.async_save` via `hass.async_create_task`.                                                                                                                                                                                                                      |
| `control_heating`     | Appeler `controller.calculate`, détecter les transitions réelles d'état (ON↔OFF), mettre à jour `thermostat.prop_algorithm`, appeler `scheduler.start_cycle` avec `force=True` lors de toute transition réelle, appliquer le niveau uniquement pour un sous-jacent climate, publier l'état HA, persister. |
| `on_state_changed`    | Transférer à `control_heating` si `changed=True`.                                                                                                                                                                                                                               |
| `on_scheduler_ready`  | Stocker la référence du scheduler, enregistrer les callbacks de cycle.                                                                                                                                                                                                          |
| `_apply_power_level`  | Appeler `climate.set_fan_mode / set_preset_mode` sur les entités climate sous-jacentes; aucun appel pour un sous-jacent switch. Anti-spam : ignorer si le niveau n'a pas changé.                                                                                                   |

**Résolution des options** (`_resolve_options`) :

```
DEFAULT_OPTIONS ← entrée globale (data → options) ← entrée par thermostat (data → options)
```

Le dict `options` (depuis l'OptionsFlow) a toujours la priorité sur `data` (depuis le ConfigFlow).

Pour un sous-jacent `switch`, le handler dérive localement `power_control_enabled=false` et `power_boost_enabled=false` pour le contrôleur. Les options résolues et persistées ne sont pas modifiées; les fonctions reprennent si le VTherm est reconfiguré avec un sous-jacent `climate`.

### `pellet/` — logique métier

Toutes les classes de ce sous-paquet sont en **Python pur** sans dépendance HA, permettant des tests unitaires légers sans instance HA.

---

## 4. Modèle de données

### Clés de configuration (`const.py`)

| Clé                         | Type         | Description                                                |
| --------------------------- | ------------ | ---------------------------------------------------------- |
| `hysteresis_on`             | float (°C)   | Seuil d'allumage en dessous de la consigne.                |
| `hysteresis_off`            | float (°C)   | Seuil d'extinction au-dessus de la consigne.               |
| `min_on_percent`            | float [0..1] | `on_percent` quand l'algorithme dit OFF.                   |
| `max_on_percent`            | float [0..1] | `on_percent` quand l'algorithme dit ON.                    |
| `min_on_duration_min`       | int (min)    | Durée minimale de chauffe avant extinction autorisée.      |
| `min_off_duration_min`      | int (min)    | Durée minimale d'arrêt avant allumage autorisé.            |
| `cooldown_duration_min`     | int (min)    | Cooldown supplémentaire ajouté à `min_off_duration_min`.   |
| `safety_room_temp`          | float (°C)   | Extinction forcée au-delà de cette température ambiante.   |
| `power_control_enabled`     | bool         | Activer le pilotage du niveau fan/preset.                  |
| `power_control_attribute`   | enum         | `fan_mode` ou `preset_mode`.                               |
| `power_levels`              | list[str]    | Valeurs de niveau ordonnées (du plus faible au plus fort). |
| `power_default_level_index` | int          | Index par défaut quand la pente est inconnue.              |
| `power_boost_enabled`       | bool         | Activer le boost après hausse de consigne.                 |
| `power_boost_duration_min`  | int (min)    | Durée du boost.                                            |

### `PelletState` (persisté)

```json
{
  "is_heating": true,
  "current_level_index": 2,
  "last_on_at": "2026-01-15T19:32:11+01:00",
  "last_off_at": "2026-01-15T17:02:00+01:00",
  "last_reason": "below_on_threshold",
  "boost_until": null
}
```

Stocké sous la clé `vtherm_pellet_stove.<slug_du_unique_id_vtherm>` (répertoire `.storage/` de HA).

---

## 5. Algorithme de régulation

### Diagramme de décision

```
Entrées : target, current, slope, hvac_mode, now, state
           │
           ▼
hvac_mode == "off" ──Oui──► on_percent=0  raison=hvac_off
           │
          Non
           ▼
current ≥ safety_room_temp ──Oui──► on_percent=0  raison=safety  (outrepasse garde-fous)
           │
          Non
           ▼
HysteresisDecider.decide(is_heating, current, target)
           │
      ┌────┴────┐
     ON        OFF
      │          │
      │ is_heating=False   is_heating=True
      │          │
  CycleGuard   CycleGuard
  .can_turn_on .can_turn_off
      │              │
   Non─┤          Non─┤
      │              │
  locked_off     locked_on (maintien ON)
      │              │
   Oui─┘          Oui─┘
      │              │
  on_percent=1   on_percent=0
  raison=...     raison=...
```

### `HysteresisDecider`

- `decide(is_heating, current, target)` retourne `HysteresisDecision(decision, reason, is_hold)`.
- `is_hold=True` signifie que le poêle maintient son état courant (température dans la bande morte).

### `CycleGuard`

```python
can_turn_off(now, state) → bool:
    elapsed = (now - state.last_on_at).total_seconds() / 60
    return elapsed >= min_on_duration_min

can_turn_on(now, state) → bool:
    elapsed = (now - state.last_off_at).total_seconds() / 60
    return elapsed >= (min_off_duration_min + cooldown_duration_min)
```

La sécurité haute température dans `PelletRegulationController._compute` outrepasse complètement `can_turn_off`.

---

## 6. Cycle de vie HA

### Séquence de démarrage

```
Démarrage HA
  └─ async_setup_entry (plugin)
       ├─ _register_factory → VThermAPI.register_prop_algorithm
       ├─ entry.async_on_unload → listener _async_update_options
      ├─ forward sensor si entrée globale
      └─ applique les options aux handlers déjà vivants, s'il y en a

Démarrage VTherm (après le plugin, dépendance déclarée dans manifest.json)
  └─ factory.create(thermostat_runtime)
       └─ PelletRegulationHandler.__init__
            ├─ handler.init_algorithm()        ← lit les options, crée controller + Store
            ├─ handler.async_added_to_hass()   ← restore_state depuis le Store
            ├─ handler.async_startup()         ← on_state_changed(True) → control_heating
            └─ handler.on_scheduler_ready(scheduler)
```

### Cycle de régulation (par `cycle_min`)

```
VTherm.async_control_heating
  └─ handler.control_heating(timestamp, force)
       ├─ controller.calculate(target, current, slope, hvac_mode, now)
       ├─ thermostat.prop_algorithm = controller
       ├─ scheduler.start_cycle(hvac_mode, on_percent, force or transition)
       │    │  transition=True lors d'une transition réelle ON→OFF ou OFF→ON
       │    │  (force l'arrêt/démarrage immédiat sans attendre la fin du cycle)
       │    └─ UnderlyingSwitch.turn_on/off
       │         └─ hass.services.async_call("climate", "set_hvac_mode", ...)
       ├─ _apply_power_level()   (si activé et is_heating=True)
       │    └─ hass.services.async_call("climate", "set_fan_mode", ...)
       ├─ thermostat.update_custom_attributes()
       ├─ thermostat.async_write_ha_state()
       └─ store.async_save(controller.save_state())
```

### Contrat de commande d'un contact sec

La configuration et l'adoption logicielle initiale du contact sont implementees. La regulation automatique complete reste conditionnee a la verification du contrat amont suivi par VTherm [#2223](https://github.com/jmcollin78/versatile_thermostat/issues/2223) : VTherm doit initialiser une seule fois son etat attendu depuis le premier etat valide avant `check_initial_state()`. Le plugin ne lit ni ne modifie les champs prives de VTherm.

Les transitions ON/OFF pilotees restent a deleguer a `scheduler.start_cycle(...)` : le `CycleScheduler` de VTherm appelle `UnderlyingSwitch.turn_on()` ou `turn_off()`. Le plugin ne doit pas appeler directement les services du switch ni doubler un OFF confie a VTherm. Avec VTherm 10.6.4, une adoption passive ON en mode `heat` peut encore etre renversee par `repair_incorrect_state`; les tests unitaires locaux ne prouvent pas le contrat amont. ON/OFF exprime une demande et n'acquitte pas l'allumage ni l'extinction physique du poele.

---

## 7. Interface de configuration

### Types de flux

| Flux               | `unique_id`           | Objet                                                |
| ------------------ | --------------------- | ---------------------------------------------------- |
| Defaults globaux   | `DOMAIN`              | Créé automatiquement à la première installation.     |
| Par thermostat     | `DOMAIN-<vtherm_uid>` | Surcharge optionnelle pour un thermostat spécifique. |
| Options (les deux) | n/a                   | Met à jour les handlers vivants sans reload VTherm.  |

### Portée et application

- Une entrée locale remplace toute la configuration globale ; ses clés absentes utilisent les défauts. Sans entrée locale, l'entrée globale s'applique.
- Options met à jour directement le handler cible (ou les handlers sans entrée locale pour une modification globale). Reconfigurer recharge l'entrée Pellet Stove, puis son setup applique les valeurs au même handler vivant.
- L'objet d'état, ses horodatages, le proxy, le verrou et le scheduler restent sur le handler existant. Les échéances diagnostiques sont recalculées depuis les horodatages d'origine et les nouvelles durées.
- Pour un underlying climate, une transition automatique vers ON exige un statut Duepi reconnu comme non-allumé (`Off`, `Eco idle` ou `Cooling down`); un état absent, indisponible, inconnu, transitoire ou contradictoire bloque ON, et `Flame On` bloque un second ON. Pour un switch, ON exige que l'état HA du contact soit explicitement `off`; un contact absent, indisponible, inconnu ou déjà `on` bloque l'allumage.
- Un seuil de sécurité dépassé peut demander OFF même sans consigne. Une commande VTherm déjà en vol reste toutefois sérialisée par son verrou ; aucune garantie d'interruption ou d'ordre matériel prioritaire n'est disponible.
- Le hook HA `async_remove_entry` désenregistre la factory après suppression réelle. `async_unload_entry` ne le fait pas, car HA l'utilise aussi pendant un reload.

---

## 8. État persistant

Le format de clé du `Store` est `vtherm_pellet_stove.<slugify(vtherm_unique_id)>`, version 1.

- Écrit après chaque appel à `control_heating`.
- Lu une fois dans `async_added_to_hass` et passé à `controller.restore_state`.
- Contient tous les champs de `PelletState`, les datetimes au format ISO-8601.
- Pour un sous-jacent switch seulement, les dates de transition sont lues de façon tolérante : les valeurs illisibles ou futures deviennent absentes, les dates naïves sont normalisées en UTC, et une date courante antérieure à l'autre transition est écartée. La restauration climate conserve son parseur historique.
- Après la restauration du mode VTherm, `async_startup` adopte une seule fois le premier état switch valide (`on` ou `off`) sans créer de date ni envoyer de commande de restauration. Si le contact est absent, `unknown` ou `unavailable`, l'adoption est différée jusqu'au premier état connu.
- Une date pertinente valide est conservée : `last_on_at` pour ON, `last_off_at` pour OFF. L'interruption de Home Assistant compte dans le délai. `next_action_allowed_at` reste fondé sur la date d'origine, même si l'échéance est passée; sans date pertinente valide, il vaut `null` et aucun délai initial artificiel n'est imposé.
- L'adoption décrit uniquement l'état estimé. Elle ne confirme pas la flamme, l'extinction ni une action externe pendant l'arrêt de Home Assistant.

---

## 9. Pilotage du niveau de puissance

Implémenté dans `PowerMapper.choose_level_index(delta_t, slope)` :

| `delta_T = target − current` | `slope` (°C/h) | Index de niveau                      |
| ---------------------------- | -------------- | ------------------------------------ |
| ≥ +2,0                       | n'importe      | dernier (max)                        |
| +1,0 .. +2,0                 | < +0,3         | avant-dernier                        |
| +1,0 .. +2,0                 | ≥ +0,3         | médian supérieur                     |
| +0,3 .. +1,0                 | < +0,2         | médian                               |
| +0,3 .. +1,0                 | ≥ +0,2         | médian inférieur                     |
| −0,3 .. +0,3                 | n'importe      | premier (min)                        |
| < −0,3                       | n'importe      | `None` (poêle éteint de toute façon) |

Anti-spam : `_apply_power_level` compare `current_level_index` avec `_last_applied_level_index` et ignore l'appel de service si le niveau n'a pas changé.

### Boost

`BoostManager.maybe_trigger` se déclenche quand `new_target − previous_target ≥ 0,5 °C`. Il positionne `state.boost_until = now + timedelta(minutes=power_boost_duration_min)`. Tant que `boost_until > now`, `_compute_level_index` retourne le dernier index (niveau maximum).

Avec un sous-jacent `switch`, ni `PowerMapper` ni `BoostManager` ne sont activés. Un niveau et une échéance de boost restaurés restent dans l'état persisté, mais aucun niveau n'est applicable et le boost n'est pas actif dans le calcul runtime; les dates de transition ON/OFF et leurs échéances de garde restent intactes.

---

## 10. Stratégie de tests

| Couche              | Module                                                                                | Outils                                          |
| ------------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------- |
| Unitaire pur        | `pellet/hysteresis`, `pellet/cycle_guard`, `pellet/power_mapper`, `pellet/controller` | `pytest` (sans HA)                              |
| Intégration handler | `handler.py`                                                                          | `pytest` + `unittest.mock`, Store patché        |
| Config flow         | `config_flow.py`                                                                      | `pytest-homeassistant-custom-component` (prévu) |

### Lancer les tests

```bash
# Installer les dépendances de développement
pip install -r requirements_dev.txt

# Lancer tous les tests
pytest tests/ -v

# Avec couverture
pytest tests/ --cov=custom_components/vtherm_pellet_stove --cov-report=term-missing
```

### Pattern de mock du Store

Le vrai `homeassistant.helpers.storage.Store` nécessite une boucle d'événements HA et un `StorageManager`. Les tests le patchent au niveau de l'import :

```python
@pytest.fixture(autouse=True)
def _patch_ha_store():
    def _make_store(*_args, **_kwargs):
        store = MagicMock()
        store.async_load = AsyncMock(return_value=None)
        store.async_save = AsyncMock()
        return store

    with patch("custom_components.vtherm_pellet_stove.handler.Store", side_effect=_make_store):
        yield
```

---

## 11. Observabilité — Logs et entité de débogage

### 11.1 Logs INFO/WARNING dans `controller.py`

Le `PelletRegulationController` émet des logs HA selon la grille suivante :

| Niveau    | Condition                                         | Exemple                                                                                              |
| --------- | ------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `WARNING` | Sécurité haute temp → extinction forcée           | `Salon - SÉCURITÉ: température ambiante 27.2°C ≥ 26.0°C → extinction forcée après 45 min de chauffe` |
| `INFO`    | Allumage réel (OFF → ON)                          | `Salon - Allumage du poêle (reason=below_on_threshold) après 27 min d'arrêt [target=20.0 …]`         |
| `INFO`    | Extinction réelle (ON → OFF)                      | `Salon - Extinction du poêle (reason=above_off_threshold) après 32 min de chauffe [target=20.0 …]`   |
| `INFO`    | Extinction reportée par garde-fou `min_on`        | `Salon - Extinction reportée (garde-fou min_on): 15/30 min de chauffe`                               |
| `INFO`    | Allumage reporté par garde-fou `min_off+cooldown` | `Salon - Allumage reporté (garde-fou min_off+cooldown): 18/25 min d'arrêt`                           |
| `INFO`    | Transition ON→OFF → arrêt immédiat forcé          | `Salon - ON→OFF transition detected (reason=above_off_threshold): forcing immediate cycle stop`      |
| `INFO`    | Transition OFF→ON → démarrage immédiat forcé      | `Salon - OFF→ON transition detected (reason=below_on_threshold): forcing immediate cycle start`      |
| `DEBUG`   | Chaque appel à `calculate()`                      | `PelletController - calculate target=20.0 current=19.3 on_percent=1.0 …`                             |

Les logs `INFO` et `WARNING` ne sont émis que lors d'un changement d'état effectif ou d'un blocage (anti-spam).

Pour les voir dans HA, configurer le niveau du logger dans `configuration.yaml` :
```yaml
logger:
  default: warning
  logs:
    custom_components.vtherm_pellet_stove: info
```

### 11.2 Entité de débogage `sensor` (DIAGNOSTIC)

Chaque VTherm utilisant `pellet_regulation` crée automatiquement une entité capteur :

- **entity_id** : `sensor.<nom_vtherm>_pellet_regulation_debug` (auto-généré par HA)
- **Catégorie** : `DIAGNOSTIC` (visible dans l'onglet Diagnostics de l'appareil)
- **Valeur d'état** : phase courante — `off`, `igniting`, `burning`, `cooldown`

**Phases** :

| Phase      | Condition                                                              |
| ---------- | ---------------------------------------------------------------------- |
| `off`      | `is_heating = false` ET garde-fou min_off+cooldown écoulé              |
| `igniting` | `is_heating = true` ET durée < `min_on_duration_min` (chauffe récente) |
| `burning`  | `is_heating = true` ET durée ≥ `min_on_duration_min`                   |
| `cooldown` | `is_heating = false` ET garde-fou min_off+cooldown en cours            |

L'entité expose également les paramètres actifs (hystérésis, garde-fous, décisions et échéances logicielles) en attributs. Avec un contact sec, ces informations décrivent le modèle du plugin et l'état du contact dans HA; elles ne mesurent ni la puissance, ni la flamme, ni l'extinction réelle.

---

## 12. Ajouter une nouvelle fonctionnalité

### Ajouter un nouveau paramètre de configuration

1. Ajouter `CONF_MON_PARAM` et `DEFAULT_MON_PARAM` dans `const.py` et `DEFAULT_OPTIONS`.
2. Ajouter le champ voluptuous + selector dans `config_flow.py → build_options_schema`.
3. Ajouter la traduction dans `translations/en.json` et `translations/fr.json`.
4. Lire la valeur dans `handler.py → init_algorithm` et la passer au constructeur approprié.
5. Mettre à jour les tests unitaires.

### Ajouter un nouveau garde-fou ou une nouvelle étape de décision

1. Implémenter la logique dans un nouveau fichier sous `pellet/` (sans imports HA).
2. L'injecter dans `PelletRegulationController.__init__` et l'appeler depuis `_compute`.
3. Ajouter des tests unitaires couvrant les nouveaux chemins de décision.
4. Mettre à jour `handler.py` si la fonctionnalité nécessite des appels de service HA.

### Ajouter des callbacks de cycle

`on_scheduler_ready` enregistre déjà `_on_cycle_start` / `_on_cycle_end`. Implémenter les corps des callbacks dans `handler.py` et optionnellement déléguer à une nouvelle méthode de `PelletRegulationController`.
