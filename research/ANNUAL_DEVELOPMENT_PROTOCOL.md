# Annual AC development comparison, version 3

This protocol was written during method development, before the annual baseline run completed. It is **not** the frozen final-evaluation protocol. All inspected 2015–2016 data and results remain development evidence. No 2017 forecasting results have been accessed.

## Question and evidence standard

Does recovery from interrupted PV and irradiance delivery create a forecasting/calibration failure that remains after credible missing-input and temporal baselines? A recovery-specific method must improve on an otherwise matched context/recency method, not merely on uncalibrated intervals. If it does not, report the negative finding and assess whether the controlled delivery experiment itself supports a useful empirical paper. Do not promise an algorithmic contribution or acceptance.

## Data and timing

Use the measured AC and POA channels specified in `data_v2.py` for geographically separate NIST Maryland (PVDAQ 4902) and Colorado (PVDAQ 4). The AC target is the nonnegative component of a signed hourly meter average, normalized for scoring by documented DC nameplate capacity. It is neither inverter DC power nor normalized by a test-period maximum. Raw objects and normalized inputs have SHA-256 checksums and retained contracts. Small negative irradiance is retained within explicit engineering bounds.

NIST uses source UTC checked against fixed EST; Colorado UTC is derived from the documented seven-hour offset. Colorado minute alignment is incompletely documented, so its timestamp-bin definition and sensitivity remain limitations. The source provides measurement timestamps, not operational receipt logs. All delivery times are simulated.[^1][^2]

For the new experiments, a bin ending HH:00 is normally released at HH:01. Forecasts issue at HH:01 and target bins ending HH+h:00, h = 1, 2, 3, 4. Endpoint lead times are therefore 59, 119, 179 and 239 minutes. For h=1, one minute of the target bin has elapsed; no measured value from that bin is exposed. Every forecast record stores both issue time and exact target end. Calibration matches the latter and waits for its recorded receipt. Never describe these as exact 60/120/180/240-minute leads.

Training features start January 3, 2015, after a history warmup. Fit only against observed targets ending by January 1, 2016 UTC. The donor bank also ends at this cutoff. January 2016 is a warmup/diagnostic period, February–June selects profiles, and July–December provides further development diagnostics. Target bins crossing a period boundary are excluded from that period's score. Training cutoffs and input data contracts are checked programmatically.

## Input and delivery design

Every model sees completed hourly slots at lags 1–24 and 48 for each stream, visible ages/current flags, missing fractions, last received values, transport ages, calendar features, and known target solar geometry. The forecasting model excludes explicit time-since-recovery features to isolate the later calibration experiment. Solar geometry is calculated from location and clock time, without future measured irradiance or weather.

Train on clean history and three independently seeded delivery augmentations: joint 12-hour interruption with immediate backfill, 24-hour PV-only permanent loss, and 24-hour joint interruption with irradiance first by three hours and gradual backfill. Repeated augmentations do not create additional independent target observations; both row counts and unique target counts are reported.

Evaluation scenarios share calendar-only random start times across all 24 UTC hours, spaced seven days apart, with seed 20261011. Main interruptions last 12 hours, with a three-hour channel-restoration gap where applicable. The eight scenarios are clean, PV-only, irradiance-only, joint/immediate, joint/gradual, joint/permanent loss, irradiance-first/gradual, and PV-first/gradual.

Immediate backfill releases the entire historical queue at restoration. Gradual backfill releases oldest first at 15-minute spacing, starting 15 minutes after restoration. New live observations bypass that queue. Permanent loss drops interrupted observations. Missing source observations are never synthesized by the scheduler. The feature builder cannot inspect fault plans, and hidden targets are first joined after predictions have been constructed. Recovery phases are evaluator annotations, not future restoration information supplied to models.

## Forecast baselines and selection

1. **Native-missing quantile gradient boosting.** Separate models for seven quantiles and four horizons; nonnegative, sorted outputs. Two profiles: 150 iterations/15 leaves and 250 iterations/31 leaves, both learning rate 0.05, minimum leaf 40, no random early-stopping split, fixed seed.
2. **Residual-dressed persistence.** Last received PV plus training residual quantiles in three target-solar strata. The geometric variant multiplies the last received value by a target-to-last-observed solar-sine ratio, denominator floor 0.1 and ratio cap 3. This is an explicitly specified geometric approximation.
3. **Single- and multiple-imputation input baselines.** Training-only 50-neighbor donor sets; mean-imputed training inputs; two point-model profiles matching the tree budgets above; 10 stochastic test-input completions versus a deterministic mean completion. Normal intervals combine training residual MSE with between-imputation variation for the multiple-input variant.[^3]

