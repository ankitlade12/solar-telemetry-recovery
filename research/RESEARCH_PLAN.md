# Conference research execution plan

## Objective and completion criteria

Develop a defensible IEEE CCWC submission package from the existing solar-forecasting PRD. Completion requires a literature-supported contribution, resolved or explicitly bounded data provenance, reproducible experiments with credible comparators, uncertainty and sensitivity analysis, a complete evidence-based manuscript, and a submission checklist. Acceptance cannot be guaranteed. The original PRD remains unchanged. External submission and author contact are outside the current authorization.

**Current execution update, September 12:** the [final protocol](FINAL_EVALUATION_PROTOCOL.md) is frozen, and `runs/final_2017_v4/` is executing 49 site/case combinations. The separate completion workflow will verify all scores, receipt-gated updates and sampled histories, then generate the frozen analysis. The IEEE working draft and reproducibility materials exist; final evidence synthesis and release packaging remain. Earlier status entries below are the retained development history, not the current task list. See [PRD traceability](PRD_TRACEABILITY.md).

The active goal was created September 11, 2026. The current venue page lists November 6, 2026 as the full-paper deadline. The regular-paper target is seven pages; anonymous review requirements must be checked in the final manuscript. Sources: [submissions](https://ieee-ccwc.org/submissions/), [call for papers](https://ieee-ccwc.org/call-for-papers/).

## Research direction

Study information delivery and calibration during recovery from joint PV/irradiance telemetry interruption. A contribution must survive comparison with missingness-aware and context-weighted methods, and with delayed-feedback conformal methods. Do not claim that missing inputs, joint channel removal, context calibration, or delayed feedback are new.

The first pilot established working replay but no benefit from its recovery candidate. Its intervals were over-wide, its correction could only expand, and its first schedule restored at night. Those results remain part of the development record. A useful paper may become a carefully isolated empirical/reproducibility study if an algorithmic improvement does not survive evaluation; neither route is assumed successful in advance.

## Evidence boundaries

- NIST 2015, its original and daytime-shifted schedules, and all inspected pilot results are development data.
- Newly acquired 2016 site-years are for data qualification and method development, not a pristine final test.
- Reserve candidate 2017 periods for a final evaluation only after data contracts and a protocol are frozen. Metadata/completeness screening must be logged separately from performance analysis. No forecast performance on those periods has yet been examined.
- No substitution of hidden truth into features or online calibration. No imputing missing target labels for evaluation. Distinguish simulated receipt times from measured arrival logs.
- A site is a geographic/statistical cluster; multiple arrays on the same NIST or NREL campus are not independent sites.

## Work stages

1. **Data qualification — active.** Screen measured power and irradiance channels, verify unit scales, timestamp semantics and source quality flags. Audit new development years. Investigate the separate NIST AC meter and at least one geographically distinct candidate. Document any alignment uncertainty and sensitivity; do not silently assume it away.
2. **Method correction — active.** Implement signed empirical CQR-style adjustment, coherent interval nesting and daylight-matched calibration. Compare global, context, mask and recovery conditioning with identical base forecasts and information access. Add a clearly specified delayed adaptive comparator; distinguish bounded engineering variants from the original algorithm and its guarantees.
3. **Mechanism experiments — active.** Immediate/gradual backfill, permanent loss and independent live resumption are implemented and evaluated for annual base forecasts. Matched calibration, score staleness, pool support and update-burst comparisons are now being run.
4. **Protocol freeze — pending.** Fix sites, train/calibration/validation/evaluation boundaries, feature contracts, tuning budgets, scenario grid, seeds, comparison endpoints, missing-target policy and inferential units before final performance evaluation.
5. **Full evaluation — pending.** Run baselines, missing-data comparators, ablations and sensitivity analysis. Use paired event/site-level uncertainty; do not count overlapping forecasts as independent samples. Report WIS with conditional coverage and width, plus failure and unsupported-state rates.
6. **Manuscript and artifact — pending.** Write a complete anonymous conference manuscript with factual contributions, limitations and verified references. Export figures with their source tables, provide environment/config/data/code provenance, and run a submission-format audit.

## Immediate technical decisions

Preserve the first pilot's code and artifacts; new calibration behavior belongs in a versioned module/config. The next controlled experiment reuses frozen development-model outputs so that a change in calibration can be separated from a change in the base forecaster. Do not silently retrofit the earlier results.

The classical CQR construction uses a signed score, so intervals can shrink as well as expand. Its exchangeability guarantee does not automatically apply to this rolling, weighted, missing-label time-series setting. Adaptive updates must evaluate the originally issued interval only when its label arrives; old labels must not retrospectively alter predictions. Sources: Romano, Patterson and Candès, [Conformalized Quantile Regression](https://arxiv.org/abs/1905.03222), 2019; Gibbs and Candès, [Adaptive Conformal Inference Under Distribution Shift](https://arxiv.org/abs/2106.00170), 2021.

## Current artifacts

- [Initial assessment](CCWC_Research_Assessment.md): venue, literature and initial contribution analysis.
- [Pilot findings](PILOT_FINDINGS.md): completed development results and their limitations.
- `pvdaq_metadata_screen.json`: bounded sixteen-system metadata screen; acquisition manifest under `data/metadata/development_screen/`.
- Subsequent data audits, method specifications, run reports and manuscript will be linked here as completed. Pending stages are not completed deliverables.

## Completed development update

See [DEVELOPMENT_V2_FINDINGS.md](DEVELOPMENT_V2_FINDINGS.md). The sixteen-system screen and three 2016 source audits are complete. NIST AC and Colorado AC data contracts now have 97.94% and 99.95% joint daylight completeness; Colorado's missing UTC/alignment metadata remains a qualified assumption. Maryland 1200 has no acquired irradiance observations in 2016 and is excluded from the joint-stream cohort.

Signed/daylight/recency/context/mask/recovery and bounded adaptive calibration have been compared on frozen 2015 development forecasts (176,640 additional records). Early gains do not persist uniformly into later recovery, and the incremental recovery contribution remains unsupported. Thirty-one tests pass. Original source snapshots and forecasts are preserved.

Immediate next work: obtain full-season 2015 AC training history for both qualified sites; assess timing and quality sensitivity; train a better common base model; implement the missing published-method comparators and gradual backfill; then freeze the final evaluation protocol. A manuscript and final submission package are still pending, so the goal remains active.

## Annual development update, September 12, 2026

The full-year 2015 AC histories are acquired and normalized for NIST and Colorado. The [annual development protocol](ANNUAL_DEVELOPMENT_PROTOCOL.md) documents training/selection boundaries, eight schedules, SI/MI adaptations, one-minute release semantics and two method corrections. The [corrected annual findings](../runs/annual_ac_daylight_causal_v3/FINDINGS.md) and [supporting spreadsheet](../runs/annual_ac_daylight_causal_v3/Annual_Development_Evidence.xlsx) are complete. All 4,497,408 forecasts passed structural/data/metric checks, with 80,000 independently checked receipt slots. Non-MI forecasts are identical to the parent daylight run, verifying that the later change isolated stochastic sampling.

The first all-hour fit produced constant-zero NIST median quantile models. Daylight training corrected the median failure; the original run and a 112-fit audit are preserved. A second correction makes stochastic imputations invariant to future-row extensions and batch order. The latest suite has 45 passing tests. Recorded zero episodes are separately described in `ac_zero_episode_audit.json`/CSV; their physical cause is unresolved and zeros were not silently discarded.

New matched calibration code compares a physical context that excludes recovery age against the same context plus recovery-state blending. A fifty-slot empirical mask control and receipt-gated bounded ACI are included. The initial annual calibration run is in progress under `runs/annual_ac_calibration_v3`; it uses fixed parameters and clean/gradual-joint scenarios. These controls are explicitly specified adaptations, not complete reproductions of the closest CACP/mask-conditional papers.

The 2017 files are being acquired for **data qualification only**. Do not inspect final-year forecast performance before freezing the protocol. Remaining work is to finish matched calibration and source-year/zero-tail, timing, quality and schedule sensitivities; settle the contribution based on those results; freeze and execute final evaluation; and write/verify the full paper. The [paper workspace](../paper/README.md), checklist and AI ledger now exist, and the local IEEEtran conference template compiles. No complete manuscript or submission exists yet.

### Completed calibration and reserved-data qualification

The [matched calibration run](../runs/annual_ac_calibration_v3/FINDINGS.md) is now complete: 983,808 forecasts, verified base/median agreement, target/score checks, 8,000 sampled interval repairs, and independently counted label updates (17,304 per method for each NIST scenario; 17,648 for each Colorado scenario). Paired early/late recovery differences remain small and mixed, with all four site/phase bootstrap intervals including zero. The new [closest-method crosswalk](CLOSEST_METHOD_CROSSWALK.md) records full algorithm/assumption checks for CACP, CP-MDA and Fan et al., and explicitly identifies implementation gaps.

[Reserved 2017 qualification](RESERVED_DATA_QUALIFICATION.md) is complete: 4,268 NIST and 4,267 Colorado complete daylight joint hours in their source-calendar extents. No 2017 forecasting performance has been accessed. The original PRD checksum was reverified unchanged. All processes for these completed stages have terminated normally.

Next decisions/work before the final protocol:

1. Add an availability-only grouping ablation if making an incremental recovery-age claim: the current recovery key also groups observation age and missing fractions.
2. Decide the empirical contribution and record a dated amendment for any original-PRD comparator omissions. Do not label heuristic mask/physical controls as exact CP-MDA, Fan or full CACP implementations.
3. Use the qualified 2016 full-year history as the candidate final training year, with model profiles already selected from development. Audit per-quantile fit variation, including lower tails; 2015 NIST contains many recorded zero episodes, so its source-year sensitivity must stay visible.
4. Implement and predeclare bounded sensitivity comparisons for outage durations/seeds, gradual-backlog rate/channel gap, one-minute interval alignment, and engineering quality limits. A full cross-product is not automatically necessary, but evaluated and unevaluated combinations must be explicit.
5. Freeze exact input/code/config hashes, train/calibration/evaluation UTC boundaries, primary comparisons and dependent-data inference units before producing 2017 forecast results. Repeated scenario seeds on the same weather are not independent site replications.
6. Execute that evaluation, generate the final evidence tables/figures, and write/compile/audit the complete anonymous manuscript and reproducible artifact. Human authorship/consent and anonymous AI-disclosure placement remain submission-readiness items; no external action is authorized.

### Final freeze and execution

Items 1–5 above are complete with the scope recorded in `FINAL_EVALUATION_PROTOCOL.md`. New controls include previous-day prediction, carry-forward quantiles, availability-only grouping and stale transport. The final inputs include tighter quality bounds and alternate Colorado alignment; recorded bright-zero targets receive a prespecified scoring sensitivity. Five schedule seeds, age/block/label-delay ablations and temporal/site transfer are fixed before final performance inspection. The original PRD's stronger unpublished-method comparison claims are narrowed explicitly, not silently claimed as completed reproductions.

The 83-file lock follows 55 passing tests. An isolated dependency installation subsequently passed 58 tests and exactly reproduced the synthetic measurement, feature, forecast and diagnostic DataFrames. Six analysis/verifier tests, including an end-to-end synthetic workbook/figure run, now pass. The working paper compiles with verified primary bibliography metadata and a source-data-linked synthetic receipt timeline. `MODEL_CARD.md`, `DATA_AVAILABILITY.md`, `ARTIFACT_GUIDE.md` and the inspection notebook describe the artifact.

Remaining work: complete the frozen run; inspect automatic verification/analysis; investigate any failure with a recorded amendment; write the evidence-based final results, abstract, conclusion and findings report; audit the seven-page PDF, citations, anonymity and figure readability; assemble a private review package and an appropriate anonymous manuscript bundle. Human consent, second-person reproduction and actual external submission remain separate gates. The goal stays active until the reviewable package is complete.
