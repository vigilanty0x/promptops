# PromptOps — compatibilité du portfolio et gate d’archivage

Date : 2026-08-18

## État

Les neuf dépôts spécialisés ont été importés avec leur historique dans `vigilanty0x/promptops`, sous `packages/`. La consolidation du code, la compatibilité de package et les avis de redirection sont vérifiés. **Cela n’autorise toujours pas à lui seul l’archivage des dépôts sources.**

Le contrat canonique est `portfolio-compatibility.v1.json`. Le checker `scripts/check_portfolio_compat.py` échoue si le manifeste dérive des `pyproject.toml`, de l’évidence d’import, des preuves de redirection ou si `archive_ready` ne correspond pas exactement aux gates explicites.

## Compatibilité conservée

Pour les neuf packages :

- le nom de distribution reste identique au nom historique du dépôt ;
- la commande CLI reste identique au nom historique ;
- la version importée reste `0.1.0` ;
- Python `>=3.11` reste le contrat de runtime ;
- les arbres importés et leurs commits sources sont consignés dans `.portfolio-rehearsal.json` ;
- la CI racine teste chaque package sur Python 3.11 et 3.12 : installation, checks, tests et wheel.

Packages : `answer-diff`, `benchmark-run-recorder`, `consensus-engine`, `eval-dataset-builder`, `llm-jury`, `model-scorecard`, `multi-agent-failure-corpus`, `prompt-package-manager`, `prompt-regression`.

## Recherche de consommateurs

Le 18 août 2026, une recherche de code GitHub a été effectuée pour chaque référence exacte `vigilanty0x/<repo-source>` dans le périmètre accessible à l’intégration GitHub connectée. Aucun match exact n’a été retourné pour les neuf dépôts.

Cette observation est **bornée**. Elle ne prouve pas l’absence de :

- dépôts privés non visibles par l’intégration ;
- clones locaux ;
- références dans des systèmes externes à GitHub ;
- dépendances via un index de packages ;
- caches, forks non indexés ou configurations hors dépôt.

Le manifeste encode donc `consumer_scan_completed=true` et `exact_reference_matches=0`, mais ne transforme pas cette observation en certitude universelle.

## Gate de redirection — VERIFIED 9/9

Les neuf dépôts sources contiennent désormais un avis en tête de `README.md` qui :

1. annonce que le développement canonique a été consolidé dans `vigilanty0x/promptops` ;
2. indique le chemin `packages/<nom>` ;
3. conserve le dépôt source et son historique ;
4. confirme que distribution et CLI `0.1.0` gardent leurs noms historiques ;
5. ne prétend pas qu’une publication PyPI ou un transfert de package a eu lieu.

Chaque avis a été livré par une PR source dédiée, a passé la CI du dépôt source, puis a été fusionné. Le manifeste enregistre pour chaque source le numéro de PR, le SHA de merge, `README.md` et `ci=success`. Le checker exige ces preuves avant d’accepter `redirect_ready=true`.

Verdict : **REDIRECT GATE VERIFIED 9/9**.

## Rollback

Le rollback ne dépend d’aucun état distant mutable : les commits sources exacts sont conservés dans le manifeste d’import.

Pour chaque package, un rollback de la consolidation consiste à :

1. identifier `source_repository` et `source_head_sha` dans `portfolio-compatibility.v1.json` ;
2. vérifier que le commit source historique est toujours accessible ;
3. restaurer le développement depuis ce commit ou depuis le dépôt source resté public ;
4. retirer ou corriger l’avis de consolidation si la localisation canonique change ;
5. ne jamais réécrire l’historique du dépôt source pour simuler un rollback.

Tant que les dépôts sources restent publics et non archivés, ce rollback est particulièrement simple.

## Gate d’archivage fail-closed

Un package n’est `archive_ready=true` que si **tous** les champs suivants sont vrais :

- `compatibility_verified` ;
- `consumer_scan_completed` ;
- `redirect_ready` ;
- `rollback_documented` ;
- `human_archive_approval`.

De plus, le checker refuse un archivage si `exact_reference_matches` est non nul.

Au moment de ce document, les quatre gates techniques sont vrais pour les neuf sources : compatibilité, scan consommateurs borné, redirection et rollback. `human_archive_approval=false` reste volontairement faux. Le verdict est donc : **ARCHIVE GATE BLOCKED — HUMAN APPROVAL REQUIRED**.

## Ce que BLOCKED signifie

`BLOCKED` ne signifie pas que la consolidation a échoué. Le code est consolidé, testé et redirigé. Cela signifie uniquement que l’action distincte d’archiver les anciens dépôts n’a pas reçu l’approbation humaine explicite requise par le contrat.
