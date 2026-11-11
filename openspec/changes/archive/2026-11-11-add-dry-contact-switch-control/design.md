# Design

## Context

La motivation est decrite dans [proposal.md](proposal.md). Les contrats vises sont les quatre deltas du repertoire `specs/` de ce changement.

Constats tires du code et des tests existants :

- `handler.py` delegue les transitions a `InterfaceCycleScheduler.start_cycle`, puis annule le cycle afin de ne pas repeter les commandes. Son observation `_physical_heating_state` filtre exclusivement les `climate` et reconnait les attributs Duepi.
- `async_added_to_hass` restaure le Store avant que VTherm ait restaure son propre mode ; `async_startup` est le point ou ce mode est disponible. La correction actuelle d'une chauffe perimee avec VTherm OFF ne consulte pas un contact.
- `PelletState` conserve deja `is_heating`, `last_on_at` et `last_off_at`. `CycleGuard` et `get_debug_attributes` calculent deja les durees et `next_action_allowed_at` depuis ces dates. Une date absente ne bloque pas le garde-fou et produit une echeance nulle.
- Le pilotage et le boost sont actives dans les valeurs integrees. Le simple filtrage des appels climate ne suffit donc pas : un switch pourrait encore afficher un niveau ou un boost sans effet.
- Les tests du handler simulent le runtime, le Store et le scheduler ; leur sous-jacent est actuellement un climate avec `burner_status`. Ils ne prouvent pas le fonctionnement d'un vrai switch via VTherm.
- Le code VTherm 10.6.4 est consultable dans le depot frere `../versatile_thermostat`; le contrat avec une version amont corrigee doit toutefois etre valide explicitement avant de declarer l'implementation compatible.
- Le formulaire initial par thermostat regroupe aujourd'hui cible et reglages, puis cree directement l'entree. Les Options et la reconfiguration affichent les reglages sans avertissement specifique ; elles doivent aussi pouvoir resoudre le sous-jacent de la cible deja enregistree.

## Goals / Non-Goals

**Goals:**

- Ajouter une branche contact sec dans le handler, en reutilisant la regulation binaire et les garde-fous existants plutot qu'une nouvelle machine d'etats physiques.
- Distinguer une adoption de l'etat du contact d'une transition commandee, afin de conserver les dates et d'eviter les commandes de restauration.
- Garder identiques le format du Store, les reglages persistants et le parcours climate, sauf adaptation locale indispensable a leur coexistence.
- Rendre les cas de premiere installation et de simple relance verifiables avec une horloge controlee.

**Non-Goals:**

- Mesurer ou garantir le demarrage, la flamme, l'extinction ou le refroidissement reels ; `igniting`, `burning` et `cooldown` restent des phases logicielles.
- Ajouter des temporisations de demarrage/extinction independantes, de la modulation periodique ou des capteurs physiques.
- Reconstituer des actions externes pendant l'arret de HA, ajouter une dependance au Recorder ou utiliser `last_changed` comme date de commande.
- Generaliser les combinaisons mixtes switch/climate ou des groupes de contacts, refondre les retries et acquittements, ou durcir tous les champs d'un Store arbitrairement corrompu.

## Decisions

### 1. Choisir le parcours depuis le sous-jacent, pas depuis une nouvelle option

Identifier les sous-jacents binaires de domaine `switch` ou `input_boolean` dans `underlying_entity_ids`, deja disponible sur le runtime VTherm. Un `switch` peut piloter une entree a contact sec physique ; un `input_boolean` represente seulement un etat logique de demande et ne fournit aucun retour physique sur le poele. Pour les formulaires, suivre le `config_entry_id` de la cible dans l'entity registry HA puis lire `underlying_entity_ids` dans les donnees de ce `ConfigEntry`, sans lecture directe du stockage interne. Classer le domaine configure sans consulter l'etat instantane du sous-jacent : un `climate` generique ne prouve pas un retour Duepi. Reutiliser cette logique dans les formulaires et le runtime lorsque necessaire. Conserver l'observation Duepi existante pour le parcours climate ; ne pas introduire une hierarchie d'adaptateurs pour ces deux cas.

