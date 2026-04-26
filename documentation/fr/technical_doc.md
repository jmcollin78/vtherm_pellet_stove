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
11. [Ajouter une nouvelle fonctionnalité](#11-ajouter-une-nouvelle-fonctionnalité)

---

## 1. Vue d'ensemble

`vtherm_pellet_stove` est une **intégration HA distribuable via HACS** qui s'enregistre comme algorithme proportionnel externe (`pellet_regulation`) dans l'interface publique [vtherm_api](https://github.com/KipK/vtherm_api).

Il est conçu exclusivement pour les thermostats VTherm en mode `over_switch` ciblant une entité `climate` (le poêle à pellets). Le cycle scheduler intégré de VTherm gère la temporalité réelle ON/OFF ; ce plugin fournit uniquement le **calcul d'`on_percent`** et l'ajustement optionnel du niveau de puissance.

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
├── __init__.py          # setup / teardown, enregistrement factory, reload VTherms
├── manifest.json        # manifeste HA (dépendance : versatile_thermostat)
├── config_flow.py       # ConfigFlow (global + par thermostat) + OptionsFlow
├── const.py             # DOMAIN, constantes CONF_*, DEFAULT_OPTIONS
├── factory.py           # PelletRegulationFactory (InterfacePropAlgorithmFactory)
├── handler.py           # PelletRegulationHandler (InterfacePropAlgorithmHandler)
└── pellet/              # Logique métier pure Python (sans dépendance HA)
    ├── __init__.py
    ├── controller.py    # PelletRegulationController — orchestration
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
- Appelle `VThermAPI.unregister_prop_algorithm("pellet_regulation")` quand la dernière entrée du plugin est supprimée.
- Déclenche `_reload_pellet_vtherms()` après un changement d'options pour que les nouveaux paramètres s'appliquent immédiatement.
- Ignore le reload pendant le démarrage de HA pour ne pas perturber la séquence de restauration de VTherm.

### `factory.py` — `PelletRegulationFactory`

Factory simple : `name = "pellet_regulation"`, `create(thermostat) → PelletRegulationHandler`.

### `handler.py` — `PelletRegulationHandler`

Adaptateur au cycle de vie HA. Implémente `InterfacePropAlgorithmHandler` :

| Méthode               | Responsabilité                                                                                                                                                              |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `init_algorithm`      | Résoudre les options effectives (`_resolve_options`), construire `PelletRegulationController`, créer le `Store`.                                                            |
| `async_added_to_hass` | Charger l'état persistant depuis le `Store`, appeler `controller.restore_state`.                                                                                            |
| `async_startup`       | Déclencher `on_state_changed(True)` → première itération `control_heating`.                                                                                                 |
| `remove`              | Planifier `store.async_save` via `hass.async_create_task`.                                                                                                                  |
| `control_heating`     | Appeler `controller.calculate`, mettre à jour `thermostat.prop_algorithm`, appeler `scheduler.start_cycle`, appliquer le niveau de puissance, publier l'état HA, persister. |
| `on_state_changed`    | Transférer à `control_heating` si `changed=True`.                                                                                                                           |
| `on_scheduler_ready`  | Stocker la référence du scheduler, enregistrer les callbacks de cycle.                                                                                                      |
| `_apply_power_level`  | Appeler `climate.set_fan_mode / set_preset_mode` sur les entités climate sous-jacentes. Anti-spam : ignorer si le niveau n'a pas changé.                                    |

**Résolution des options** (`_resolve_options`) :

```
DEFAULT_OPTIONS ← entrée globale (data → options) ← entrée par thermostat (data → options)
```

Le dict `options` (depuis l'OptionsFlow) a toujours la priorité sur `data` (depuis le ConfigFlow).

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
       └─ (si CoreState.running) _reload_pellet_vtherms

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
       ├─ scheduler.start_cycle(hvac_mode, on_percent, force)
       │    └─ UnderlyingSwitch.turn_on/off
       │         └─ hass.services.async_call("climate", "set_hvac_mode", ...)
       ├─ _apply_power_level()   (si activé et is_heating=True)
       │    └─ hass.services.async_call("climate", "set_fan_mode", ...)
       ├─ thermostat.update_custom_attributes()
       ├─ thermostat.async_write_ha_state()
       └─ store.async_save(controller.save_state())
```

---

## 7. Interface de configuration

### Types de flux

| Flux               | `unique_id`           | Objet                                                            |
| ------------------ | --------------------- | ---------------------------------------------------------------- |
| Defaults globaux   | `DOMAIN`              | Créé automatiquement à la première installation.                 |
| Par thermostat     | `DOMAIN-<vtherm_uid>` | Surcharge optionnelle pour un thermostat spécifique.             |
| Options (les deux) | n/a                   | Modifie les paramètres en place ; déclenche le reload du VTherm. |

### Logique de reload (`_reload_pellet_vtherms`)

- Itère sur toutes les entrées de config `versatile_thermostat`.
- Filtre celles avec `CONF_PROP_FUNCTION == "pellet_regulation"`.
- Entrée par thermostat : recharge uniquement le VTherm dont le `unique_id` correspond.
- Entrée globale : recharge tous les VTherms correspondants **sauf** ceux ayant une entrée par thermostat.
- S'exécute uniquement si `hass.state == CoreState.running`.

---

## 8. État persistant

Le format de clé du `Store` est `vtherm_pellet_stove.<slugify(vtherm_unique_id)>`, version 1.

- Écrit après chaque appel à `control_heating`.
- Lu une fois dans `async_added_to_hass` et passé à `controller.restore_state`.
- Contient tous les champs de `PelletState`, les datetimes au format ISO-8601.

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

## 11. Ajouter une nouvelle fonctionnalité

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
