# Suite and report schemas

## Suite 1.0

A suite has a lowercase identifier, semantic version, shared limits, 1-200 scenarios, 1-20 candidates, and an exact replay matrix. Candidate and scenario identifiers must be unique. Every candidate/scenario series must contain exactly `limits.repeats` samples.

Scenarios contain difficulty (`easy`, `medium`, `hard`, or `adversarial`), input, expected value, and an explicit judge. Candidate templates contain `{input}` exactly once and may declare integer micro-unit prices per 1,000 input and output tokens.

A replay sample contains exactly one of `output` or `error`, plus bounded latency and token evidence.

## Report 1.0

Every run records candidate, model, scenario, difficulty, attempt, prompt SHA, bounded output, output SHA, error/status, judge result, diff, latency, tokens, and calculated cost. Candidate metrics preserve pass rate, pass@1, variance, mean and p95 latency, cost, tokens/run, and recovery.

The report also includes ranking, methodology, limitations, suite SHA, and a deterministic report SHA.
