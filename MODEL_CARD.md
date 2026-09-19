# Model card: receipt-time solar forecasting research

**Completed separate extension:** PVDAQ system 10 completed all eleven declared cases under `research/PRODUCING_EXTENSION_LOCK_V1.json`, after original-result exposure. It uses complete recorded-minute AC means, 1.12 kW DC normalization, inferred fixed MST and a full one-minute alignment sensitivity. Verification passed for 4,702,320 forecasts and 192,700 history slots; all eight analysis tables reproduced exactly. The [integrated manuscript](paper/build/manuscript.pdf) and [extension findings](research/PRODUCING_EXTENSION_FINDINGS.md) report no clear early benefit, a small late recovery penalty and failure of the 5% improvement gate. The nearby system adds no independent climate; source qualification does not certify plant behavior or meter timing.

**Scientific qualification update:** Colorado 2017 contains a prolonged near-idle recorded AC regime: 3,876/3,957 unique scored targets are below 0.01 kW on the 1 kW system. The physical cause is unresolved. It must not be treated as validation on a second normally producing system. See [the post-hoc source diagnostic and staff review](research/staff_review_v2/STAFF_RESEARCH_AND_IEEE_REVIEW.md). Frozen forecasts and primary estimates are unchanged.

**Status:** offline research implementation. The frozen 2017 evaluation is complete and passed automated final verification; analysis, exact table reproduction and measured inference timing are complete. Recovery grouping did not demonstrate a stable benefit, and all three systems missed the planned improvement gate; see [the original findings](research/FINAL_FINDINGS.md) and [extension findings](research/PRODUCING_EXTENSION_FINDINGS.md). This card describes the implemented system and must be read with the final run's verification and analysis.

## Intended use and scientific question

The system replays interrupted measured AC/irradiance streams to investigate whether recovery-age calibration groups add value beyond otherwise matched availability-aware groups. Intended users are researchers reviewing information access, missing telemetry and empirical prediction intervals. The artifact does not implement grid dispatch, fault diagnosis, available-power estimation, communications monitoring or an operational service-level guarantee.

## Inputs and outputs

Inputs are UTC-tagged hourly observations with separate measurement-end and receipt timestamps, stream identity, measured value and a stable message identifier. Static contracts specify instrument channels, unit conversions, DC capacity, coordinates, quality bounds and alignment. Missing or dropped observations remain absent. Conflicting values at a measurement end require a revision policy and are rejected by this implementation.

At each issue time the observer exposes 25 slots per stream, latest values, ages, currentness, recovery ages, transport ages and missing fractions. Known calendar and solar geometry are available; future measured irradiance is not. Model features and calibration features are explicitly separated. Forecasts contain seven nonnegative ordered quantiles, target start/end, exact issue time and actual lead, with observer health available by joining the saved feature table on origin. All model variants for a case use that same feature history except the declared privileged-label diagnostic, which changes calibration label access only.

The target is recorded hourly mean AC after clipping a signed hourly mean at zero. The first target interval has begun at issue time but has no released within-interval measurements. Primary leads to interval end are 59/119/179/239 minutes. Output units are kW; normalized scores and widths divide by static DC capacity, not estimated AC capacity or observed maxima.

## Training and evaluation provenance

Public PVDAQ systems 4902 and 4 provide two geographic sites. Primary final models fit only observed 2016 daylight targets. All inspected 2015/2016 performance is development. January 2017 supplies fresh causal calibration warmup; the final evaluation begins February 1 after a four-hour no-forecast gap. Source objects, normalized variants, code and configuration were hash-locked before final predictions.

Seven quantile HGB fits per horizon use a development-selected fixed profile. An adapted training-only donor-imputation model, carry-forward model and three dressed persistence/previous-day controls provide alternative forecasts. Calibration uses rolling or weighted signed scores and repairs intervals around a fixed median. The mask blend is not CP-MDA or distributional-imputation conformal prediction; the physical kernel is not a full CACP reproduction; bounded ACI differs from the original unrestricted algorithm. See [the method crosswalk](research/CLOSEST_METHOD_CROSSWALK.md) and [frozen protocol](research/FINAL_EVALUATION_PROTOCOL.md).

## Known limitations and failure modes

- Receipt times and failure schedules are simulated, not measured communications logs. Real failure frequency and correlations with weather are not estimated.
- The original two sites plus the nearby producing-system extension and one evaluation year cannot establish broad geographic or long-term generalization. Repeated seeds reuse weather.
- Colorado's timestamp interpretation is qualified; an alternate one-minute alignment is evaluated. Tighter bounds do not establish the correctness of any individual instrument reading.
- Recorded zeros may reflect physical shutdown, curtailment, measurement problems or other unknown causes. They remain in the main target. The bright-zero sensitivity changes scoring eligibility only.
- Local calibration pools can be sparse, especially after permanent loss. Fallback rates and effective support are part of the evidence, not hidden implementation details.
- Clipped alpha, capped empirical ranks, interval repair, rolling windows and non-exchangeable missing labels preclude an automatic formal coverage guarantee.
- Nighttime predictions are zero, and the main performance endpoint is daylight-only. The output is not a calibrated nighttime distribution of possible sensor errors or parasitic consumption.
- Imputation uncertainty uses a specified approximation and fixed donor budget. It does not prove that missingness is ignorable or that all unobserved states are supported by the training donors.
- Cross-site weights use static target metadata and local causal calibration; this is not wholly unadapted deployment.

## Verification and maintenance

The freeze record covers 83 files and records 55 passing pre-evaluation tests. A later independent analysis-test module adds three checks for common-weather resampling, equal-cell weighting and matched scoring counts. A fresh isolated dependency environment passed all 58 tests and exactly reproduced the synthetic measurement, feature, forecast and diagnostic DataFrames from the reference environment. That is automated same-machine reproduction, not a second person's review or a full-data independent rerun.

The complete 49-case final run passed `research.verify_final_evaluation`: 14,106,960 forecast records and 874,300 directly looked-up visible history slots. The verifier recomputed score arithmetic, checked source targets, quantile validity, calibration median invariance, scheduled phases, scoring eligibility and receipt-gated update counts, and verified the scientific dependency hashes and original PRD bytes. Exact scope, source hashes and limits are in `runs/final_2017_v4/verification.json`. This is automated verification, not independent human reproduction or proof of every modeling assumption. Any scientific change after final performance exposure needs a dated amendment and a fresh run identifier. Historical failed experiments and original PRD bytes remain preserved.

Human authors must review the scientific claims, source attribution, disclosure, authorship and release terms before external submission. No model or artifact has been externally published by this work.
