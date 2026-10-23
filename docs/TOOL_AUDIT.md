# Tool audit (initial)

| Tool | Upstream | Purpose | Required verification |
|---|---|---|---|
| PyDriller | https://github.com/ishepard/pydriller | Git history | Confirm installed version and run tests |
| tsDetect CLI | https://github.com/TestSmells/TestSmellDetector | Java test smell detection | Approve JAR release and checksum; validate CSV output |
| PIT | https://pitest.org/ | Mutation testing (Experimenter) | Validate build tooling and attribution |
| Python | https://python.org | Pipeline | Freeze versions for replication |

tsDetect input CSV uses appName,pathToTestFile,pathToProductionFile. Missing production mapping is allowed but reduces detection coverage. A detected smell is a boolean observation, not a causal conclusion.

Pending team decisions: primary papers/competitor research, valid sample, DAG, mutation attribution and time horizons.
