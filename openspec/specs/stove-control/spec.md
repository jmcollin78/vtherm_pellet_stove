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

Pour un sous-jacent `climate`, le handler SHALL autoriser OFF vers ON seulement si l'observation confirme un etat non chauffant. Une observation inconnue, indisponible, contradictoire ou chauffante SHALL bloquer l'allumage avec `physical_state_not_confirmed_off`. Pour un sous-jacent binaire `switch` ou `input_boolean`, l'autorisation SHALL suivre son etat, sans exiger de retour physique.

#### Scenario: Retour d'etat inconnu

- **GIVEN** une demande de chauffe et un controleur arrete
- **WHEN** le `climate` sous-jacent est `unknown`
- **THEN** aucun cycle d'allumage n'est lance et la raison vaut `physical_state_not_confirmed_off`

#### Scenario: Flamme deja presente

- **GIVEN** un controleur logiciel arrete et une observation coherente `Flame On`
- **WHEN** la temperature demanderait un allumage
- **THEN** aucune commande d'allumage en double n'est envoyee

### Requirement: Autorisation d'allumage par contact sec

Pour un sous-jacent binaire `switch` ou `input_boolean`, l'integration SHALL autoriser un nouvel allumage automatique seulement si son etat est explicitement `off` et si les autres regles de regulation l'autorisent. Un etat absent, inconnu, indisponible, non reconnu ou deja `on` SHALL bloquer l'allumage. Aucun attribut `burner_status` ou `hvac_action` SHALL etre requis.

#### Scenario: Contact arrete sans attribut de poele

- **GIVEN** un contact `off`, une demande de chauffe et des delais satisfaits
- **WHEN** le controle est execute sans attribut de retour physique
- **THEN** un allumage peut etre demande via VTherm

#### Scenario: input_boolean explicitement OFF

- **GIVEN** un sous-jacent `input_boolean` `off`, une demande de chauffe et des delais satisfaits
- **WHEN** le controle est execute
- **THEN** un allumage peut etre demande via VTherm sans pretendre observer la flamme

#### Scenario: Contact indisponible

- **GIVEN** une demande de chauffe depuis un etat logiciel arrete
- **WHEN** le contact est absent, `unknown`, `unavailable` ou dans un etat non reconnu
- **THEN** aucune commande ON n'est demandee

#### Scenario: Contact deja actif

- **GIVEN** un contact `on` adopte au demarrage et une demande de maintien en chauffe
- **WHEN** le controle est execute
- **THEN** aucune nouvelle commande ON n'est demandee

#### Scenario: Temporisation d'arret encore active

- **GIVEN** un contact `off` et une date d'arret exploitable dont l'echeance n'est pas atteinte
- **WHEN** la temperature demande l'allumage
- **THEN** l'etat du contact seul ne suffit pas a autoriser ON

### Requirement: Commandes de contact sur transition uniquement

Pour un sous-jacent binaire `switch` ou `input_boolean`, l'integration SHALL demander via VTherm l'activation ou l'ouverture lors d'une transition de regulation, sans cycles marche/arret periodiques. Un maintien ou la seule restauration SHALL ne pas produire de commande supplementaire. Une transition de regulation apres restauration SHALL rester possible. Une commande SHALL ne pas etre presentee comme une confirmation physique.

#### Scenario: Transition de regulation vers ON

- **GIVEN** un contact `off` et un allumage autorise
- **WHEN** la regulation decide ON
- **THEN** une seule commande d'activation est demandee via VTherm
- **AND** des controles de maintien ne repetent pas cette commande

#### Scenario: Transition de regulation vers OFF

- **GIVEN** une chauffe demandee, le minimum de marche satisfait et le seuil haut atteint
- **WHEN** la regulation decide OFF
- **THEN** une seule commande d'ouverture est demandee via VTherm
- **AND** aucun cycle periodique ne rappelle OFF pendant le refroidissement

#### Scenario: Relance sans changement de decision

- **GIVEN** un contact et un historique restaures coherents avec la decision de regulation
- **WHEN** HA redemarre et la decision reste identique
- **THEN** ni ON ni OFF ne sont demandes du seul fait de cette relance

### Requirement: Priorites d'ouverture du contact

Pour un sous-jacent binaire `switch` ou `input_boolean`, un arret manuel de VTherm ou une securite haute SHALL demander l'ouverture sans attendre le minimum de marche. VTherm et le plugin SHALL ne pas doubler la commande pour une transition. Cette regle SHALL aussi s'appliquer si l'etat initial est ON sans historique exploitable. L'extinction progressive SHALL rester a la charge du poele.

#### Scenario: Arret manuel pendant la marche minimale

- **GIVEN** un contact `on` et un minimum de marche non ecoule
- **WHEN** l'utilisateur passe VTherm sur OFF
- **THEN** l'ouverture du contact est demandee sans attendre l'echeance et sans commande OFF en double

#### Scenario: Limite haute pendant le demarrage suppose

- **GIVEN** un contact `on`, une chauffe demandee et un minimum de marche non ecoule
- **WHEN** la temperature atteint la limite de securite
- **THEN** l'ouverture est demandee sans attendre la chauffe effective supposee

#### Scenario: Premier demarrage avec VTherm OFF et contact ON

- **GIVEN** un contact `on` sans historique exploitable et VTherm restaure sur OFF
- **WHEN** le controle de demarrage applique le mode VTherm
- **THEN** l'ouverture du contact est demandee sans attente artificielle
- **AND** une simple correction de l'etat logiciel ne remplace pas cette demande d'ouverture

### Requirement: Coherence avec la reparation automatique VTherm

Le plugin SHALL maintenir l'etat attendu par la reparation VTherm coherent avec toute adoption ou transition d'un sous-jacent binaire `switch` ou `input_boolean`. La reparation SHALL NOT commander l'etat oppose. Le plugin SHALL NOT desactiver repair ni modifier un etat prive ; toute synchronisation SHALL utiliser un contrat public. Sans contrat compatible, l'implementation SHALL attendre l'evolution suivie par l'issue VTherm #2223. Le garde-fou parent OFF de #2219 SHALL rester intact.

#### Scenario: Adoption ON avec reparation active

- **GIVEN** un contact `on`, un VTherm en mode `heat` et `repair_incorrect_state` active
- **WHEN** l'integration adopte l'etat du contact et que la reparation devient eligible
- **THEN** VTherm ne demande ni OFF ni une nouvelle commande ON a contretemps

#### Scenario: Transition pilotee avec reparation active

- **GIVEN** un contact dont l'etat adopte est coherent avec l'etat attendu par VTherm
- **WHEN** l'integration demande une transition ON ou OFF puis que la reparation devient eligible
- **THEN** la reparation ne renverse pas cette transition et n'emet pas de commande contradictoire

#### Scenario: Adoption input_boolean avec reparation active

- **GIVEN** un sous-jacent `input_boolean` `on`, un VTherm en mode `heat` et `repair_incorrect_state` active
- **WHEN** l'integration adopte l'etat logique et que la reparation devient eligible
- **THEN** la reparation ne demande pas l'etat oppose au seul motif que la commande vient d'un `input_boolean`

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