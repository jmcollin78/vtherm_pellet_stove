# Reference OpenSpec de la release 1.0.1

## Statut et perimetre

Reference initiale extraite le 2026-11-10, **a relire et valider par l'utilisateur**.
Base : commit `f6b62c10d45903f6fa3164990a790f47c7ba48db` (`Release 1.0.1`).
L'initialisation a ete realisee sur `reboot-issue-9`, au commit
`6be927269bf5c2b195a44b946a8e5694b6f1a75a`, qui ajoute uniquement le
[document de reprise](../documentation/tech-docs/reprise-issue-9-openspec.md)
a cette base. Le manifeste annonce bien la version 1.0.1.

Ces documents decrivent le plugin present, pas les evolutions beta #9/#12.
L'ancienne branche n'a ete ni fusionnee ni restauree. Le code de regulation,
les tests et le simulateur n'ont pas ete modifies. Aucune commande n'a ete
envoyee a un poele ou a une instance Home Assistant.

## Lecture

| Specification | Contenu |
| --- | --- |
| [pellet-configuration](specs/pellet-configuration/spec.md) | Factory, entrees globale/locale, valeurs, selecteurs, mises a jour a chaud et evenement |
| [pellet-regulation](specs/pellet-regulation/spec.md) | Contrat de calcul, hysteresis, priorites d'arret et temporisations |
| [stove-control](specs/stove-control/spec.md) | Proxy VTherm, transitions, scheduler et autorisation d'allumage |
| [power-control](specs/power-control/spec.md) | Table ecart/pente, niveau de repli, boost et transmission climate |
| [runtime-state](specs/runtime-state/spec.md) | Persistance, phases, diagnostic, estimation d'energie et reset |

Lire aussi le [registre des observations et limites](observations.md) : les
ecarts documentaires, anomalies potentielles et inconnues ne sont pas des
regles a conserver par defaut.

Chaque specification relie ses exigences et scenarios aux fichiers et symboles
du code et aux tests existants. Un scenario OpenSpec est un exemple de comportement
attendu dans la reference, pas necessairement un test automatise deja implemente.

## Convention de reference

- Documents en francais, titres structurels OpenSpec et mots `SHALL` en anglais.
- Les exigences sont la formalisation proposee des regles etayees par le code,
  les tests et la documentation de la base ; elles ne valent pas approbation
  d'un nouveau comportement ni garantie de conformite materielle.
- Les faits observes mais discutables sont dans le registre separe, sans `SHALL`.
  Une anomalie ne devient pas automatiquement une exigence.
- Les contradictions des guides sont signalees, pas masquees par une copie.
- Les choix concernant contact sec, generalisation des sous-jacents, retry et
  refonte de l'etat physique restent hors perimetre et non approuves.

Les dossiers dans `specs/` sont des capacites de reference, **pas un decoupage
valide des futures demandes #9**. Aucun changement n'a ete cree sous `changes/`.
Il n'y a pas de proposition, conception, taches d'implementation ou archive
fictive pour ce travail de documentation de l'existant.

## Verification

Initialisation : OpenSpec 1.15.0, schema `spec-driven`, integration GitHub
Copilot locale, langue francaise. Les commandes et skills Copilot ont ete
generes par `openspec init`, sans installation supplementaire.

Validation de la reference :

```bash
rtk proxy openspec validate --specs --strict --no-interactive
rtk proxy openspec list --specs
```

La validation OpenSpec controle la structure des exigences et scenarios ;
elle ne prouve pas leur conformite semantique au code.

Les six fichiers de tests de la base ont ete consultes pour la tracabilite.
Sur l'hote, **52 tests de logique pure passent** avec Python 3.14.7 et pytest
9.2.0 : controleur, hysteresis, temporisations et mapping de puissance.

```bash
rtk proxy python3 -m pytest tests/test_controller.py tests/test_cycle_guard.py tests/test_hysteresis.py tests/test_power_mapper.py -q
```

La suite complete (`python3 -m pytest tests -q`) echoue a la collecte des tests
du handler et des services : `homeassistant.exceptions` et `voluptuous` ne sont
pas disponibles. Pytest signale aussi que l'option `asyncio_mode` n'est pas
reconnue. Ces tests ne sont donc pas annonces comme passes. VS Code ne les
decouvre pas et le Python du dossier `.venv` n'est pas executable sur l'hote.
Aucune dependance n'a ete installee. La CI existante utilise Python 3.14 ;
aucun essai HA complet ou essai materiel n'est revendique.

## Suite du travail

1. Relire et valider cette reference, notamment le registre des observations.
2. Reexaminer les demandes #9 et faire valider un decoupage en petits changements independants.
3. Creer et traiter un seul changement OpenSpec a la fois, apres accord sur son perimetre.

Les developpements #9/#12 restent suspendus. Cette reference n'est ni une
correction deployee, ni une garantie de surete, ni une autorisation de remise
en service du poele.