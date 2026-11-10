# Observations et limites de la reference 1.0.1

Ce registre est **non normatif**. Il distingue les faits du code, les ecarts
documentaires et les risques a examiner. Aucun point ci-dessous n'approuve
une correction, un retry OFF, une generalisation des sous-jacents ou une
reprise des developpements #9/#12. Aucun essai materiel n'a ete realise.

## O-01 : Lecture physique specifique a Duepi

**Fait de code et limite de compatibilite.** Le guide annonce plusieurs marques
exposees comme `climate`, mais `_physical_heating_state` exige un attribut
`burner_status` avec des chaines reconnues et des informations coherentes.
Le statut est lu sur les sous-jacents `climate` uniquement :

| burner_status | Mode attendu | hvac_action accepte | Observation |
| --- | --- | --- | --- |
| `Flame On` | `heat` | absent ou `heating` | chauffe |
| `Off` | `off` | absent ou `off` | non chauffant |
| `Eco idle`, `Eco Idle`, `Cooling down` | `heat` | absent ou `idle` | non chauffant |

L'absence de climate, un etat inconnu/indisponible, une autre chaine, une
incoherence ou des observations divergentes donnent une observation inconnue
et bloquent un nouvel allumage automatique. `Cooling down` est traite comme
non chauffant par ce lecteur ; cela ne prouve pas que le materiel est pret
a redemarrer. Un simple `switch` n'est pas couvert par ce chemin.

La dependance aux chaines Duepi n'est pas formalisee comme une obligation
de la future architecture. Compatibilite generique et contact sec restent
a specifier dans un changement ulterieur approuve.

Sources : [handler](../custom_components/vtherm_pellet_stove/handler.py),
`_physical_heating_state` ; [tests du handler](../tests/test_handler.py),
tests d'etat inconnu, de flamme deja presente et d'etat contradictoire.

## O-02 : Decision logicielle et livraison de la commande

**Limite et risque identifie par lecture du code, non reproduit ici.** Le
controleur modifie son etat avant `scheduler.start_cycle`. Le handler ne
restaure pas cet etat si cet appel echoue et ne possede pas de mecanisme
de confirmation physique ou de retry garanti. Un calcul suivant stable
ne constitue pas une nouvelle transition. En mode HVAC OFF, le plugin
delegue l'envoi d'arret a VTherm au lieu de demander un nouveau cycle.

La reference decrit les appels existants, pas une livraison exactement une
fois, une priorite materielle de OFF ou une convergence automatique vers
l'etat souhaite. La 1.0.1 n'est pas presentee comme une correction de
l'incident beta #12.

Sources : [handler](../custom_components/vtherm_pellet_stove/handler.py),
`_async_control_heating` ; [controleur](../custom_components/vtherm_pellet_stove/pellet/controller.py),
`calculate`, `_compute` ; [tests du handler](../tests/test_handler.py),
scenarios 13, 15 et 16.

## O-03 : Temperature ou consigne absente

**Comportement observe, politique de defaillance a confirmer.** Avec
`current = None`, l'hysteresis conserve l'etat, y compris ON. Le terme
« securitaire » dans certaines docstrings ne demontre aucune surete.
Sans temperature valide, la securite haute ne peut pas evaluer son seuil.

Avec `target = None`, le handler retourne sans calcul normal, sauf si une
mesure haute permet d'arreter un controleur deja en chauffe. Ce retour
precede aussi le traitement normal du mode HVAC OFF. La description d'un
arret prioritaire dans le controleur seul ne couvre donc pas tous les
chemins d'entree du handler.