The imputation comparator adapts the published Setup 2: it retains observed training targets, extends donor conditioning to missing irradiance and joint gaps, uses gradient boosting and extra causal features, and fixes k=50. It is not a reproduction of the paper's models, tuning procedure or train-and-test multiple-imputation setup. Observed input entries are unchanged. Joint gaps sample paired PV/irradiance donors using calendar/solar geometry; PV-only gaps condition on available irradiance and irradiance-only gaps on available PV. No evaluation targets are imputed.

Within each site and model family, select the profile with lowest validation daylight normalized WIS, averaging equally over scenarios and horizons. SI and MI select independently; their matched-profile comparison is also retained. Fixed architecture differences mean equal tree-profile budgets do not imply equal total computational cost. Training residual variance may underestimate uncertainty, and the normal approximation can fail; these weaknesses must be visible in coverage and width, not hidden by selective reporting.

## Reporting and outstanding gates

Report WIS, median absolute error, 50/80/90% coverage, 90% width, target eligibility and event counts by site, horizon, scenario and phase. Recovery is split into 0–6 and 6–24 hours after full live-stream restoration, regardless of queue completion. Phase labels describe the injected schedule even when natural data gaps remain; observable stream state is retained separately. Do not treat hourly forecasts, repeated augmentations or nearby arrays as independent replications.

Before final evaluation, complete matched context/mask/recency/delayed-adaptive calibration; paired event-level analysis; multiple schedule seeds and interruption durations; timing/quality sensitivity; and an immutable final protocol. The existing bounded ACI variant is empirical and does not inherit the original algorithm's guarantees. Signed CQR scores and weighted temporal variants likewise require an explicit distinction between empirical coverage and exchangeability-based theory.[^4][^5]

All run directories preserve code snapshots, configuration, source hashes, fitted local model artifacts, prediction records, exact schedules and summary tables. Models are trusted local pickle files; do not load externally supplied pickle artifacts. The original PRD remains unchanged. External submission and author contact are not part of this run.

## Sources

### Development amendment: daylight fitting and stochastic prefix invariance

The first all-hour annual run completed 4,497,408 forecasts. An audit of all 112 quantile fits found all eight NIST median models constant at zero before rearranging quantiles. At zero initialization, the pinned scikit-learn 1.8.0 pinball loss returns identical gradients for zero and positive targets; this explains why the zero-heavy target distribution can prevent meaningful splits. The observed fit failure is recorded in `runs/annual_ac_baselines_v3/quantile_fit_audit.json` and its CSV, with a direct gradient probe and the [pinned upstream source](https://github.com/scikit-learn/scikit-learn/blob/1.8.0/sklearn/_loss/_loss.pyx.tp). This failed baseline cannot support superiority claims.

The corrected comparison restricts **all baseline families** to daylight training targets, using clock/location geometry available at issue time. It retains nighttime observations in lag histories. Nighttime predictions are set to zero and explicitly outside the scored/calibrated scope. No target value or model error determines the daylight filter. Both tree profiles are refitted and selected anew on the same development interval; 2017 remains untouched. Per-quantile training standard deviations and crossing rates are recorded to detect further degenerate fits.

A second audit found that a sequential pseudorandom generator made imputation draws depend on the number/order of other rows in a prediction batch. Although no future target values were used, changing future missingness could change an earlier realized stochastic prediction. The sampler now uses a fixed 64-bit mixing rule keyed only to forecast origin, lag, missingness type and imputation round. Regression tests check equality under future-row extension, future-mask changes and reversed batch order. Fitted trees and donor banks can be reused because training uses deterministic mean imputation; any such reuse records the original model and manifest checksums. Earlier predictions are preserved and superseded explicitly.

[^1]: Open Energy Data Initiative, [PVDAQ documentation](https://github.com/openEDI/documentation/blob/main/pvdaq.md), dataset [DOI 10.25984/1846021](https://doi.org/10.25984/1846021). Public catalog and acquired per-system metadata, inspected September 11, 2026.
[^2]: M. Boyd, [Performance Data from the NIST Photovoltaic Arrays and Weather Station](https://nvlpubs.nist.gov/nistpubs/jres/122/jres.122.040.pdf), 2017; NIST [data dictionary supplement](https://www.nist.gov/document/datadictionarysupplementalcontentpdf).
[^3]: Pashmchi, Benoit and Kanagawa, [Predictive Uncertainty in Short-Term PV Forecasting under Missing Data: A Multiple Imputation Approach](https://arxiv.org/abs/2603.15564), 2026, preprint. Adaptations are specified above.
[^4]: Romano, Patterson and Candès, [Conformalized Quantile Regression](https://arxiv.org/abs/1905.03222), 2019.
[^5]: Gibbs and Candès, [Adaptive Conformal Inference Under Distribution Shift](https://arxiv.org/abs/2106.00170), 2021.
