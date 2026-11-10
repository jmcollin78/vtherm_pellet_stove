# Spec Delta

## MODIFIED Requirements

### Requirement: Allumage automatique conditionne par l'observation

Pour un sous-jacent `climate`, le handler SHALL autoriser une transition automatique OFF vers ON uniquement si son observation conclut explicitement a un etat non chauffant. Une observation inconnue, indisponible, contradictoire ou deja chauffante SHALL bloquer cette transition avec `physical_state_not_confirmed_off`. Pour un contact sec `switch`, l'autorisation SHALL suivre l'etat du contact decrit ci-dessous, sans exiger d'observation physique.

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

Pour un sous-jacent `switch`, l'integration SHALL autoriser un nouvel allumage automatique seulement si le contact est explicitement `off` et si les autres regles de regulation l'autorisent. Un contact absent, `unknown`, `unavailable`, dans un etat non reconnu ou deja `on` SHALL bloquer un nouvel allumage. Aucun attribut `burner_status` ou `hvac_action` SHALL etre requis.

#### Scenario: Contact arrete sans attribut de poele

- **GIVEN** un contact `off`, une demande de chauffe et des delais satisfaits
- **WHEN** le controle est execute sans attribut de retour physique
- **THEN** un allumage peut etre demande via VTherm

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

L'integration SHALL demander via VTherm l'activation ou l'ouverture du contact lors d'une transition de regulation, sans cycles marche/arret periodiques. Un maintien ou la seule restauration SHALL ne pas produire de commande supplementaire. Une transition demandee pour une raison de regulation apres restauration SHALL rester possible. Une commande de contact SHALL ne pas etre presentee comme une confirmation physique.

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

Un arret manuel de VTherm ou une securite haute SHALL demander l'ouverture du contact sans attendre le minimum de marche. Le chemin VTherm et le plugin SHALL ne pas doubler cette commande pour une meme transition. Cette regle SHALL aussi s'appliquer a un contact initialement ON sans historique exploitable. L'extinction progressive SHALL rester a la charge du poele.

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