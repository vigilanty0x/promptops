# PromptOps — compatibilité du portfolio et gate d’archivage

Date : 2026-08-18

## État

Les neuf dépôts spécialisés ont été importés avec leur historique dans `vigilanty0x/promptops`, sous `packages/`. La consolidation du code est vérifiée, mais **elle n’autorise pas à elle seule l’archivage des dépôts sources**.

Le contrat canonique est `portfolio-compatibility.v1.json`. Le checker `scripts/check_portfolio_compat.py` échoue si le manifeste dérive des `pyproject.toml`, de l’évidence d’import ou si `archive_ready` ne correspond pas exactement aux gates explicites.

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

## Gate de redirection

`redirect_ready` reste faux tant que le dépôt source ne contient pas une indication explicite vers la nouvelle localisation canonique dans PromptOps. Une redirection acceptable doit au minimum :

1. annoncer que le développement canonique a été consolidé dans `vigilanty0x/promptops` ;
2. indiquer le chemin `packages/<nom>` ;
3. conserver l’historique et ne pas supprimer le dépôt source ;
4. ne pas prétendre qu’une publication PyPI ou un transfert de package a eu lieu si ce n’est pas prouvé.

L’ajout d’un avis de consolidation est réversible et doit précéder toute décision d’archivage.

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

Au moment de ce document, `redirect_ready=false` et `human_archive_approval=false` pour les neuf sources. Le verdict est donc volontairement : **ARCHIVE GATE BLOCKED**.

## Ce que BLOCKED signifie

`BLOCKED` ne signifie pas que la consolidation a échoué. Le code est consolidé et testé. Cela signifie uniquement que l’action distincte et potentiellement perturbatrice d’archiver les anciens dépôts n’a pas encore toutes ses preuves.