La configuration du plugin continue de cibler le climate VTherm : le selecteur de `config_flow.py` n'est pas le selecteur du poele. Un climate intermediaire serait inutile et ne fournirait pas les attributs Duepi manquants.

La detection repose sur l'identifiant configure du sous-jacent, pas sur sa valeur ON/OFF ni sur la presence de son etat HA. Un sous-jacent binaire absent ou indisponible reste donc identifie par son domaine. Ne pas memoriser un type choisi par l'utilisateur ni reutiliser aveuglement un ancien type : resoudre a nouveau la configuration lors de chaque ouverture d'Options ou de reconfiguration. Si cette resolution echoue, ne pas annoncer un retour physique fiable ; le domaine climate seul ne prouve pas qu'il s'agit d'un Duepi reconnu.

Le parcours initial par thermostat devient :

```text
Choix du VTherm --> lecture du sous-jacent --> reglages --> enregistrement
                                                  |
                                                  v
                       avertissement si sous-jacent binaire switch ou input_boolean
```

Conserver temporairement la cible choisie dans le flow, puis afficher les reglages dans une seconde etape ; creer l'entree seulement apres leur validation. Ce decoupage permet d'afficher l'avertissement avant l'enregistrement, contrairement au formulaire unique actuel. Il ne change ni l'identite de l'entree, ni la prevention des doublons, ni le selecteur VTherm. La creation automatique de l'entree globale reste inchangee ; une entree globale sans cible ne doit pas etre classee arbitrairement comme Duepi.

Afficher l'avertissement dans la description traduite du formulaire de reglages switch, puis dans les formulaires d'Options et de reconfiguration de cette cible. Utiliser les mecanismes natifs de description et de placeholders des flows HA, pas une erreur de validation ni une case d'acceptation obligatoire. Les reglages de duree restent directement accessibles a cote du message.

Texte de reference pour les traductions FR/EN, de meme signification :

> Contact sec : aucun retour sur l'etat reel du poele. Le switch indique seulement une demande de marche ou d'arret. Configurez soigneusement les delais : le minimum de marche doit inclure l'allumage et la chauffe utile ; le minimum d'arret additionne au refroidissement doit couvrir l'extinction et le repos.

Pour un Duepi avec retour d'etat reconnu, ne pas afficher ce message propre au contact sec et conserver les reglages anti-court-cycle. L'avertissement informe sur la configuration ; il ne modifie ni les dates de transition ni la politique d'initialisation deja definie dans les deltas.

### 2. Initialiser le contact apres la restauration de VTherm

Conserver les etapes distinctes :

```text
Store charge --> dates restaurees --> mode VTherm restaure
                                           |
                                           v
                                contact connu ON ou OFF
                                           |
                                           v
                              adoption + echeance initiale
                                           |
                                           v
                               premiere decision normale
```

Dans la branche sous-jacent binaire, effectuer l'adoption au startup sous la serialisation de controle existante, avant la premiere decision. Si son etat n'est pas encore connu, conserver une initialisation en attente jusqu'au premier etat connu ; ne pas autoriser de nouvel ON entre-temps. Les demandes prioritaires OFF ne sont pas subordonnees a cette autorisation ON. Cette regle s'applique egalement a `input_boolean`, dont l'etat reste une demande logique et non une observation physique.

L'adoption fixe la chauffe demandee selon le contact, sans ecrire une date a maintenant. Elle n'est executee qu'une fois pour ce demarrage : ne pas resynchroniser aveuglement le controleur sur chaque lecture HA, au risque d'annuler une transition dont le retour du relais n'est pas encore arrive.

