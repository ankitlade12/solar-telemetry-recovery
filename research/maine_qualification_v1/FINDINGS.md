# Maine source qualification: not admitted to the producing-site extension

The quarter-hour source checks completed successfully. Maine PVDAQ 1239 is useful for further source investigation, but is **not yet qualified as the additional normally producing site** requested by the staff review. This decision is based on source semantics and seasonal operating behavior, without fitting or scoring forecasts. The original experiment and its results remain unchanged.

## What is supported

The catalog identifies a 20.16 kW DC system at Presque Isle, Maine. Channels 3015 (AC), 3018 (POA irradiance), and 3022 (cumulative energy) were checked against every object in the acquired 2016/2017 manifests. Selected timestamp/channel pairs have no conflicts or identical duplicate rows. Both principal channels have observations in every month and a dominant 15-minute grid.

Channel 3015 has raw units kW, calculated units W, and scale 1000. Applying that transform and expressing the result in kW leaves the stored value unchanged. Positive consecutive energy-counter increments support this interpretation: observed-to-integrated energy ratios are 0.99869–0.99877 in 2016 and 0.99990–1.00006 in 2017, over 12,035 and 11,882 eligible intervals respectively. This is a consistency diagnostic on selected positive intervals, not a calibrated energy-meter accuracy certificate. The two channels may share instrument processing.

The diagnostic hourly construction requires four valid expected quarter-hour records per channel. An extra off-grid record makes its channel-hour ambiguous and therefore missing. Signed AC is averaged before clipping its mean at zero. Bounds are AC in [-5%, 150%] of DC capacity and POA in [-20, 2000] W/m². Missing values remain missing; all discarded observed records are retained in `excluded_records.csv` with reasons.

Under the fixed-EST, left-aligned diagnostic convention, paired daylight support is 4,368/4,416 hours (98.91%) in 2016 and 4,320/4,405 (98.07%) in 2017. Every month exceeds the predeclared 70% screen: the lowest monthly support is 96.08%, in August 2017. The right-aligned alternative gives similar support. These are diagnostic counts, not admitted experimental targets.

## Clock evidence and remaining interval ambiguity

Every civil daylight-saving transition date in both years has 96 paired on-grid quarter-hour records. At recorded timestamps shifted to UTC by adding five hours, there are zero POA >20 W/m² observations in geometric night in 2016 and one in 2017. The corresponding civil-Eastern interpretation yields 514 and 510. This supports a fixed EST interpretation; it does not establish the clock from an operator log.

The names `fixed_utc_plus_5` in the CSVs mean **UTC = native time + 5 hours**, i.e. native UTC−05:00. They do not mean that the site is east of UTC.

The catalog labels AC aggregation as `avg`, but the interval-alignment metadata are blank. Trapezoidal integration matches energy increments more closely than either adjacent quarter-hour value alone (MAE 0.15881 versus 0.26217/0.26439 kWh in 2016; 0.13051 versus 0.21788/0.21788 in 2017). That does not prove the source values are instantaneous samples: common instrument processing, offsets and rounding remain possible. The left/right diagnostic variants do not resolve the physical interval convention. They must not be promoted to a verified hourly energy average.

The [official PVDAQ schema](https://github.com/openEDI/documentation/blob/main/pvdaq.md) distinguishes raw/calculated units, aggregation type, and left/center/right acquisition alignment. Its general description cannot fill missing site-specific metadata. Accessed September 13, 2026.

## Winter behavior prevents an unqualified producing-site claim

The annual bright near-idle fraction is 7.31% in 2016 and 9.94% in 2017 for the left-aligned construction, slightly below the provisional 10% annual flag. Passing an annual aggregate does not establish normal operation throughout the year. The plan also requires no unexplained dominant near-idle regime; monthly inspection reveals one:

| Month | Bright hours (POA >200 W/m²) | AC below 1% of capacity | Fraction |
|---|---:|---:|---:|
| December 2016 | 38 | 38 | 100.00% |
| January 2017 | 72 | 61 | 84.72% |
| February 2017 | 123 | 96 | 78.05% |
| December 2017 | 62 | 50 | 80.65% |

The right-aligned alternative retains the same qualitative concern. Several early-2016 months also exceed 10%. Snow, obstruction, shutdown, instrument behavior, or other causes are possible; none is established by these observations. No winter targets have been removed, no alternative threshold was selected to admit the site, and no favorable season has been substituted for the full evaluation year.

## Decision and next action

Status: **pending metrological and operating-regime qualification; not admitted under the current producing-site plan**. Coverage and scaling pass their descriptive checks; interval semantics and winter behavior remain unresolved. A future study explicitly about recorded sensor averages or mixed operating regimes would require a separate estimand and protocol. It would not retroactively validate this source for the present purpose.

Continue with the already declared reserve, system 10, using its cataloged aggregate AC/POA channels. Its nearby Colorado location must be described honestly: an additional instrument/system, not an independent climate. Record its source-only findings whether favorable or unfavorable. No new forecast should be run before source qualification and a separate extension protocol.

## Reproduction and evidence

Run `python3 -m research.qualify_maine_sources` from the repository root into its declared, previously nonexistent output directory. Existing output is deliberately refused. The exact executed script hash, source-manifest hashes, plan hash, and twelve diagnostic output hashes are recorded in `manifest.json`; this findings document is a subsequent interpretation and is covered by `decision.json`.

Evidence tables: `annual_quality.csv`, `monthly_quality.csv`, `grid_audit.csv`, `energy_consistency.csv`, and `clock_diagnostics.csv`. Quarter-hour and diagnostic hourly parquet files preserve the intermediate values needed to check the counts. This is an author-side scientific source audit, not official IEEE approval.
