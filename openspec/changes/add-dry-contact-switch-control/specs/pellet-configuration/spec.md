# Spec Delta

## ADDED Requirements

### Requirement: Parcours de configuration avec contact sec

L'integration SHALL permettre de selectionner `pellet_regulation` pour un VTherm `over_switch` dont le sous-jacent est un `switch` commandant un contact sec. La cible de la configuration du plugin SHALL rester le `climate` VTherm, distinct du sous-jacent. Ce parcours SHALL ne pas exiger de creer un `climate` intermediaire ni de consulter l'historique Home Assistant du contact.

#### Scenario: Thermostat avec un vrai switch

- **GIVEN** un VTherm `over_switch` configure avec un `switch` de contact sec
- **WHEN** l'utilisateur lui associe les reglages pellet
- **THEN** la cible du plugin reste le thermostat VTherm et les commandes visent le switch par VTherm
- **AND** les commandes personnalisees `set_hvac_mode` propres au parcours climate ne sont pas requises

### Requirement: Detection automatique du type de sous-jacent

Apres selection du VTherm, l'integration SHALL identifier le domaine de son sous-jacent depuis la configuration du thermostat, sans demander un choix manuel switch ou climate. Cette detection SHALL etre independante de la disponibilite instantanee du contact et reevaluee a l'ouverture des Options ou de la reconfiguration ciblees. Un climate generique ou un type non resolu SHALL ne pas etre presente comme un Duepi avec retour physique fiable.

#### Scenario: Selection du thermostat et non du poele

- **GIVEN** un VTherm climate dont la configuration designe un sous-jacent switch
- **WHEN** l'utilisateur selectionne ce VTherm
- **THEN** le parcours detecte un contact sec sans demander le type de poele
- **AND** le domaine climate du VTherm cible n'est pas confondu avec celui de son sous-jacent

#### Scenario: Switch indisponible pendant la configuration

- **GIVEN** un sous-jacent switch identifie dans la configuration du VTherm mais actuellement indisponible
- **WHEN** le formulaire de reglages est affiche
- **THEN** le type switch reste detecte et son avertissement reste visible

#### Scenario: Sous-jacent modifie depuis une precedente configuration

- **GIVEN** un VTherm dont le sous-jacent a ete remplace par un switch
- **WHEN** l'utilisateur ouvre ses Options ou sa reconfiguration pellet
- **THEN** le type courant est detecte sans reutiliser aveuglement un ancien type climate

#### Scenario: Retour physique non etabli

- **GIVEN** un climate generique ou une configuration dont le type ne peut pas etre resolu
- **WHEN** le parcours affiche les informations de configuration
- **THEN** il n'affirme pas qu'un retour d'etat physique Duepi est disponible

### Requirement: Avertissement de contact sec dans les formulaires

Pour un switch detecte, les formulaires de reglages initiaux, d'Options et de reconfiguration par thermostat SHALL afficher avant enregistrement un avertissement explicite FR/EN : aucun retour sur l'etat reel du poele, ON/OFF exprime seulement une demande, et les delais doivent couvrir allumage, chauffe utile, extinction et repos. L'avertissement SHALL accompagner les reglages de duree sans exiger une case de confirmation supplementaire.

#### Scenario: Reglages initiaux d'un contact sec

- **WHEN** le type switch est detecte apres le choix du VTherm
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

- **WHEN** les formulaires du parcours switch sont utilises en francais ou en anglais
- **THEN** l'avertissement est disponible dans la langue selectionnee avec la meme signification

### Requirement: Documentation des temporisations de contact sec

La documentation utilisateur FR/EN SHALL expliquer que le minimum de marche inclut le demarrage et la chauffe utile, et que le minimum d'arret additionne au refroidissement couvre l'extinction et le repos. Ces delais SHALL etre presentes comme comptes depuis les demandes de transition, non depuis une observation physique. Aucun reglage supplementaire de delai SHALL etre requis pour ce parcours.

#### Scenario: Reglage sans retour physique

- **WHEN** l'utilisateur consulte le parcours contact sec
- **THEN** il trouve la signification des trois durees existantes et de leur point de depart
- **AND** la documentation distingue le contact sec d'une coupure d'alimentation secteur
- **AND** elle explique que le switch ne permet ni de confirmer la flamme ni de detecter un echec d'allumage

### Requirement: Documentation de la reprise et de la responsabilite initiale

La documentation FR/EN SHALL decrire la priorite aux dates restaurees exploitables, le decompte du temps d'arret de HA et l'absence d'attente sans date exploitable pour l'etat courant. Elle SHALL expliciter la responsabilite de l'utilisateur pour les manoeuvres precedant cette initialisation et ne pas presenter les temporisations comme une garantie de surete materielle.

#### Scenario: Installation avec poele deja en service

- **WHEN** l'utilisateur consulte les regles du premier demarrage
- **THEN** il peut identifier que ON et OFF sont adoptes sans redemarrer artificiellement un delai
- **AND** il est averti qu'une manoeuvre recente hors du plugin ne peut pas etre reconstituee

#### Scenario: Simple arret puis relance

- **WHEN** l'utilisateur consulte les regles de redemarrage avec dates exploitables
- **THEN** la documentation annonce la conservation des echeances et non un nouveau delai complet