La reparation automatique de VTherm compare aussi l'etat HA du sous-jacent binaire a son propre etat attendu. Pour un `input_boolean`, le meme contrat de coherence ON/OFF doit s'appliquer, sans que son etat soit considere comme un retour physique. Dans la version VTherm 10.6.4 (commit `bdef348b579b14d306291bb89099be01d9d2bc12`), le switch conserve cet attendu dans `_is_on_part_running`, initialise a faux. Le code du `CycleScheduler` passe les transitions normales par `turn_on()` ou `turn_off()`, qui mettent a jour cet attendu apres la commande. Les tests amont `test_cycle_scheduler.py` (39 passes) et `test_repair_incorrect_state_manager.py` (1 passe) ont ete executes, mais utilisent des doubles pour les sous-jacents et ne prouvent pas cette synchronisation avec le vrai switch. `test_check_initial_state.py` passe aussi (39 passes) ; son test `UnderlyingSwitch` remplace `turn_off()` par un mock et verifie l'appel : avec VTherm OFF et le contact ON, `check_initial_state()` demande OFF, mais en mode heat avec le contact ON, il ne synchronise pas l'attendu.

Le chemin d'adoption passive ON d'un sous-jacent binaire en mode heat reste donc incompatible avec `repair_incorrect_state` : apres son delai d'activation, `_is_on_part_running` peut rester faux alors que l'entite est ON, et `check_and_repair()` commande alors OFF. Les tests existants ont ete executes dans un environnement temporaire propre avec Home Assistant 2026.11.0, Home Assistant precharge avant pytest et les plugins `pytest_homeassistant`, `pytest_asyncio` et, pour le scheduler, `pytest_freezer` explicitement charges. Ils ne constituent pas un test combine de l'adoption et de repair ; le comportement contradictoire decoule ici du code reel de ces deux classes.

Le code VTherm 10.6.4 ne fournit pas de contrat general d'adoption silencieuse. Pour poursuivre l'implementation, l'hypothese approuvee par l'utilisateur le 2026-11-10 est que VTherm fera evoluer son initialisation interne : au premier etat HA valide du switch, avant `check_initial_state()` et avant le premier controle, il initialisera `_is_on_part_running` une seule fois depuis `is_device_active`, sans emettre de commande. Le plugin ne lira ni ne modifiera ce champ prive. En mode OFF, le `check_initial_state()` existant pourra ensuite commander OFF et `turn_off()` remettra l'attendu a faux. Les etats absents, `unknown` ou `unavailable` ne seront pas adoptes ; l'initialisation attendra un etat valide. Cette hypothese est suivie par l'issue VTherm [#2223](https://github.com/jmcollin78/versatile_thermostat/issues/2223), tandis que [#2219](https://github.com/jmcollin78/versatile_thermostat/issues/2219) garde son perimetre distinct de protection parent-OFF. La tache 1.2 reste a confirmer sur une version amont contenant le changement ; la verification finale est reprise en 5.2.

La correction actuelle `is_heating=True` avec VTherm OFF reste propre au parcours climate. Pour un sous-jacent binaire `switch` ou `input_boolean`, ne pas effacer d'abord l'etat ON : cela pourrait masquer l'ouverture necessaire. Appliquer ensuite le mode VTherm avec un unique chemin de commande OFF.

### 3. Conserver en priorite la date pertinente exploitable

La date pertinente est `last_on_at` pour un sous-jacent binaire ON, `last_off_at` pour un sous-jacent binaire OFF, qu'il soit de domaine `switch` ou `input_boolean`. La presence des deux dates n'est pas requise.

Definition retenue pour les tests : une date exploitable est une date ISO interpretable, normalisee en UTC si elle n'a pas de fuseau, non future au moment de la reprise et compatible avec la derniere transition connue. Si les deux dates sont valides, la date pertinente ne doit pas preceder la date opposee. Une date opposee absente ou illisible ne suffit pas a invalider la date pertinente valide. Le contact prime pour l'etat initial ; les dates ne constituent pas une preuve de l'etat physique.

Valider les dates de la branche sous-jacent binaire avant qu'une date illisible puisse faire echouer la restauration complete. Utiliser les parseurs de dates existants ou la bibliotheque standard et une copie des donnees chargees ; ne pas modifier directement les fichiers de stockage HA. Limiter cette tolerance aux dates utiles a ce changement, sans modifier la politique generale du parcours climate.

| Etat adopte | Date exploitable | Echeance conservee |
| --- | --- | --- |
| ON | `last_on_at` | date + `min_on_duration_min` |
| OFF | `last_off_at` | date + `min_off_duration_min` + `cooldown_duration_min` |
| ON ou OFF | aucune date pertinente exploitable | date pertinente nulle, echeance nulle, delai satisfait |

