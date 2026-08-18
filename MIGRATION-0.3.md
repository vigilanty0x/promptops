# Migration vers PromptOps 0.3.0

PromptOps 0.3.0 ajoute le routing déterministe offline et consolide le portfolio historique sans remplacer les contrats PromptBench/PromptOps introduits en 0.2.0.

## Compatibilité

- Python 3.11 et 3.12 restent supportés.
- Les commandes `promptbench` et `promptops` existantes restent disponibles.
- Les sous-commandes `scorecard`, `failures`, `regress`, `jury`, `datasets` et `release` conservent leur rôle.
- Une nouvelle sous-commande `promptops route` est ajoutée.
- Les artefacts PromptOps restent offline, JSON, versionnés et liés par SHA-256.
- Les neuf packages consolidés sous `packages/` conservent leurs distributions, CLI et versions historiques `0.1.0`; la version `0.3.0` concerne le package racine `promptbench-replay`.

## Routing

Un routing recommandé part d’un scorecard déjà produit :

```bash
promptops scorecard report.json -o scorecard.json
promptops route scorecard.json \
  --min-pass-rate 0.90 \
  --max-latency-ms 500 \
  --max-cost-microunits 10000 \
  --fallbacks 1 \
  -o route.json
```

Contraintes optionnelles :

- `--min-pass-rate` : seuil absolu entre `0` et `1` ;
- `--max-latency-ms` : latence moyenne maximale ;
- `--max-cost-microunits` : coût total maximal ;
- `--allow-candidate` : allowlist répétable de candidats ;
- `--fallbacks` : nombre de fallbacks, de `0` à `64`.

Le scorecard est vérifié avant décision. Un artefact altéré est refusé avec code `2`. Si aucun candidat ne satisfait toutes les contraintes, le résultat contient `decision=abstain` et la CLI retourne `3`. Aucun provider n’est appelé et aucune capacité absente n’est inférée.

## Portfolio consolidé

Neuf dépôts spécialisés ont été importés avec leur historique sous `packages/`. Leur CI est désormais rejouée depuis la racine sur Python 3.11 et 3.12. Les dépôts sources restent publics et non archivés, avec un avis vers leur chemin canonique dans PromptOps.

Le fichier `portfolio-compatibility.v1.json` et `scripts/check_portfolio_compat.py` gardent l’archivage fail-closed. Au moment de cette migration, `human_archive_approval=false` reste le blocage explicite de l’archivage des neuf sources.

## Codes de sortie PromptOps

- `0` : commande valide et gate vert, ou route trouvée ;
- `2` : entrée invalide, incohérente ou altérée ;
- `3` : gate de régression/release rouge ou routing en abstention.

## Ruptures intentionnelles

Aucune rupture intentionnelle de l’API PromptBench ni des commandes PromptOps 0.2 n’est introduite. `route_decision` est un nouvel artefact PromptOps utilisant `schema_version=1.0` et son propre `artifact_sha`.

## Rollback vers 0.2.0

Le package racine peut revenir à `promptbench-replay==0.2.0`. Les rapports, scorecards, regressions, jurys, manifests de datasets et failure corpora 0.2 restent indépendants du nouveau routeur. Les artefacts `route_decision` peuvent être conservés comme preuves JSON mais ne sont pas requis par 0.2.0.

Aucune migration de base de données, aucun état provider et aucun secret distant ne doivent être annulés. Les dépôts historiques restent également disponibles séparément, ce qui conserve un chemin de rollback du portfolio.
