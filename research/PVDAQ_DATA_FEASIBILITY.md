# PVDAQ feasibility and initial execution — September 11, 2026

The real-data replay pilot is implemented, with NIST system 4902 selected for its identifiable co-located DC-power and measured irradiance channels. **This 2015 slice passes the initial sensor/unit gate but fails a strong year-round completeness gate.** Use it to validate causal replay and expose weaknesses; obtain better independent data before making a conference-paper performance claim.

## Acquisition and provenance

The public [PVDAQ data description](https://github.com/openEDI/documentation/blob/main/pvdaq.md) identifies system metadata, sensor metrics and daily measurement partitions. The [dataset record](https://data.openei.org/submissions/4568) gives DOI `10.25984/1846021`; the [Data.gov catalog](https://catalog.data.gov/dataset/photovoltaic-data-acquisition-pvdaq-public-datasets) lists CC-BY 4.0. Attribute PVDAQ and the contributing NIST measurement system in the paper and any redistributed derivative. Original instrument certificates and upstream cleaning were not independently verified.

The local snapshot contains 364 daily 2015 partitions plus system metadata and sensor metrics, approximately 111.4 MB compressed. `data/raw/pvdaq_4902_2015/manifest.json` records each public object key, byte count, ETag and SHA-256. Its missing calendar partition and native source gaps are not filled. The normalized snapshot retains the explicit UTC field, so the catalog's ambiguous numeric timezone is not used to localize timestamps.

Sources: [inspected local catalog snapshot](../data/metadata/systems_20250729.csv), [NIST system metadata](https://oedi-data-lake.s3.amazonaws.com/pvdaq/csv/system_metadata/4902_system_metadata.json). Exact measurement and metadata object paths are authoritative in the acquired manifest.

## Sensor selection

| Quantity | Metric ID | Native sensor label | Units / treatment |
| --- | --- | --- | --- |
| Forecast target | 82610 | InvPDC_kW_Avg | kW; hourly mean inverter DC power |
| Historical irradiance feature | 82595 | RefCell1_Wm2_Avg | W/m²; measured plane-of-array reference cell |
| Rejected direct irradiance input | 82593 | Pyra1_mV_Avg | mV; raw GHI-channel voltage cannot be assumed to be W/m² |

Selected channels have average aggregation, unit scale 1 and offset 0. The matched inverter and reference-cell instrument metadata specify left-aligned samples. A timestamp at 10:00 represents the minute beginning 10:00; the completed 10:00–11:00 hourly average is timestamped 11:00. The adapter checks these metadata expectations before processing.

The 270.7 kW DC nameplate normalizes WIS; it is not used to cap predictions or observations. The measured maximum hourly DC power is 282.18 kW. The maximum retained POA irradiance is 1,073.97 W/m². These descriptive ranges are not a calibration certificate or a physical consistency proof.

## Quality gate

There are 951,147 selected minute rows, 38 exact duplicate rows, and zero conflicting timestamp/metric pairs. Negative or nonfinite readings total 98,227; the negative values are dominated by apparent invalid-value sentinels (−999 in power and −300 in irradiance). The policy excludes all negative/nonfinite values without silently replacing them with zero. Legitimate reported zero remains zero. An hourly value requires 60 distinct valid minute samples for that stream; there is no interpolation or target imputation.

| Subset | Hourly bins | Valid PV | Valid irradiance | Both valid |
| --- | ---: | ---: | ---: | ---: |
| All hours | 8,760 | 6,272 | 7,332 | 6,270 |
| Geometric daylight | 4,404 | 3,077 | 3,675 | 3,075 |
| Geometric night | 4,356 | 3,195 | 3,657 | 3,195 |

Only about 69.9% of daylight hours have a scorable PV target. June has zero usable PV hours, November only 42, and May only 143. These gaps are a material selection limitation: observed-target metrics say nothing about the unknown targets. Do not claim full-year coverage, robustness to physical outages, or unbiased performance during naturally missing periods.

Geometric daylight is solar elevation above zero at the target-hour midpoint using [NOAA's documented approximation](https://gml.noaa.gov/grad/solcalc/solareqns.PDF). An hourly interval classified as night can straddle sunrise/sunset, so nonzero twilight averages are possible. It is a fixed evaluation convention, not a weather-derived target mask.

The catalog labels system 4902 `pass` but also flags clipping, less than one year after filtering, a mounting-configuration issue requiring review, and correlation below 0.5. A `pass` string does not override those flags. The public catalog's QA flags apply to its processing scope, which need not match this adapter or 2015 slice. Inspect them before publication.

Reproduce all completeness numbers with `python3 -m research.audit_pilot_quality`; the machine-readable result is `research/pvdaq_pilot_quality.json`. Month bins use UTC and therefore include six interval-end timestamps in January 2016; the downloaded partitions describe source-local 2015. The pilot excludes origins at or after its configured UTC evaluation end.

## Other inspected candidates

| System | Finding | Decision for this initial pilot |
| --- | --- | --- |
| 34 — Las Vegas Building A | Power and measured POA are present; power naming, scale metadata and interval alignment need reconciliation. | Defer; do not assume the scale is already applied. |
| 1332 — NREL parking garage | Inspected sensor metadata contains power but no identified irradiance channel. Catalog also has multiple configuration rows and QA flags. | Not eligible as a co-located two-stream site on current evidence. |
| 1272 — residential New Orleans | Four-channel catalog entry, QA fail; location is not Colorado. | Exclude from this first selection. |

These are inspection outcomes, not claims that no additional valid public sites exist. Additional years, sites and channels remain to investigate.

A follow-up audit within the acquired NIST snapshot also inspected inverter AC metric 82607 and separate meter AC metric 82633. The inverter AC channel has the same 6,272 valid hours and 3,077 valid daylight hours as inverter DC. The separate meter has 7,088 nonnegative complete hours and 3,460 valid daylight hours; it includes 607 hours in June and 699 in November. This is a promising alternative channel, but AC versus DC target semantics, meter sign convention, instrument alignment and remaining missingness need validation before use. It has not been substituted into the running DC experiment. Reproduce with `python3 -m research.audit_alternative_power`; results are in `pvdaq_alternative_power.json`.

## What the replay can establish

The adapter separates physical interval time from synthetic receipt time. Normal receipt at the completed hour boundary is an explicit assumption because the public data do not contain operational arrival logs. Scheduled communication faults delay or permanently discard receipts; they never modify the hidden target. Features use only delivered observations, preserve lag time slots and distinguish live restoration from old backfill. PV calibration labels enter once at their simulated receipt time and are scored against the original forecast's base intervals and origin state.

The first run compares five methods over seven delivery scenarios and 1–4-hour horizons. It is a development experiment with fixed choices, not a preregistered confirmatory benchmark. Observed native gaps coexist with injected faults and can outlast their scheduled restoration. Report evaluator phases separately from observable recovery features.

## Next decision gates

1. Inspect the pilot's WIS, coverage, width and calibration support; report improvements and regressions together.
2. Establish a better independent site/year pool, sensor provenance and exclusion-sensitivity analysis before final experimental design.
3. Freeze the contribution and protocol, including untouched evaluation data, then implement the strongest missing comparators and ablations.
4. Use repeated event schedules and event/site-level uncertainty; overlapping hourly forecasts are not independent replicates.
5. Draft the paper around verified evidence. The existing CCWC assessment remains the venue and literature reference; this pilot does not establish novelty or acceptance readiness.
