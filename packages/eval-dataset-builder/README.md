# Eval Dataset Builder

Canonical synthetic evaluation datasets with deterministic splits.

Offline Python 3.11+ MVP with zero runtime dependencies, deterministic JSON evidence, bounded inputs, a CLI, synthetic tests, and fail-visible errors.

## Usage

```bash
python -m eval_dataset_builder.cli input.json
python -m unittest discover -s tests -v
python scripts/check.py
```

Input is a JSON object matching the public `run(data)` API in `eval_dataset_builder.core`. With no path, the CLI reads stdin.

Apache License 2.0.

