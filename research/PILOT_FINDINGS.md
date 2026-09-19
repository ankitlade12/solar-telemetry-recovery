# First implementation milestone — September 11, 2026

**The real-data pipeline works, but the proposed recovery calibration has not demonstrated an advantage.** Continue with data and method development; these results do not support a paper performance claim yet.

## Completed

- Acquired and hash-verified a full source-calendar year of NIST PVDAQ data: 364 daily partitions plus metadata, approximately 111 MB compressed.
- Identified measured DC power and measured POA irradiance, corrected the risk of treating a raw millivolt GHI channel as calibrated irradiance, and built a strict hourly adapter.
- Implemented receipt-gated features, delayed calibration labels, asynchronous restoration, backfill and permanent-loss replay.
- Trained 28 frozen quantile models: seven quantiles at each of four horizons.
- Compared five methods in seven original scenarios: 618,240 issued forecast records. Added an exploratory daytime-restoration follow-up with 88,320 records, for **706,560 total**. These are overlapping forecast records, not independent observations or experimental replicates.
- Passed **19 tests** and the main run's independent saved-output integrity checks. Inspected the recovery and event figures. The original PRD's SHA-256 remains unchanged.

## Findings that change the research plan

**Data completeness is inadequate for a strong benchmark.** Only 3,077 of 4,404 geometric daylight hours have valid DC targets under the strict rule. June has none; November has only 42 valid hours across day and night. Only eight of the original development period's 13 scheduled recovery events have scorable daylight targets. Missing-target performance is unknown. A separate AC meter improves completeness, but its semantics and sign convention still need validation. See [the data feasibility report](PVDAQ_DATA_FEASIBILITY.md).

**The original fault schedule restored telemetry at night.** That is a weak test of immediate daytime recovery. The follow-up shifts the schedule twelve hours earlier, putting all 52 scheduled full restorations in daylight. This change was made after inspecting the first schedule and is explicitly exploratory. See [the daytime results](../runs/nist_2015_daytime_probe_v1/README.md).

**The recovery calibrator is inactive on the measured daytime recovery slice.** It makes zero nonzero corrections across 336 scorable development recovery forecasts. Its normalized WIS is the same as raw quantiles and rolling calibration to the reported precision. The first six recovery hours have 99.26% coverage for nominal 90% intervals, suggesting the intervals are already broad. The current method can only widen them. This is a finding about the present implementation and setting, not proof that recovery conditioning is useless. See [the calibration diagnostics](../runs/nist_2015_daytime_probe_v1/DIAGNOSTICS.md).

**Backfill policy matters to the research question.** Instant complete backfill can immediately restore a frozen model's historical features to the clean-delivery state. Any remaining degradation then comes from calibration history and native gaps, rather than necessarily from the base forecast. Gradual backfill, permanent missing history and normal receipt delays need separate experiments. The original pilot includes permanent loss, but the daytime probe only tests complete backfill.

**Calibration and evaluation currently target different hour distributions.** Calibration uses all available hours; primary evaluation uses daylight. Together with broad base intervals and limited state-matched support, that can make correction inactive. It must be investigated before claiming calibrated daytime reliability.

## Next work, in order

1. Validate the separate AC-meter target and find better independent site/year data. Resolve units, interval alignment, signed measurements, native gaps and catalog QA flags; do not splice AC and DC into one target.
2. Improve the probabilistic baseline on development data and examine daylight-matched calibration and coherent interval shrinkage as well as expansion. Measure whether the resulting baseline has a recovery problem worth solving.
3. Implement the missing adaptive-conformal, mask-conditional and imputation comparators; align information access, tuning budgets and forecast origins.
4. Freeze the experimental protocol before opening new evaluation data. Include daylight and nighttime restoration, multiple fault seeds/durations, receipt delays, gradual backfill, permanent loss and ablations.
5. Assess WIS, conditional coverage, width, support and recovery-time estimates with event/site-level uncertainty. Draft the paper around whatever the evidence supports, including negative findings.

## Review and reproduce

- [Main run report and figures](../runs/nist_2015_pilot_v1/README.md)
- [Main run integrity verification](../runs/nist_2015_pilot_v1/verification.json)
- [Daytime follow-up](../runs/nist_2015_daytime_probe_v1/README.md)
- [Paired recovery and calibration diagnostics](../runs/nist_2015_daytime_probe_v1/DIAGNOSTICS.md)
- [Repository setup and commands](../README.md)
- [Full venue and literature assessment](CCWC_Research_Assessment.md)

No final-test result, statistical significance, theoretical coverage guarantee, novelty demonstration or manuscript submission is claimed.
