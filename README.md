# Prompt Regression

> [!IMPORTANT]
> Canonical development has been consolidated into [`vigilanty0x/promptops`](https://github.com/vigilanty0x/promptops), under [`packages/prompt-regression`](https://github.com/vigilanty0x/promptops/tree/main/packages/prompt-regression). This repository remains available to preserve its source history and compatibility reference. The imported `0.1.0` package keeps the `prompt-regression` distribution and CLI names. This notice does not claim a package-index transfer or publication.

Deterministic prompt-output regression detection with visible failures.

Offline Python 3.11+ MVP with zero runtime dependencies, deterministic JSON evidence, bounded inputs, a CLI, synthetic tests, and fail-visible errors.

## Usage

```bash
python -m prompt_regression.cli input.json
python -m unittest discover -s tests -v
python scripts/check.py
```

Input is a JSON object matching the public `run(data)` API in `prompt_regression.core`. With no path, the CLI reads stdin.

Apache License 2.0.

