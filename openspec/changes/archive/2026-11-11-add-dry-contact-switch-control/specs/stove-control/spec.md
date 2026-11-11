# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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