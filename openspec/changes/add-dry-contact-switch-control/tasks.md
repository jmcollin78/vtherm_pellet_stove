# Tasks

## 1. Contrat VTherm, detection et configuration

- [x] 1.1 Etendre les helpers de `tests/test_handler.py` pour representer les sous-jacents `switch` et `input_boolean` ON/OFF sans attributs climate, en conservant les fixtures Duepi ; verifier que les tests climate existants passent avec `rtk proxy python -m pytest tests/test_handler.py -q`.
- [ ] 1.2 Verifier avec la version VTherm cible l'acces a la configuration du sous-jacent et le contrat `over_switch` : commandes ON/OFF via scheduler, absence de repetition, startup ON avec parent OFF et coherence avec repair eligible. Le code 10.6.4 manque l'adoption initiale. Continuer sous l'hypothese utilisateur que VTherm #2223 initialisera en interne `_is_on_part_running` une fois au premier etat valide, avant `check_initial_state`, sans commande. Ne cocher qu'apres verification sur la version amont corrigee, avec version, commit et tests reels du contrat ; reprendre cette preuve en 5.2. Ne pas modifier le depot VTherm depuis ce changement.
- [x] 1.3 Documenter dans les guides techniques FR/EN le chemin natif de commande valide et son proprietaire OFF unique ; verifier la concordance avec le resultat de 1.2 et l'absence de promesse d'acquittement physique.
- [x] 1.4 Resoudre et classifier les sous-jacents `switch` et `input_boolean` du VTherm sans nouvelle option de type ni lecture directe du stockage interne ; verifier dans `tests/test_config_flow.py` les domaines binaires, les etats indisponibles et les types non resolus ou climate generiques sans retour Duepi affirme. Executer `rtk proxy python -m pytest tests/test_config_flow.py -q`.
- [x] 1.5 Separer selection du VTherm et reglages initiaux par thermostat pour presenter l'avertissement des sous-jacents `switch` et `input_boolean` avant enregistrement ; verifier l'absence de creation prematuree, le selecteur VTherm inchange, les doublons, les valeurs sauvegardees et la creation globale inchangee, sans choix manuel de type ni case d'acceptation obligatoire.
- [x] 1.6 Reutiliser la detection `switch`/`input_boolean` a chaque ouverture des Options et de la reconfiguration locales ; verifier le sous-jacent remplace, l'avertissement avec les durees, la conservation de la cible et du contrat de sauvegarde, ainsi que l'absence de commande ou de modification des dates a la seule ouverture du formulaire.
- [x] 1.7 Ajouter les descriptions et avertissements aux traductions FR/EN avec les mecanismes natifs de flow ; verifier les trois formulaires, le sens identique des deux langues, la mention des durees et l'absence d'avertissement contact sec pour un Duepi reconnu. Executer `rtk proxy python -m pytest tests/test_config_flow.py -q`.

## 2. Initialisation et restauration temporelle

- [x] 2.1 Identifier les parcours sous-jacents `switch` et `input_boolean` dans le handler et adopter une seule fois leur premier etat connu apres restauration de VTherm ; verifier qu'aucune date ni commande de restauration n'est inventee et que l'etat attendu par `repair` reste coherent.
- [x] 2.2 Differer l'adoption d'un sous-jacent binaire absent ou indisponible, puis l'effectuer avant un nouvel allumage automatique au premier etat connu ; verifier les etats `unknown`, `unavailable`, absent puis ON/OFF dans les tests du handler.
- [x] 2.3 Normaliser et valider les dates utiles au parcours binaire `switch`/`input_boolean` sans casser la restauration sur une date illisible ; verifier dates partielles, sans fuseau, futures et contradictoires.
- [x] 2.4 Reutiliser la date pertinente exploitable sans decalage au redemarrage, sinon laisser cette date et l'echeance nulles ; verifier `next_action_allowed_at` pour ON et OFF, interruption de HA comprise, dans les tests du handler et du controleur.
- [x] 2.5 Distinguer adoption et transition pilotee afin que la premiere vraie transition datee rearme les garde-fous normaux ; verifier les deux sens, les maintiens et plusieurs cycles sauvegarde/restauration sans nouvel allumage en double.
- [x] 2.6 Conserver le comportement de restauration climate et les formules existantes de `CycleGuard` pour les sous-jacents binaires `switch` et `input_boolean` ; verifier les scenarios de restauration et de chauffe perimee.
- [x] 2.7 Mettre a jour les sections de persistance et de diagnostic des guides techniques FR/EN ; verifier les dates restaurees, le temps hors ligne, l'echeance nulle sans date et la distinction entre adoption logique et transition.

