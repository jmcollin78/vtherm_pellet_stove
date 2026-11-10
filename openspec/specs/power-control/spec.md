# power-control

## Purpose

Decrire le choix et la transmission optionnelle d'un niveau de puissance en
1.0.1. Le niveau choisi n'est pas une mesure de puissance reellement consommee.
Le choix ON/OFF appartient a la regulation, pas a la table de niveaux.

## Mapping

`delta_t = consigne - temperature`, pente en degres par heure, indices a partir
de zero et `n` nombre de niveaux, ordonnes du plus faible au plus fort.

| Intervalle de delta_t | Pente | Index calcule | Exemple avec 5 niveaux |
| --- | --- | --- | --- |
| `delta_t >= 2.0` | quelconque | `n - 1` | 4 |
| `1.0 <= delta_t < 2.0` | `< 0.3` | `max(0, n - 2)` | 3 |
| `1.0 <= delta_t < 2.0` | `>= 0.3` | `min(n - 1, n // 2 + 1)` si `n > 2`, sinon `n // 2` | 3 |
| `0.3 <= delta_t < 1.0` | `< 0.2` | `n // 2` | 2 |
| `0.3 <= delta_t < 1.0` | `>= 0.2` | `max(0, n // 2 - 1)` si `n > 2`, sinon `n // 2` | 1 |
| `-0.3 <= delta_t < 0.3` | quelconque | 0 | 0 |
| `delta_t < -0.3` | quelconque | `None` | `None` |

## Requirements

### Requirement: Pilotage optionnel pendant la chauffe

Le controleur SHALL calculer un niveau uniquement si le pilotage est active
et une liste de niveaux non vide existe. Le handler SHALL envoyer ce niveau
uniquement lorsque le controleur est en chauffe et le pilotage active.
La desactivation SHALL ne pas desactiver l'hysteresis ni les temporisations.

#### Scenario: Pilotage desactive

- **GIVEN** `power_control_enabled = false`
- **WHEN** la regulation decide ON
- **THEN** aucun niveau n'est calcule ni envoye et la decision ON reste valide

### Requirement: Validation de la liste du mapper

`PowerMapper` SHALL lever `ValueError` pour une liste vide, a sa construction
ou lors du remplacement de `power_levels`. Le controleur SHALL ne pas creer
de mapper si le pilotage est desactive ou si aucun niveau n'est fourni.
Le rejet du composant seul ne signifie donc pas que le controleur rejette
une configuration sans niveaux.

#### Scenario: Mapper sans niveau

- **WHEN** `PowerMapper` est construit avec `power_levels = []`
- **THEN** il leve `ValueError`

### Requirement: Selection par ecart et pente

Hors boost, avec une temperature disponible, le mapper SHALL suivre la table
Mapping. Une pente absente SHALL etre traitee comme zero dans cette table.
La valeur envoyee SHALL etre celle de la liste configuree a l'index choisi,
borne entre zero et le dernier index lors de sa conversion en valeur.

#### Scenario: Ecart important et pente faible

- **GIVEN** les niveaux `['1', '2', '3', '4', '5']`
- **WHEN** `delta_t = 1.5` et la pente vaut 0.1
- **THEN** l'index vaut 3 et la valeur correspondante est `'4'`

#### Scenario: Pente absente

- **GIVEN** les cinq niveaux integres et `delta_t = 1.5`
- **WHEN** la pente est absente et aucun boost n'est actif
- **THEN** le mapper choisit l'index 3, pas l'index configure par defaut 2

#### Scenario: Limite a 0.3

- **GIVEN** les cinq niveaux integres et une pente de 0.1
- **WHEN** `delta_t = 0.3`
- **THEN** le mapper choisit l'index 2 et non l'index minimum

### Requirement: Niveau de repli sans changement de la decision ON

