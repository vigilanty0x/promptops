# Migration vers PromptOps 0.5.0

PromptOps 0.5.0 ajoute la vérification explicite d’un bundle de release local. Le changement est additif : les commandes et artefacts 0.4 restent disponibles.

## Compatibilité

- Python 3.11 et 3.12 restent supportés.
- Les commandes `promptbench` et `promptops` existantes restent disponibles.
- `promptops verify` conserve son rôle de vérification d’un artefact individuel.
- Une nouvelle sous-commande `promptops verify-bundle` vérifie les liens entre un `release_manifest` et ses preuves locales.
- Aucun scan implicite de dossier, réseau, provider, secret distant ou migration de base de données n’est introduit.
- Les neuf packages consolidés restent indépendamment versionnés en `0.1.0`; `0.5.0` concerne le package racine `promptbench-replay`.

## Vérifier un bundle de release

```bash
promptops verify-bundle release.json \
  --artifact datasets.json \
  --artifact scorecard.json \
  --artifact regression.json
```

Les fichiers doivent être fournis explicitement. La commande accepte uniquement les artefacts de preuve qu’un release manifest peut référencer :

- `dataset_manifest` ;
- `scorecard` ;
- `regression`.

Chaque fichier est d’abord vérifié avec les mêmes garanties que `promptops verify`. Ensuite le bundle verifier exige que l’ensemble unique `(kind, artifact_sha)` fourni corresponde exactement aux références du release manifest.

## Références répétées

Un release manifest peut historiquement contenir plusieurs fois le même SHA de scorecard ou de régression. Une seule copie locale du fichier suffit pour satisfaire cette référence identique.

La multiplicité du manifest reste toutefois significative pour les compteurs de gate : si la même régression rouge est référencée deux fois, elle contribue deux fois au `failed_regression_count`, conformément au producteur de release actuel.

## Gate rouge et vérification

`verify-bundle` répond à la question « ce bundle est-il cohérent et lié aux preuves qu’il annonce ? », pas « faut-il déployer cette release ? ».

Par conséquent :

- bundle cohérent avec gate vert → code `0` ;
- bundle cohérent avec gate rouge → code `0` et `release_gate_passed=false` ;
- preuve manquante, supplémentaire, dupliquée dans les arguments, altérée, de mauvais type ou contradictoire → code `2`.

Cela permet d’auditer correctement une release rouge sans transformer une vérification d’intégrité en autorisation de déploiement.

## Contre-preuve du gate de release

La commande recompte les régressions `passed=false` parmi les preuves hash-valides et exige que le résultat corresponde à `failed_regression_count` et `regression_gate_passed`.

Un release manifest modifié puis re-hashé pour prétendre `regression_gate_passed=true` alors que la régression référencée est réellement rouge échoue donc, même si le manifest est individuellement cohérent et possède un SHA valide.

## Reçu

Un bundle valide indique notamment :

- `integrity=verified` ;
- `contract=verified` ;
- `linkage=verified` ;
- `provenance=not-verified` ;
- le nombre de références et de preuves uniques ;
- le nombre observé de régressions rouges ;
- l’état réel du gate de release.

La provenance reste explicitement non vérifiée : aucune signature ou attestation distante n’est ajoutée.

## Rollback vers 0.4.0

Un rollback applicatif consiste à réinstaller `promptbench-replay==0.4.0`. Les artefacts PromptOps ne nécessitent aucune transformation : `verify-bundle` devient simplement indisponible après rollback, tandis que `promptops verify`, routing, release et les autres opérations 0.4 restent compatibles.

Aucun état distant ou de base de données ne doit être annulé.
