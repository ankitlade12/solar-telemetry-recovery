# Producing-system replication: separate post-exposure extension

Status: design recorded before system 10 model fitting or forecast scoring; **not yet executable/frozen**. An adapter and dependency verification remain necessary before the new lock. This document does not amend `FINAL_PROTOCOL_LOCK.json` or recast any original result as untouched.

## Question and source

Does the lack of stable incremental benefit from the implemented recovery grouping persist on an additional archive with a productive recorded-AC regime? This is a fixed-method replication, not a claim of a new forecasting algorithm or superiority to unimplemented external methods. PVDAQ system 10 was the reserve in the source-only qualification plan; Nevada 1367 remains ineligible under its selected channel/year plan and Maine 1239 remains pending because of winter operating-regime and interval questions. Preserve all three decisions.

Use system 10's full 2016 training and 2017 replay/evaluation years, AC 423, POA 421, capacity 1.12 kW DC. Its recorded-sample target, inferred fixed-MST clock, engineering bounds, completeness rule and limitations are specified in `reserve_10_qualification_v1/FINDINGS.md`. The final adapter must preserve full native-year boundary bins, reject conflicting cross-year values and verify the source/qualification hashes. Do not treat the existing diagnostic hourly files as a final contract without this adapter.

The site is adjacent to original Colorado system 4. Report per-system results and dependence-aware uncertainty; do not count it as an independent climate or add its replays to an artificial independent-row sample. Qualification inspected source distributions, including 2017 AC, but no forecasting performance. Thus even before considering earlier original-study exposure, this is not a claim of a completely unseen source distribution.

## Fixed replication design

Carry forward original version-4 training, augmentation, model, calibration, horizon, scoring and bootstrap settings exactly, with the following explicit scope:

- Train only on observed 2016 daylight targets; fitting starts January 3, and targets end by January 1, 2017. Replay starts January 3, 2017 with empty calibration state; January is warmup. Preserve the February 1 00:00–04:00 UTC issue gap and evaluate from 04:01 UTC through eligible year-end targets.
- Use the original seven quantile levels and four horizons, flexible HGB settings, seed 20260911, compact imputation configuration and deterministic training augmentations. No model family, hyperparameter or channel selection on extension results.
- Run all eight original primary receipt scenarios with their original seed and fifteen outputs. In particular, retain recovery, matched availability, physical calibration, raw forecasts, and previous-day/geometry-adjusted persistence.
- Add exactly three joint-gradual sensitivities: the full one-minute alignment-shift train/replay pipeline, five-minute normal receipt margin, and privileged label delivery. The last is an information-access diagnostic, excluded from deployable rankings. Use the original five sensitivity outputs. No old-weight or other-site transfer is needed for this bounded replication.
- Primary target is the declared recorded AC, observed daylight only. Retain zeros and positive near-idle readings. Missing labels remain absent. The existing exact-zero/bright-POA population may be reported as the original secondary diagnostic; do not introduce a post-result near-idle exclusion.
- Primary contrast is recovery minus matched availability NWIS in 0–6 and 6–24 hour recovery windows, equal-weighted over supported original faulted cases/horizons. Report both windows together. Also retain the original combined recovery, interruption, clean, and recovery-minus-physical summaries.
- Use the original 7-day nonoverlapping calendar-block bootstrap with 10,000 replicates, seed 20260912, and 14/28-day sensitivity. Scenarios and horizons sharing weather remain together within resampled calendar blocks. Intervals describe this fixed system, not a site population. If a future table pools systems, it must resample a shared calendar jointly; the existing separate-system bootstrap cannot justify a pooled independent-site interval.
- Retain the original 5% improvement point gate against physical calibration, clean tolerance, empirical coverage diagnostic, and 30-event/200-pair support flags. Passing a point gate is not a significance or acceptance guarantee. Report the relative improvement denominator and all unfavorable outcomes.

## Verification and reporting

Before execution, create a separate machine-readable configuration and extension lock covering this protocol, adapter, exact original reused source dependencies, input contracts/hourly hashes and environment. Authenticate the unchanged parent 83-file lock. A wrapper must say explicitly that this is an extension; it must not overwrite the original runner, lock or results.

Adapter verification must check a raw productive hour, W-to-kW scaling, complete-hour requirements, negative-mean handling, cross-year merge behavior and both alignment variants. Check the new executable configuration includes only the declared site/cases and carries unchanged fixed settings. Tests should target real risks in the adapter/extension boundary; the original forecast engine's unchanged test history remains relevant.

After forecasting, run receipt/label/target verification on the extension artifacts before interpreting performance. Record any tool assumptions that only support original site names and repair them outside the original freeze with explicit scope. Reproduce summary tables and verify claim-to-source rows before modifying the paper's numerical narrative.

Record performance exposure before reading scores. Any later repair or new analysis belongs in the post-freeze log with its affected files and exposed scope. A positive replication is not guaranteed, and additional architectures will not be added merely because the fixed replication is unfavorable. Only a completed, verified result may enter a revised manuscript or package. Human author consent, independent second-contributor reproduction and final CCWC submission gates remain separate.