Hors boost, si le controleur a decide ON, il SHALL utiliser `power_default_level_index`
quand la temperature est absente ou que le mapper retourne `None`.
Le resultat `None` du mapper SHALL ne pas annuler une decision ON maintenue
par l'hysteresis ou la duree minimale de marche.

#### Scenario: Marche minimale encore obligatoire

- **GIVEN** un controleur maintenu ON par la duree minimale de marche et aucun boost
- **WHEN** `delta_t < -0.3`
- **THEN** il reste ON et utilise le niveau de repli

### Requirement: Declenchement et expiration du boost

Avec le boost active, une hausse de consigne d'au moins 0.5 degre entre deux
calculs SHALL fixer `boost_until` a maintenant plus `power_boost_duration_min`.
Le premier calcul sans consigne precedente SHALL ne pas declencher de boost.
Le boost SHALL etre actif strictement avant cette echeance et utiliser le
dernier niveau si le controleur decide ON et le pilotage de puissance est actif.

#### Scenario: Hausse suffisante

- **GIVEN** une consigne precedente de 20 et une duree de boost de 15 minutes
- **WHEN** la consigne passe a 21 a T et la chauffe est autorisee
- **THEN** le niveau maximal est choisi jusqu'a T plus 15 minutes, echeance exclue

#### Scenario: Petite hausse

- **WHEN** la consigne passe de 20 a 20.3
- **THEN** aucun nouveau boost n'est declenche

#### Scenario: Premier calcul

- **GIVEN** aucune consigne precedente
- **WHEN** le premier calcul demande la chauffe
- **THEN** aucun boost n'est declenche, quel que soit l'ecart a la temperature mesuree

#### Scenario: Echeance exacte

- **GIVEN** un boost se terminant a T et les cinq niveaux integres
- **WHEN** le calcul s'execute a T avec ON, `delta_t = 0.5` et une pente nulle, sans nouvelle hausse de consigne
- **THEN** le boost est inactif et le mapper choisit l'index 2

### Requirement: Detection du boost avant les decisions d'arret

Avec le boost active, le controleur SHALL comparer les consignes avant les
priorites HVAC OFF, securite, observation physique et temporisations.
Une hausse suffisante SHALL donc pouvoir fixer une echeance meme si le
calcul reste OFF. Une chauffe autorisee avant cette echeance SHALL utiliser
le boost ; un arret ne constitue pas a lui seul une annulation de l'echeance.

#### Scenario: Hausse pendant le mode OFF

- **GIVEN** un controleur arrete, une consigne precedente de 20 et un boost de 15 minutes
- **WHEN** un calcul recoit une consigne de 21 en mode `off` a T
- **THEN** il reste arrete avec `hvac_off` et memorise une fin de boost a T plus 15 minutes
- **WHEN** un calcul en mode `heat` autorise ON a T plus 5 minutes sans nouvelle hausse
- **THEN** il choisit le niveau maximal pour le temps de boost restant

### Requirement: Boost desactive

Avec `power_boost_enabled = false`, le controleur SHALL ne pas declencher de
nouveau boost ni utiliser une echeance memorisee pour forcer le niveau maximal.
Le choix de puissance SHALL alors suivre le mapping ou le repli, si le
pilotage est actif et la decision ON.

#### Scenario: Hausse sans boost

- **GIVEN** le boost desactive, les cinq niveaux integres et une consigne precedente de 20
- **WHEN** la consigne passe a 21 avec une mesure de 19.5 et une pente nulle, et ON est autorise
- **THEN** l'index choisi vaut 3 selon le mapping, sans nouveau boost

### Requirement: Boost subordonne a la regulation

Un boost actif SHALL ne pas forcer une transition ON interdite par le mode
HVAC, la securite haute, l'observation physique ou la temporisation d'arret.

#### Scenario: Boost pendant le refroidissement logiciel

- **GIVEN** un boost actif, un delai minimal d'arret non ecoule et une observation physique explicitement non chauffante
- **WHEN** la temperature demande la chauffe
- **THEN** le controleur reste OFF avec `locked_off`, sans commande de puissance

