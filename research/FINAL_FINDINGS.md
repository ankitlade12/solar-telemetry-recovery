# Final findings and conference-paper decision

**Interpretation amendment, September 13:** The original numerical findings below remain unchanged. A subsequent source audit identifies a prolonged near-idle Colorado AC regime that the exact-zero check missed. Read [the staff review](staff_review_v2/STAFF_RESEARCH_AND_IEEE_REVIEW.md) alongside these findings. This weakens producing-site generalization and changes scientific readiness; earlier completion audits certify their historical artifacts only.

The frozen experiment does **not** support promoting recovery-age grouping as an improved forecasting method. It supports a narrower paper about receipt-time evaluation, the importance of matched availability controls, and negative evidence about the additional recovery grouping in this setting. The original improvement hypothesis and threshold were retained; unfavorable outcomes are reported below.

All 49 site/case combinations completed, producing 14,106,960 forecast records. Automated verification passed, including score recomputation, source-target checks, quantile validity, scheduled scoring phases, receipt-gated label-update counts, dependency hashes and 874,300 direct history-slot lookups. This is not proof of every modeling assumption or independent human reproduction. [Verification record](../runs/final_2017_v4/verification.json)

The final analysis contains eight CSV tables, a workbook, three measured figure pairs and daily score sums. The table-only reproduction completed successfully; the exact comparison record defines its tolerance. These are fixed-site results using recorded PV output and simulated telemetry receipts, with 2016 training and 2017 final evaluation. Earlier inspected years remain development. [Analysis manifest](../runs/final_2017_v4/analysis/manifest.json) · [Table reproduction](../runs/final_evidence_exports_v1/reproduced_tables/reproduction_comparison.json) · [Frozen protocol](FINAL_EVALUATION_PROTOCOL.md)

## 1. Primary question: does recovery grouping add value?

The primary comparator is availability grouping with the same base forecast, physical-context kernel, recency weighting and shrinkage. Only the recovery-group coordinates differ. Positive differences favor availability. The values below are multiplied by 1,000 for readability; the outcome is NWIS, normalized by DC capacity.

| Site | Scheduled recovery window | 1,000 × difference | Seven-day-block 95% interval |
|---|---|---:|---:|
| NIST | 0–6 hours | 0.034 | [−0.109, 0.228] |
| NIST | 6–24 hours | −0.030 | [−0.097, 0.032] |
| Colorado | 0–6 hours | 0.011 | [−0.057, 0.074] |
| Colorado | 6–24 hours | 0.049 | [0.007, 0.090] |

Three intervals include zero. The Colorado later-window point difference is approximately 0.097% of availability NWIS, a small adverse effect. Its 28-day-block interval includes zero, approximately [−0.004, 0.093] on the table's scale. The other three primary comparisons remain inconclusive with both 14- and 28-day blocks. A non-significant comparison is not an equivalence finding. [Exact contrast rows](../runs/final_2017_v4/analysis/Contrasts.csv)

The four primary contrasts use 28 supported case/horizon strata each. Early-window cells have only 124–150 eligible forecast-target pairs, all below the specified 200-pair support flag. Distinct events range from 29 to 35; some NIST cells also fall below the 30-event flag. The 14.1-million-record archive must not be presented as 14.1 million independent observations. Horizons, methods and simulated scenarios reuse measured weather and targets. [Support table](../runs/final_2017_v4/analysis/Support.csv)

## 2. Strong baselines change the interpretation

The primary failure/recovery aggregate uses equal supported scenario/horizon means over seven faulted replays. It contains 24,986 eligible pairs per method at NIST and 24,646 at Colorado. The selected rows below illustrate why raw-model improvement alone is insufficient; the complete manuscript table retains all fifteen methods.

