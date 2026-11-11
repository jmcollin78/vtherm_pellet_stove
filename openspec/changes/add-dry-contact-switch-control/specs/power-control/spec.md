# Spec Delta

## MODIFIED Requirements

### Requirement: Pilotage optionnel pendant la chauffe

Pour un sous-jacent `climate`, le controleur SHALL calculer un niveau uniquement si le pilotage est active et une liste non vide existe ; le handler SHALL l'envoyer uniquement en chauffe et avec pilotage actif. Pour un sous-jacent binaire `switch` ou `input_boolean`, le pilotage SHALL rester effectivement desactive, quels que soient les reglages enregistres. La desactivation SHALL ne pas desactiver l'hysteresis ni les temporisations.

#### Scenario: Pilotage desactive

- **GIVEN** `power_control_enabled = false`
- **WHEN** la regulation decide ON
- **THEN** aucun niveau n'est calcule ni envoye et la decision ON reste valide

#### Scenario: Sous-jacent binaire avec valeurs globales activees

- **GIVEN** un sous-jacent `switch` ou `input_boolean` et `power_control_enabled = true` dans les reglages effectifs enregistres
- **WHEN** la regulation decide ON
- **THEN** aucun niveau de puissance n'est calcule ni envoye
- **AND** la decision ON, l'hysteresis et les temporisations restent operationnelles

## ADDED Requirements

### Requirement: Absence de boost de puissance sur contact sec

Pour un sous-jacent binaire `switch` ou `input_boolean`, l'integration SHALL ne pas activer de boost de puissance ni exposer un niveau courant applicable, meme si le boost est configure ou restaure. Elle SHALL ne pas envoyer de commande `climate.set_fan_mode` ou `climate.set_preset_mode` pour ce parcours. L'inhibition SHALL rester effective apres une mise a jour des options sans modifier les durees ni les dates de transition.

#### Scenario: input_boolean avec boost configure

- **GIVEN** un sous-jacent `input_boolean` et `power_boost_enabled = true`
- **WHEN** la consigne augmente suffisamment pour declencher un boost sur un climate
- **THEN** aucun boost de puissance n'est actif pour le switch et aucun niveau n'est expose comme applicable
- **AND** une hausse de consigne ne contourne pas les garde-fous ON/OFF

#### Scenario: Reprise avec ancien niveau et ancien boost

- **GIVEN** un sous-jacent `switch` ou `input_boolean` et un Store contenant un niveau et une echeance de boost
- **WHEN** le runtime est restaure
- **THEN** le diagnostic ne presente ni niveau applicable ni boost actif
- **AND** les dates ON/OFF exploitables restent disponibles pour la reprise des temporisations

#### Scenario: Options reactivees pendant la chauffe

- **GIVEN** une chauffe commandee par un sous-jacent `switch` ou `input_boolean`
- **WHEN** une mise a jour des options active la puissance et le boost
- **THEN** ces fonctions restent inhibees pour le switch sans modification de l'echeance ON/OFF

### Requirement: Conservation du pilotage de puissance climate

L'ajout des sous-jacents binaires `switch` et `input_boolean` SHALL conserver pour les sous-jacents `climate` le choix optionnel du niveau, le boost, la transmission `fan_mode` ou `preset_mode` et la non-repetition d'un niveau inchange. Leur inhibition SHALL ne pas modifier les reglages enregistres ni le comportement des thermostats climate.

#### Scenario: Deux thermostats partageant les reglages globaux

- **GIVEN** un thermostat avec un sous-jacent `switch` ou `input_boolean` et un thermostat avec climate utilisant des reglages globaux de puissance actives
- **WHEN** chacun demande la chauffe
- **THEN** le sous-jacent binaire reste sans pilotage de niveau et le climate conserve son pilotage configure
- **AND** les reglages globaux enregistres restent inchanges