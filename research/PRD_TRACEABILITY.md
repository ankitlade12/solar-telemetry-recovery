# Original PRD requirement traceability

The original `Solar_Forecasting_Research_PRD.docx` remains unchanged, SHA-256 `75b6e28dda396d72162ef5c8f5750426336eae7997b099573ef256ff729a2a6c`. This matrix distinguishes implemented mechanisms from completed evidence and records narrowed claims. All 49 original final-2017 cases are complete and automated verification passed for 14,106,960 forecasts and 874,300 directly checked history slots. Original statistical analysis, table reproduction and latency measurement are complete. A subsequent staff review found a dominant near-idle Colorado regime and revised the seven-page manuscript; this materially limits producing-system interpretation. The extension and integrated manuscript are complete; human review and author decisions remain unconfirmed. Superseded archives have been removed from the working tree, and new packages must be generated from current checked sources.

The [separate producing-system replication](PRODUCING_EXTENSION_EXECUTION.md) now has qualified system-10 inputs, 75 passing pre-freeze tests and its own 139-file lock. All eleven cases and 4,702,320 forecasts are complete and verified; all eight principal tables reproduced exactly and are integrated into the current paper. System 10 is adjacent to original Colorado system 4, so it cannot establish another independent climate. Maine remains pending and Nevada is ineligible under their selected source plans. These decisions preserve all source-screen outcomes and the original unfavorable experiment.

## Scientific hypotheses and gates

| Requirement | Disposition and evidence | Remaining check |
|---|---|---|
| H1: joint loss versus isolated loss | Same-weather primary PV-only, irradiance-only and joint scenarios; horizon/phase tables and failure curves specified | Matched curves: joint loss worsens NIST and extension C10, but original C4 PV-only loss is worse than joint loss; no universal ordering |
| H2: information-state calibration | Raw, rolling, recency, physical, availability, recovery, mask and bounded adaptive controls | Complete common-row tables and intervals; calibration improves raw coverage. Previous day is strongest at original C4; availability has the smallest descriptive point NWIS at C10 |
| H3: restoration-specific benefit | Primary recovery-versus-availability contrast drops only recovery-age group coordinates | Original four contrasts reported: three seven-day intervals include zero, one small adverse Colorado effect crosses zero with 28-day blocks; C10 early recovery is inconclusive and its small late penalty remains positive across 7/14/28-day intervals |
| H4: temporal/site transfer | 2015-trained sensitivity and other-site normalized quantile weights with fresh local calibration | Final transfer/2015 checks reported with local-calibration and development-site qualifications |
| Proposed 5% signal and clean tradeoff | Fixed against development-selected physical context; clean tolerance has explicit 0.0001 NWIS floor | 5% signal missed at all three systems; all three clean point tolerances pass; uncertainty and non-guarantee stated |
| Minimum support and coverage diagnostics | 30 events/200 cases and nominal 90% ±5 percentage-point targets | Original early cells have 124–150 pairs and 29–35 events; C10 has 120–135 pairs and 27–33 events. Support flags remain; aggregate calibrated coverage passes the diagnostic |
| Second contributor reproduction | Fresh-environment automated reproduction is complete | **A second human contributor has not reproduced the principal tables** |

## Functional and data requirements

| ID | Implemented mechanism / artifact | Qualification |
|---|---|---|
| F01: validate units, duplicates and time | `data_v2.py`, source manifests, channel contracts, excluded-measurement ledgers, final input qualification, cross-channel investigation and source-screen decisions | 97.95% of original Colorado scored targets are below 1% of capacity; raw/channel checks support a source-regime concern, not a conversion correction. Physical cause remains unresolved; source completeness is not metrological validation |
| F02: chronological isolation | 2016 observed-target fitting, January 2017 causal warmup, four-hour purged issue gap, target-end cutoffs | Actual year-based split supersedes tentative percentage split; all inspected earlier years are development |
| F03: deterministic interruption/delay/stale/restoration | `replay_v3.py` and `replay_v4.py`; calendar schedules and immutable message semantics | Receipts are simulated, not observed operational logs |
| F04: common information/scoring rows | Shared feature table by site/case; analysis and verifier assert identical origin/horizon keys | Privileged labels are explicitly diagnostic and excluded from operational ranking |
| F05: labels only at receipt | Stored issued forecasts, delayed label gating, duplicate-safe updates; independent count verifier | No imputed target labels; permanent loss can leave pending forecasts forever |
| F06: forecast plus health schema | Seven quantiles, origin, target start/end, actual lead, capacity, model/run version; separate per-origin feature file | Join health by origin within site/case; source schema names are `end`/`receipt`, corresponding to observation/availability time |
| F07: stratified figures and manifests | Analysis writes cell/day/support/diagnostic/update tables, three figure pairs and workbook; synthetic receipt timeline has CSV source | Measured figures, exact source tables and workbook complete |
| F08: clean-environment example | `examples/synthetic_replay.py`, fresh pinned install, tests and exact DataFrame comparison under `runs/clean_environment_v4/` | Same machine and Python version; not a full-data rerun or second-person review |
| Data/target ambiguity | Preserve recorded AC zeros; retain original bright-zero sensitivity and separate post-hoc positive near-idle diagnostic | Exact-zero filtering missed the original Colorado regime. No post-hoc target removal or retuning; physical fault cause is unobserved. New system-10 inputs retain all seasons under a bounded recorded-sample contract |
| Provenance and licenses | Source object hashes, dataset DOI/license, normalization audit, frozen code/config, model and environment records | Public original-code license/release terms remain an author decision; no fictitious release URL |

