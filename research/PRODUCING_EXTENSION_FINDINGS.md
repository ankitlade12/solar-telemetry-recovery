# Verified producing-system replication findings

The completed system-10 replication strengthens the bounded negative conclusion: adding the implemented recovery-age grouping does not yield stable improvement over matched availability grouping on an additional productive recorded-AC archive. It does not establish that recovery information can never help. The model, configuration and source were fixed before extension forecasting, after original-study result exposure; this is a separately declared replication, not another untouched original test or an independent climate.

All eleven cases completed, generating 4,702,320 issued forecast records. Automated verification checked those records and 192,700 visible-history slots. All three queued stages exited successfully. The eight principal tables reproduced with identical CSV hashes. Counts include repeated outputs and are not independent sample sizes. Source artifacts are [verification](../runs/producing_extension_v1/verification.json), [analysis](../runs/producing_extension_v1/analysis/manifest.json), [table reproduction](../runs/producing_extension_reproduced_v1/reproduction_comparison.json) and the [first-inspection record](PRODUCING_EXTENSION_PERFORMANCE_EXPOSURE.json).

## Primary comparison and uncertainty

Recovery minus availability NWIS is negative when recovery is better. All values below are multiplied by 1,000 for readability; intervals are paired calendar-block bootstrap intervals conditional on this system.

| Recovery window | Point difference | 7-day 95% interval | 14-day interval | 28-day interval |
|---|---:|---:|---:|---:|
| 0–6 hours | −0.057 | [−0.127, 0.018] | [−0.132, 0.034] | [−0.145, 0.047] |
| 6–24 hours | 0.070 | [0.003, 0.146] | [0.019, 0.122] | [0.016, 0.132] |

Early recovery remains inconclusive. Its cells have 120–135 pairs and 27–33 distinct events, so every cell misses the 200-pair threshold and some miss 30 events. Later recovery shows a small adverse difference, about 0.131% of availability NWIS, across all three block lengths. Later cells contain 412–429 pairs and 45 events. These are dependent replay/horizon observations, and the conclusion is neither a population-site claim nor a test of practical equivalence. [Contrasts](../runs/producing_extension_v1/analysis/Contrasts.csv), [cells](../runs/producing_extension_v1/analysis/Cells.csv).

## Forecasting controls and point gates

All fifteen outputs remain in the [method table](../paper/extension_evidence_v1/extension_methods.tex). Across the same 24,258 primary failure/recovery pairs per method, availability has the smallest descriptive point NWIS (0.056690); recovery is 0.056716, physical context 0.056706 and raw quantile HGB 0.056915. Geometric persistence, previous-day forecasting and latest-value persistence score 0.103386, 0.103471 and 0.124522, respectively. Thus the original Colorado system-4 persistence advantage does not generalize to system 10. No selected significance comparison across all method rankings is claimed. [Summary](../runs/producing_extension_v1/analysis/Summary.csv).

Recovery calibration increases empirical 90% coverage from 84.96% to 91.40%, while the normalized median absolute error remains 0.103033 by construction. This is a coverage adjustment, not a repaired median or evidence of the incremental value of recovery grouping. Recovery NWIS is 0.0171% worse than physical-context NWIS over failure/recovery, failing the proposed 5% improvement gate. Clean NWIS decreases by 0.000002622 against a tolerance of 0.001050804, satisfying the separate clean point gate. Passing clean or coverage diagnostics does not offset the absent improvement signal. [Gate arithmetic](../paper/extension_evidence_v1/engineering_gate_facts.csv).

## Declared sensitivities and mechanism checks

For joint-gradual combined recovery, 1,000 times recovery-minus-availability NWIS is 0.026 [−0.040, 0.101] with seven-day blocks. Full minute-end alignment gives 0.027 [−0.038, 0.104], the five-minute receipt margin 0.026 [−0.039, 0.099], and privileged labels 0.026 [−0.041, 0.100]. All corresponding 14/28-day intervals also include zero. Privileged labels are an information-access diagnostic and do not enter deployable rankings. All isolated-loss and asynchronous-order combined-recovery intervals also include zero. [Full contrasts](../runs/producing_extension_v1/analysis/Contrasts.csv).

The secondary early-recovery contrast against physical context narrowly favors recovery with seven-day blocks, but includes zero with 14/28-day blocks. The matched availability primary comparison remains inconclusive in this early window. Reporting the secondary result alone would overstate a recovery-specific contribution.

The predeclared bright-zero exclusion removes 99 primary failure/recovery pairs (24,258 to 24,159); it does not remove positive near-idle readings. Under this diagnostic population, the primary early contrast still includes zero and the late contrast still favors availability across all three block lengths. Recorded AC remains the main target, including zeros. No target exclusions were added after results.

In joint-gradual early recovery, the implemented rule has no insufficient-score fallback but uses the global pool for lack of a matching state in 2.745% of pairs. Adequate total pool size therefore does not imply a populated local recovery group. Matched interruption scores on this producing system show joint loss worse than either isolated channel loss, unlike the original system-4 pattern. These diagnostics describe the fixed implementation and simulated schedules, not a universal monotonicity theorem. [Diagnostics](../runs/producing_extension_v1/analysis/Diagnostics.csv), [matched interruption comparison](../runs/producing_extension_v1/analysis/InterruptionComparison.csv).

## Consequences for the paper

The manuscript retains the auditable receipt-time replay and matched-control contribution. Its abstract, results and conclusion report that the producing-system replication also fails the recovery improvement gate and reveals a small late-recovery penalty. The original Colorado near-idle finding motivated source qualification but cannot by itself explain the extension's negative result. System-10 results remain separate from the original two-system experiment; intervals are not pooled, and the study covers two geographic settings. Qualification establishes a bounded recorded-sample target with inferred fixed MST and interval-alignment uncertainty, not certified plant or meter behavior.

The current seven-page manuscript incorporates these findings. Superseded packages have been removed from the working tree; fresh packages must identify their exact source revision. Human scientific review, authorship consent, disclosure placement and applicable release/submission decisions remain separate; no external submission or publication has occurred.