Garder les dates absolues, y compris si l'echeance est passee. Le temps d'indisponibilite de HA est ainsi pris en compte sans compteur additionnel. Ne pas remplacer une date par maintenant, ni fabriquer une date antidatee pour simuler un delai satisfait.

L'hypothese est que les dates chronologiquement compatibles retracent encore les decisions utiles. Aucune mecanique ne peut detecter une manoeuvre inconnue pendant l'arret de HA ; cette limite est documentee, pas masquee par une fausse precision.

### 4. Reutiliser les garde-fous apres l'adoption

Le comportement de `CycleGuard` n'a pas besoin d'une nouvelle formule pour un sous-jacent binaire `switch` ou `input_boolean` : absence de date signifie autorisation temporelle immediate ; une transition decidee par le controleur renseigne ensuite la date normale. `next_action_allowed_at` et les phases derivent de ce meme etat.

L'adoption ON sans date permet une extinction immediate, mais ne la commande pas si l'hysteresis demande de rester ON. L'adoption OFF sans date permet un allumage uniquement si la consigne, le mode VTherm, la temperature et l'etat disponible du contact le permettent.

Apres une transition pilotee, conserver les dates lors des maintiens, publications et relances. Ne pas ajouter de declencheur periodique pour executer automatiquement une action a l'echeance : il s'agit d'une autorisation, evaluee aux appels de controle existants.

### 5. Conserver la commande native VTherm et son proprietaire unique

Pour une transition normale en mode heat, conserver `start_cycle` suivi de `cancel_cycle`. Un sous-jacent binaire `switch` ou `input_boolean` explicitement OFF peut autoriser ON ; s'il est deja ON, il n'autorise pas une seconde activation. Les etats absents, inconnus, indisponibles ou non reconnus interdisent un nouvel ON, sans pretendre observer la flamme.

Pour un arret manuel, conserver VTherm comme proprietaire de la commande OFF et ne pas ajouter un second appel de scheduler au meme changement de mode. Pour la securite thermique en mode heat, utiliser le chemin de transition deja existant. Ne pas contourner VTherm par un appel direct au service du relais.

Le test de contrat avec la version VTherm cible doit verifier trois cas precis : une transition heat active le vrai switch, une transition de regulation ouvre le switch sans cycle recurrent, et un contact ON au startup avec VTherm deja OFF recoit bien une demande OFF unique. Si ce dernier cas n'est pas assure par le cycle de vie natif, bloquer la livraison et identifier le point de commande VTherm approprie ; ne pas declarer le cas couvert par une simple correction de l'etat logiciel ou par un mock du scheduler. Toute adaptation reste soumise au contrat d'un seul proprietaire OFF et aux deltas, sans modification implicite de VTherm.

### 6. Inhiber localement puissance et boost

Conserver les options enregistrees et les regles de resolution globale/locale. Lors de la construction et de chaque mise a jour de configuration du controleur pour un sous-jacent binaire `switch` ou `input_boolean`, forcer les capacites effectives de puissance et de boost a faux. La branche `_apply_power_level` ne doit pas etre appelee pour ce parcours.

Lors d'une restauration de sous-jacent binaire `switch` ou `input_boolean`, neutraliser le niveau et le boost applicables au runtime sans effacer les dates de transition exploitables. Les diagnostics ne doivent afficher ni niveau applicable ni boost actif. Ne pas modifier les options globales, car d'autres thermostats climate peuvent les partager.

L'alternative consistant a demander seulement a l'utilisateur de decocher la puissance laisserait les valeurs par defaut et les mises a jour d'options produire des etats trompeurs ; elle est ecartee.

### 7. Etendre les tests et la documentation existants

Adapter les helpers de `tests/test_handler.py` pour representer les sous-jacents `switch` et `input_boolean` sans attributs de climate, tout en conservant les fixtures Duepi et les assertions de non-regression. Reutiliser les fichiers existants pour le handler et les calculs purs d'echeance dans `tests/test_controller.py` et `tests/test_cycle_guard.py`.

