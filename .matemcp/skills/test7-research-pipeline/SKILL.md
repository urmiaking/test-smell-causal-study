# Team7 test-smell study implementation notes

When working in this repository:
- The Team7 pipeline is a Python CLI (src/team7_pipeline); experimental conclusions are NOT produced by its data collector.
- Before any edits, read docs/RESEARCH_CONTRACT.md, docs/ROADMAP.md and docs/PILOT_RESULTS.md.
- Unit of observation is baseline Java test FILE, keyed by repository_id + snapshot_sha + test_file. Do not conflate file observations with a test method or class.
- The approved checked-in configs contain immutable baseline/followup SHAs; do not substitute HEAD for a real causal study without an explicit study design.
- tsDetect CLI v2.2 from the official TestSmells release is stored locally under tools/ (binary git-ignored), SHA256 6a12de6d1613c7ee9e845a2b69d876834f8ee98379e85d38c0e6027f7110f7bc.
- This release accepts CSV input with NO header, positional argument; its output CSV sometimes contains integer counts and blank/non-applicable fields. Missing != false.
- The v2.2 detector can throw EagerTest NullPointerException for individual test files; detector_batch.py bisects failed chunks and preserves exact failing cases/logs.
- Watch for JUnit 5 compatibility and helper classes; test_framework is heuristic, not ground truth.
- Do not use project mutation score as per-test-class mutation score without defensible attribution.
- Run .venv/Scripts/python -m pytest -q on Windows (8 passing as of 2026-10-23), and verify the CLI real-world pilot if changing detector integration.
- Results and cloned repositories are intentionally Git-ignored; never commit unreviewed third-party JARs or generated raw datasets.
