# pellet-configuration

## Purpose

Decrire l'installation logique et la resolution des reglages de la 1.0.1.
Le parcours documente utilise un VTherm `over_switch` dont le sous-jacent est
un `climate`, avec les commandes personnalisees `set_hvac_mode/hvac_mode:heat`
et `set_hvac_mode/hvac_mode:off`. La compatibilite effective du retour d'etat
est limitee : voir [les observations](../../observations.md).

## Parameters

| Parametre                   | Defaut     | Selecteur du formulaire           |
| --------------------------- | ---------- | --------------------------------- |
| `hysteresis_on`             | 0.5        | nombre 0 a 5, pas 0.01            |
| `hysteresis_off`            | 0.3        | nombre 0 a 5, pas 0.01            |
| `min_on_percent`            | 0.0        | nombre 0 a 1, pas 0.01            |
| `max_on_percent`            | 1.0        | nombre 0 a 1, pas 0.01            |
| `min_on_duration_min`       | 30         | entier 0 a 240 minutes            |
| `min_off_duration_min`      | 20         | entier 0 a 240 minutes            |
| `cooldown_duration_min`     | 5          | entier 0 a 60 minutes             |
| `safety_room_temp`          | 26.0       | nombre 15 a 40, pas 0.1           |
| `power_control_enabled`     | true       | booleen                           |
| `power_control_attribute`   | `fan_mode` | choix `fan_mode` ou `preset_mode` |
| `power_default_level_index` | 2          | entier 0 a 10                     |
| `power_boost_enabled`       | true       | booleen                           |
| `power_boost_duration_min`  | 15         | entier 0 a 120 minutes            |

La liste integree `power_levels` est `['1', '2', '3', '4', '5']`.
Son absence du formulaire est une observation, pas une exigence de restriction.

## Requirements

### Requirement: Enregistrement de l'algorithme

L'integration SHALL enregistrer la factory `pellet_regulation` dans l'API
VTherm lorsqu'elle est disponible, sans enregistrer deux fois une factory
de ce nom. La factory SHALL creer un handler lie au thermostat fourni.
Un dechargement d'entree SHALL conserver cette factory ; sa desinscription
SHALL intervenir a la suppression de la derniere entree du plugin.

#### Scenario: Creation d'un thermostat pellet

- **GIVEN** l'API VTherm disponible et la factory enregistree
- **WHEN** VTherm demande un handler `pellet_regulation`
- **THEN** la factory retourne un handler propre a ce thermostat

#### Scenario: Rechargement d'une entree

- **WHEN** une entree plugin est dechargee pour etre rechargee
- **THEN** la factory reste enregistree

#### Scenario: Suppression de la derniere entree

- **GIVEN** la factory enregistree et aucune autre entree plugin restante
- **WHEN** HA confirme la suppression de l'entree
- **THEN** la factory `pellet_regulation` est desinscrite de l'API VTherm

### Requirement: Cycle de vie du service partage

L'integration SHALL enregistrer le service `reset` une seule fois lors du
setup reussi d'une entree. Elle SHALL le retirer au dechargement de la derniere
entree chargee, independamment des handlers et capteurs encore memorises.
Un setup ulterieur SHALL pouvoir enregistrer a nouveau le service.

#### Scenario: Deux entrees chargees puis dechargees

- **GIVEN** deux entrees chargees, des handlers et des capteurs memorises
- **WHEN** une seule entree est dechargee
- **THEN** le service reste disponible sans desinscription de la factory
- **WHEN** la derniere entree chargee est dechargee
- **THEN** le service est retire, mais la factory reste enregistree

### Requirement: Echecs de chargement de la plateforme globale

Le setup global SHALL charger la plateforme sensor avant d'enregistrer `reset`.
Un echec de ce setup SHALL ne pas creer le service. Un refus de dechargement
de la plateforme SHALL conserver l'entree chargee et le service.

#### Scenario: Echec de la plateforme globale

- **GIVEN** aucun service `reset` enregistre
- **WHEN** le chargement de la plateforme sensor globale echoue
- **THEN** le setup echoue sans enregistrer le service

#### Scenario: Refus de dechargement de la plateforme globale

- **GIVEN** une entree globale chargee et le service disponible
- **WHEN** le dechargement de sa plateforme sensor retourne faux
- **THEN** le dechargement de l'entree retourne faux et le service reste disponible

### Requirement: Entree globale et identite locale

