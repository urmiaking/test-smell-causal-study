# Engineering replication protocol

Technical settings: Python 3.14.7, Git 2.55 Windows, Java 17, PyDriller 2.12, TestSmellDetector v2.2 JAR SHA256 6a12de6d1613c7ee9e845a2b69d876834f8ee98379e85d38c0e6027f7110f7bc.

Procedure completed locally:

1. Read configs/engineering-replication-a.json: fixed Java repository SHA pairs and declared purposive technical sample.
2. Run A with --max-repositories 1; observe pending=1 and checkpoint for commons-csv.
3. Run A with --resume: only remaining JUnit4 repo processed and aggregate manifest finalized.
4. Run B with a distinct output directory, fresh and without resume.
5. Validate dataset key integrity and compare all six semantic CSV files.

**Observed in both runs:** 2 repositories, 245 discovered test-file candidates, 5124 long-form smell values, 4724 measured and 400 not-applicable, 13 future test-file commit events. Commons CSV status complete_with_na; JUnit4 status partial (1 detector-crashing file).

All 6 normalized CSV outputs matched exactly. This is **one-machine process-level repetition**, not a truly independent second-machine reproduction or ground-truth scientific validity.

To replicate on a second computer: install a compatible Python and Java, verify JAR SHA256, clone original repos at pinned SHA, run into fresh run_id/output_dir, use the compare command against exported A results, document tool versions, SHA and any failures. The initial results and downloaded tool are intentionally Git-ignored, so the other team member needs access to the data via the team's approved shared storage.