Regrouper les nouveaux tests de formulaire dans `tests/test_config_flow.py`, aucun fichier dedie a ces parcours n'existant actuellement. Verifier la selection puis les reglages sans creation prematuree d'entree, la detection des domaines `switch` et `input_boolean` meme si leur etat est indisponible, la resolution renouvelee en Options et reconfiguration, l'absence de choix manuel et de case obligatoire, les traductions FR/EN et l'absence d'avertissement contact sec pour le Duepi reconnu. Conserver les contrats de cible, de doublon et de sauvegarde des options. L'ouverture de ces formulaires et l'affichage du message ne doivent ni commander le poele ni modifier ses dates.

Tester avec des dates deterministes les seuils avant, a et apres echeance, les historiques partiels, les relances repetees, les valeurs inconnues et l'absence de nouvelle commande lors d'un maintien restaure. Tester aussi les options de puissance actives par defaut, leur mise a jour et un ancien boost persiste.

Mettre a jour les README et les guides utilisateur et techniques dans les deux langues. Expliquer la detection automatique et l'avertissement dans les formulaires, le contact sec, l'absence de feedback, les delais comptes depuis la demande et le choix assume de ne pas imposer d'attente sans date exploitable. Ne pas presenter les tests logiciels comme une certification de surete materielle.

## Risks / Trade-offs

- [Contact actif mais allumage rate] -> Limite assumee du materiel ; parler de demande de chauffe et ne pas inferer une flamme depuis ON.
- [Manoeuvre externe pendant l'arret de HA] -> Impossible a reconstituer sans retour fiable ; documenter la responsabilite de l'utilisateur et les limites des dates persistantes.
- [Retour du relais retarde] -> Adoption unique au startup ; ne pas transformer chaque lecture transitoire en nouvelle transition.
- [Contact indisponible au startup] -> Adoption differee et interdiction des nouveaux ON ; ne pas convertir l'indisponibilite en OFF.
- [Double OFF ou OFF perdu a la relance] -> Propriete unique du chemin de commande et test de contrat VTherm obligatoire, distinct des tests unitaires locaux.
- [Dates invalides ou futures] -> Repli sans date uniquement pour la date non exploitable, jamais remplacement systematique par maintenant.
- [Options de puissance communes a plusieurs thermostats] -> Inhibition locale au runtime switch, sans modification des options persistantes partagees.
- [Reparation VTherm contradictoire avec l'adoption ou une transition] -> Tester avec la fonction active et apres son delai d'activation ; ne pas contourner ses etats prives. Si aucun contrat public ne maintient la coherence, bloquer le parcours et attendre le contrat d'adoption suivi par l'issue #2223.
- [Type mal deduit depuis le climate VTherm ou un relais indisponible] -> Lire le domaine du sous-jacent configure et ne pas assimiler une resolution impossible a un retour physique Duepi.
- [Regressions du parcours climate] -> Conserver les tests Duepi, les priorites d'arret et les tests de restauration et de puissance existants.

## Migration Plan

1. Implementer le parcours binaire `switch`/`input_boolean` sans changer les identifiants d'entites ni la version du Store. Le `switch` peut piloter un contact physique ; `input_boolean` reste un etat logique sans retour physique. Les donnees existantes restent lisibles.
2. Executer les tests locaux et le test de contrat VTherm avant publication, y compris avec la reparation automatique active ; si le contrat requis manque, attendre l'evolution VTherm suivie par l'issue #2223. Une verification materielle eventuelle reste distincte et sous controle de l'utilisateur.
3. Configurer le sous-jacent binaire `switch` ou `input_boolean` dans le parcours VTherm `over_switch`, sans commandes `set_hvac_mode` pour ce parcours. Seul un `switch` peut representer une entree a contact sec physique. Garder la cible plugin sur le climate VTherm.
4. Pour revenir a une version ne supportant pas ce parcours, mettre d'abord VTherm sur OFF et laisser le poele effectuer son extinction. Ne pas compter sur cette ancienne version pour commander le switch ; conserver les dates et les donnees au lieu de les purger.