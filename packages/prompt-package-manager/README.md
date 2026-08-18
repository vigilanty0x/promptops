# Prompt Package Manager

## Purpose

Validate a bounded prompt-package declaration and execute deterministic local substitution/schema test cases.

## Non-goals

The package does not install, store, publish, fetch, or execute model prompts, plugins, arbitrary code, or remote tests.

## Install

Requires Python 3.11 or newer: `python -m pip install .`

## API

`evaluate(record)` validates lowercase name, strict SemVer, simple exact variables, prompt text, supported output schema, and 1-100 tests. Each test declares variables, exact expected rendered prompt, and sample output.

## CLI

Run `prompt-package-manager examples/valid.json`; the receipt explicitly sets `installed: false` and `stored: false`.

## Example

The synthetic `summarize` package substitutes `{text}` and checks a string output.

## Security

Attribute/index field traversal, format conversions/specifiers, undeclared placeholders, malformed braces, excessive expansion, invalid schema output, and oversized input fail closed.

## Limits

Prompts are capped at 16,384 characters, rendered prompts at 32,768, variables at 64, tests at 100, and input at 128 KiB. Schema support is intentionally small and deterministic.

## Tests

Run `python -m unittest discover -s tests -v` and `python scripts/check.py`.

## AI assistance

See `AI_ASSISTANCE.md`; package behavior and prompt safety require maintainer review.

## License

Apache-2.0; see `LICENSE`.
