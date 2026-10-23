# Team 7: Do Test Smells Matter? — Developer prototype

Research-oriented Java test-smell collection pipeline. **This collects observational evidence; it does NOT establish causality.** The causal analysis, PIT experiment and validity assessment belong to other team roles and require agreed research design.

## Environment

- Python 3.10+ (tested environment initially Python 3.14)
- Git
- Java 17+ (for approved tsDetect CLI JAR)
- Maven is useful for the Experimenter's PIT jobs but is not required for basic mining.

On Windows PowerShell:

    py -m venv .venv
    .\.venv\Scripts\python -m pip install -r requirements.txt
    .\.venv\Scripts\python -m team7_pipeline doctor

On Linux/macOS:

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt
    .venv/bin/python -m team7_pipeline doctor

## Safe smoke test (fixture only)

After the initial Git commit, the provided config references this very repository containing a tiny Java example. Without the detector JAR, run:

    python -m team7_pipeline run --config configs/pilot.example.json --skip-detector

The outputs are created under results/synthetic-smoke and include tests.csv, commit_events.csv, outcomes.csv, repository_status.csv, analysis_ready.csv and manifest.json. The smells.csv is **empty by design** with headers only. Zero follow-up commits for snapshot=HEAD is not evidence of zero change-proneness.

## Actual detector setup

1. Obtain the **standalone CLI JAR** from the upstream TestSmells/TestSmellDetector release. Do not confuse it with the IntelliJ plugin.
2. Record exact release URL, checksum, and Java version in docs/TOOL_AUDIT.md.
3. Place the reviewed binary at tools/TestSmellDetector.jar (ignored by Git).
4. Use a NEW run_id and output_dir in a copied config for every run.
5. Run without --skip-detector:

    python -m team7_pipeline run --config configs/real-pilot.json

The legacy v2.2 JAR accepts three CSV values per row (appName, pathToTestFile, pathToProductionFile) but NO header row. The runner runs isolated batches, preserves both successful and failed attempts, bisects crashing batches and normalizes count/boolean flags; empty values are explicitly not_applicable, never false. See docs/PILOT_RESULTS.md.

## Configuration and repository sampling

See configs/pilot.example.json. Each repository needs unique id, local path or HTTPS Git URL, snapshot_ref and followup_ref. Pin both refs to concrete, preselected Git SHAs for an actual study. Local source paths resolve relative to the config file. A downloaded repository is cached without silently fetching revisions. To avoid measurement leakage, tests and smells are measured at snapshot_ref and temporal outcomes only after it through followup_ref.

Select the study repositories based on a documented sampling protocol. Repository cloning might require network and GitHub rate controls at scale. The pipeline does not yet implement 1000-repository scheduling or persistent per-repository restart checkpoints.

## CSV contract

- tests.csv: baseline test candidates, JUnit framework heuristic, potential production associations, test LOC, approximate assert-call count and per-file detector_status.
- smells.csv: one row per returned test-smell field. smell_status distinguishes measured from not_applicable; raw values and integer counts are preserved. A missing value is not false.
- commit_events.csv: follow-up file-change events, matching recognized renames. Regex-classified messages are a potential bug-fix proxy only.
- outcomes.csv: file-level change-proneness, not class-level mutant kill counts.
- analysis_ready.csv: baseline test data joined with temporally bounded outcomes. Smell labels remain in normalized smells.csv, to be joined on repository_id + snapshot_sha + test_file.
- repository_status.csv: includes failures and partial runs; raw/JAR outputs and per-file failures are retained under raw/ per repository.
- manifest.json: environment details, resolved SHAs, tool metadata and logs.

**Research limitations:** file-level observations may contain multiple classes; failure to discover tests, rename inaccuracies, unobserved confounders, missing production-file mappings, Git message noise, observational causality, missing PIT attribution. Discuss each with Analyst and Experimenter before scaling. See docs/RESEARCH_CONTRACT.md.

## Developer tests

    python -m pytest -q

No external Java build or long real-repository trial is performed by unit tests. A real-world tsDetect run and independent replication are mandatory before completing the Team 7 project.

## Engineering pilots already executed

See docs/PILOT_RESULTS.md for pinned commits and detector anomalies. Example real command:

    python -m team7_pipeline run --config configs/junit4-pilot-002.json

Runs cannot overwrite a completed output directory; select a new run_id/output_dir for a repeat. Local results/ and data/repos/ are ignored by Git. A successful process can still have per-file errors (status=partial), and reported numbers are not causal-study findings.
