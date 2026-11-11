# pellet-regulation

## Purpose

Decrire les decisions logicielles de regulation de la release 1.0.1.
Une decision ON/OFF et l'etat interne du controleur ne prouvent pas l'etat
physique du poele. Les commandes et observations HA sont decrites separement.

## Requirements

### Requirement: Contrat de calcul VTherm

Le controleur SHALL accepter une consigne et une temperature courante via
`calculate(target_temp, current_temp, ...)`, et retourner `max_on_percent`
lorsqu'il decide de chauffer, ou `min_on_percent` lorsqu'il decide l'arret.
`on_percent` et `calculated_on_percent` SHALL exposer la derniere valeur calculee.
Ce resultat est binaire entre deux valeurs configurees, pas un calcul TPI.

#### Scenario: Demande de chauffe

- **GIVEN** une consigne de 20 degres, une mesure de 19 degres et un allumage autorise
- **WHEN** le calcul decide ON avec `max_on_percent = 1.0`
- **THEN** le resultat et les deux proprietes valent `1.0`

#### Scenario: Arret avec minimum configure

- **GIVEN** `min_on_percent = 0.1`
- **WHEN** le controleur recoit le mode HVAC `off`
- **THEN** le resultat vaut `0.1`, et non necessairement zero

### Requirement: Hysteresis a deux seuils inclusifs

En l'absence de priorite d'arret, le controleur SHALL demander ON depuis l'etat
arrete si `current <= target - hysteresis_on`, et OFF depuis l'etat en chauffe
si `current >= target + hysteresis_off`. Il SHALL conserver l'etat courant
dans les autres cas. Les temporisations restent applicables aux transitions.

#### Scenario: Allumage a la limite basse

- **GIVEN** un controleur arrete, une consigne de 20 et `hysteresis_on = 0.5`
- **WHEN** la mesure vaut 19.5 et les autorisations d'allumage sont reunies
- **THEN** il decide ON avec la raison `below_on_threshold`

#### Scenario: Extinction a la limite haute

- **GIVEN** un controleur en chauffe, une consigne de 20 et `hysteresis_off = 0.3`
- **WHEN** la mesure atteint 20.3 et la duree minimale de marche est ecoulee
- **THEN** il decide OFF avec la raison `above_off_threshold`

#### Scenario: Maintien dans la bande

- **GIVEN** une consigne de 20 et des hysteresis de 0.5 et 0.3
- **WHEN** la mesure vaut 20
- **THEN** l'etat courant est conserve avec la raison `hold_in_band`

### Requirement: Rejet des hysteresis negatives

`HysteresisDecider` SHALL lever `ValueError` si un seuil negatif est fourni
a sa construction ou affecte a l'une de ses proprietes. Cette validation
du composant Python complete les bornes individuelles du formulaire.

#### Scenario: Seuil negatif a la construction

- **WHEN** `hysteresis_on` ou `hysteresis_off` vaut -0.1 lors de la creation du decideur
- **THEN** la construction leve `ValueError`

### Requirement: Duree minimale de marche

Le controleur SHALL retarder une extinction par hysteresis tant que
`min_on_duration_min` n'est pas ecoulee depuis `last_on_at`.
Il SHALL conserver ON avec la raison `locked_on`. A l'egalite, l'extinction
SHALL etre autorisee. En l'absence de date d'allumage, ce garde-fou ne bloque pas.

#### Scenario: Extinction retardee

- **GIVEN** une duree minimale de marche de 30 minutes et un allumage il y a 15 minutes
- **WHEN** le seuil d'extinction par hysteresis est atteint
- **THEN** le controleur maintient ON avec la raison `locked_on`

#### Scenario: Duree minimale atteinte

- **GIVEN** une duree minimale de marche de 30 minutes
- **WHEN** le seuil d'extinction est atteint exactement 30 minutes apres l'allumage
- **THEN** la temporisation autorise OFF

### Requirement: Duree minimale d'arret et refroidissement

Le controleur SHALL retarder un rallumage jusqu'a ce que la somme
`min_off_duration_min + cooldown_duration_min` soit ecoulee depuis `last_off_at`.
Il SHALL conserver OFF avec la raison `locked_off` avant cette echeance.
A l'egalite, ce garde-fou SHALL autoriser l'allumage. Sans date d'arret, il ne bloque pas.

#### Scenario: Somme des delais

- **GIVEN** un minimum d'arret de 20 minutes et un refroidissement de 5 minutes
- **WHEN** une demande ON survient 24 minutes apres l'arret
- **THEN** le controleur reste OFF avec la raison `locked_off`
- **WHEN** le calcul est refait a 25 minutes, avec les autres autorisations reunies
- **THEN** le controleur peut decider ON

### Requirement: Temps restants exposes par les garde-fous

Les methodes `seconds_until_can_turn_on` et `seconds_until_can_turn_off`
SHALL exposer les secondes restantes avant leur echeance respective,
bornees a zero. Sans date correspondante, elles SHALL retourner zero.
Ces methodes auxiliaires ne programment pas d'action et ne sont pas appelees
par la boucle de controle du handler.

#### Scenario: Une minute avant le rallumage autorise

- **GIVEN** un minimum d'arret de 20 minutes et un refroidissement de 5 minutes
- **WHEN** `seconds_until_can_turn_on` est appelee 24 minutes apres l'arret
- **THEN** elle retourne 60 secondes

#### Scenario: Extinction deja autorisee