#### Scenario: Boost avec observation physique bloquante

- **GIVEN** un boost actif, un controleur arrete et `allow_turn_on = false`
- **WHEN** la temperature demande la chauffe
- **THEN** il reste OFF avec `physical_state_not_confirmed_off`, sans commande de puissance

### Requirement: Transmission du niveau aux sous-jacents climate

Le handler SHALL traduire la valeur choisie en appel `climate.set_fan_mode`
ou `climate.set_preset_mode` selon `power_control_attribute`, avec l'identifiant
de chaque sous-jacent `climate` et la valeur correspondante. Il SHALL ne pas
repeter un index deja memorise comme applique tant que la configuration
effective du pilotage ne l'invalide pas. Cela ne prouve pas l'application materielle.

#### Scenario: Nouveau niveau fan_mode

- **GIVEN** une chauffe active, `power_control_attribute = 'fan_mode'` et un nouvel index de valeur `'3'`
- **WHEN** le handler applique la puissance
- **THEN** il demande `climate.set_fan_mode` avec `fan_mode = '3'` sur chaque sous-jacent climate
- **AND** un second controle au meme index ne repete pas cet appel

#### Scenario: Valeur changee au meme index

- **GIVEN** l'index 2 deja applique avec la valeur `'3'`
- **WHEN** une mise a jour remplace la valeur a cet index par `'high'`
- **THEN** la memorisation est invalidee et le nouveau niveau peut etre envoye

#### Scenario: Nouveau niveau preset_mode

- **GIVEN** une chauffe active, `power_control_attribute = 'preset_mode'` et un nouvel index de valeur `'high'`
- **WHEN** le handler applique la puissance
- **THEN** il demande `climate.set_preset_mode` avec `preset_mode = 'high'` sur chaque sous-jacent climate

## Observations

La desactivation du boost ne supprime pas en elle-meme l'ancienne date
`boost_until` de l'etat persiste ; le diagnostic la masque tant que le boost
n'est pas actif. `BoostManager.cancel` efface cette date, mais cette methode
n'est pas appelee dans le chemin de regulation actuel. Elle n'introduit pas
une commande utilisateur d'annulation du boost.

L'anti-spam de puissance ne garantit pas une application reelle ni une reprise
sur erreur ; ses limites restent non normatives dans
[l'observation O-04](../../observations.md).

## Traceability

- [Table et conversion des niveaux](../../../custom_components/vtherm_pellet_stove/pellet/power_mapper.py) : constructeur, setter `power_levels`, `choose_level_index`, `level_value`.
- [Boost](../../../custom_components/vtherm_pellet_stove/pellet/boost.py) : `maybe_trigger`, `is_boosting`.
- [Integration au controleur](../../../custom_components/vtherm_pellet_stove/pellet/controller.py) : `_compute_level_index` et ordre des priorites de `_compute`.
- [Transmission et invalidation](../../../custom_components/vtherm_pellet_stove/handler.py) : `_apply_power_level`, `async_update_options`.
- [Tests de mapping](../../../tests/test_power_mapper.py) : table, pente absente, bornage de valeur, deux niveaux, `test_empty_power_levels_raises`.
- [Tests du controleur](../../../tests/test_controller.py) : scenarios 8 et 9 ; l'expiration exactement a l'echeance est etablie par lecture de `is_boosting`.
- [Tests du handler](../../../tests/test_handler.py) : application de puissance, non-repetition, `test_duration_only_options_update_does_not_reapply_power_level`, `test_changed_effective_power_value_is_reapplied`.
- Le boost desactive, le declenchement pendant OFF, le premier calcul sans boost, la validation du setter de niveaux et l'envoi `preset_mode` sont etablis par lecture du code ; aucun test automatise distinct n'est revendique pour ces cas.