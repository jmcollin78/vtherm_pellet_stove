# Proposal

## Why

Un poele pilote par contact sec peut etre represente uniquement par un `switch`, sans retour de flamme ni d'extinction effective. Le plugin bloque aujourd'hui son allumage car l'observation attend exclusivement un `climate` avec des attributs Duepi ; il faut permettre ce pilotage tout en conservant les protections temporelles et une reprise transparente apres redemarrage.

## What Changes

- Ajouter le parcours VTherm `over_switch` avec un sous-jacent `switch` commandant une entree a contact sec : ON demande l'allumage, OFF demande l'extinction geree par le poele.
- Detecter automatiquement le type de sous-jacent depuis la configuration du VTherm, sans choix manuel switch/climate. Apres selection du thermostat, afficher avec les reglages de duree un avertissement explicite FR/EN pour le switch, egalement dans les Options et la reconfiguration ciblees, sans case de confirmation obligatoire.
- Adopter l'etat connu du contact comme etat logiciel initial, sans le presenter comme une observation physique. Un etat absent, inconnu ou indisponible interdit un nouvel allumage automatique.
- Reutiliser en priorite les dates restaurees exploitables pour calculer la prochaine transition autorisee ; le temps d'arret de Home Assistant compte dans le delai restant.
- Sans date exploitable pour l'etat courant, considerer son delai deja satisfait : un contact ON peut etre eteint immediatement, un contact OFF peut etre allume immediatement, sous reserve des autres regles de regulation.
- Conserver apres les transitions pilotees l'hysteresis, le minimum de marche et le delai d'arret additionne au refroidissement. Ne pas introduire de cycles periodiques, de commande de restauration ni de temporisation supplementaire.
- Desactiver effectivement les niveaux de puissance et le boost de puissance pour le parcours contact sec, meme avec les valeurs globales activees par defaut ; conserver le parcours `climate` existant.
- Documenter en francais et en anglais les delais comptes depuis les demandes, l'absence de retour physique et la responsabilite de l'utilisateur lors d'une initialisation sans historique exploitable.

## Capabilities

### New Capabilities

Aucune : les comportements relevent des capacites existantes.

### Modified Capabilities

- `pellet-configuration` : parcours contact sec, detection automatique, avertissement dans les formulaires, cible VTherm inchangee et documentation des hypotheses d'initialisation.
- `stove-control` : autorisation d'allumage adaptee au contact et maintien des commandes sur transition via VTherm.
- `runtime-state` : adoption de l'etat du contact, priorite aux dates restaurees et echeances de diagnostic sans attente artificielle.
- `power-control` : inhibition effective du pilotage et du boost de puissance sur un sous-jacent `switch`.

## Impact

- Adaptations futures principalement dans le handler, avec reutilisation de `PelletState`, `CycleGuard` et des diagnostics du controleur ; tests dans les fichiers existants du handler, du controleur et des garde-fous.
- Adapter aussi `config_flow.py` et les traductions FR/EN pour separer selection du VTherm et reglages avertis, puis reutiliser la detection dans les Options et la reconfiguration. Couvrir ces parcours par des tests de flow ; aucun choix manuel de type n'est ajoute.
- Guides utilisateur et techniques FR/EN et README a mettre a jour lors de l'implementation. Aucune modification du code ni des specs principales dans cette proposition.
- Pas de dependance supplementaire, de consultation du Recorder, de nouveau service ni de changement du selecteur ciblant le `climate` VTherm.
- Hors perimetre : coupure secteur, retour physique ajoute, nouveaux niveaux de puissance, ensembles de sous-jacents mixtes et reconstitution des manoeuvres pendant l'indisponibilite de HA.
- Le chemin effectif du scheduler VTherm vers un vrai `switch` devra etre verifie lors de l'implementation : les sources VTherm ne sont pas presentes dans ce workspace. Les tests logiciels ne constituent pas une validation materielle du poele.