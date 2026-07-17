# LEGACY — structured JSON evaluation baseline

All T3 generation/comparison runs created before the prose-only migration in
Round 3 used the retired structured JSON path for S0–S3 (`generate_json` plus
`AdviseOutput`). Their pointwise, pairwise, parse, empty-core, citation, latency,
and derived aggregate values are historical evidence only.

Do not compare those values directly with prose-only T3 runs. A valid comparison
must regenerate every compared system through the prose adapter under one locked
dataset, prompt, sampling, retrieval, metric, and judge contract.

S4 extractive and unit/calibration artifacts did not necessarily call the JSON
generator, but they remain attached to the legacy baseline unless their report
explicitly states otherwise. No historical artifact is rewritten or deleted by
this notice.

Rollback point for the pre-migration code: Git tag `pre-json-removal`.
