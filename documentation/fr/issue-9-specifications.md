# Issue #9 - Spécifications fonctionnelles consolidées

| Métadonnée | Valeur |
| --- | --- |
| Version | 1.0, consolidation du 2026-11-05 |
| Statut | Arbitrages fonctionnels validés ; conception et conformité technique à vérifier ; développement non autorisé |
| Sources | [Issue #9](https://github.com/jmcollin78/vtherm_pellet_stove/issues/9), décisions utilisateur des 2026-11-03 et 2026-11-05 |
| Documents | [Version EN](../en/issue-9-specifications.md), [conception bilingue](../tech-docs/issue-9-design.md), [revue](../tech-docs/issue-9-review.md), [guide FR](vtherm_pellet_stove.md), [guide EN](../en/vtherm_pellet_stove.md) |

Cette version remplace les amendements et propositions historiques. Les identifiants restent stables ; les critères décrivent des vérifications à réaliser, pas des tests déjà réussis. L'autorisation porte sur les documents, pas sur l'implémentation.

## 1. Objectif et périmètre

Permettre à Pellet Stove de réguler un poêle par contact sec : poêle, contact bistable, entité HA `switch`, VTherm `over_switch`, algorithme `pellet_regulation`. Aucun thermostat générique intermédiaire n'est nécessaire.

Tout VTherm utilisé par Pellet Stove doit avoir **exactement un sous-jacent**, en contact sec comme en mode `climate`. Le contact sec est une option locale explicite, non une activation automatique déduite du domaine ou héritée d'un réglage commun.

Le suivi de l'état réel exposé, la sauvegarde/reprise, la réconciliation et les commandes en attente concernent les deux modes. En `climate`, conserver les phases de brûleur et leurs protections : le changement commun de suivi est intentionnel, pas une exigence de comportement strictement inchangé. Conserver identifiants, configuration et commandes propres au type, sauf adaptations explicitement spécifiées ici.

Exclus : plusieurs sous-jacents, `input_boolean`, impulsions et inversion matérielle présumée, retour physique inventé, nouveau délai d'allumage ou d'extinction, puissance/boost sur contact sec, modifications de VTherm, Duepi-EVO, firmware ou matériel. Une limitation d'interface externe doit être signalée, pas contournée par une garantie fictive.

## 2. Observations et temps

| Observation exploitable | Interprétation et acquittement |
| --- | --- |
| `switch.on` | Contact actif / chauffe demandée ; acquitte ON, sans preuve de flamme ou de chauffe. Au démarrage, ON déjà présent est immédiatement adopté comme allumé pour la régulation uniquement. |
| `switch.off` | Contact coupé / refroidissement présumé ; acquitte OFF et démarre les compteurs OFF/refroidissement à l'observation. |
| Brûleur `climate` en démarrage | Acquitte ON sans attendre une chauffe effective. |
| Brûleur directement en chauffe | Acquitte aussi ON sans exiger d'avoir observé le démarrage. |
| Brûleur Duepi-EVO `Cooldown` | Acquitte OFF, puis suivre le refroidissement ; ne pas attendre `Off` ni annoncer un refroidissement achevé. |
| Brûleur directement `Off` | Acquitte aussi OFF sans exiger un `Cooldown` préalable ni inventer sa durée. |
| Seul HVAC demandé `heat` / `off` | Ne prouve ni chauffe ni fin du refroidissement ; ne remplace pas l'observation de brûleur. |
| `unknown`, `unavailable`, observation absente/non classable | Pas d'état exploitable ; suspendre la régulation et les compteurs, surveiller puis réconcilier. |

`Cooldown` est le libellé fonctionnel validé. La conception doit mapper explicitement les représentations de la version cible, dont `Cooling down` dans le code local. Un retour de service n'est jamais un acquittement observé ni une preuve physique.

Conserver exclusivement les trois durées existantes, leurs unités, valeurs et bornes :

- `min_on_duration_min` : minimum d'activation avant OFF ordinaire, jamais délai d'allumage.
- `cooldown_duration_min` : durée de refroidissement présumé du contact sec ; sa fin n'est pas une preuve physique.
- `min_off_duration_min + cooldown_duration_min` : garde de prochain ON depuis l'observation OFF, en temps actif comptabilisé.

Les compteurs sont suspendus hors HA et pendant une indisponibilité. Une échéance donne une permission, pas un ordre. Les phases physiques `climate` restent des gardes distinctes ; ne pas réduire le brûleur à un relais binaire ni réinitialiser tout le cycle à chaque progression normale de phase.

## 3. Exigences

| ID | Exigence normative |
| --- | --- |
| FR-001 | Proposer le mode contact sec dans la configuration Pellet Stove propre au VTherm, à la création, dans Options et dans Reconfigurer si offert. Activation explicite, aucune conversion automatique ni propagation depuis le global. |
| FR-002 | Afficher un avertissement visible FR/EN avant confirmation du choix : ON ne prouve pas l'allumage, refroidissement seulement présumé, durées à régler selon le poêle ; un cooldown trop court peut autoriser un rallumage pendant son refroidissement. Journaux/diagnostic seuls insuffisants. |
| FR-003 | Exiger un sous-jacent unique pour tous les VTherm Pellet Stove ; en contact sec, `over_switch` et un `switch` ON/OFF. L'utilisateur confirme le contact bistable, sans détection matérielle prétendue. Refuser les configurations hors contrat sans choisir arbitrairement une entité. |
| FR-004 | Réutiliser uniquement les trois durées existantes, sans les confondre avec des temps physiques. Des durées applicables invalides n'autorisent pas ON. |
| FR-005 | Adopter l'état exploitable observé et distinguer contact actif, convention de régulation au démarrage, refroidissement présumé et phases de brûleur. Aucune transition physique ni ancienneté passée inventée. |
| FR-006 | Émettre les commandes ON/OFF justifiées sans répétition sur état stable ou simple attente. En contact sec, masquer et neutraliser puissance/boost à l'exécution, quelle que soit la source des valeurs, tout en préservant les anciennes valeurs stockées pour un retour explicite au mode `climate`. |
| FR-007 | ON exige une demande courante, toutes les gardes levées et aucun arrêt en cours. Ignorer silencieusement ON non conforme, sans alerte de refus, file, intention différée ni rejeu après arrêt/expiration. Seule une nouvelle évaluation conforme peut décider un nouveau ON. |
| FR-008 | Sauvegarder état du cycle et valeurs des compteurs par VTherm ; restaurer avant régulation. Concordance : reprendre sans crédit de l'interruption ; divergence ou sauvegarde inexploitable : adopter et initialiser les compteurs correspondants à zéro. Aucun ordre du seul fait du cycle de vie ou de la réconciliation. |
| FR-009 | En indisponibilité, Pellet Stove devient `unavailable`, attend sans limite, suspend décisions/compteurs et surveille. Suivre les manœuvres externes sans blocage permanent. Une erreur de commande explicite reste visible, sans retry automatique ; surveiller et réconcilier même si le sous-jacent évolue malgré l'erreur. |
| FR-010 | OFF explicite/sécurité est immédiatement prioritaire, même pendant minimum ON ou attente ON. Une confirmation ON tardive ne restaure pas l'ancienne intention. Distinguer priorité logique, transmission et observation ; ne pas garantir annulation d'un ON en vol ni arrêt matériel. |
| FR-011 | Exposer état observé, phase interprétée, disponibilité, compteurs, attente distincte, raison de reprise et erreur explicite. Aucun faux horodatage ni état physique garanti ; conserver l'erreur consultable sans blocage historique permanent. Refus ON normal silencieux. |
| FR-012 | Préserver identifiants, options et absence de conversion implicite des entrées existantes. Étendre explicitement le suivi/réconciliation aux `climate` en conservant phases/protections et commandes spécifiques. La contrainte d'unicité vaut aussi pour eux. |
| FR-013 | Maintenir guides et avertissement FR/EN cohérents avec ces règles. Jusqu'à implémentation validée, présenter ces comportements comme prévus, non comme disponibles dans la version actuelle. |

## 4. Règles métier

| ID | Règle normative |
| --- | --- |
| BR-001 | L'observation exploitable prime sur l'ancien état interne ; décision, appel, acquittement observé et fin de phase physique sont distincts. États stables et progressions normales ne remettent pas les compteurs du cycle à zéro. |
| BR-002 | En contact sec, prochain ON après minimum OFF plus cooldown comptabilisés depuis OFF observé, sous demande courante et autres gardes. En `climate`, conserver en plus les gardes de phases. Aucun ON différé depuis une demande rejetée. |
| BR-003 | OFF ordinaire respecte le minimum ON comptabilisé ; OFF explicite/sécurité le contourne et prime sur ON en attente. Aucun délai supplémentaire. |
| BR-004 | Appel sans observation : attente distincte, compteurs non avancés fictivement. OFF reste en attente sans expiration, alerte temporelle ou retry. Erreur explicite : visible, état conservé, pas de réémission automatique ; observation tardive permet la réconciliation sans intervention. |
| BR-005 | Option contact sec locale explicite avec avertissement, sous-jacent unique dans les deux modes, options puissance/boost masquées et inopérantes en contact sec sans destruction des valeurs, aucune activation implicite ni modification des autres règles de résolution d'options communes. |

## 5. Reprise et réconciliation

À l'arrêt HA, sauvegarder les compteurs effectués et l'état du cycle, pas seulement la configuration. Exemple : 20 minutes sauvegardées sur un minimum ON de 30 minutes laissent 10 minutes à la reprise, quelle que soit l'interruption, si l'état concorde.

| État conservé et première observation exploitable | Traitement |
| --- | --- |
| Concordants | Reprendre les compteurs sauvegardés/conservés, sans crédit du temps arrêté ou indisponible. |
| ON conservé, OFF observé | Adopter OFF ; minimum OFF et cooldown repartent de zéro à l'observation. |
| OFF conservé, ON observé | Adopter ON ; minimum ON complet depuis l'observation avant OFF ordinaire. |
| Pas de sauvegarde exploitable / première installation | Adopter le premier état exploitable et initialiser les compteurs correspondants à zéro. |
| Crash avec sauvegarde exploitable concordante | Reprendre les valeurs sauvegardées, sans reconstruire le temps non sauvegardé. |
| Sous-jacent indisponible | Pellet Stove `unavailable`, compteurs/décisions suspendus, surveillance sans limite puis même réconciliation au retour. |

Ces règles valent au démarrage, après reload, en fonctionnement et pour les deux types ; la conception précise la concordance des phases `climate`. Ne pas prétendre connaître l'instant d'une transition pendant l'interruption. Aucune extinction par défaut. OFF explicite/sécurité conserve sa priorité lorsque la commande est possible, sans prétendre livraison/exécution pendant l'indisponibilité.

Une manœuvre externe exploitable est adoptée, puis la régulation se poursuit normalement sous gardes. Ne pas commander l'inverse pour retrouver l'ancien état interne, ni exiger un acquittement manuel du seul fait de cette manœuvre. Un auteur externe n'est pas toujours identifiable.

## 6. Commandes en attente et erreurs

Après ON/OFF, conserver le dernier état observé séparément de la commande en attente. L'ancien état publié, notamment par polling, ne suffit pas à conclure à un échec ou une manœuvre externe. Les observations du §2 peuvent acquitter sans phase intermédiaire observée ; n'inventer ni étape ni durée passée.

Après OFF, attendre l'observation sans limite ni alerte liée au seul temps écoulé ; surveiller même très tard. Aucun nouveau timeout ou mécanisme de répétition ON n'est ajouté. Attente seule avec sous-jacent disponible ne signifie pas `unavailable`.

Erreur explicitement remontée sur ON/OFF : conserver l'état observé, rendre l'erreur visible et poursuivre la surveillance. L'erreur ne prouve ni transition ni absence d'effet matériel. Pas de réémission automatique, y compris via évaluations périodiques ; une observation pertinente ultérieure peut confirmer sans intervention. Conserver l'erreur consultable mais ne pas maintenir un blocage du seul fait de son historique.

OFF explicite/sécurité reçu pendant ON en attente devient immédiatement prioritaire. Un ON tardif observé est réconcilié sans lever cette priorité. À l'inverse, ON reçu pendant l'arrêt est ignoré silencieusement, sans mémoire/rejeu ; il ne modifie ni état ni compteurs. Une demande ON ignorée n'est pas conservée pour après l'arrêt.

## 7. Critères d'acceptation

Tous sont **à exécuter lors du développement**, pas des preuves d'exécution ou de comportement matériel.

| ID | Scénario et résultat attendu |
| --- | --- |
| AC-001 | Création, Options, Reconfigurer si offert : choix explicite non présélectionné, avertissement FR/EN avant validation, annulation sans effet, aucun nouveau délai et durées applicables validées. |
| AC-002 | Migration/reload sans choix : pas de conversion, IDs/options conservés ; `climate` suit les règles communes validées sans perte de ses commandes/phases spécifiques. |
| AC-003 | Contact sec admissible et demande courante : un ON ; ON observé signifie contact actif, même après attente, jamais flamme ; OFF ordinaire respecte minimum ON ; aucune puissance/boost. |
| AC-004 | OFF observé : refroidissement présumé jusqu'au cooldown comptabilisé ; prochain ON seulement après minimum OFF plus cooldown, demande courante et autres gardes ; expiration seule sans commande. |
| AC-005 | ON initial adopté pour la régulation sans date physique inventée ni nouvel ON ; compteurs selon sauvegarde concordante ou initialisation à zéro, conformément à AC-012 à AC-016. |
| AC-006 | Indisponibilité en ON/OFF/phase : disponibilité Pellet Stove alignée, compteurs suspendus, reprise automatique sans crédit du temps inconnu, selon AC-013 à AC-016. |
| AC-007 | Manœuvres externes ON/OFF : adoption sans inverse automatique ni blocage permanent, compteurs adaptés et gardes conservées ; voir AC-017/018. |
| AC-008 | Appel sans observation distinct d'une erreur explicite : ni transition ni compteur inventé, surveillance maintenue, réconciliation tardive et absence de retry ; voir AC-019 à AC-025. |
| AC-009 | OFF explicite/sécurité contourne minimum ON et attente ON ; demande prioritaire sans garantie fictive d'arrêt ; voir AC-026. |
| AC-010 | Diagnostic et guides FR/EN distinguent observation, attente, compteurs, reprise, incertitude et présomption ; aucun refus ON normal transformé en alerte. |
| AC-011 | Configuration hors contrat refusée sans choix arbitraire ; bistabilité non authentifiée depuis HA ; voir AC-030. |
| AC-012 | Arrêt/redémarrage en ON, OFF et cooldown partiels : reprendre valeurs sauvegardées, dont 20/30 minutes ON, sans crédit de l'interruption ni ON/OFF dû au seul cycle de vie ; répétitions incluses. |
| AC-013 | Indisponibilité longue, au boot ou en fonctionnement : `unavailable`, gel, aucun délai de cinq minutes, surveillance et retour automatique même tardif avant décision. |
| AC-014 | ON conservé vers OFF observé : adoption, compteurs OFF/cooldown à zéro, aucun ordre de réconciliation ni crédit passé ; demande courante et gardes pour nouveau ON. |
| AC-015 | OFF conservé vers ON observé : minimum ON complet depuis observation ; cas concordants reprennent compteurs ; OFF explicite/sécurité prioritaire. |
| AC-016 | Première installation, sauvegarde perdue/invalide, crash : première observation adoptée et compteurs à zéro, sauf sauvegarde exploitable concordante reprise sans reconstruction du temps perdu. |
| AC-017 | Manœuvres `switch` et publications stables : suivre et réguler sans acquittement utilisateur, répétition, inverse d'adoption ou remise à zéro sur état stable. |
| AC-018 | Même suivi/reprise en `climate`, avec phases/protections conservées, aucune assimilation HVAC demandé/phase physique et aucune remise à zéro générale lors d'une progression normale. |
| AC-019 | OFF Duepi-EVO, anciens états puis `Cooldown` : attendre puis acquitter à `Cooldown`, pas à `Off`, sans annoncer fin du refroidissement ; vérifier mapping version cible. |
| AC-020 | OFF sans confirmation, prolongé ou jamais confirmé : attente sans expiration, alerte temporelle, répétition ou inverse ; acquitter automatiquement une observation très tardive. |
| AC-021 | Brûleur directement `Off` : acquitter sans `Cooldown` préalable, durée passée inventée ou commande d'adoption ; conserver gardes. |
| AC-022 | Contact OFF tardif : acquitter et démarrer compteurs depuis observation, jamais appel ; OFF stable ne les réinitialise pas ; absence OFF reste en attente. |
| AC-023 | ON : contact ON ou phase de démarrage Duepi-EVO acquitte sans attendre chauffe ; retour de service/HVAC seul insuffisant, attente disponible, compteurs depuis observation et pas de répétition. |
| AC-024 | Phase de chauffe directe, même tardive : acquitter ON sans démarrage préalable, commande d'adoption, phase passée ou âge inventé ; état stable sans reset et sécurité conservée. |
| AC-025 | Erreurs ON et OFF avec sous-jacent disponible : erreur visible, observation conservée, aucun faux succès ni retry périodique ; observation tardive réconcilie sans intervention et erreur reste consultable. Tester séparément vraie indisponibilité. |
| AC-026 | OFF explicite/sécurité pendant ON en attente : priorité immédiate sans minimum ; ON tardif ne rétablit pas demande ON ; distinguer priorité, transmission et arrêt observé. Vérifier ordre des services en vol, sans supposer annulation matérielle. |
| AC-027 | ON répétés pendant arrêt ou gardes non levées : aucun ON, alerte, mémoire, rejeu ou changement d'état/compteurs dû au refus ; arrêt confirmé et garde expirée ne rejouent rien. Seule une nouvelle évaluation conforme peut décider ON, selon demande actuelle. |
| AC-028 | Deux VTherm : choix local et avertissement FR/EN ne changent que l'entrée validée ; global, migration et reload n'activent pas contact sec ailleurs. |
| AC-029 | Puissance/boost masqués et inopérants malgré anciennes valeurs/global/défauts ; sauvegarde, reload et restart préservent les valeurs ; retour explicite `climate` les rend disponibles, autre entrée `climate` inchangée sur ces fonctions. |
| AC-030 | Un seul sous-jacent dans les deux modes : zéro/plusieurs refusés sans sélection ; contact sec `over_switch` + `switch` ON/OFF et confirmation bistable utilisateur, sans conversion implicite du mode `climate`. Vérifier validation et changement ultérieur de configuration. |

## 8. Décisions et conditions de passage

| Question | Décision validée |
| --- | --- |
| Q-001 | Uniquement les trois durées existantes ; aucune durée d'allumage/extinction ajoutée. |
| Q-002 | Sauvegarde/reprise des compteurs, pause pendant interruption, attente indisponibilité sans limite et adoption/réconciliation selon concordance. |
| Q-003 | Suivre les manœuvres et états exploitables `switch` et `climate`, sans blocage permanent ni commande inverse d'adoption. |
| Q-004 | Attentes/acquittements observés, erreurs sans retry, OFF explicite/sécurité prioritaire, ON non conforme ignoré sans mémoire. Ordre technique en vol reste à démontrer. |
| Q-005 | Option locale explicite avec avertissement ; puissance/boost masqués, neutralisés et valeurs conservées ; sous-jacent unique pour les deux modes. |

D-001 : modèle fondé sur observations et durées, jamais preuve physique inventée. D-002 : option explicite avec avertissement avant validation. D-003 : durées réglées par l'utilisateur selon son appareil. Les anciennes hypothèses H-001/H-002 sont remplacées par Q-002 ; H-003 est confirmée par Q-005.

Plus d'arbitrage fonctionnel identifié à ce stade. La conception doit fournir modèle de données, mapping de phases, validation, persistance/cycle de vie, commande/dédoublonnage et diagnostic. L'ordre effectif ON/OFF externe ne doit pas être déclaré garanti sans preuve. Si les interfaces existantes ne permettent pas la priorité requise, signaler le blocage et demander un arbitrage, sans modifier les dépendances hors périmètre.

Avant développement : consolidation et audit documentaire, revue de conception et accord explicite. Avant livraison : exécuter les critères et gates techniques, vérifier intégration HA/VTherm et non-régression. Aucun test matériel ni cause prouvée du signalement d'extinction au redémarrage n'est établi dans ces documents.