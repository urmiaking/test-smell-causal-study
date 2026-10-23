# Tool audit and experimental prerequisites

| Tool | Version verified | Source / purpose |
|---|---|---|
| PyDriller | 2.12 (local) | https://github.com/ishepard/pydriller : temporal Git miner |
| TestSmellDetector JAR | v2.2 | https://github.com/TestSmells/TestSmellDetector/releases/tag/v2.2 |
| Java | Oracle 17.0.12 | executes standalone tsDetect CLI |
| Python | 3.14.7 | pipeline and tests, local environment |
| pytest | 9.1.1 | developer regression tests |
| PIT | NOT INSTALLED or RUN | https://pitest.org/ , Experimenter ownership |
| Maven | NOT INSTALLED | required for many PIT/Java build tasks, not for source parsing |

**Exact JAR SHA256:** 6a12de6d1613c7ee9e845a2b69d876834f8ee98379e85d38c0e6027f7110f7bc

**Verified behavior differs from older website samples:** The v2.2 JAR accepts CSV input without a header. It treats a literal header as a file path and crashes. Use a positional CSV path (not the newer repository README's --file/--granularity flags). Output includes integer counts and absent/not-applicable flags. EagerTest may throw on some JUnit4 files; isolate failures. Do not assume this version fully supports JUnit 5.

**Pending before full study:** approved baseline papers, dated competitor survey, sampling protocol, compatible test frameworks, 100-sample validation, PIT build support, confounder/DAG protocol, reproducibility on another machine.
