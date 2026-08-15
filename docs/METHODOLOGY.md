# Methodology and limits

Replay removes provider/network variance and makes comparisons exactly repeatable. It does not claim that a hosted model still produces the recorded output. Dataset authors must version scenario or replay changes and avoid tuning only to known benchmark wording.

Rule-based judges are transparent but narrow. Exact matching can penalize a correct paraphrase; contains matching can reward irrelevant text; JSON equality checks structure but not whether the requested reasoning was sound. Use several representative scenarios and human review for consequential conclusions.

Price and token fields are evidence supplied by the suite. PromptBench calculates them consistently but does not independently meter a provider. Latency describes recorded samples, not current service latency.

Always retain failures, examine variance and recovery, and treat ranking as one decision input rather than universal model quality.