Le premier parcours d'ajout SHALL creer automatiquement l'entree globale
`Pellet Stove defaults`, d'identifiant `vtherm_pellet_stove`, avec les valeurs
integrees. Les ajouts suivants SHALL proposer une entree par thermostat.
La cible locale SHALL etre un `climate` du registre ayant un `unique_id`,
stocke dans `target_vtherm_unique_id`, avec prevention des doublons.

#### Scenario: Premiere installation

- **GIVEN** aucune entree plugin existante
- **WHEN** le parcours utilisateur est lance
- **THEN** une entree globale est creee avec `DEFAULT_OPTIONS`

#### Scenario: Cible absente du registre

- **WHEN** une cible locale n'a pas d'entree de registre ou de `unique_id`
- **THEN** le formulaire affiche `invalid_entity` sans creer l'entree

#### Scenario: Cible deja configuree

- **GIVEN** une entree locale existante pour le `unique_id` selectionne
- **WHEN** un nouveau parcours tente de creer la meme entree locale
- **THEN** le parcours est interrompu sans creer de doublon

#### Scenario: Identite et titre de l'entree locale

- **GIVEN** une cible valide d'identifiant unique U
- **WHEN** son entree locale est creee
- **THEN** l'identifiant d'entree vaut `vtherm_pellet_stove-U`
- **AND** le titre est le nom de son etat HA si cet etat existe, sinon son `entity_id`

### Requirement: Parcours global explicite et correspondance des flux

L'etape explicite `async_step_global` SHALL utiliser l'identifiant unique
`vtherm_pellet_stove`, refuser son doublon, presenter les valeurs integrees
et creer l'entree globale avec les valeurs soumises. Deux flux SHALL etre
consideres correspondants par `is_matching` si leurs identifiants uniques
sont egaux. Cette etape explicite ne change pas le routage du parcours utilisateur.

#### Scenario: Soumission de l'etape globale explicite

- **GIVEN** aucune entree globale et un appel direct de l'etape globale
- **WHEN** des reglages sont soumis
- **THEN** l'entree `Pellet Stove defaults` est creee avec ces reglages

### Requirement: Resolution sans heritage partiel du global

Pour un thermostat donne, l'integration SHALL partir de `DEFAULT_OPTIONS`,
puis appliquer soit son entree locale si elle existe, soit l'entree globale.
Elle SHALL lire `options` si ce dictionnaire est non vide, sinon `data`.
Une entree locale partielle SHALL completer ses valeurs manquantes uniquement
avec `DEFAULT_OPTIONS`, jamais avec celles de l'entree globale.

#### Scenario: Entree locale partielle

- **GIVEN** un global avec `min_on_duration_min = 12` et une entree locale ne reglant que `hysteresis_on = 1.2`
- **WHEN** les reglages de ce thermostat sont resolus
- **THEN** son hysteresis vaut 1.2 et sa duree minimale de marche vaut 30, pas 12

#### Scenario: Thermostat sans entree locale

- **GIVEN** un global avec `hysteresis_on = 0.8`
- **WHEN** les reglages d'un thermostat sans entree locale sont resolus
- **THEN** son hysteresis d'allumage vaut 0.8

### Requirement: Valeurs integrees et champs du formulaire

L'integration SHALL utiliser les valeurs et selecteurs de la section Parameters. Les bornes
sont celles des champs individuels ; elles ne constituent pas une validation
de coherence entre plusieurs parametres.

#### Scenario: Absence de configuration

- **WHEN** aucun reglage plugin ne s'applique a un thermostat
- **THEN** les valeurs de la colonne Defaut sont utilisees, ainsi que les cinq niveaux integres

### Requirement: Mise a jour des handlers actifs

Une modification via Options SHALL mettre a jour les handlers actifs concernes
sans recreer leur controleur ni leur scheduler, en conservant l'historique
et sans recharger VTherm. Les echeances SHALL utiliser les dates conservees et
les nouvelles durees. Avec un scheduler lie, un controle SHALL etre execute.

#### Scenario: Modification d'une duree en cours de chauffe

- **GIVEN** un allumage enregistre a T et un handler actif
- **WHEN** le minimum de marche passe de 30 a 42 minutes
- **THEN** le meme controleur et son historique sont conserves, et l'echeance devient T plus 42 minutes

### Requirement: Ciblage commun au setup et aux Options

Le setup d'une entree et les modifications via Options SHALL appliquer les
reglages aux handlers actifs selon le meme ciblage : une entree locale cible
son seul thermostat ; une entree globale exclut ceux ayant une entree locale.
Le caractere actif est defini dans [runtime-state](../runtime-state/spec.md).

