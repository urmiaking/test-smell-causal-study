# Engineering integration results (not causal evidence)

**Recorded 2026-10-23.** These are functionality checks for the collection software. They do NOT answer the study hypotheses and are not a statistically representative sample.

## TestSmells tsDetect
- Standalone JAR: TestSmellDetector v2.2 from https://github.com/TestSmells/TestSmellDetector/releases/tag/v2.2
- SHA256: 6a12de6d1613c7ee9e845a2b69d876834f8ee98379e85d38c0e6027f7110f7bc
- Java runtime: Oracle Java 17.0.12 (Windows)
- Observed CLI: positional input CSV **without header**. Passing a header triggered FileNotFoundException(pathToTestFile).
- Observed output: counts encoded as integers (not only 0 and 1); some smell columns were blank/not applicable. Never convert blanks to false.
- Known defect: EagerTest throws NullPointerException on src/test/java/org/junit/experimental/categories/CategoryTest.java in the tested JUnit 4 snapshot. Batch bisection isolates failures; no result is fabricated for this file.

## Local synthetic test
- Git checkout contained the small Java fixture shipped in this project.
- Results from results/synthetic-smoke-v3: 1 detected test file, 21 smell values; no follow-up time (HEAD=HEAD), **not an empirical observation**.

## Apache Commons CSV (compatibility caution)
- Source: https://github.com/apache/commons-csv
- Baseline SHA: 2dc0d8900677a9750ec4a59d5506a9ad0fe1fd02
- Follow-up SHA: 584a79a034aea8037ed6751acc39a0ea5918befc
- First technical pilot (before handling missing values): 44 Java files in src/test, 822 parsed binary flags, 3 test-file events.
- **Do not use these counts to infer prevalence.** JUnit Jupiter/JUnit 5 and test helper files may not be supported/classified as intended by this older JAR. Re-run with strict discovery and missing-value handling before any interpretation.

## JUnit 4 fault-tolerant pilot
- Source: https://github.com/junit-team/junit4
- Baseline SHA: 354b72771d70255a860001c6b11786897c1c2fbd
- Follow-up SHA: 890f3c972647de378f25e7271d8fbbd9d3456b79
- Raw run: results/junit4-pilot-002 (local only, intentionally Git-ignored)
- Discovered Java test candidates: 205; tsDetect produced data for 204; 1 test file failed and is explicitly logged.
- Long-format test-smell observations: 4,284, including 3,950 measured flags and 334 missing/not-applicable values.
- File-change follow-up events: 10, mined with PyDriller.
- Framework heuristic: 176 files indicated JUnit4, 29 unknown; framework labels require human validation.
- Result status: **partial**, never complete.
- The 10 events are not ten confirmed bug fixes. PIT mutation outcomes and causal analysis have NOT been run.

## Outstanding for scientific study
Sampling protocol, GitHub selection log, multi-project pilot, manual smell validation, independent rerun, confounder definitions and DAG, PIT attribution, and propensity-score/DoubleML/sensitivity analysis.
