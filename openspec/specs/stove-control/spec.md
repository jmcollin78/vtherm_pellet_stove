# stove-control

## Purpose

Decrire le chemin de commande entre le controleur pellet et le scheduler VTherm
en 1.0.1. Le plugin ne dialogue pas directement avec le materiel. Les decisions
et les appels au scheduler ne constituent pas un acquittement physique.

## Requirements

### Requirement: Initialisation de l'interface VTherm

`init_algorithm` SHALL construire le controleur avec les reglages effectifs,
affecter le proxy a `thermostat.prop_algorithm` et creer le Store propre au
thermostat selon [runtime-state](../runtime-state/spec.md). L'initialisation
SHALL ne pas commander le scheduler ; le controle est un appel distinct.

#### Scenario: Creation de l'algorithme

- **GIVEN** un thermostat avec des reglages effectifs resolus
- **WHEN** `init_algorithm` est appelee
- **THEN** le controleur utilise ces reglages, le proxy est expose et le Store est initialise
- **AND** aucune commande de cycle n'est demandee par cette initialisation

### Requirement: Calcul autoritatif dans le handler

Le handler SHALL exposer un proxy comme `prop_algorithm` du thermostat.
Le `calculate` de ce proxy SHALL retourner la derniere valeur sans modifier
le controleur. Le calcul qui peut modifier l'etat SHALL etre execute dans
la boucle de controle du handler, pour y detecter les transitions. Les
proprietes `on_percent` et `calculated_on_percent` du proxy SHALL relayer
celles du controleur sans modifier son etat.

#### Scenario: Recalcul VTherm avant le controle

- **GIVEN** un controleur arrete et un allumage qui devient autorise
- **WHEN** VTherm appelle le proxy puis le handler execute son controle
- **THEN** l'appel au proxy ne consomme pas la transition, qui reste detectee par le handler

### Requirement: Rattachement du scheduler et callbacks de cycle

`on_scheduler_ready` SHALL memoriser le scheduler et enregistrer les callbacks
`_on_cycle_start` et `_on_cycle_end`. Ces callbacks et les methodes
`on_cycle_started` et `on_cycle_completed` du controleur SHALL ne modifier
ni la regulation ni l'energie. `should_publish_intermediate` SHALL retourner
vrai. Le suivi d'energie appartient a la boucle du handler, pas aux callbacks.

#### Scenario: Scheduler disponible

- **WHEN** VTherm fournit un scheduler au handler
- **THEN** ce scheduler est memorise et chacun des deux callbacks est enregistre une fois pour cet appel

#### Scenario: Fin de cycle sans effet sur la regulation

- **GIVEN** un controleur et son historique
- **WHEN** le callback de fin de cycle est invoque
- **THEN** l'etat du controleur et l'energie ne sont pas modifies par ce callback

### Requirement: Commande sur transition sans cycle periodique

Hors mode HVAC `off`, avec un scheduler lie, le handler SHALL appeler
`start_cycle(hvac_mode, on_percent, True)` lors d'une transition interne ON/OFF,
puis `cancel_cycle()` lorsque cet appel aboutit. En etat stable, il SHALL
ne pas lancer un nouveau cycle et annuler un cycle residuel en cours.
Le parametre `force` SHALL ne pas creer a lui seul une commande supplementaire.

#### Scenario: Transition vers la chauffe

- **GIVEN** un controleur arrete, un allumage autorise et un scheduler lie
- **WHEN** le calcul decide ON en mode `heat`
- **THEN** le handler appelle `start_cycle('heat', max_on_percent, True)` puis annule le cycle

#### Scenario: Maintien OFF meme avec force

- **GIVEN** un controleur arrete dont la temporisation interdit le rallumage
- **WHEN** le controle est invoque avec `force = true`
- **THEN** aucun nouveau cycle OFF n'est lance

#### Scenario: Cycle residuel pendant un maintien

- **GIVEN** un etat logiciel stable et un cycle scheduler encore actif
- **WHEN** le handler execute le controle
- **THEN** ce cycle est annule sans nouvel appel a `start_cycle`

### Requirement: Arret HVAC sans double commande du scheduler

En mode HVAC `off`, le handler SHALL ne pas appeler `start_cycle`, meme si
le controleur vient de passer de ON a OFF. Il SHALL annuler un cycle residuel.
Le chemin existant repose sur la commande OFF envoyee au sous-jacent par VTherm ;
il ne garantit pas une nouvelle commande d'arret par le plugin.

#### Scenario: VTherm passe sur OFF

- **GIVEN** un controleur en chauffe et un scheduler lie
- **WHEN** le mode VTherm passe a `off`
- **THEN** le controleur devient arrete et aucun `start_cycle` supplementaire n'est demande
- **AND** un cycle scheduler actif est annule

