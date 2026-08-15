# Multi-Agent Failure Corpus

## Purpose

Create minimized, allowlisted failure-corpus entries with bounded reproduction steps and fail-closed secret/identifier detection.

## Non-goals

The package does not guarantee anonymity, discover every secret, retain arbitrary metadata, or safely process raw production incident exports without prior review.

## Install

Requires Python 3.11 or newer: `python -m pip install .`

## API

`evaluate(record)` accepts exactly `scenario_id`, allowlisted `category`, `reproduction`, and `expected_failure`. It never returns the original record. Any redaction makes the receipt `failed`; only records with zero detected sensitive patterns can pass.

## CLI

Run `multi-agent-failure-corpus examples/valid.json` to print a sanitized entry receipt.

## Example

The example is synthetic and contains no personal or production data.

## Security

Patterns cover private keys, AWS session/access keys, Slack and Stripe tokens, JWTs, common code-host/API tokens, bearer credentials, generic secret assignments, high-entropy tokens, email addresses, and IPv4-looking identifiers. Detected values are removed from sanitized failure output and extra fields fail closed.

## Limits

Pattern redaction can miss novel, encoded, or contextual identifiers and is explicitly not an anonymity guarantee. Inputs are capped at 64 KiB and 50 steps.

## Tests

Run `python -m unittest discover -s tests -v` and `python scripts/check.py`.

## AI assistance

See `AI_ASSISTANCE.md`; a human must review sanitized data before publication.

## License

Apache-2.0; see `LICENSE`.
