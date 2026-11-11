# runtime-state

## Purpose

Decrire l'etat logiciel, les diagnostics, l'estimation d'energie et le reset
de la 1.0.1. Les phases et dates sont des vues de la regulation, pas des
confirmations d'allumage, d'extinction ou de refroidissement physique.

## State Model

Le Store HA de version 1 est propre a chaque thermostat :
`vtherm_pellet_stove.<unique_id transforme par slugify>`.

| Champ persiste        | Type serialise        |
| --------------------- | --------------------- |
| `is_heating`          | booleen               |
| `current_level_index` | entier ou null        |
| `last_on_at`          | date ISO 8601 ou null |
| `last_off_at`         | date ISO 8601 ou null |
| `last_reason`         | chaine ou null        |
| `boost_until`         | date ISO 8601 ou null |

Les attributs de diagnostic regroupent `phase`, `is_heating`, `on_percent`,
`current_level`, `current_level_index`, `elapsed_on_min`, `elapsed_off_min`,
`next_action_allowed_at`, `last_reason`, `last_on_at`, `last_off_at`,
`boost_active`, `boost_until`, `hysteresis_on`, `hysteresis_off`,
`min_on_duration_min`, `min_off_duration_min`, `cooldown_duration_min` et
`safety_room_temp`.

Les champs persistes ne constituent pas tout le runtime : la derniere decision,
la consigne precedente et les caches de puissance et d'energie ne sont pas
restaures. Les limites des donnees invalides restent dans
[l'observation O-08](../../observations.md).

## Requirements

### Requirement: Enregistrement du handler actif

Apres la correction de startup, `async_startup` SHALL demander un premier
controle avec `on_state_changed(True)`, puis enregistrer le handler par
`unique_id` dans `DATA_HANDLERS` s'il n'a pas ete retire. Ce registre SHALL
identifier les handlers actifs pour le reset et les mises a jour de reglages.

#### Scenario: Startup termine

- **GIVEN** un handler initialise et non retire
- **WHEN** son startup et le controle initial se terminent
- **THEN** le registre actif associe le `unique_id` du thermostat a ce handler

### Requirement: Retrait sans suppression du successeur

`remove` SHALL marquer le handler retire et le desinscrire seulement s'il est
encore le handler actif de ce thermostat. Les controles suivants SHALL etre
ignores. Dans HA, une sauvegarde finale SHALL etre planifiee, attendre le
controle en cours et ne pas ecrire si un successeur est deja actif. Le capteur
memorise SHALL rester disponible pour une recreation du handler.

#### Scenario: Ancien handler remplace

- **GIVEN** un nouveau handler actif pour le meme `unique_id`
- **WHEN** l'ancien handler est retire
- **THEN** le nouveau reste dans le registre et la sauvegarde finale de l'ancien ne remplace pas son etat

### Requirement: Sauvegarde et restauration par thermostat

Le handler SHALL restaurer les champs du State Model lors de son ajout a HA si le Store contient des donnees. A chaque publication d'un resultat de controle, il SHALL sauvegarder l'etat courant. Sans donnees, l'ajout SHALL conserver l'etat initial arrete sans dates. Au startup d'un sous-jacent binaire `switch` ou `input_boolean`, l'etat SHALL ensuite etre initialise depuis son etat connu, en conservant les dates restaurees exploitables pour les garde-fous.

#### Scenario: Redemarrage pendant la chauffe

- **GIVEN** un Store valide avec `is_heating = true` et un allumage une minute auparavant
- **WHEN** la restauration est suivie d'un controle en mode `heat` avec un minimum de marche de 30 minutes
- **THEN** une extinction par hysteresis reste bloquee jusqu'a l'echeance, sauf priorite d'arret

#### Scenario: Aucun historique

- **WHEN** le Store est vide lors de l'ajout du handler
- **THEN** `is_heating` reste faux et les dates de transition restent nulles
- **AND** pour un sous-jacent binaire, cet etat provisoire ne remplace pas son adoption au startup

### Requirement: Normalisation des dates restaurees

La restauration SHALL relire les dates ISO 8601 valides et attribuer le fuseau
UTC aux dates sans fuseau. Un champ date absent, nul ou vide SHALL devenir
null. Cette regle ne promet pas la recuperation d'un stockage corrompu.

#### Scenario: Date ISO sans fuseau

- **WHEN** `last_off_at` est restaure depuis une date ISO valide sans fuseau
- **THEN** la date est interpretee en UTC pour les calculs de duree

### Requirement: Correction d'une chauffe restauree avec VTherm OFF

Pour un sous-jacent `climate`, au startup apres restauration du mode VTherm, le handler SHALL corriger `is_heating = true` en faux si VTherm est sur OFF, sans remplacer `last_off_at` par maintenant. Cette correction SHALL ne pas etre faite lors de l'ajout a HA. Pour un sous-jacent binaire `switch` ou `input_boolean`, le startup SHALL adopter son etat connu et appliquer le mode VTherm sans masquer une ouverture necessaire.

#### Scenario: Historique de chauffe perime

- **GIVEN** un sous-jacent climate, une chauffe restauree, VTherm sur OFF et aucune ancienne date d'arret
- **WHEN** le startup s'execute
- **THEN** le controleur est arrete sans nouvelle date d'arret ni nouveau delai de refroidissement

#### Scenario: Date d'arret existante

- **GIVEN** un sous-jacent climate, une chauffe restauree, VTherm sur OFF et une date d'arret enregistree
- **WHEN** le startup corrige l'etat
- **THEN** l'ancienne date d'arret est conservee

#### Scenario: Sous-jacent binaire deja OFF au retour de HA

- **GIVEN** un sous-jacent `switch` ou `input_boolean` `off`, VTherm sur OFF et une date d'arret restauree exploitable
- **WHEN** le startup adopte l'etat du contact
- **THEN** la date d'arret est conservee sans nouvelle commande OFF ni remise a zero du delai

### Requirement: Phases derivees de l'historique logiciel

Le controleur SHALL exposer `igniting` s'il est en chauffe depuis moins que
le minimum de marche, puis `burning`. A l'arret, il SHALL exposer `cooldown`
avant l'echeance `last_off_at + min_off + cooldown`, puis `off`.
Sans date correspondante, la phase SHALL etre `burning` en chauffe, ou `off`
a l'arret. Les echeances sont inclusives pour la sortie de ces delais.

#### Scenario: Passage en burning

- **GIVEN** un allumage a T et un minimum de marche de 30 minutes
- **WHEN** le diagnostic est calcule a T plus 30 minutes
- **THEN** la phase vaut `burning`

#### Scenario: Fin du cooldown

- **GIVEN** un arret a T, un minimum d'arret de 20 minutes et un refroidissement de 5 minutes
- **WHEN** le diagnostic est calcule a T plus 25 minutes
- **THEN** la phase vaut `off`

### Requirement: Capteur de diagnostic par thermostat

L'integration SHALL exposer un capteur de categorie diagnostic, sans polling,
d'identifiant unique `vtherm_pellet_stove_<unique_id VTherm>_debug`, dont la
valeur est la phase et les attributs sont la liste de diagnostic du State Model,
pas seulement les six champs persistes. Le handler
SHALL reutiliser un capteur deja enregistre lors de sa recreation, sans
l'enregistrer en double. La plateforme sensor est portee par l'entree globale.

#### Scenario: Recreation d'un handler

- **GIVEN** un capteur deja enregistre pour le thermostat
- **WHEN** un nouveau handler attache son diagnostic
- **THEN** il reutilise le capteur et y publie les nouveaux attributs sans doublon d'identifiant

### Requirement: Rattachement differe et rechargement du capteur

Sans plateforme sensor prete, le handler SHALL mettre son capteur en attente
sans doublon. Le setup de la plateforme SHALL enregistrer ces capteurs et
rattacher les handlers actifs. Au dechargement global reussi, l'integration
SHALL detacher les capteurs et oublier leurs enregistrements et le callback.
Le setup suivant SHALL creer et enregistrer de nouveaux capteurs pour les
handlers toujours actifs.

#### Scenario: Handler pret avant la plateforme

- **GIVEN** un handler avec son capteur et aucun callback de plateforme
- **WHEN** le capteur est attache puis la plateforme est chargee
- **THEN** le capteur en attente est ajoute une seule fois avec `update_before_add = true`

#### Scenario: Rechargement de la plateforme globale

- **GIVEN** un handler actif avec un capteur enregistre
- **WHEN** la plateforme globale est dechargee avec succes puis rechargee
- **THEN** le handler recoit un nouveau capteur, enregistre sur la nouvelle plateforme

### Requirement: Identite de l'appareil de diagnostic

Le capteur SHALL utiliser la cle de traduction `pellet_debug` et le nommage
d'entite HA. Son `DeviceInfo` SHALL identifier l'appareil par le domaine
`vtherm_pellet_stove` et la valeur `vtherm_pellet_stove_<unique_id VTherm>`,
avec le fabricant `VTherm Pellet Stove` et le modele `Pellet Regulation`.

#### Scenario: Creation du diagnostic

- **WHEN** le capteur d'un thermostat d'identifiant unique U est cree
- **THEN** son appareil est identifie par `vtherm_pellet_stove_U` dans le domaine du plugin
- **AND** sa cle de traduction vaut `pellet_debug`

### Requirement: Valeurs derivees des attributs de diagnostic

`elapsed_on_min` SHALL etre arrondi a 0.1 minute en chauffe et nul a l'arret ;
`elapsed_off_min` SHALL suivre la regle inverse. Une date absente dans l'etat
concerne SHALL donner zero minute. `boost_active` SHALL exiger un gestionnaire
de boost et une echeance future ; le diagnostic `boost_until` SHALL etre nul
si le boost n'est pas actif, meme si le Store conserve son ancienne date.

#### Scenario: Echeance du boost atteinte

- **GIVEN** un `boost_until` persiste egal a T
- **WHEN** les attributs sont lus a T
- **THEN** `boost_active` est faux et le diagnostic `boost_until` est nul
- **AND** cette lecture n'efface pas la date du Store

#### Scenario: Historique incomplet pendant la chauffe

- **GIVEN** un controleur en chauffe sans date d'allumage
- **WHEN** ses attributs sont calcules
- **THEN** `elapsed_on_min` vaut zero et `elapsed_off_min` est nul

### Requirement: Echeance de diagnostic

`next_action_allowed_at` SHALL etre la date d'allumage plus le minimum de marche pendant la chauffe, ou la date d'arret plus le minimum d'arret et le refroidissement a l'arret. Une date restauree exploitable SHALL etre reutilisee sans decalage lie au redemarrage, meme si l'echeance est passee. Sans date correspondante exploitable, ce champ SHALL valoir null. Il decrit une echeance de duree, pas une promesse d'action future.

#### Scenario: Reset de l'historique

- **WHEN** les dates de transition sont effacees par un reset reussi
- **THEN** `next_action_allowed_at` vaut null

#### Scenario: Echeance ON conservee

- **GIVEN** un contact `on`, `last_on_at = T` exploitable et un minimum de marche de 30 minutes
- **WHEN** HA redemarre a T plus 15 minutes sans nouvelle transition
- **THEN** `next_action_allowed_at` reste T plus 30 minutes
- **AND** les 15 minutes restantes ne sont pas remplacees par un nouveau delai de 30 minutes

#### Scenario: Echeance OFF conservee

- **GIVEN** un contact `off`, `last_off_at = T` exploitable, un minimum d'arret de 20 minutes et un refroidissement de 5 minutes
- **WHEN** HA redemarre a T plus 15 minutes sans nouvelle transition
- **THEN** `next_action_allowed_at` reste T plus 25 minutes
- **AND** seules 10 minutes restent a attendre

#### Scenario: Echeance deja depassee

- **GIVEN** un contact connu et une date restauree exploitable dont l'echeance est passee
- **WHEN** le diagnostic est publie apres la reprise
- **THEN** l'echeance d'origine reste exposee et la temporisation ne bloque plus la transition

### Requirement: Adoption initiale du contact sans preuve physique

Au demarrage du parcours sous-jacent binaire `switch` ou `input_boolean`, l'integration SHALL adopter le premier etat connu `on` ou `off` comme etat de demande de chauffe. Cette adoption SHALL preceder la premiere decision automatique et ne pas constituer une nouvelle transition datee. Les phases et diagnostics SHALL rester des estimations logicielles, sans confirmation de flamme ou d'extinction effective.

#### Scenario: Contact actif sans Store

- **GIVEN** un Store vide et un contact `on`
- **WHEN** l'initialisation du contact s'execute
- **THEN** la chauffe demandee est adoptee sans commande ON et sans date d'allumage inventee
- **AND** le minimum de marche ne retarde pas une extinction demandee

#### Scenario: Contact ouvert sans Store

- **GIVEN** un Store vide et un contact `off`
- **WHEN** l'initialisation du contact s'execute
- **THEN** l'arret est adopte sans commande OFF et sans date d'arret inventee
- **AND** le minimum d'arret et le refroidissement ne retardent pas un allumage autrement autorise

#### Scenario: Adoption d'un input_boolean

- **GIVEN** un sous-jacent `input_boolean` connu `on` ou `off` et un Store vide
- **WHEN** l'initialisation du sous-jacent binaire s'execute
- **THEN** son etat logique est adopte sans commande ni date de transition inventee
- **AND** cet etat ne confirme pas la flamme ou l'extinction physique

#### Scenario: Contact initialement indisponible

- **GIVEN** un contact dont l'etat est indisponible au startup
- **WHEN** son premier etat connu devient `on` ou `off`
- **THEN** cet etat est adopte avant d'autoriser une nouvelle decision automatique d'allumage
- **AND** l'indisponibilite n'a pas ete assimilee a un contact OFF

#### Scenario: Adoption ON avec reparation VTherm active

- **GIVEN** un contact `on`, un VTherm en mode `heat` et la reparation automatique active
- **WHEN** l'etat du contact est adopte, puis que VTherm execute sa reparation apres son delai d'activation
- **THEN** la reparation ne commande pas OFF au seul motif que l'etat attendu interne n'a pas ete synchronise

### Requirement: Priorite de la date exploitable de l'etat courant

Pour un sous-jacent binaire `switch` ou `input_boolean` connu, l'integration SHALL utiliser en priorite la date restauree exploitable correspondant a son etat : `last_on_at` pour ON, `last_off_at` pour OFF. L'absence de l'autre date SHALL ne pas invalider celle-ci. Une date exploitable SHALL etre interpretable, non future et coherente avec l'etat adopte et la chronologie connue. La duree de l'arret de HA SHALL compter dans le temps ecoule.

#### Scenario: Reprise ON avec historique partiel

- **GIVEN** un contact `on`, une date d'allumage exploitable et aucune date d'arret
- **WHEN** HA reprend apres une interruption
- **THEN** le minimum de marche est calcule depuis cette date d'allumage, interruption comprise

#### Scenario: Reprise OFF avec historique partiel

- **GIVEN** un contact `off`, une date d'arret exploitable et aucune date d'allumage
- **WHEN** HA reprend apres une interruption
- **THEN** l'autorisation ON utilise la date d'arret plus le minimum d'arret et le refroidissement

#### Scenario: Reprise exactement a l'echeance

- **GIVEN** un contact connu et sa date restauree exploitable
- **WHEN** le controle reprend exactement a l'echeance du delai applicable
- **THEN** la temporisation autorise la transition, sous reserve des autres regles

### Requirement: Initialisation sans date exploitable et sans attente artificielle

Sans date restauree exploitable pour l'etat courant d'un sous-jacent binaire `switch` ou `input_boolean`, l'integration SHALL considerer le delai de cet etat deja satisfait et exposer une echeance nulle. Elle SHALL ne pas creer une date a maintenant ni reconstituer des manoeuvres a partir du Recorder ou de l'age de l'etat HA. Cette exception SHALL ne pas supprimer une date exploitable ni contourner les autres regles de regulation.

#### Scenario: Date pertinente absente

- **GIVEN** un contact connu et aucune date restauree pour cet etat
- **WHEN** le premier controle demande la transition opposee
- **THEN** aucune temporisation initiale artificielle ne la retarde

#### Scenario: Date pertinente invalide ou future

- **GIVEN** un contact connu et une date pertinente illisible, future ou chronologiquement incoherente
- **WHEN** l'initialisation evalue cette date
- **THEN** elle suit le parcours sans date exploitable sans inventer de nouvelle echeance
- **AND** une date non pertinente invalide ne detruit pas une date pertinente exploitable

### Requirement: Reprise des garde-fous apres une transition pilotee

Apres une transition pilotee d'un sous-jacent binaire `switch` ou `input_boolean`, l'integration SHALL dater la nouvelle demande ON ou OFF et appliquer les temporisations normales a partir de cette date. Une simple adoption, un maintien, une publication ou une relance SHALL ne pas modifier ces dates. L'exception initiale sans historique SHALL ne pas neutraliser les garde-fous des transitions suivantes.

#### Scenario: Premier allumage apres adoption OFF sans date

- **GIVEN** un contact initialement `off` sans historique exploitable et un premier allumage autorise a T
- **WHEN** une extinction par hysteresis est demandee avant T plus le minimum de marche
- **THEN** cette extinction est retardee par le garde-fou normal

#### Scenario: Premiere extinction apres adoption ON sans date

- **GIVEN** un contact initialement `on` sans historique exploitable et une extinction demandee a T
- **WHEN** un rallumage est demande avant T plus le minimum d'arret et le refroidissement
- **THEN** ce rallumage est retarde par le garde-fou normal

#### Scenario: Relances successives sans transition

- **GIVEN** un contact connu et une date de transition sauvegardee exploitable
- **WHEN** plusieurs relances ont lieu sans nouvelle transition
- **THEN** chaque reprise conserve la meme date et la meme echeance de duree

### Requirement: Estimation d'energie pendant la chauffe logique

Pendant la chauffe, le handler SHALL initialiser un repere temporel puis
appeler `incremente_energy`, si disponible, quand un controle constate au
moins `cycle_min` minutes ecoulees ; la valeur de repli est 5 minutes.
Il SHALL remettre le repere a maintenant apres ce credit et l'effacer a
l'arret. Ce credit est une estimation VTherm, pas une mesure du poele.

#### Scenario: Echeance d'energie

- **GIVEN** un debut de suivi a T, une chauffe continue et `cycle_min = 5`
- **WHEN** un controle s'execute a T plus 5 minutes
- **THEN** un credit d'energie est demande et le repere est avance

### Requirement: Cible unique et autorisations du reset

Le service `vtherm_pellet_stove.reset` SHALL exiger un seul `entity_id` explicite
correspondant a un VTherm climate du registre avec un handler pellet actif
et un etat disponible. Si un utilisateur est present dans le contexte, il
SHALL disposer du droit de controle sur cette entite. Les autres thermostats
SHALL ne pas etre commandes.

#### Scenario: Mauvaise cible

- **WHEN** la cible est un climate sous-jacent, un VTherm sans handler pellet, une liste ou une entite indisponible
- **THEN** la demande est rejetee sans reset d'un handler

#### Scenario: Permission absente

- **WHEN** l'utilisateur du contexte n'a pas le droit de controle
- **THEN** le reset est refuse

### Requirement: Erreurs de validation du reset

Le service SHALL signaler `invalid_reset_target` pour une cible non admissible
et `reset_target_unavailable` pour un etat absent, inconnu ou indisponible
d'une cible admissible. Si l'utilisateur du contexte est introuvable, il
SHALL lever `UnknownUser` ; sans droit de controle, il SHALL lever `Unauthorized`.
Une cible manquante ou sous forme de liste SHALL etre rejetee par le schema.

#### Scenario: Utilisateur introuvable

- **WHEN** le contexte contient un identifiant d'utilisateur inexistant
- **THEN** `UnknownUser` est leve sans appeler le reset du handler

#### Scenario: Cible valide sans etat disponible

- **GIVEN** une cible VTherm admissible avec un handler actif
- **WHEN** son etat est absent, `unknown` ou `unavailable`
- **THEN** le service signale `reset_target_unavailable` sans appeler le handler

### Requirement: Arret confirme par VTherm avant effacement

Le reset SHALL serialiser les demandes, ignorer le controle pendant sa phase
active et annuler un cycle scheduler en cours. Si VTherm n'est pas deja OFF,
il SHALL demander `climate.set_hvac_mode` sur VTherm avec `hvac_mode = off`,
en appel bloquant et avec le contexte recu. Il SHALL verifier le mode VTherm
avant d'effacer l'historique. Cette verification n'est pas un acquittement materiel.

#### Scenario: Sauvegarde de controle en cours

- **GIVEN** un controle dont la sauvegarde est encore en cours
- **WHEN** un reset est demande
- **THEN** le reset attend cette sauvegarde avant de demander OFF et de sauvegarder son propre etat

#### Scenario: Deux resets concurrents

- **GIVEN** un premier reset en attente de la commande OFF
- **WHEN** un controle et un second reset sont demandes
- **THEN** le controle est ignore et le second reset attend la fin du premier
- **AND** si VTherm est alors OFF, aucune seconde commande OFF n'est envoyee

#### Scenario: Arret refuse

- **GIVEN** un historique existant et VTherm en mode `heat`
- **WHEN** la commande echoue ou que le mode reste different de `off`
- **THEN** l'historique n'est pas efface

### Requirement: Disponibilite du handler pendant le reset

Le handler SHALL signaler `reset_not_ready` s'il est retire ou si son
controleur ou son Store n'est pas initialise. Il SHALL verifier a nouveau
son retrait apres la commande OFF, avant l'effacement. Si VTherm ne confirme
pas le mode OFF, il SHALL signaler `reset_not_off` sans effacer l'historique.
Le drapeau de reset actif SHALL etre libere meme en cas d'erreur.

#### Scenario: Retrait pendant la commande OFF

- **GIVEN** un historique existant et une commande OFF en cours pour le reset
- **WHEN** le handler est retire avant la verification finale
- **THEN** le reset signale `reset_not_ready` sans effacer l'historique

#### Scenario: Mode OFF refuse

- **WHEN** la commande se termine mais VTherm reste en mode `heat`
- **THEN** le reset signale `reset_not_off` et conserve l'historique

### Requirement: Effets d'un reset reussi

Apres verification de OFF, le reset SHALL effacer la chauffe logique, les
dates de transition, le niveau courant, le boost, la consigne precedente et
les memorisations d'application de puissance et de suivi d'energie.
Il SHALL fixer `last_reason = reset`, publier le diagnostic `off`, sauvegarder
l'etat, conserver la configuration et l'energie cumulee, et laisser VTherm OFF.

#### Scenario: Reinitialisation sans redemarrage automatique

- **WHEN** un reset aboutit
- **THEN** les dates et le boost sont nuls, la raison vaut `reset` et VTherm reste OFF
- **AND** les delais logiciels d'arret et de refroidissement sont effaces, sans attendre le refroidissement physique

### Requirement: Erreur de sauvegarde du reset

Si la sauvegarde du reset echoue avec une erreur HA ou systeme de fichiers,
le handler SHALL signaler `reset_save_failed` sans remettre VTherm en chauffe.
L'etat memoire deja efface SHALL ne pas etre presente comme persiste avec succes.

#### Scenario: Stockage indisponible

- **GIVEN** un VTherm arrete et un reset dont la sauvegarde leve `OSError`
- **WHEN** le reset se termine en erreur
- **THEN** l'erreur est signalee, la raison en memoire reste `reset` et VTherm reste OFF

### Requirement: Metadonnees et traductions du reset

Le descripteur du service SHALL exposer un `entity_id` requis, avec un selecteur
`climate` de l'integration `versatile_thermostat`, sans selection multiple.
Les traductions francaise et anglaise SHALL fournir les libelles du service
et du champ et partager les memes cles d'exceptions.

#### Scenario: Description du service dans les deux langues

- **WHEN** les metadonnees et traductions du reset sont chargees
- **THEN** le champ cible est requis et unique et les libelles du service et du champ existent en francais et en anglais
- **AND** les cles d'exceptions des deux langues sont identiques

## Observations

Avant sa premiere mise a jour, l'objet capteur initialise sa phase a `unknown`.
L'attachement lui fournit immediatement les attributs du controleur avant son
enregistrement : ce detail de construction n'ajoute pas une cinquieme phase
de regulation et ne garantit pas la publication d'un etat HA `unknown`.

## Traceability

- [Etat serialise](../../../custom_components/vtherm_pellet_stove/pellet/state.py) : `save_state`, `restore_state`.
- [Phases et reset du controleur](../../../custom_components/vtherm_pellet_stove/pellet/controller.py) : `current_phase`, `get_debug_attributes`, `reset`.
- [Cycle de vie et reset](../../../custom_components/vtherm_pellet_stove/handler.py) : `async_added_to_hass`, `async_startup`, `remove`, `_async_save_removed_state`, `_publish_current_state`, `async_reset`, `control_heating`.
- [Capteur](../../../custom_components/vtherm_pellet_stove/sensor.py) : `PelletDebugSensor`, `async_setup_entry`.
- [Validation du service](../../../custom_components/vtherm_pellet_stove/__init__.py) : `_register_services`.
- [Tests du controleur](../../../tests/test_controller.py) : reset, aller-retour de serialisation.
- [Tests du handler](../../../tests/test_handler.py) : tests de reset, `TestScenario10RestoreAfterRestart`, `TestScenario12DebugSensorReuse`, `TestScenario14StaleHeatingOnRestart`, tests d'energie de `TestScenario15BinaryControlNoCycling`.
- Meme fichier : `test_handler_registry_survives_old_handler_removal`, `test_unload_during_stop_prevents_reset_of_removed_handler`, `test_reset_waits_for_inflight_control_save`, `test_control_skipped_during_stop_and_reset_calls_serialized`, `test_sensor_is_recreated_after_platform_unload`.
- [Tests des services](../../../tests/test_services.py) : ciblage, permissions, cycle de vie, metadata et traductions.
- [Avertissements utilisateur du reset](../../../README.fr.md) : preservation des protections materielles et suppression des delais logiciels.
- La normalisation des dates sans fuseau, le garde de sauvegarde finale face a un successeur, le drainage de la file d'attente par la plateforme, les metadonnees du capteur et les details de calcul des diagnostics sont etablis par lecture du code, sans test automatise distinct revendique.