The implementation exposes the ingestion, fitting/replay, verification and reporting stages through named Python module CLIs and hash-bound JSON configurations. These replace the PRD's proposed single command surface/YAML representation; the artifact guide documents the actual commands. No claim of an unimplemented generic CLI is made.

## Required baselines and ablations

| PRD item | Final implementation | Scope |
|---|---|---|
| B0 persistence and previous day | Latest-value, geometry-adjusted and previous-day same-target-hour forecasts with residual intervals | Previous-day missing slot falls back to latest received value |
| B1 carry-forward quantile model | `CarryForwardQuantile` with within-origin older-to-newer visible lag filling; constant availability indicators | Earliest unresolved slot defaults to zero; no target imputation |
| B2 missingness/age-aware quantiles | Native-missing-value HGB with explicit health features | Recovery age excluded from the base predictor |
| B3 block dropout plus global calibration | Fixed clean plus three block-augmented training replays; rolling/recency signed calibration | No final-year tuning |
| B4 rolling/adaptive | Uniform rolling and bounded receipt-gated ACI | Clipped-alpha engineering variant, not the original guarantee |
| B5 closest PV multiple imputation | Fixed training-only donor adaptation of single-training/multiple-input setup; SI, MI and MI+recency outputs | Explicit HGB/joint-channel/observed-label changes; not a full reproduction |
| B6 missingness-adaptive published methods | Full-paper crosswalk and [Wen architecture supplement](WIND_QUANTILE_CROSSWALK.md); empirical availability/mask controls evaluated | **Full published B6 algorithms are not reproduced.** The PRD explicitly permits narrowing the claim; the frozen amendment limits this paper to evaluated empirical controls |
| Remove input age | `no_input_age`: zero measurement/transport age columns in fitting and replay, including the measurement-age coordinates consumed by calibration context/groups | Joint predictor/calibration-input ablation; currentness, missing patterns and observed recovery age remain |
| Remove recovery | Availability grouping retains everything except two recovery-age coordinates | Primary matched contrast |
| Remove matching-state pool | Physical-context weighting without local-state blending | Secondary contrast |
| Remove block augmentation | Clean-only training sensitivity | Other method parameters fixed |
| Remove correct delay | Privileged normal label delivery despite missing inputs | Deliberately non-operational diagnostic, never a fair deployment comparator |

## Scenario coverage and package

The final grid contains eight primary cases and seventeen additional sensitivities, including five joint-gradual schedule seeds, 6/12/24-hour duration, asynchronous restoration, gradual/immediate/permanent history policies and stale transport. The PRD's tentative 1/3-hour durations and full seed cross-product are omitted by the dated protocol amendment; the study must not claim exhaustive fault coverage.

| Deliverable | Current artifact/status |
|---|---|
| Deep venue/literature assessment | `CCWC_Research_Assessment.md` and related reports, full-method crosswalk, primary citations |
| Immutable experiments and configuration | Historical development runs preserved; final protocol locked; all 49 final cases complete and automatically verified |
| Availability timeline | `paper/figures/receipt_timeline.pdf` plus CSV and source manifest; visually inspected |
| WIS/coverage/width, failure curves, recovery counts, ablation and clean tables | Complete measured tables, three figure pairs, diagnostics and exact table reproduction |
| Source-linked spreadsheets | Development, original final and staff-diagnostic workbooks complete; extension workbook and all eight reproduced tables are complete under `runs/producing_extension_v1/analysis/` |
| CPU, memory and four-horizon latency | Host hardware plus measured 512-call benchmark: workload median 0.261–0.609 s, P95 0.346–0.831 s; scope and memory limits recorded |
| Environment and end-to-end example | Pinned dependencies, resolved clean-environment lock, exact synthetic reproduction complete |
| Notebook | `notebooks/inspect_evidence.ipynb`; all code cells checked headlessly on verified synthetic artifacts |
| Model/data cards and commands | `MODEL_CARD.md`, `DATA_AVAILABILITY.md`, `ARTIFACT_GUIDE.md` |
| Conference paper | Current seven-page author-side review paper, 159 original plus 19 separate post-hoc checked source-row claims, 20 embedded fonts and current mechanical/visual audits. Eight recent/close references and the Colorado limitation were added; surname correction is recorded separately. The completed extension is incorporated across the manuscript, adding a 304-entry integrated ledger (482 total ledger entries), separate declaration timing and three-system tables/figures |
| Reviewable release archive | Local package builders retain both verified experiments and all three claim ledgers. No current bundle is supplied after cleanup; each fresh package must pass current manuscript/evidence checks |
| Public-release package | Historical candidate has a verified 82-file public dependency view and clean-environment checks. The extension now has a verified 138-file public view and isolated dependency/import check without private PRD. The earlier integrated public candidate passed both dependency views, 98 tests and four exact synthetic DataFrame comparisons. These are historical checks for that archived revision; a new package must be checked again. Original-code license selection remains an author decision; no external release has occurred |
| Submission readiness | Human review, author order/consent, originality/conflict check, disclosure placement and second-person reproduction remain; no submission/contact/payment performed |
