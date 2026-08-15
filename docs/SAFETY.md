# Safety

- Inputs are bounded by file size, scenario count, candidate count, repeat count, text size, output size, latency, tokens, and prices.
- The default path performs no network calls, model calls, shell execution, credential loading, or account access.
- Producers and judges are separate interfaces.
- Producer exceptions and declared errors are preserved as failed records.
- Oversized outputs are hashed but not copied into the report.
- Report integrity is verified from canonical content and an embedded SHA.
- Public examples are synthetic.

PromptBench evaluates supplied samples; it is not a security scanner, semantic oracle, or substitute for domain experts.
