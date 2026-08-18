# Migration vers PromptOps 0.2.0

PromptOps 0.2.0 ajoute une couche d'exploitation déterministe au-dessus des rapports PromptBench existants. Le producteur de benchmark et les contrats de jugement ne sont pas remplacés.

## Compatibilité

- Python 3.11 et 3.12 restent supportés.
- La commande `promptbench` reste disponible sans changement de nom.
- Une nouvelle commande `promptops` est installée avec le même package.
- Les opérations PromptOps restent hors-ligne et consomment des artefacts JSON locaux vérifiés par SHA-256.

## Nouveau flux recommandé

1. Produire un rapport avec PromptBench.
2. Générer un scorecard avec `promptops scorecard`.
3. Comparer baseline/candidat avec `promptops regress` et des tolérances explicites.
4. Agréger plusieurs rapports avec `promptops jury` si nécessaire.
5. Construire le manifeste de datasets avec `promptops datasets`.
6. Conserver les échecs bornés avec `promptops failures`.
7. Produire un manifeste de release avec `promptops release`.

## Codes de sortie

- `0` : commande valide et gate vert lorsqu'un gate s'applique.
- `2` : entrée invalide, incohérente ou altérée.
- `3` : gate qualité/release rouge.

## Ruptures intentionnelles

Aucune rupture de l'API PromptBench 0.1 n'est introduite dans cette release. Les nouveaux artefacts PromptOps utilisent leur propre contrat `schema_version=1.0` et sont content-addressed.

## Rollback

Un rollback applicatif consiste à réinstaller `promptbench-replay==0.1.0`. Les rapports PromptBench 0.1 restent indépendants des artefacts PromptOps 0.2 ; aucun état distant ni migration de base de données n'est nécessaire.