#### Scenario: Modification globale avec exception locale

- **GIVEN** deux handlers actifs dont un possede une entree locale
- **WHEN** l'entree globale change
- **THEN** seul le handler sans entree locale recoit les nouveaux reglages globaux

#### Scenario: Setup local sans entree globale

- **GIVEN** une entree locale et son handler actif sans entree globale
- **WHEN** cette entree est chargee puis ses Options sont modifiees
- **THEN** son handler recoit les reglages dans les deux cas, sans rechargement de VTherm

### Requirement: Isolation des echecs de mise a jour

Lors d'une application a plusieurs handlers, l'integration SHALL journaliser
un retour faux ou une exception d'un handler et poursuivre l'application aux
autres handlers selectionnes. Cette isolation ne garantit pas une application
atomique des reglages a tous les thermostats.

#### Scenario: Un handler refuse les nouveaux reglages

- **GIVEN** deux handlers selectionnes pour une mise a jour globale
- **WHEN** le premier retourne faux ou leve une exception
- **THEN** un avertissement est journalise et le second est quand meme sollicite

### Requirement: Reconfiguration d'une entree

La reconfiguration SHALL conserver la cible locale eventuelle, fusionner les
valeurs saisies dans `data` et vider les anciennes `options` afin que les
donnees sauvegardees soient effectivement relues. Elle SHALL demander le
rechargement de l'entree plugin, pas celui de VTherm. Le rechargement de
l'entree globale suit le cycle de dechargement et de rattachement des capteurs
decrit dans [runtime-state](../runtime-state/spec.md).

#### Scenario: Anciennes options presentes

- **GIVEN** une entree locale dont les anciennes options contiennent un seuil different
- **WHEN** une nouvelle valeur est soumise par Reconfigurer
- **THEN** la cible est conservee et les anciennes options ne masquent plus la nouvelle valeur

### Requirement: Notification des reglages effectifs modifies

Apres application de reglages effectifs differents, le handler SHALL publier
`versatile_thermostat_pellet_settings_event` avec `entity_id`, `name`, `state`,
`state_attributes` et `configuration` contenant les cles de `DEFAULT_OPTIONS`.
Une application sans difference SHALL ne pas emettre de nouvel evenement.
L'evenement decrit l'application des reglages, pas le succes d'une commande physique.

#### Scenario: Nouvelle duree puis meme configuration

- **WHEN** une nouvelle duree est appliquee puis les memes reglages sont reappliques
- **THEN** un seul evenement de changement est emis

### Requirement: Echec avant application des options

Si `update_configuration` echoue avant l'application des options du handler,
le handler SHALL propager l'erreur sans publier l'evenement ni remplacer ses
options effectives.

#### Scenario: Echec de configuration du controleur

- **GIVEN** de nouveaux reglages et `update_configuration` qui leve une exception
- **WHEN** le handler tente la mise a jour
- **THEN** l'erreur se propage, ses options precedentes restent selectionnees et aucun evenement n'est emis

### Requirement: Echec du controle apres application des options

Si le controle echoue apres application de reglages differents, le handler
SHALL conserver les reglages, publier l'evenement de changement et propager
l'erreur, sans log INFO de succes.

#### Scenario: Controle en echec apres application

- **GIVEN** de nouveaux reglages appliques et un scheduler lie
- **WHEN** le controle consecutif leve une exception
- **THEN** les reglages restent appliques, l'evenement est emis et l'erreur se propage sans log INFO de succes
- **AND** reappliquer les memes reglages ne republie pas l'evenement

### Requirement: Echec de notification sans annulation des reglages

Une erreur de publication sur le bus SHALL etre journalisee sans annuler les
reglages ni faire echouer a elle seule la mise a jour. Reappliquer les memes
reglages SHALL ne pas retenter cette notification.

#### Scenario: Bus indisponible

- **WHEN** la publication de l'evenement leve une exception apres application des reglages
- **THEN** l'erreur est journalisee, les reglages restent appliques et la mise a jour retourne vrai si le controle a reussi
- **AND** une application identique ne retente pas la notification

### Requirement: Parcours de configuration avec contact sec

L'integration SHALL permettre de selectionner `pellet_regulation` pour un VTherm `over_switch` dont le sous-jacent binaire est un `switch` commandant un contact sec ou un `input_boolean` representant une demande logique. La cible de la configuration du plugin SHALL rester le `climate` VTherm, distinct du sous-jacent. Ce parcours SHALL ne pas exiger de creer un `climate` intermediaire ni de consulter l'historique Home Assistant du contact.

