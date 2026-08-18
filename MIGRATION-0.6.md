# Migration vers PromptOps 0.6.0

PromptOps 0.6.0 normalise l'identité publique du produit sans casser les consommateurs du moteur de replay historique.

## État de publication

Cette version est **PREPARED**, pas publiée. La policy `release-policy.v1.json` lie le candidat à `v0.6.0` avec `publish_enabled=false`. La dernière release publiée et vérifiée reste `v0.5.0`, enregistrée séparément dans `published-release.v1.json`.

## Identité canonique

- Produit et dépôt : **PromptOps** / `vigilanty0x/promptops`.
- Distribution candidate : `promptops-replay`.
- Namespace Python canonique : `import promptops`.
- CLI canonique : `promptops`.

Le nom de distribution `promptops` n'est pas utilisé : il appartient déjà à un projet tiers sur l'index public Python. Le suffixe `-replay` conserve le caractère déterministe/offline du produit tout en évitant une collision de distribution.

## Compatibilité PromptBench

Le changement d'identité ne supprime aucune surface historique en 0.6 :

- l'ancienne distribution publiée `promptbench-replay` reste la référence de rollback 0.5 ;
- `import promptbench` reste disponible dans le wheel 0.6 ;
- le CLI `promptbench` reste disponible comme interface de compatibilité du moteur de benchmark/replay ;
- `promptops` et `promptbench` exposent exactement le même `__version__` ;
- les rapports, suites et artefacts 0.5 restent lisibles ;
- les neuf distributions consolidées sous `packages/` ne changent ni nom, ni CLI, ni version dans cette migration d'identité.

Nouveau code :

```python
import promptops

print(promptops.__version__)
```

Code historique toujours accepté :

```python
import promptbench

print(promptbench.__version__)
```

## Installation du candidat local

Avant publication, construire et installer uniquement depuis le SHA approuvé :

```bash
python -m pip wheel . --no-deps --wheel-dir dist
python -m venv /tmp/promptops-060
/tmp/promptops-060/bin/python -m pip install --no-deps dist/promptops_replay-0.6.0-py3-none-any.whl
/tmp/promptops-060/bin/python -m promptops --help
/tmp/promptops-060/bin/promptops --help
/tmp/promptops-060/bin/promptbench --help
```

La CI doit aussi prouver que `import promptops`, `import promptbench` et les deux CLIs rapportent la même version.

## Publication et attestations

Le candidat continue d'utiliser la matrice de 40 wheel-producing jobs : quatre versions Python pour le root et pour chacune des neuf distributions consolidées. Les wheels canoniques doivent rester reproductibles et passer la génération puis la vérification de SLSA provenance.

La présence d'artefacts attestés ne vaut pas autorisation de publication. Tant que `publish_enabled=false`, le workflow CI ne doit contenir aucun job `publish-release`, aucun `contents: write` et aucun `gh release create`.

Pour autoriser `v0.6.0`, une modification séparée et revue doit :

1. passer `release-policy.v1.json` à `publish_enabled=true` ;
2. réintroduire le publisher owner/main avec ses gates ;
3. conserver les contre-preuves, le rollback et le read-back post-publication ;
4. vérifier la release publiée avant de mettre à jour `published-release.v1.json`.

## Rollback

Rollback applicatif : revenir à la release publiée et vérifiée `v0.5.0` / distribution `promptbench-replay`.

```bash
# depuis les artefacts v0.5.0 vérifiés
python -m pip install --force-reinstall promptbench_replay-0.5.0-py3-none-any.whl
```

Aucune migration de base de données, état distant ou secret n'est introduite par 0.6. Un rollback ne nécessite donc qu'une réinstallation du wheel 0.5 vérifié et le retour aux commandes/imports historiques si nécessaire.

## Gate de suppression future

La suppression de `promptbench` ou du CLI `promptbench` n'est **pas** autorisée par cette migration. Elle nécessitera un inventaire consommateurs actualisé, une période de dépréciation explicite, des alias/redirects vérifiés, une release distincte et une décision humaine.
