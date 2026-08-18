# Migration vers PromptOps 0.5.1

PromptOps 0.5.1 est un patch de cohérence de release au-dessus de 0.5.0. Les fonctionnalités applicatives de 0.5.0 restent disponibles, notamment `promptops verify-bundle`; le patch corrige surtout l’identité de version après les durcissements CI, provenance, publication et gouvernance ajoutés après le tag `v0.5.0`.

## Pourquoi 0.5.1 existe

`v0.5.0` a été publié de manière immuable avec ses wheels, checksums et provenance. Après cette publication, le dépôt a encore reçu des changements source-owned importants : vérification indépendante de la GitHub Release, preuve main-push de la provenance et sémantique de gouvernance 1.1. Laisser le package racine annoncer `0.5.0` aurait permis de reconstruire de nouveaux octets sous le même numéro de version que les octets déjà publiés.

0.5.1 évite cette collision : tout nouvel artefact racine correspondant à l’état post-0.5.0 est identifié comme `promptbench-replay==0.5.1`.

## Compatibilité

- CPython 3.11, 3.12, 3.13 et 3.14 sont couverts par le gate complet.
- Les commandes `promptbench` et `promptops` existantes restent disponibles.
- `promptops verify` conserve son rôle de vérification d’un artefact individuel.
- `promptops verify-bundle` continue de vérifier les liens entre un `release_manifest` et ses preuves locales.
- Aucun scan implicite de dossier, provider, secret distant ou migration de base de données n’est introduit.
- Les neuf packages consolidés restent indépendamment versionnés en `0.1.0`; `0.5.1` concerne uniquement le package racine `promptbench-replay`.
- `release-policy.v1.json` décrit la candidate de publication autorisée; `published-release.v1.json` décrit séparément la dernière publication immuable déjà relue et vérifiée.

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

## Publication et provenance

Le gate 0.5.1 comporte 40 jobs producteurs de wheels : quatre versions Python pour le package racine et les neuf packages consolidés. Chaque producteur réalise deux builds déterministes, vérifie leur SHA-256, installe le wheel en environnement virtuel propre et ne conserve l’artefact qu’après le smoke test.

Après ces 40 jobs, `attest-wheels` réduit les artefacts à dix wheels canoniques byte-identiques entre versions Python, produit la provenance GitHub/Sigstore SLSA et re-vérifie chacun des dix sujets avec `gh attestation verify`.

`publish-release` ne peut créer `v0.5.1` qu’après ces gates, depuis un push propriétaire vers `main`. La Release contient dix wheels, `SHA256SUMS`, le ZIP de provenance et `RELEASE-RECEIPT.json`, soit treize assets uploadés, puis le job les re-télécharge et recalcule leurs digests.

Pendant la PR de préparation 0.5.1, le workflow read-only continue de vérifier la dernière publication déjà attestée (`v0.5.0`) via `published-release.v1.json`; il ne prétend donc jamais qu’une candidate non publiée existe déjà.

## Rollback vers 0.5.0

Un rollback applicatif du patch consiste à réinstaller le wheel publié et vérifié `promptbench-replay==0.5.0` correspondant au tag immuable `v0.5.0`. Les artefacts PromptOps ne nécessitent aucune transformation.

Le rollback ne doit pas déplacer ni réécrire `v0.5.0`. Les tags/releases publiés restent immuables; une correction ultérieure reçoit un nouveau numéro de version.