| Site | Method | NWIS | Empirical 90% coverage |
|---|---|---:|---:|
| NIST | Raw quantile model | 0.0525 | 82.7% |
| NIST | Physical context | 0.0520 | 90.0% |
| NIST | Availability grouping | 0.0520 | 90.2% |
| NIST | Recovery grouping | 0.0520 | 90.0% |
| NIST | Previous day | 0.0867 | 92.3% |
| Colorado | Raw quantile model | 0.0692 | 32.1% |
| Colorado | Physical context | 0.0567 | 92.5% |
| Colorado | Availability grouping | 0.0567 | 92.7% |
| Colorado | Recovery grouping | 0.0567 | 92.6% |
| Colorado | Previous day | 0.0253 | 98.4% |
| Colorado | Geometric persistence | 0.0365 | 99.3% |

At NIST, physical context has the lowest point NWIS, with very small differences among several calibrated alternatives. At Colorado, previous day has the lowest point NWIS and geometric persistence also beats recovery calibration. Their high empirical coverage exceeds the nominal level; a favorable WIS ranking does not certify nominal coverage. These are descriptive comparisons, not additional selectively chosen superiority tests. [All method means, widths and counts](../runs/final_2017_v4/analysis/Summary.csv) · [Complete case/horizon cells](../runs/final_2017_v4/analysis/Cells.csv)

## 3. Interruption and recovery mechanisms

The raw-forecast interruption comparison matches clean, PV-only, irradiance-only and joint-loss forecasts to identical origin/horizon rows. Isolated loss occupies the `partial_restoration` phase because the unaffected channel never left; excluding that phase would give an incomplete comparison. Immediate and gradual joint-backfill forecasts coincide before restoration, when their delivered histories are identical.

At NIST, joint loss is worse than either isolated loss. At Colorado, PV-only loss is worse than joint loss, and irradiance-only loss is close to or better than clean delivery. The assumed ordering “more missing channels always causes worse forecasts” is therefore not supported at both sites. This describes these fitted models; it does not establish why an instrument, plant or model behaves that way. [Matched interruption table](../runs/final_2017_v4/analysis/InterruptionComparison.csv) · [Failure figure](../runs/final_2017_v4/analysis/figures/failure_by_horizon.pdf)

Recovery and availability trajectories nearly overlap. The scoring clock begins at the later **scheduled** channel return, whereas calibration recovery age begins at **observed** live-currentness restoration. These clocks need not coincide when native gaps or queued history remain. The figures must not be read as measured network-recovery curves. [Recovery trajectories and pair counts](../runs/final_2017_v4/analysis/Recovery.csv) · [Recovery figure](../runs/final_2017_v4/analysis/figures/recovery_trajectory.pdf)

No primary recovery-calibrated cell uses the insufficient-score fallback after warmup. However, the joint-gradual early window uses the global pool because no matching state exists in 4.8% of NIST and 4.1% of Colorado pairs. Overall pool size and support for a fine state are different quantities. Update diagnostics count scored forecast records across horizons, not unique received physical measurements. [Fallback and effective-support diagnostics](../runs/final_2017_v4/analysis/Diagnostics.csv) · [Label-update activity](../runs/final_2017_v4/analysis/UpdateActivity.csv)

## 4. Sensitivities and original engineering gates

All declared sensitivity contrasts remain in the table, including favorable, inconclusive and adverse results. Across the five joint-gradual seeds, no seven-day interval excludes zero in favor of recovery at either site. NIST's two asynchronous-order cases have small favorable exploratory intervals, while its cross-site-weight case has an adverse interval. Colorado's tighter-quality, alternate-alignment, no-age and no-block cases have small adverse point differences. These unadjusted checks do not establish a stable recovery benefit. [Full contrasts](../runs/final_2017_v4/analysis/Contrasts.csv)

The no-age sensitivity zeros measurement and transport-age inputs in fitting and replay; this also changes measurement-age coordinates used by calibration context and groups. Missing patterns, currentness and observed recovery age remain. It is a joint predictor/calibration-input ablation, not removal of all staleness information. The cross-site case uses target metadata and fresh local calibration; both sites informed development. The privileged-label case deliberately changes information access and is a diagnostic, not an operational comparator. [Protocol](FINAL_EVALUATION_PROTOCOL.md) · [Requirement traceability](PRD_TRACEABILITY.md)