## 3. Autorisation et commandes du contact

- [x] 3.1 Ajouter au handler l'autorisation ON fondee sur l'etat explicitement OFF d'un `switch` ou `input_boolean`, sans exiger d'attribut Duepi ; verifier OFF autorise, ON deja actif et etat non reconnu, tout en conservant les tests climate.
- [ ] 3.2 Conserver les commandes sur transition via VTherm pour `switch` et `input_boolean` ; verifier une commande par transition ON/OFF, sans repetition en maintien. Avec le contrat VTherm cible, verifier que `repair` active ne renverse pas une transition apres son delai d'activation.
- [ ] 3.3 Adapter le startup des sous-jacents `switch` et `input_boolean` sans appliquer aveuglement la correction climate ; verifier les demandes OFF uniques avec VTherm OFF et la coherence ulterieure de `repair` selon le contrat 1.2.
- [x] 3.4 Verifier l'arret manuel et la securite thermique pour les sous-jacents binaires sans attendre le minimum de marche, y compris apres adoption ON sans historique ; conserver les priorites d'arret existantes.
- [x] 3.5 Mettre a jour les README et les guides utilisateur FR/EN avec les sous-jacents binaires `switch` et `input_boolean`, leur detection, l'avertissement des trois formulaires, les durees et la responsabilite de l'utilisateur sans historique exploitable.

## 4. Inhibition de puissance propre au switch

- [x] 4.1 Inhiber localement puissance et boost pour les sous-jacents `switch` et `input_boolean`, sans modifier les reglages persistants ; conserver les tests des options globales et de leur mise a jour.
- [x] 4.2 Neutraliser au runtime binaire un ancien niveau et un ancien boost restaures sans effacer les dates ON/OFF ; conserver les echeances temporelles et ne produire aucune commande de puissance.
- [x] 4.3 Verifier l'isolation d'un thermostat binaire `switch`/`input_boolean` et d'un thermostat climate partageant les reglages globaux ; executer les tests de puissance, boost et non-repetition.
- [x] 4.4 Completer les descriptions de puissance et de diagnostic des guides utilisateur et techniques FR/EN ; indiquer l'inhibition automatique des sous-jacents binaires, sans decrire les phases comme une observation materielle.

## 5. Verification d'integration

- [x] 5.1 Executer toute la suite locale puis la commande de CI avec les dependances de test et Python 3.14 : `rtk proxy python -m pytest -qq --timeout=9 --durations=10 -n auto -o console_output_style=count -p no:sugar tests` ; verifier notamment les regressions du reset, des options et du cycle de vie des capteurs, sans modifier les tests sans rapport avec ce changement (190 passes).
- [ ] 5.2 Rejouer le contrat VTherm 1.2 pour les sous-jacents `switch` et `input_boolean` et verifier l'installation ON/OFF, la reprise des delais, l'absence de commandes de maintien et la compatibilite avec `repair_incorrect_state` active ; rapporter separement les preuves logicielles et les limites materielles.
- [x] 5.3 Valider le changement avec `rtk proxy openspec validate add-dry-contact-switch-control --strict --no-interactive` et controler la coherence entre les quatre deltas, le comportement teste et les documents FR/EN ; verifier qu'aucune modification de VTherm, du simulateur ou d'un stockage HA interne n'est necessaire.