- **GIVEN** un minimum de marche de 30 minutes
- **WHEN** `seconds_until_can_turn_off` est appelee 30 minutes ou plus apres l'allumage
- **THEN** elle retourne zero

### Requirement: Priorites d'arret logiciel

Le controleur SHALL traiter le mode HVAC `off` avant la securite de temperature,
puis traiter `current >= safety_room_temp` avant l'hysteresis et les garde-fous.
Ces deux arrets SHALL outrepasser la duree minimale de marche et retourner
`min_on_percent`, avec respectivement `hvac_off` et `safety` comme raison.
Une transition depuis ON SHALL enregistrer `last_off_at`.

#### Scenario: Arret VTherm pendant la duree minimale de marche

- **GIVEN** un controleur en chauffe depuis 5 minutes et un minimum de marche de 60 minutes
- **WHEN** le mode HVAC devient `off`, quelle que soit la casse de cette chaine
- **THEN** il decide OFF avec la raison `hvac_off` sans attendre 60 minutes

#### Scenario: Limite haute atteinte

- **GIVEN** un controleur en chauffe depuis 5 minutes, un minimum de 60 minutes et une securite a 26 degres
- **WHEN** la temperature atteint 26 degres en mode `heat`
- **THEN** il decide OFF avec la raison `safety` sans attendre le minimum de marche

#### Scenario: Limite haute alors que le controleur est deja arrete

- **GIVEN** un controleur arrete et une date d'arret eventuelle
- **WHEN** le calcul recoit une temperature de 26 pour une securite a 26 en mode `heat`
- **THEN** il reste arrete avec la raison `safety` sans modifier `last_off_at`

#### Scenario: Mode OFF et limite haute simultanes

- **WHEN** le calcul recoit le mode `off` et une temperature atteignant la securite
- **THEN** la raison est `hvac_off`, pas `safety`

### Requirement: Autorisation physique d'allumage

Lors d'une demande de transition OFF vers ON, le controleur SHALL rester OFF
si `allow_turn_on` est faux et exposer `physical_state_not_confirmed_off`.
Cette autorisation est fournie par le handler ; sa valeur par defaut dans
l'API du controleur seul est vraie. Ce refus SHALL etre evalue avant la
temporisation d'arret ; les priorites HVAC OFF et securite restent anterieures.

#### Scenario: Allumage non autorise par le handler

- **GIVEN** un controleur arrete et une temperature sous le seuil d'allumage
- **WHEN** `allow_turn_on = false`
- **THEN** il retourne `min_on_percent` sans enregistrer un nouvel allumage

#### Scenario: Observation physique et temporisation bloquantes

- **GIVEN** une demande d'allumage, une temporisation d'arret non ecoulee et `allow_turn_on = false`
- **WHEN** le calcul s'execute sans priorite HVAC OFF ni securite
- **THEN** la raison est `physical_state_not_confirmed_off`, pas `locked_off`

### Requirement: Horodatage des transitions logicielles

Le controleur SHALL mettre a jour `last_on_at` uniquement lors d'une transition
interne OFF vers ON, et `last_off_at` lors d'une transition interne ON vers OFF.
Un calcul de maintien SHALL conserver ces dates.

#### Scenario: Calculs repetes pendant la chauffe

- **GIVEN** une transition ON a l'instant T
- **WHEN** un nouveau calcul maintient ON a T plus une minute
- **THEN** `last_on_at` reste T

## Observations

Avec `current_temp = None`, le decideur conserve l'etat courant, y compris
ON, avec `hold_in_band` ; la securite haute ne peut pas evaluer son seuil.
Ce comportement est teste par `test_no_sensor_heating_holds_on` et
`test_no_sensor_not_heating_holds_off`, mais reste une politique de defaillance
a confirmer, pas une exigence de surete : voir [O-03](../../observations.md).

Le controleur distingue uniquement la chaine `off`, apres conversion en
chaine et en minuscules. Les autres modes empruntent le chemin de regulation
normal ; cela ne specifie pas une prise en charge fonctionnelle de `cool`,
`auto` ou d'un mode inconnu.

## Traceability

- [Controleur et priorites](../../../custom_components/vtherm_pellet_stove/pellet/controller.py) : `calculate`, `_compute`.
- [Hysteresis](../../../custom_components/vtherm_pellet_stove/pellet/hysteresis.py) : `HysteresisDecider`, `decide` et validation des proprietes.
- [Temporisations](../../../custom_components/vtherm_pellet_stove/pellet/cycle_guard.py) : `can_turn_on`, `can_turn_off`, `seconds_until_can_turn_on`, `seconds_until_can_turn_off`.
- [Tests du controleur](../../../tests/test_controller.py) : scenarios 1 a 6, `test_on_percent_and_calculated_on_percent_alias`, `test_calculate_positional_args_compat`.
- [Tests d'hysteresis](../../../tests/test_hysteresis.py) : seuils inclusifs, maintien, mesure absente et rejet des seuils negatifs a la construction.
- [Tests des durees](../../../tests/test_cycle_guard.py) : cas avant, a et apres les limites, absence d'historique, temps restants bornes a zero.
- L'ordre entre observation physique et temporisation, la priorite simultanee HVAC OFF/securite et la validation des setters sont etablis par lecture du code, sans test automatise distinct revendique.
- Les scenarios ci-dessus decrivent la reference ; leur presence n'affirme pas qu'un test automatise distinct existe pour chacun.