Sources : [hysteresis](../custom_components/vtherm_pellet_stove/pellet/hysteresis.py),
`decide` ; [tests d'hysteresis](../tests/test_hysteresis.py), tests de capteur
absent ; [handler](../custom_components/vtherm_pellet_stove/handler.py),
branche `target is None` ; [tests du handler](../tests/test_handler.py),
cas sans consigne et securite haute sans consigne.

## O-04 : Anti-spam de puissance sans confirmation d'application

**Risque identifie par lecture du code, non reproduit ici.** Les appels de
puissance sont non bloquants. Leur exception est journalisee, mais l'index
est ensuite memorise comme applique, meme apres echec ou en l'absence de
cible climate. Cette memorisation n'est pas remise a zero a chaque arret
normal. Une nouvelle demande au meme index peut donc etre ignoree sans
que l'application materielle ait ete confirmee.

Ce fait ne devient pas une exigence d'ignorer les erreurs. Aucun choix de
retry n'est valide par la creation de cette reference.

Source : [handler](../custom_components/vtherm_pellet_stove/handler.py),
`_apply_power_level`, `_last_applied_level_index`, `async_update_options`.

## O-05 : Reglages sans validation de coherence globale

**Limite du formulaire.** Les selecteurs bornent individuellement les valeurs,
mais ne verifient pas `min_on_percent < max_on_percent` ou l'adequation de
l'index par defaut a la liste des niveaux. Les valeurs ON/OFF ne sont pas
necessairement 1 et 0. La description « binaire » concerne le choix entre
deux valeurs, pas une preuve d'arret materiel pour n'importe quel reglage.

**Ecart documentaire confirme.** `power_levels` est present dans les constantes
et lu par le handler, mais absent de `build_options_schema`, alors que le
guide utilisateur invite a le regler via l'interface. La reference ne propose
pas de modifier manuellement le stockage HA pour contourner cette absence.

Sources : [formulaire](../custom_components/vtherm_pellet_stove/config_flow.py),
`build_options_schema` ; [constantes](../custom_components/vtherm_pellet_stove/const.py) ;
[guide utilisateur](../documentation/fr/vtherm_pellet_stove.md), sections 5 a 7.

## O-06 : Descriptions de configuration et de controle depassees

**Ecarts documentaires confirmes.** Le guide utilisateur annonce un reload
automatique des VTherm apres Options ; le code et les tests appliquent les
valeurs aux handlers actifs sans recharger VTherm.

La documentation technique contient a la fois la regle correcte d'une entree
locale autonome et un ancien diagramme d'heritage global puis local. Elle
presente aussi un `prop_algorithm = controller`, un demarrage de cycle avec
`force or transition` et un filtrage `changed=True`, alors que le code utilise
un proxy, des commandes sur transition avec annulation de cycle et un recalcul
meme pour `changed=False`.

Sources : [guide utilisateur](../documentation/fr/vtherm_pellet_stove.md), section 5.3 ;
[documentation technique](../documentation/fr/technical_doc.md), sections 3, 6 et 7 ;
[handler](../custom_components/vtherm_pellet_stove/handler.py) ;
[tests des services](../tests/test_services.py), mises a jour locales/globales ;
[tests du handler](../tests/test_handler.py), scenarios 7, 14 et 16.

## O-07 : Pente absente et niveau de repli

**Ecart entre descriptions et implementation testee.** Certains textes
annoncent le niveau par defaut quand la pente est absente. Le mapper emploie
en realite une pente nulle ; le controleur utilise le niveau par defaut si
la temperature manque ou si le mapper retourne `None` alors que ON est maintenu.
Une valeur `None` du mapper n'est donc pas une extinction autonome.

Sources : [mapper](../custom_components/vtherm_pellet_stove/pellet/power_mapper.py),
`choose_level_index` ; [tests du mapper](../tests/test_power_mapper.py),
`test_slope_none_uses_zero` ; [controleur](../custom_components/vtherm_pellet_stove/pellet/controller.py),
`_compute_level_index` ; [documentation technique](../documentation/fr/technical_doc.md),
description de `power_default_level_index`.

## O-08 : Restauration et donnees invalides

**Limite de robustesse, non testee dans cette session.** Les dates sont relues
par `datetime.fromisoformat` sans interception locale d'une date invalide.
Le guide ne suffit donc pas a etablir une garantie de reinitialisation propre
en presence d'un stockage corrompu. Sans dates de transition, les garde-fous
correspondants autorisent l'action ; aucun nouveau delai materiel ne peut
etre deduit de l'absence d'historique.

La consigne precedente, la derniere decision complete, le cache d'application
de puissance et le repere de suivi d'energie ne font pas partie du Store.
La restauration d'etat ne signifie pas la restauration de tout le runtime.

Sources : [etat](../custom_components/vtherm_pellet_stove/pellet/state.py),
`restore_state`, `_parse_iso` ; [garde-fous](../custom_components/vtherm_pellet_stove/pellet/cycle_guard.py) ;
[guide utilisateur](../documentation/fr/vtherm_pellet_stove.md), section 9.

## O-09 : Metadonnees de version non alignees

**Ecart documentaire confirme.** Le manifeste HA vaut 1.0.1, le projet Python
vaut 0.1.0 et le changelog n'a pas de section 1.0.1. La base de cette reference
est identifiee par son commit Git et le manifeste, sans corriger ces fichiers.

Sources : [manifeste](../custom_components/vtherm_pellet_stove/manifest.json),
[projet Python](../pyproject.toml), [changelog](../CHANGELOG.md).

## O-10 : Preuves de l'incident beta distinctes de la reference

**Information issue du document de reprise, non reverifiee ici.** Le defaut
beta de decision OFF memorisee sans branche d'envoi et la reproduction hors
ligne rapportee ne sont pas des essais de la presente reference 1.0.1.
L'origine exacte de l'allumage nocturne rapporte n'est pas prouvee.
Ni ce registre ni les specs ne permettent d'affirmer une correction deployee
ou d'autoriser la remise en service.

Source : [document de reprise](../documentation/tech-docs/reprise-issue-9-openspec.md).