# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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