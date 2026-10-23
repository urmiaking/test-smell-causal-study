# Developer roadmap — implementation vs scientific approvals

## Developer implementation completed and verified locally

- [x] Initialize repository, Python package and CLI
- [x] Audit verified tsDetect v2.2 and PyDriller; record SHA256 and runtime versions
- [x] Pin snapshot/followup refs and Git mining window; handle Git-recognized renames
- [x] Discover Java test candidates, framework heuristics, production mapping candidates
- [x] Run tsDetect, preserve raw/missing/count values; bisect crashes rather than drop whole repository
- [x] Build test/smell/change/outcome datasets with per-file statuses and manifest
- [x] **Stage 8 software integration:** implement strict machine-validated keys and optional PIT attribution CSV join; handoff contract included
- [x] **Stage 9 implementation:** audited GitHub sampling with UTC snapshot dates; per-repo atomic checksummed checkpoints, resumable multi-repo run, immutable fingerprint, explicit failed-only retry with archive
- [x] **Stage 10 engineering pilot:** interrupted 2-repo run resumed successfully; fresh run on same machine produced all 6 semantically identical output CSV files; contract validator passed

## Scientific / externally owned checkpoints not yet completed

- [ ] Three-member team signs observation unit, PIT protocol and DAG/confounders
- [ ] Professor approves sample selection and Go/No-Go milestone
- [ ] Analyst completes manual validation (including ambiguity in JUnit5/helper test discovery)
- [ ] Experimenter verifies PIT attribution and executes baselines
- [ ] Independent **other-machine** repetition by another member (only same-machine equivalence verified)
- [ ] Actual 1000-repository load test, data-policy and resource evaluation
- [ ] Statistical causal analysis, robustness checks and scientific report

**Conclusion:** Developer-side engineering deliverable and interfaces are implemented and locally verified; full *research methodology approval*, PIT measurements and independent second-machine signoff are not something software can self-certify.
