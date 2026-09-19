# Reserve system 10: passes producing-regime screen with a bounded target contract

PVDAQ system 10 passes the predeclared all-month coverage and bright near-idle screens. It can support a **separate replication of recorded-AC forecasting**, subject to the explicit timestamp-bin target and alignment sensitivity below. It is not certified as a physical production meter, and its nearby Colorado location does not provide a third independent climate. No forecast performance has been inspected for this system.

## Verified scope

All 723 daily objects and four accompanying catalog/metadata objects in the acquired 2016/2017 manifests were hash-checked. The preselected channels are aggregate AC 423 and POA irradiance 421. Both have a nominal 60-second cadence, no conflicting or identical duplicate timestamp/channel rows, no populated UTC fields, and no off-minute records. Raw AC is in W with scale 1/offset 0; it is divided by 1000 to express the recorded target in kW. Catalog capacity is 1.12 kW DC, at latitude 39.7404 and longitude −105.1774.

The minute-level engineering bounds exclude 21 POA readings in 2016 and 27 in 2017; none of the observed AC readings fails the declared AC bounds. All such observations are retained in `excluded_records.csv`. Native missing minutes are represented as missing. A complete hourly channel requires all 60 expected valid minute records. Signed AC is averaged first, then its mean is clipped at zero; small negative POA readings within bounds are retained.

| Left-aligned diagnostic | 2016 | 2017 |
|---|---:|---:|
| Geometric-daylight hours | 4,414 | 4,401 |
| Complete paired AC/POA hours | 4,334 | 4,264 |
| Paired daylight support | 98.19% | 96.89% |
| Bright hours, POA >200 W/m² | 2,927 | 2,708 |
| Bright hours with AC <1% of DC capacity | 32 | 10 |
| Bright near-idle fraction | 1.09% | 0.37% |

Every month in both years has usable paired observations and more than 70% daylight support. The minimum is 86.85% in March 2017. The highest monthly bright near-idle fraction is 6.72%, in February 2016. Thus neither an annual nor a monthly fraction exceeds the declared 10% diagnostic flag. This screen does not prove that every remaining observation is physically accurate or that unobserved periods had normal operation.

The one-minute right-aligned diagnostic yields 4,334 and 4,265 paired daylight hours, with 31/2,924 and 10/2,707 bright near-idle hours. Its conclusion is the same. Native missingness and flagged low-output observations remain present; no favorable calendar interval was selected for forecasting.

## Clock and target qualification

At recorded timestamps mapped by UTC = native +7 hours (fixed MST), 132 of 241,218 and 150 of 236,641 POA >20 W/m² minute readings fall in geometric night. None of the POA >200 readings does. Mapping through civil Mountain time instead produces 8,935 and 8,033 low-threshold nighttime readings, including 486 and 378 at the high threshold. Fixed MST is strongly supported as a diagnostic clock convention; no operator log or recorded UTC establishes it externally.

The [PVDAQ schema](https://github.com/openEDI/documentation/blob/main/pvdaq.md) distinguishes aggregation type and acquisition-interval alignment. This source's AC/POA channels are cataloged as averages, but instrument alignment is blank. The adopted target must therefore be named precisely: **the nonnegative component of the mean of 60 recorded minute AC values in a stated timestamp bin**. It is not a verified energy integral or latent available production.

Primary construction: map timestamps using fixed MST, group the records at minutes 00–59 in a left-closed clock-hour bin, and label the result at the next clock hour. Release the complete bin no earlier than its label plus one minute in the simulator. A separately fitted and replayed sensitivity subtracts one minute before binning; an additional five-minute receipt-margin check bounds sensitivity to the release convention. These margins are modeling assumptions, not observed communications latency. They cover the declared minute-alignment alternatives; they do not establish a bound on arbitrary clock drift or undocumented sensor smoothing.

Admission is justified for this bounded recorded-sample estimand, with the unresolved physical interval meaning stated explicitly. This is the same type of recorded-AC target used in the original protocol, not an assertion that missing interval metadata have been recovered. The original experiment is unchanged. A future physical-energy or operational-availability claim would require additional evidence.

## Extension constraints

1. Record a separate extension protocol and hash lock before model fitting or forecast-performance inspection. Carry forward the fixed model and calibration settings; no tuning on this site's 2017 outcomes.
2. Retain all seasons, observed zeros, near-idle readings and native missingness under the declared bounds. Apply every comparator to the same eligible target rows.
3. Include the matched availability control and the strong previous-day baseline. A producing-system replication can test whether the earlier null result persists; it cannot retroactively rescue the original hypothesis.
4. Carry the primary/right-alignment and receipt-margin assumptions into the complete train/replay pipeline. Preserve source exclusions and cross-year boundary bins in the final adapter.
5. Keep common-calendar weather dependence in uncertainty calculations. System 10 is geographically adjacent to original system 4; it is neither another independent climate nor an independent set of weather events.
6. Label all results as a new extension declared after original-result exposure. Report negative and adverse results as well as improvements. Broader external-method superiority remains untested.

## Evidence and reproduction

`manifest.json` hashes the executed script snapshot, source manifests, reserve plan and all diagnostic outputs. `quality.csv`, `monthly_inventory.csv`, `grid_audit.csv` and `clock_diagnostics.csv` supply the counts above. `minute_2016.parquet` and `minute_2017.parquet` retain the qualified native-grid values; the four hourly parquet files are diagnostic constructions, not final experiment inputs.

Reproduction command: `python3 -m research.qualify_reserve_source`. It requires complete acquired snapshots and a previously nonexistent declared output directory. It intentionally refuses an overwrite. `decision.json` separately hashes this interpretation, so the original machine-output manifest is preserved. Official schema accessed September 13, 2026. This is an author-side source audit, not IEEE certification.
