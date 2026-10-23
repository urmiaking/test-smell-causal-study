# Team 7 — Developer pipeline

Developer-side collector for **Do Test Smells Matter? A Causal Study**. It collects observational evidence at pinned Java Git snapshots; it does not estimate causal effects or run PIT.

## Setup

Requires Python 3.10+, Git, Java 17+. On Windows:

    .\setup.ps1
    .\.venv\Scripts\python.exe -m team7_pipeline doctor
    .\.venv\Scripts\python.exe -m pytest -q

On Linux/macOS: run bash setup.sh and .venv/bin/python -m pytest -q.

Obtain trusted standalone tsDetect JAR v2.2 from https://github.com/TestSmells/TestSmellDetector/releases/tag/v2.2 and put it at tools/TestSmellDetector.jar. Verify its SHA256 in docs/TOOL_AUDIT.md. The binary is not committed.

## Collection

Fresh runs need unique run_id and output_dir. Demonstrated with pinned configs in configs/:

    python -m team7_pipeline run --config configs/engineering-replication-a.json --max-repositories 1
    python -m team7_pipeline run --config configs/engineering-replication-a.json --resume

An interrupted run contains run_state.json and checksummed per-repository checkpoint shards. Resume refuses changed configuration or detector SHA; it skips completed shards. To retry only failed repositories:

    python -m team7_pipeline run --config configs/engineering-replication-a.json --resume --retry-failed

Old failure checkpoints and raw logs are archived. Use a **new** config/output for a wholly new attempt. Single-writer, sequential collector; 1000-repository performance not yet benchmarked. --skip-detector explicitly produces missing smell data, never false smell values.

## Audited GitHub discovery

    python -m team7_pipeline sample --query "topic:testing" --count 10 --baseline-date 2025-01-01 --followup-date 2025-07-01 --seed 7 --max-candidates 50 --max-pages 2 --output configs/my-sample.json

Creates pinned commit refs plus a sampling-audit.json of candidate decisions. Search-result ranking, API rate limits and public-only visibility bias the cohort. Do not call a discovered set an approved scientific sample. Set GITHUB_TOKEN in the environment if necessary.

## Validation and repeatability

    python -m team7_pipeline validate --results results/engineering-replication-a
    python -m team7_pipeline compare --left results/engineering-replication-a --right results/engineering-replication-b

For Experimenter-supplied **test-file-attributable** PIT results:

    python -m team7_pipeline validate --results results/engineering-replication-a --pit experiments/pit-results.csv --export results/joined.csv

See contracts/pit-results.example.csv and docs/HANDOFF.md. Project-level mutation scores must not be assigned to individual tests.

## Run artifacts

Inside results/RUN_ID/: tests.csv, smells.csv (including missing/not applicable flags), commit_events.csv, outcomes.csv, analysis_ready.csv, repository_status.csv, raw detector batch logs, run_state.json, .checkpoints, and final manifest.json. Results and cloned repositories are excluded from Git. The baseline join key is repository_id + snapshot_sha + test_file.

A successful run is **not a validated causal study**. JUnit5 compatibility, manual smell validation, scientific sampling, PIT outcome attribution, DAG/confounders and cross-machine independent replication remain team responsibilities. See docs/PILOT_RESULTS.md and docs/RESEARCH_CONTRACT.md.