#### Scenario: Thermostat avec un vrai switch

- **GIVEN** un VTherm `over_switch` configure avec un `switch` de contact sec
- **WHEN** l'utilisateur lui associe les reglages pellet
- **THEN** la cible du plugin reste le thermostat VTherm et les commandes visent le switch par VTherm
- **AND** les commandes personnalisees `set_hvac_mode` propres au parcours climate ne sont pas requises

### Requirement: Detection automatique du type de sous-jacent

Apres selection du VTherm, l'integration SHALL determiner le domaine du sous-jacent depuis sa configuration, sans choix manuel. Elle SHALL classer `switch` et `input_boolean` comme binaires, independamment de leur etat courant, et refaire cette detection a l'ouverture des Options ou de la reconfiguration. Un `climate` generique ou un type non resolu SHALL ne pas etre presente comme un Duepi avec retour physique fiable.

#### Scenario: Selection du thermostat et non du poele

- **GIVEN** un VTherm climate dont la configuration designe un sous-jacent switch
- **WHEN** l'utilisateur selectionne ce VTherm
- **THEN** le parcours detecte un contact sec sans demander le type de poele
- **AND** le domaine climate du VTherm cible n'est pas confondu avec celui de son sous-jacent

#### Scenario: Sous-jacent input_boolean

- **GIVEN** un VTherm `over_switch` configure avec un `input_boolean`
- **WHEN** l'utilisateur selectionne ce VTherm
- **THEN** l'integration detecte le sous-jacent binaire et affiche le formulaire avec l'avertissement correspondant
- **AND** l'etat de l'`input_boolean` n'est pas presente comme une preuve physique de flamme ou d'extinction

#### Scenario: Sous-jacent binaire indisponible pendant la configuration

- **GIVEN** un sous-jacent `switch` ou `input_boolean` identifie dans la configuration du VTherm mais actuellement indisponible
- **WHEN** le formulaire de reglages est affiche
- **THEN** le type switch reste detecte et son avertissement reste visible

#### Scenario: Sous-jacent modifie depuis une precedente configuration

- **GIVEN** un VTherm dont le sous-jacent a ete remplace par un `switch` ou un `input_boolean`
- **WHEN** l'utilisateur ouvre ses Options ou sa reconfiguration pellet
- **THEN** le type courant est detecte sans reutiliser aveuglement un ancien type climate

#### Scenario: Retour physique non etabli

- **GIVEN** un climate generique ou une configuration dont le type ne peut pas etre resolu
- **WHEN** le parcours affiche les informations de configuration
- **THEN** il n'affirme pas qu'un retour d'etat physique Duepi est disponible

### Requirement: Avertissement de contact sec dans les formulaires

Pour un sous-jacent `switch` ou `input_boolean`, les formulaires initiaux, d'Options et de reconfiguration SHALL afficher avant enregistrement un avertissement FR/EN indiquant que ON/OFF est une demande sans retour physique. L'avertissement SHALL accompagner les reglages de duree sans case de confirmation obligatoire.

#### Scenario: Reglages initiaux d'un sous-jacent binaire

- **WHEN** le domaine `switch` ou `input_boolean` est detecte apres le choix du VTherm
- **THEN** l'utilisateur voit l'avertissement avant de valider les durees
- **AND** le message explique que le minimum de marche inclut l'allumage et la chauffe utile
- **AND** il explique que le minimum d'arret additionne au refroidissement couvre l'extinction et le repos

#### Scenario: Modification ulterieure des delais

- **GIVEN** une entree pellet ciblant un VTherm avec contact sec
- **WHEN** l'utilisateur ouvre les Options ou la reconfiguration
- **THEN** l'avertissement est de nouveau visible avec les champs de duree
- **AND** aucune case d'acceptation obligatoire n'est ajoutee

#### Scenario: Duepi avec retour d'etat reconnu

- **GIVEN** un sous-jacent climate Duepi avec retour d'etat reconnu
- **WHEN** ses reglages pellet sont affiches
- **THEN** l'avertissement propre au contact sec n'est pas affiche
- **AND** les reglages anti-court-cycle restent disponibles

#### Scenario: Traductions des formulaires

- **WHEN** les formulaires du parcours sous-jacent binaire sont utilises en francais ou en anglais
- **THEN** l'avertissement est disponible dans la langue selectionnee avec la meme signification

### Requirement: Documentation des temporisations de contact sec

