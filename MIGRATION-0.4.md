# Migration vers PromptOps 0.4.0

PromptOps 0.4.0 ajoute la vérification générique des artefacts stockés. Le changement est additif : les contrats d’évaluation, de routing et de release de 0.3 restent disponibles.

## Compatibilité

- Python 3.11 et 3.12 restent supportés.
- Les commandes `promptbench` et `promptops` existantes restent disponibles.
- Les sous-commandes `scorecard`, `failures`, `regress`, `jury`, `datasets`, `route` et `release` conservent leur rôle.
- Une nouvelle sous-commande `promptops verify` est ajoutée.
- Aucun provider, réseau, secret distant ou état de base de données n’est requis par la vérification.
- Les neuf packages consolidés sous `packages/` conservent leurs distributions, CLI et versions historiques `0.1.0`; la version `0.4.0` concerne le package racine `promptbench-replay`.

## Vérifier un artefact stocké

```bash
promptops verify scorecard.json
promptops verify route.json --kind route_decision
```

Types supportés :

- `scorecard` ;
- `regression` ;
- `failure_corpus` ;
- `jury_consensus` ;
- `dataset_manifest` ;
- `route_decision` ;
- `release_manifest`.

La vérification recalcule d’abord `artifact_sha`, puis contrôle les invariants propres au type. Le paramètre `--kind` est optionnel et permet de verrouiller le type attendu.

Un artefact peut donc être refusé même si son auteur a recalculé un SHA valide après modification : le contenu doit aussi rester cohérent avec le contrat PromptOps. Par exemple, un `route_decision` doit être cohérent avec sa policy, ses métriques, ses raisons de rejet, son candidat sélectionné et ses fallbacks.

## Reçu de vérification

Une vérification réussie retourne notamment :

- `valid=true` ;
- `integrity=verified` ;
- `contract=verified` ;
- `provenance=not-verified`.

`provenance=not-verified` est volontaire. Une empreinte locale et un contrat cohérent ne prouvent pas l’identité de l’auteur, une signature, un environnement d’exécution de confiance ou une attestation distante.

## Compatibilité des release manifests historiques

Les `release_manifest` antérieurs à 0.3 peuvent utiliser `schema_version=1.0` sans contenir `evidence_hashes_verified`, puisque cette garantie n’existait pas encore.

PromptOps 0.4 les vérifie sans réécrire l’histoire :

- champ absent → reçu `source_evidence_integrity=not-recorded` ;
- champ présent avec `true` → `source_evidence_integrity=verified` ;
- champ présent avec `false` → artefact invalide.

L’absence historique du champ ne devient donc jamais une fausse preuve 0.3.

## Codes de sortie

Pour `promptops verify` :

- `0` : artefact valide, hash et contrat vérifiés ;
- `2` : JSON/entrée invalide, SHA incohérent, mauvais type ou contrat interne incohérent.

Les codes existants des autres commandes restent inchangés : `3` reste utilisé pour les gates rouges ou l’abstention de routing.

## Ruptures intentionnelles

Aucune rupture intentionnelle de l’API PromptBench ou des commandes PromptOps 0.3 n’est introduite. Les artefacts existants n’ont pas besoin d’être réécrits ou migrés.

## Rollback vers 0.3.0

Un rollback applicatif consiste à réinstaller `promptbench-replay==0.3.0`. Les artefacts produits en 0.4 utilisent toujours `schema_version=1.0` et restent des JSON content-addressed ; la nouvelle commande `verify` n’est simplement plus disponible après rollback.

Aucune migration de base de données, aucun provider et aucun état distant ne doivent être annulés. Les artefacts historiques restent inchangés sur disque.
