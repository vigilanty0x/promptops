# Contributing

Contributions should keep comparisons reproducible and explain the methodological effect.

1. Add a failing or adversarial fixture for the intended behavior.
2. Make the smallest compatible implementation change.
3. Preserve every failed run and existing report field.
4. Run the full test suite, functional probe, demo, and wheel build.
5. Document judge false positives, false negatives, or ranking changes.

Default features must remain offline and dependency-free. A new judge must be deterministic, explicit, bounded, and independent from the producer it evaluates.