La documentation utilisateur FR/EN SHALL expliquer les trois durees et preciser qu'elles sont comptees depuis les demandes de transition, non depuis une observation physique. Pour `input_boolean`, elle SHALL preciser que l'etat est logique, non physique. Aucun delai supplementaire SHALL etre requis.

#### Scenario: Reglage sans retour physique

- **WHEN** l'utilisateur consulte le parcours contact sec
- **THEN** il trouve la signification des trois durees existantes et de leur point de depart
- **AND** la documentation distingue le contact sec d'une coupure d'alimentation secteur
- **AND** elle explique que le switch ne permet ni de confirmer la flamme ni de detecter un echec d'allumage

#### Scenario: Sous-jacent input_boolean dans la documentation

- **WHEN** l'utilisateur consulte la documentation du parcours `input_boolean`
- **THEN** il trouve la distinction entre l'etat logique de l'entite et un contact physique
- **AND** il est averti que cet etat ne confirme ni la flamme ni l'extinction effective

### Requirement: Documentation de la reprise et de la responsabilite initiale

La documentation FR/EN SHALL decrire la priorite aux dates restaurees exploitables, le decompte du temps d'arret de HA et l'absence d'attente sans date exploitable pour l'etat courant. Elle SHALL expliciter la responsabilite de l'utilisateur pour les manoeuvres precedant cette initialisation et ne pas presenter les temporisations comme une garantie de surete materielle.

#### Scenario: Installation avec poele deja en service

- **WHEN** l'utilisateur consulte les regles du premier demarrage
- **THEN** il peut identifier que ON et OFF sont adoptes sans redemarrer artificiellement un delai
- **AND** il est averti qu'une manoeuvre recente hors du plugin ne peut pas etre reconstituee

#### Scenario: Simple arret puis relance

- **WHEN** l'utilisateur consulte les regles de redemarrage avec dates exploitables
- **THEN** la documentation annonce la conservation des echeances et non un nouveau delai complet

## Observations

Les traductions francaise et anglaise contiennent `config.error.invalid_entity`
et les cles d'abandon `single_instance_allowed` et `reconfigure_successful`.
Leur presence ne garantit pas la traduction de chaque retour du flow HA.
Les tests de metadonnees du reset ne couvrent ni les parcours de configuration
et d'Options, ni leur traduction, ni la parite complete de leurs cles.

## Traceability

- [Identite et valeurs integrees](../../../custom_components/vtherm_pellet_stove/const.py) : `DEFAULT_OPTIONS`.
- [Parcours et selecteurs](../../../custom_components/vtherm_pellet_stove/config_flow.py) : `build_options_schema`, `PelletStoveConfigFlow`, `PelletStoveOptionsFlow`.
- [Enregistrement et ciblage](../../../custom_components/vtherm_pellet_stove/__init__.py) : `_register_factory`, `_register_services`, `_async_update_live_handlers`, `async_setup_entry`, `async_unload_entry`, `async_remove_entry`.
- [Factory](../../../custom_components/vtherm_pellet_stove/factory.py) : `PelletRegulationFactory`.
- [Resolution et application](../../../custom_components/vtherm_pellet_stove/handler.py) : `_resolve_options`, `async_update_options`.
- [Tests du handler](../../../tests/test_handler.py) : `TestScenario7OptionsUpdate`, `TestScenario11Reconfigure`.
- [Tests des entrees et du service](../../../tests/test_services.py) : `test_service_lifecycle_ignores_handler_and_sensor_keys`, `test_failed_global_setup_does_not_register_service`, `test_failed_global_unload_keeps_service`, `test_local_options_reload_does_not_reload_vtherm`, `test_local_options_reload_without_global_keeps_vtherm_running`, `test_global_options_skip_handlers_with_local_entries`.
- Traductions [francaise](../../../custom_components/vtherm_pellet_stove/translations/fr.json) et [anglaise](../../../custom_components/vtherm_pellet_stove/translations/en.json) : cles `config.error` et `config.abort`, etablies par lecture des donnees.
- [Guide utilisateur](../../../documentation/fr/vtherm_pellet_stove.md) : parcours d'installation et reference des parametres ; ecarts repertories separement.
- Les parcours de creation, la correspondance des flux, les bornes du formulaire et l'isolation des echecs entre handlers sont etablis par lecture du code ; cette specification ne leur attribue pas une couverture de test inexistante. Les tests de reconfiguration verifient la resolution des donnees, pas l'execution complete du flow HA.