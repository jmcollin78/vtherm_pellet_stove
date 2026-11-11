# Reprise de session : issue #9 et OpenSpec

## Objet

Point de reprise du 2026-11-10, avant de quitter le dev container Python pour
utiliser les outils de l'hote. Ce document remplace le contexte de conversation
qui ne sera plus accessible. **Aucune implementation n'est a reprendre.**

Projet : [jmcollin78/vtherm_pellet_stove](https://github.com/jmcollin78/vtherm_pellet_stove),
plugin de regulation pour Versatile Thermostat / Home Assistant.

## Decisions utilisateur

- L'evolution [#9](https://github.com/jmcollin78/vtherm_pellet_stove/issues/9),
  actuellement en beta test, et les extensions envisagees pour
  [#12](https://github.com/jmcollin78/vtherm_pellet_stove/issues/12) sont jugees
  trop complexes. Rechercher un fonctionnement beaucoup plus simple et
  comprehensible par un humain, pas de nouveaux mecanismes compensatoires.
- Les developpements ont ete mis en attente. Aucun choix de retry OFF n'a ete
  valide ; aucun nouvel accord de specification/conception/implementation #12
  n'a ete donne. Ne pas poursuivre l'ancien processus comme s'il etait approuve.
- Repartir de **main / release 1.0.1** pour etablir des specifications de
  reference au format OpenSpec, a partir du code, des tests et de la documentation.
  Les faits observes et les anomalies doivent rester distincts des regles voulues :
  ne pas transformer automatiquement un defaut du code en exigence normative.
- Reexaminer ensuite les demandes de #9, les decouper en petits changements
  independants, et les traiter **un par un**, sans tout melanger. Le decoupage
  exact n'est pas encore valide. Le contact sec ne doit pas servir de pretexte
  a reconduire implicitement toute la refonte des sous-jacents climate.
- Conserver l'ancienne branche et ses documents pour reference, pas les fusionner
  ou les recopier integralement dans les nouvelles specifications.

## Etat Git verifie

Etat releve dans le conteneur avant creation de ce document :

| Element                      | Valeur                                                                     |
| ---------------------------- | -------------------------------------------------------------------------- |
| Repertoire dans le conteneur | `/workspaces/vtherm_pellet_stove` ; chemin de l'hote a retrouver           |
| Branche active               | `reboot-issue-9`                                                           |
| Commit de reference          | `f6b62c10d45903f6fa3164990a790f47c7ba48db` : `Release 1.0.1`               |
| Base                         | `main` et `origin/main`, meme commit lors de la verification               |
| Creation effectuee           | `git switch --no-track -c reboot-issue-9 origin/main`, apres fetch         |
| Publication                  | Nouvelle branche locale, pas poussee, pas d'upstream configure             |
| Ancienne branche             | `9-pellet_stove-on-a-vtherm-over_switch-on-a-switch-doesnt-work`           |
| Commit ancien travail        | `a1c7e94` : `Update Issue 12 report and incident analysis`                 |
| Conservation                 | Ancienne branche locale et son suivi `origin/...` conserves                |
| Etat local preexistant       | Repertoire non suivi `custom_components/heating_simulator/`, laisse intact |

Ce nouveau document est lui aussi non suivi tant qu'aucun ajout/commit n'est
demande. Aucun commit, push, revert ou suppression de l'ancien travail n'a ete
effectue pour cette reprise. Les changements #9 ont ete mis de cote par bascule
de branche, **pas annules par un revert**.

Ne pas supprimer, nettoyer ou ecraser le simulateur. Ne pas faire de reset dur,
clean, fusion de l'ancienne branche ou commit/push sans demande explicite.

## Sources a retrouver

Sur la branche courante : code et tests de la 1.0.1, [guide FR](../../README.fr.md),
[guide EN](../../README.md), [changelog](../../CHANGELOG.md),
[configuration du projet](../../pyproject.toml), ainsi que la documentation
presente sous `documentation/` et `tech-docs/`.

Les documents suivants ont ete verifies **dans l'ancienne branche** ; ils ne
sont pas presents dans l'arbre de travail actuel :

```text
documentation/fr/issue-9-specifications.md
documentation/en/issue-9-specifications.md
documentation/tech-docs/issue-9-design.md
documentation/tech-docs/issue-9-review.md
documentation/en/issue-priority-off-dispatch.md
documentation/tech-docs/issue-12-review.md
```

Les consulter sans changer de branche ni les restaurer dans le nouvel arbre :

```bash
git show 9-pellet_stove-on-a-vtherm-over_switch-on-a-switch-doesnt-work:documentation/fr/issue-9-specifications.md
git show 9-pellet_stove-on-a-vtherm-over_switch-on-a-switch-doesnt-work:documentation/tech-docs/issue-9-design.md
git show 9-pellet_stove-on-a-vtherm-over_switch-on-a-switch-doesnt-work:documentation/tech-docs/issue-12-review.md
```

Ces sources anciennes contiennent des arbitrages et propositions desormais a
reexaminer ; leur existence ne vaut pas autorisation de les reimplementer.

## Incident #12 : conserver la distinction des preuves

Un defaut d'envoi OFF a ete identifie dans la beta : VTherm OFF, poele observe
ON, decision OFF prise, mais `pending="OFF"` memorise sans branche d'envoi
executee. Cette attente empeche ensuite une nouvelle decision OFF. La reproduction
hors ligne fournie est distincte d'un essai HA complet ou materiel ; elle n'a pas
ete reexecutee dans cette session.

Un allumage nocturne alors que VTherm etait OFF a aussi ete rapporte. **L'origine
exacte de cet allumage et la chaine causale complete ne sont pas prouvees.**
Ne pas presenter la simplification, la 1.0.1 ou la suspension comme une garantie
de surete, une correction deployee ou une autorisation de remise en service.
Ne commander aucun poele ni service HA pour reprendre ce travail documentaire.

## OpenSpec et environnement

- Aucun dossier OpenSpec n'a ete cree ; aucun `openspec init` lance ; aucune
  specification OpenSpec generee ; aucun outil installe par cette session.
- `openspec`, `node`, `npm` et `gh` sont absents du PATH du terminal du conteneur
  lors de la derniere verification. **Leur disponibilite sur l'hote est inconnue.**
- Git et l'acces a `origin` fonctionnent dans le conteneur. Cela ne garantit pas
  l'authentification Git/SSH ou GitHub CLI dans le terminal de l'hote.
- OpenSpec peut s'ajouter a un projet existant. Son initialisation cree la
  structure et les instructions de l'assistant, pas des specs retroactives fiables.
- Un binaire OpenSpec autonome est propose ; Node/npm ne sont pas requis avec ce
  mode de distribution. Verifier la documentation de la version effectivement
  utilisee, sans installer d'outillage non demande.
- L'utilisateur quitte le conteneur pour utiliser l'outillage de l'hote. Ne pas
  rouvrir automatiquement le dev container ni installer Node/npm dedans.

References officielles consultees : [projet OpenSpec](https://github.com/Fission-AI/OpenSpec),
[installation](https://openspec.dev/docs/installation),
[initialisation](https://openspec.dev/docs/setup).

## Prochaine session sur l'hote

1. Retrouver **le meme repertoire de travail**, lire ce document et verifier
   `git status --short --branch`, `git branch --show-current` et `git log -1`.
   Attendu : `reboot-issue-9`, base 1.0.1, ancien travail conserve. Ne pas cloner
   simplement la branche distante #9 : `reboot-issue-9` n'est pas publiee.
2. Verifier l'acces a ce document avant de supprimer/recreer un conteneur ou volume.
   Le chemin de l'hote peut differer ; si le workspace est dans un volume Docker,
   recuperer le travail local avant de le perdre. Ne pas supposer qu'il est pousse.
3. Verifier les outils de l'hote avec `command -v openspec node npm gh`, puis
   `openspec --version` si disponible. Determiner une installation seulement si
   necessaire et demandee, sans reprendre les suppositions faites pour le conteneur.
4. Apres confirmation utilisateur, lancer `openspec init` a la racine du depot et
   choisir GitHub Copilot. Inspecter les fichiers generes, leur perimetre et les
   commandes disponibles pour cette version. L'initialisation est documentaire,
   pas une autorisation de modifier le code de regulation.
5. Preparer les specifications de reference de la 1.0.1 dans la structure OpenSpec :
   exigences courtes, regles lisibles et scenarios concrets, avec tracabilite vers
   code/tests. Signaler les inconnues, ne pas inventer de garanties. Valider le
   perimetre et la langue des documents avant une generation etendue.
6. Faire valider cette reference, puis proposer un decoupage minimal de #9 en
   changements OpenSpec distincts. Aucune implementation, reprise automatique des
   anciens arbitrages, ni generation en bloc de toute la conception #9/#12.

La structure usuelle distingue `openspec/specs/` pour la reference et
`openspec/changes/` pour les evolutions. Il n'est pas necessaire de fabriquer un
changement implemente ou de lancer une commande apply/archive pour simplement
documenter l'existant. La methode exacte sera adaptee a la version installee.

## Message a donner au prochain assistant

> Lis documentation/tech-docs/reprise-issue-9-openspec.md. Nous sommes maintenant
> sur l'hote. Verifie le depot, la branche reboot-issue-9 et les outils disponibles.
> Nous voulons initialiser OpenSpec puis etablir les specs de reference de la
> release 1.0.1, avant de reprendre les demandes de #9 une par une en simplifiant.
> Les developpements restent suspendus. Ne restaure pas l'ancienne implementation,
> ne modifie pas le code et n'installe rien sans mon accord. Commence par les
> verifications et indique la prochaine action d'initialisation a valider.