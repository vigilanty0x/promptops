# Benchmark Run Recorder

## Purpose

Create a deterministic record of caller-supplied benchmark configuration, finite metrics, duration, and artifact digests.

## Non-goals

The package does not run benchmarks, open artifacts, observe metrics, or verify that a digest corresponds to a file.

## Install

Requires Python 3.11 or newer: `python -m pip install .`

## API

`evaluate(record)` requires `benchmark`, object `configuration`, bounded `duration_ms`, numeric `result`, and structured `{path, sha256}` artifacts. Output says `verification: not-performed`.

## CLI

Run `benchmark-run-recorder examples/valid.json` to print the benchmark record receipt.

## Example

`examples/valid.json` is synthetic and uses placeholder artifact evidence.

## Security

Booleans, NaN, infinities, extreme metrics, malformed digests, excessive collections, and oversized input fail closed.

## Limits

At most 100 metrics and artifacts, a one-day duration, and 64 KiB input. Recorded values remain self-reported.

## Tests

Run `python -m unittest discover -s tests -v` and `python scripts/check.py`.

## AI assistance

See `AI_ASSISTANCE.md`; benchmark interpretation and release claims require human review.

## License

Apache-2.0; see `LICENSE`.
