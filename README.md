# Test Smell Causal Study

**Reproducible Java test-smell and Git-history research data pipeline**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue) ![Java](https://img.shields.io/badge/Java-17%2B-orange) ![Local tests](https://img.shields.io/badge/local%20tests-14%20passing-brightgreen)

A developer-side implementation for the three-person empirical software-testing research project **“Do Test Smells Matter? A Causal Study.”** The project uses [tsDetect](https://github.com/TestSmells/TestSmellDetector) to observe Java test smells at a pinned commit, [PyDriller](https://github.com/ishepard/pydriller) to collect subsequent Git changes, and a Python CLI to generate auditable datasets.

> **Research caveat:** This repository collects observational evidence; it does **not** prove causality, run PIT mutation tests, estimate causal effects, or constitute a completed scientific study. The observation unit is a **Java test file**, not necessarily one test method.

## What does it do?

The main pipeline performs these operations:

1. Accepts pinned baseline and follow-up **Git commit SHAs** per Java repository. It clones an HTTPS source (or uses a local clone) and reads the baseline using an isolated Git worktree.
2. Discovers Java test-file candidates, potential production counterparts, estimated test LOC, approximate assertion-call counts and a heuristic test framework classification.
3. Runs standalone **tsDetect v2.2** on those baseline files, retaining original input/output CSV files, stderr/stdout and failures. Each detector batch is isolated; crash-inducing files are identified by batch bisection.
4. Converts detector results to long-form smell observations: measured positive/negative, or explicitly missing/not-applicable. Integer counts are retained. Blank is **not** the same as zero.
5. Mines changes **after the baseline snapshot**, up to the follow-up SHA, with PyDriller; recognizes Git-recorded renames and records file change counts. A commit-message regex suggesting a fix is merely a proxy, not a validated defect.
6. Generates deterministic CSV tables and per-repository checkpoints, logging resolved SHA, runtime and package information.
7. Safely resumes interrupted multi-repository runs, validates joins and optionally imports PIT results using a strict contract.
8. Offers an audited GitHub Java-repository sampler with fixed UTC dates, seeded candidate selection and documented exclusions.

**Responsibilities:** Developer supplies this pipeline and its datasets; Experimenter owns PIT and build experiments; Analyst owns DAG, confounders, manual labeling, causal estimation and reporting. See [the team handoff](docs/HANDOFF.md).

## Architecture

    Audited GitHub sampler / selected pinned Java Git repository
                             |
                       Git resolver
                             |
                 Immutable baseline checkout
                     /             \
       Java test-file discovery    PyDriller history mining
                   |                (follow-up commits)
             tsDetect runner             |
       (batching, failure isolation)     |
                     \             /
                    Dataset builder
                             |
                Atomic per-repository checkpoint
                             |
      tests.csv / smells.csv / outcomes.csv / commit_events.csv
                             |
                 Contract validation + PIT join
                             |
                    Analyst / Experimenter

## Prerequisites

| Dependency | Purpose | Local verification |
|---|---|---|
| Python 3.10+ | Installable CLI, analysis-ready data | 3.14.7 |
| Git | SHA resolution, worktrees and commit history | 2.55.0 |
| Java 17+ | Run tsDetect CLI JAR | 17.0.12 |
| PyDriller | Temporal Git mining | 2.12 |
| pytest | Unit/integration tests | 14 passing |
| Maven | PIT / some Java builds (Experimenter role) | Not installed or required for basic collection |

### Install

**Windows PowerShell**

    git clone https://github.com/urmiaking/test-smell-causal-study.git
    cd test-smell-causal-study
    .\setup.ps1
    .\.venv\Scripts\python.exe -m team7_pipeline doctor
    .\.venv\Scripts\python.exe -m pytest -q

**Linux/macOS**

    git clone https://github.com/urmiaking/test-smell-causal-study.git
    cd test-smell-causal-study
    bash setup.sh
    .venv/bin/python -m team7_pipeline doctor
    .venv/bin/python -m pytest -q

### Install the detector JAR

Download the standalone **TestSmellDetector.jar** from the [upstream v2.2 release](https://github.com/TestSmells/TestSmellDetector/releases/tag/v2.2) and place it at **tools/TestSmellDetector.jar**. It is **Git-ignored**, not redistributed in this repository.

Verified SHA-256:

    6a12de6d1613c7ee9e845a2b69d876834f8ee98379e85d38c0e6027f7110f7bc

In PowerShell verify it:

    Get-FileHash .\tools\TestSmellDetector.jar -Algorithm SHA256

The tested legacy v2.2 CLI takes a positional input CSV **without a header**. The program constructs it automatically. Detector output includes integer counts, boolean-like flags and blanks; the parser preserves those distinctions.

## Quick start — real Java repository

A pinned pilot config is included in **configs/junit4-pilot-002.json**. First copy it to **configs/my-pilot.json** and edit its **run_id** and **output_dir** to fresh values; runs with previous output artifacts intentionally refuse overwrites.

    Copy-Item configs/junit4-pilot-002.json configs/my-pilot.json

Example core config values:

~~~json
{
  "run_id": "my-pilot",
  "output_dir": "../results/my-pilot",
  "cache_dir": "../data/repos",
  "detector_jar": "../tools/TestSmellDetector.jar",
  "detector_timeout_seconds": 300,
  "repositories": [
    {
      "id": "junit4",
      "source": "https://github.com/junit-team/junit4.git",
      "snapshot_ref": "354b72771d70255a860001c6b11786897c1c2fbd",
      "followup_ref": "890f3c972647de378f25e7271d8fbbd9d3456b79"
    }
  ]
}
~~~

Paths inside config resolve relative to the config file. Run and validate:

    python -m team7_pipeline run --config configs/my-pilot.json
    python -m team7_pipeline validate --results results/my-pilot

The run prints counts and statuses. Inspect **results/my-pilot/manifest.json** and **repository_status.csv** before using the data. To test Git mining without tsDetect, append **--skip-detector**; this records **no smell measurements**, not zero smells.

## Resume after interruption

Each repository has an atomic, SHA-256-checked checkpoint in the output directory, and the run state is fingerprinted against the exact input configuration and JAR checksum.

Demonstrate an intentional partial run (make a fresh config and output first):

    python -m team7_pipeline run --config configs/your-run.json --max-repositories 1
    python -m team7_pipeline run --config configs/your-run.json --resume

Completed checkpoints are reused; only missing repositories are processed. With an explicit choice, failed repositories can be retried, archiving previous raw logs/checkpoints:

    python -m team7_pipeline run --config configs/your-run.json --resume --retry-failed

**Limitations:** The worker is sequential and supports one writer per output directory. Resume was validated on two real repositories, not benchmarked across 1,000 repositories. Partial detector outcomes are **not** automatically promoted to complete.

## Auditable repository sampling

Example public GitHub search with explicit dates and seed:

    python -m team7_pipeline sample --query "topic:testing" --count 10 --baseline-date 2025-01-01 --followup-date 2025-07-01 --seed 7 --max-candidates 50 --max-pages 2 --output configs/my-sample.json

This writes a runnable config with dated immutable commit refs and a separate **sampling-audit.json** with candidate decisions/exclusions. Use **GITHUB_TOKEN** via environment only, if needed for rate limits.

**Not scientific sampling by itself:** GitHub Search has ranking bias, public-only coverage, API caps and exclusion criteria. The Analyst must define the population, sampling methodology and time horizon and obtain team/supervisor approval.

## Data model and outputs

The immutable observation key is **(repository_id, snapshot_sha, test_file)**. A file may include several classes/methods.

| Generated file | Meaning |
|---|---|
| **tests.csv** | Baseline test candidates, linked production path guesses, framework heuristic, LOC/assertion estimates and detector status |
| **smells.csv** | Long-form smell type, measured/missing state, raw numeric/boolean value, positive/negative observation |
| **commit_events.csv** | Later file-change commit events, timestamps and *potential* bugfix-message flags |
| **outcomes.csv** | Changes to baseline test files within the pinned follow-up range |
| **analysis_ready.csv** | Baseline test metrics joined to later outcomes; smell rows remain separately normalized |
| **repository_status.csv** | Complete / complete_with_na / partial / failed / no_smells_measured flags |
| **raw/** | Detector input/output, exceptions and per-batch logs, including attempts that failed |
| **run_state.json**, **.checkpoints/** | Resume metadata and checksummed per-repo shards |
| **manifest.json** | Final provenance, resolved SHAs, environment, package versions and aggregate counts |

Do not interpret absence of a detector row as **false**. File-change events are not necessarily confirmed bug fixes. Runtime artifacts under **results/** and Git clones under **data/repos/** are not committed.

## Experimenter integration — PIT

The header-only template **contracts/pit-results.example.csv** documents the external PIT schema:

    repository_id,snapshot_sha,test_file,mutation_score,attribution_method,measurement_status

For a **measured** result, mutation_score must be in [0,1] and attribution_method must be **isolated_test_file** or **verified_per_test_coverage**. This is a declared claim that Experimenter must substantiate with experimental evidence; it is not validated by a string alone. A project-wide mutation score must **never** be mechanically assigned to individual test files.

Validate and join (only after an Experimenter actually produces the CSV):

    python -m team7_pipeline validate --results results/my-pilot --pit experiments/pit-results.csv --export results/pit-joined.csv

The Analyst then determines confounders, causal estimand, DAG and sensitivity checks. The Developer does not fabricate PIT data or estimate causal effects.

## Verified local engineering results — October 23, 2026

Two publicly available Java repositories were tested: **Apache Commons CSV** and **JUnit 4**. One execution was deliberately stopped after the first repository and resumed; another execution started from scratch on the **same Windows machine**.

| Observed engineering metric | Result |
|---|---:|
| Repositories | **2** |
| Baseline test-file candidates | **245** |
| Long-form test-smell observations | **5,124** |
| Measured smell values | **4,724** |
| Missing/not-applicable smell values | **400** |
| Later test-file change events | **13** |
| Semantically identical CSV outputs between the two runs | **6 / 6** |
| Local automated tests | **14 passed** |

**By repository:** Commons CSV contributed **40** test-file candidates and **840** smell rows (774 measured, 66 missing). JUnit 4 contributed **205** test candidates and **4,284** smell rows (3,950 measured, 334 missing). These are **test × smell-field observations**, not confirmed bugs and not necessarily positive smells.

JUnit 4 was marked **partial** because tsDetect's **EagerTest** visitor crashed on one file; fault isolation preserved results for the other 204 files. Commons CSV was **complete_with_na**, but JUnit 5 compatibility and identification of helper classes still need manual checks. The **13** Git events are file changes, **not** confirmed defect fixes.

**Replication result:** All six normalized CSV files matched across two same-machine runs, once resumed and once from scratch. This confirms local repeatability; independent replication on a *different computer* is pending. These engineering metrics **cannot be interpreted as causal research findings**.

More details: [Pilot results](docs/PILOT_RESULTS.md) · [Replication protocol](docs/REPRODUCIBILITY.md) · [Tool audit](docs/TOOL_AUDIT.md).

## Verification

    python -m pytest -q
    python -m team7_pipeline doctor
    python -m team7_pipeline validate --results results/my-pilot

The tests cover Git temporal windows and snapshots, test discovery, numeric/missing detector fields, crashing detector batches, checkpoint integrity and resume, config fingerprinting, PIT join constraints, reproducible output comparison and cached repo-origin checks. GitHub Actions has Windows/Linux pytest jobs; **remote CI status must be checked after publishing**.

## What is finished, and what remains?

**Implemented and locally verified (Developer):** initial setup, Java discovery, tsDetect integration, PyDriller history, reproducible dataset generation, error recovery, GitHub sampling audit, checkpoint/resume, validation, PIT handoff and two-run pilot comparisons.

**Not yet completed or not Developer-owned:** pre-registered cohort selection; scientific validation of JUnit 5 support and detector accuracy; manual smell labeling/inter-rater reliability; PIT build experiments and test-level mutation attribution; causal DAG and confounder definition; regression/PSM/DoubleML/sensitivity analysis; large-scale performance testing; another team member's cross-machine replication; instructor Go/No-Go approval and a research report. See [the roadmap](docs/ROADMAP.md), [the research contract](docs/RESEARCH_CONTRACT.md) and [the handoff](docs/HANDOFF.md).

## Repository layout

    src/team7_pipeline/
       cli.py             # CLI commands
       pipeline.py        # end-to-end batch orchestration
       checkpoint.py      # atomic storage and resume
       sampling.py        # GitHub discovery and audit
       gitutils.py        # Git refs/worktrees/cache
       discovery.py       # Java test discovery
       miner.py           # temporal PyDriller mining
       detector.py        # tsDetect CLI adapter
       detector_batch.py  # fault-isolated runs
       contract.py        # data/PIT validation and comparison
    configs/              # pinned research-engineering pilot configs
    contracts/            # Experimenter-facing PIT schema
    tests/                # regression and integration tests
    examples/             # tiny Java fixture
    docs/                 # tool audit, roadmap, research handoff, findings
    tools/                # tool instructions; JAR ignored
    results/              # local run outputs; Git-ignored
    data/repos/           # Git clones; Git-ignored

---

### خلاصه فارسی

این ریپو شامل بخش **Developer** پروژه پژوهشی بررسی Test Smell در کدهای تست Java است: جمع‌آوری مخزن‌های Git در نسخه مشخص، تشخیص Test Smell با tsDetect، استخراج تاریخچه تغییرات بعدی با PyDriller، تولید دیتاست، ثبت خطاها و پشتیبانی از Checkpoint/Resume.

در پایلوت فنی دو مخزن بررسی شدند: **۲۴۵ فایل تست، ۵٬۱۲۴ ردیف داده، ۴٬۷۲۴ مقدار اندازه‌گیری‌شده و ۴۰۰ مقدار ناموجود/غیرقابل‌اندازه‌گیری**. دو اجرای مستقل از نظر فرآیند روی یک کامپیوتر، شش فایل CSV یکسان تولید کردند. این نتایج به‌معنای اثبات رابطه علّی نیستند. اجرای PIT، تحلیل آماری، طراحی DAG، اعتبارسنجی دستی و تأیید علمی بر عهده سایر اعضای تیم و استاد است.