### Requirement: Allumage automatique conditionne par l'observation

Le handler SHALL autoriser une transition automatique OFF vers ON uniquement
si sa lecture des sous-jacents conclut explicitement a un etat non chauffant.
Une observation inconnue, indisponible, contradictoire ou deja chauffante SHALL
bloquer cette transition avec `physical_state_not_confirmed_off`.
La lecture disponible en 1.0.1 et ses limites sont consignees hors exigences.

#### Scenario: Retour d'etat inconnu

- **GIVEN** une demande de chauffe et un controleur arrete
- **WHEN** le `climate` sous-jacent est `unknown`
- **THEN** aucun cycle d'allumage n'est lance et la raison vaut `physical_state_not_confirmed_off`

#### Scenario: Flamme deja presente

- **GIVEN** un controleur logiciel arrete et une observation coherente `Flame On`
- **WHEN** la temperature demanderait un allumage
- **THEN** aucune commande d'allumage en double n'est envoyee

### Requirement: Controle declenche meme sans changement de valeur

`on_state_changed` SHALL lancer le controle meme si son argument `changed`
vaut faux, afin que le franchissement d'un seuil ou d'une echeance soit pris
en compte lors de cet appel.

#### Scenario: Notification changed faux

- **GIVEN** un controleur en chauffe dont le minimum de marche est ecoule
- **WHEN** une notification `changed = false` survient avec une mesure au-dessus du seuil OFF
- **THEN** le handler recalcule et traite la transition OFF

### Requirement: Securite haute sans consigne

Sans consigne, si le controleur est en chauffe et la mesure atteint la limite
haute, le handler SHALL enregistrer un arret `safety`, publier et sauvegarder
l'etat. Avec un scheduler et un mode different de `off`, il SHALL demander un
cycle d'arret force puis l'annuler. L'absence de consigne seule n'est pas
une regle d'arret general : voir les observations.

#### Scenario: Piece trop chaude et consigne absente

- **GIVEN** un controleur en chauffe, aucune consigne, un mode `heat` et un scheduler lie
- **WHEN** la mesure vaut 27 degres pour une limite de 26
- **THEN** le handler demande l'arret via le scheduler, puis publie l'etat logiciel arrete

## Observations

Hors arret de securite d'un controleur deja en chauffe, une consigne absente
fait retourner le handler sans calcul normal, commande ni publication. Le
test `test_control_heating_skipped_when_no_target` couvre ce retour depuis
l'etat initial ; il ne valide pas toutes les combinaisons d'historique et de
mode HVAC. Le retour precede notamment le traitement normal de HVAC OFF.
Cette politique reste non normative dans [O-03](../../observations.md) ;
elle n'est pas une garantie d'arret en cas de perte de consigne.

Dans la boucle normale, un mode VTherm absent ou vide est remplace par `off`.
Ce repli ne corrige pas le retour anticipe sans consigne et n'etablit pas
une garantie de commande physique. Les autres modes ne sont pas valides
par une liste de modes supportes dans ce handler.

## Traceability

- [Controle du poele](../../../custom_components/vtherm_pellet_stove/handler.py) : `_PropAlgoProxy`, `_async_control_heating`, `_physical_heating_state`, `on_state_changed`.
- Meme fichier : `init_algorithm`, `on_scheduler_ready`, `_on_cycle_start`, `_on_cycle_end`, `should_publish_intermediate`.
- [Callbacks du controleur](../../../custom_components/vtherm_pellet_stove/pellet/controller.py) : `on_cycle_started`, `on_cycle_completed`.
- [Tests du handler](../../../tests/test_handler.py) : `test_unknown_physical_state_blocks_automatic_ignition`, `test_known_flame_does_not_send_duplicate_ignition`, `test_conflicting_physical_status_blocks_automatic_ignition`, `test_safety_stop_without_target_requests_off`.
- Meme fichier : `test_on_scheduler_ready_registers_callbacks`, `test_control_heating_skipped_when_no_target`, `test_handler_reads_options_on_init`, `test_init_sets_prop_algorithm_on_thermostat`.
- Meme fichier : `TestScenario13ForceOnToOffTransition`, `TestScenario14ChangedFalseStillRecomputes`, `TestScenario15BinaryControlNoCycling`, `TestScenario16PropAlgoProxy`.
- L'absence d'effet des callbacks, `should_publish_intermediate` et le repli de mode absent sont etablis par lecture du code, sans test automatise distinct revendique.
- [Limites et faits non normatifs](../../observations.md) : absence de retry garanti, lecture Duepi, ecarts entre etat logique et etat physique.