Removing bright-zero scoring targets leaves the primary failure/recovery rows unchanged. This does not diagnose other zeros or prove the source measurements correct. The Colorado alignment alternative bounds one unresolved timestamp interpretation; it does not resolve instrument semantics from favorable forecasting performance. [Cells and scoring populations](../runs/final_2017_v4/analysis/Cells.csv) · [Data statement](../DATA_AVAILABILITY.md)

The separate 5% improvement gate was fixed against physical-context calibration. It is missed at both sites: relative failure/recovery NWIS changes are **+0.0047% at NIST** and **−0.0323% at Colorado**. Both clean-data point tolerances are met, and aggregate recovery-calibrated 90% coverage is within five percentage points of nominal. Those diagnostics do not offset the absent improvement signal. [Exact engineering-gate inputs](../paper/generated/engineering_gate_facts.csv)

## 5. Computational cost and reproducibility

The loaded-inference benchmark completed 512 measured calls across sixteen workloads, using 32 origins per workload, all four horizons and seven quantiles per call. Workload medians range from 0.261 to 0.609 seconds and empirical P95 values from 0.346 to 0.831 seconds. Every workload meets the requested P95-under-one-second target; the maximum individual call is 1.875 seconds, so this is not a per-request deadline guarantee. The host is an Apple M4 with 16 GiB RAM, with supported thread pools limited to one thread. [Measured workload summary](../runs/inference_benchmark_v1/summary.csv) · [Individual calls](../runs/inference_benchmark_v1/calls.csv)

Recovery workloads use synthetic pools of 0, 360 and 720 scores per horizon. The timer includes loaded prediction and, where applicable, context construction and calibration. It excludes model loading, receipt/history construction, label ingestion, score-pool preparation, disk and network operations. Peak benchmark-process memory is about 402 MiB and includes loading the model bundles; it is not a measurement of training peak memory. Fixed workload order and shared personal hardware mean that differences between workload timings must not be interpreted as isolated calibration overhead or deployment guarantees. [Benchmark scope, hardware and hashes](../runs/inference_benchmark_v1/manifest.json)

All eight reproduced CSV tables also have the same SHA-256 as their originals. This stronger observed file-identity result accompanies the declared numerical comparison tolerance; it remains an automated same-agent reproduction from archived forecasts. [Comparison record](../runs/final_evidence_exports_v1/reproduced_tables/reproduction_comparison.json)

## 6. Submission decision and remaining completion work

**Method-promotion decision:** do not claim a novel superior recovery-calibration method, a general coverage guarantee, dominance over full published algorithms that were not reproduced, or broad site generalization. The evaluated adaptations and exclusions must remain explicit. [Closest-method crosswalk](CLOSEST_METHOD_CROSSWALK.md) · [Wen architecture boundary](WIND_QUANTILE_CROSSWALK.md) · [Delayed-feedback boundary](DELAYED_FEEDBACK_CROSSWALK.md)

**Paper direction:** prepare the regular-paper review draft around the auditable receipt-time protocol and controlled negative result. Completed experiments do not make novelty or acceptance automatic. A human research review should judge whether the empirical and reproducibility contribution clears the conference's bar; the manuscript should not be relabeled as a successful method paper to improve its apparent fit. [Current venue checklist](../paper/SUBMISSION_CHECKLIST.md)

The measured-table reproduction is automated and does not satisfy the original PRD's separate second-contributor requirement. Statistical analysis, table reproduction, loaded-inference measurement and the seven-page PDF mechanical/visual audits are complete. Archive manifests separately establish successful assembly and exact entry checks. Author review, second-person reproduction, original-code license choice and any external action require their own actual completion. Nothing has been submitted or published. [Independent reproduction procedure](../release/INDEPENDENT_REPRODUCTION.md) · [Evidence workflow](../runs/final_evidence_exports_v1/status.json)
