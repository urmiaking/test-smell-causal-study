# Team7 research pipeline — durable engineering notes

Before editing code, read docs/ROADMAP.md, docs/RESEARCH_CONTRACT.md, docs/HANDOFF.md, docs/REPRODUCIBILITY.md and docs/PILOT_RESULTS.md.

- This is the Developer-side Python CLI; causal inference is NOT performed here.
- Unit: one baseline Java test FILE, joined with repository_id + snapshot_sha + test_file. Do not claim per-class/method causal estimates.
- Stage 8 data exchange: src/team7_pipeline/contract.py validates test, smell, temporal outcome, PIT attributed scores. PIT measurements belong to Experimenter; project-level score cannot be attributed to one file without a documented method.
- Stage 9 scaling: pipeline.py uses atomic gzip JSON checkpoint shards, fingerprinted run_state.json, --resume, --retry-failed, archived old raw evidence and aggregated CSVs. No concurrent writers; 1000-project performance remains untested.
- Stage 9 sampling: sampling.py can generate GitHub fixed-date immutable commit refs and exclusion audit using a seed. GitHub Search is biased; this is not a scientifically representative cohort.
- Stage 10: two-repository real technical pilot using configs/engineering-replication-a.json (interrupted + resumed) and b.json (fresh) produced all six identical normalized CSVs on one Windows PC. Independent *other-machine* replication still requires a team member.
- Java tsDetect standalone v2.2 from official release SHA256 6a12de6d1613c7ee9e845a2b69d876834f8ee98379e85d38c0e6027f7110f7bc; binary is locally under tools/ and ignored by Git.
- tsDetect CLI v2.2 requires CSV input without header. Output can be nonnegative counts or blank (not applicable, NEVER false). It may throw EagerTest NullPointerException for some Java files. detector_batch.py fault-isolates files and preserves failed attempts.
- JUnit5 compatibility uncertain, framework labels heuristic and must be validated manually.
- Runtime local Python 3.14, Java 17, PyDriller 2.12; tests currently 14 passed as of 2026-10-23. Run .venv/Scripts/python -m pytest -q and CLI integration checks for changes.
- Raw results and cloned repositories are intentionally Git-ignored. Preserve version numbers, commit refs, parameter config and raw evidence. Do not commit secrets, unreviewed JARs, or unapproved research conclusions.
