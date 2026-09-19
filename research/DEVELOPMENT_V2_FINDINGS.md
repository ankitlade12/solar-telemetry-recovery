# Solar forecasting research development

**Two substantially more complete AC-power datasets are now qualified for development, and a controlled calibration experiment separates useful interval correction from the still-unproven recovery contribution.** The project has advanced beyond the initial feasibility pilot. A final protocol, stronger published-method comparators and an untouched evaluation remain necessary before drafting conclusive paper claims.

## Research position

The paper should investigate uncertainty under information-delivery failures: which power and irradiance observations are available when a forecast is issued, when missing labels arrive, and whether a calibration method remains useful during recovery. Missing-data forecasting and context-conditioned calibration already have close precedents; the [full research assessment](CCWC_Research_Assessment.md) documents that literature boundary. Neither adding a missingness indicator nor allowing a delayed update establishes novelty.

The active execution plan is [RESEARCH_PLAN.md](RESEARCH_PLAN.md). It targets a complete reviewable conference manuscript and reproducible artifact, with claims determined by the evidence. The current CCWC deadline is November 6, 2026; the regular-paper target is seven pages and review is double blind.[^1][^2]

## Data qualification

Sixteen PVDAQ systems were screened using sensor and instrument metadata. Three 2016 site-years were then downloaded for measurement-level qualification: NIST ground array 4902, Colorado array 4, and Maryland system 1200. All source partitions and metadata are checksummed. This screen used data availability, timestamp semantics and instrument values, not forecast performance.

The Maryland example demonstrates why a channel catalog is insufficient. Its metadata lists DC power and POA irradiance, but the acquired 2016 partitions contain no observations for those selected channels. Its AC meter is available, but the system is ineligible for the current measured joint-stream experiment. It was excluded rather than supplied with an unrelated or modeled irradiance signal.

The NIST inverter logger has missing periods that are not shared by the separate AC meter. In 2016, the meter and reference cell each have 525,859 raw rows; the inverter power channels have 474,075. Inverter readings also contain −999 values. The meter range is approximately −0.678 to 258.3 kW, with small negative readings rather than the inverter's extreme negative sentinel. The original NIST data dictionary identifies the meter channel as AC real power and the irradiance inputs as measured instrument channels.[^3]

The new target is explicitly **the nonnegative component of the hourly mean of recorded AC real-power samples**. The adapter first computes the valid hourly signed mean and then applies `max(mean, 0)`; it does not clip each minute before averaging. Signed means remain in the artifact for sensitivity analysis. Missing values remain missing. This target differs from the original inverter-DC pilot and must not be silently pooled with its results.

| Development contract | Complete hourly targets | Complete daylight target + irradiance hours | Daylight bins | Joint daylight completeness |
| --- | ---: | ---: | ---: | ---: |
| NIST AC meter, 2016 | 8,653 | 4,326 | 4,417 | 97.94% |
| Colorado AC inverter, 2016 | 8,783 | 4,412 | 4,414 | 99.95% |

Each valid hourly stream requires 60 distinct valid minute records. The source calendar is a leap year; converted UTC bins include boundary hours from the following year. These counts describe usable records under the adapter, not a guarantee of instrument accuracy or complete operational event coverage.

Quality screening is deliberately explicit: AC values outside −5% to 150% of DC nameplate and irradiance outside −20 to 2,000 W/m² are excluded. Small negative irradiance readings are retained as recorded sensor values, so nighttime sensor offset is not incorrectly interpreted as lost telemetry. The limits are engineering choices, not a claim that a standard mandates them, and need sensitivity analysis. The NIST 2016 selected channels have no exclusions under these bounds; Colorado has six excluded minute rows.

### Time semantics and limitations

NIST's original publication specifies Eastern Standard Time without daylight-saving changes and one-minute aggregate data.[^4] Its available UTC field was checked against native timestamps plus five hours. The meter metadata specifies left alignment. This is stronger evidence than guessing a timezone from a site name.

Colorado's UTC field is entirely absent. The catalog's numeric offset is 7; the acquired local grid contains every minute of the year except one and no conflicting repeated local timestamps. The development contract derives UTC by adding seven hours. Instrument interval alignment is unspecified, so the target is defined by recorded timestamp bins rather than asserted to be an exact physical-hour integral. The fixed-offset and one-minute alignment assumptions must be included in sensitivity analysis; high completeness does not resolve these metadata limitations.[^5]

Reproduction and exact quantities are in `development_source_audit.json`, `solar_recovery/data_v2.py`, and the `contract.json`/`audit.json` files under `data/processed/nist_ac_2016/` and `data/processed/colorado_ac_2016/`. These are development datasets. No forecasting experiment on them, or on reserved 2017 evaluation periods, is reported here.

## Controlled calibration experiment

The original calibration clipped every score correction at zero. The classical CQR score is signed, allowing contraction as well as expansion; the ordinary exchangeability guarantee does not automatically transfer to this rolling, weighted, missing-label setting.[^6] The revised experiment therefore tests an empirical signed adjustment and explicitly reports its departures from classical conformal inference.

The experiment reuses the original NIST 2015 daytime-probe base forecasts and delivery schedule. It adds 176,640 forecast records across ten methods. Every method receives the same base quantiles and permitted observations; no base model was retrained and no untouched test period was examined. This isolates several choices:

- Sign of the correction: expansion-only versus signed adjustment.
- Calibration population: all available hours versus geometric daylight targets.
- Score weights: uniform versus recency weights.
- Additional conditioning: context, exact observed-lag mask, or coarse recovery state.
- Adaptation: fixed levels versus a bounded empirical delayed-ACI variant.

Adjusted intervals are enlarged outward where necessary to preserve quantile order and contain the unchanged median. These repairs are counted; they are material, occurring frequently in the signed variants. A method should not be described as exact unmodified CQR when postprocessing changes its interval.

The adaptive variant updates from the originally issued interval when its label arrives. It clips miscoverage levels to [0.01, 0.99] and caps score quantiles at the largest available score. The original ACI construction can issue unbounded or empty sets; the finite engineering variant here does not inherit that algorithm's guarantee.[^7] Full faithful published-method comparisons remain pending.

### Early improvements do not establish a recovery-method advantage

The first six recovery hours contain 135 scorable daylight forecast records across eight events. The raw model's normalized WIS is 0.076641. Signed daylight calibration gives 0.073985, and context weighting gives 0.073562. Their nominal 90% coverage is 99.26% and 97.78%, respectively: these are still broad intervals, so a smaller WIS is not evidence of exact conditional calibration.

Recovery conditioning gives 0.074462 compared with 0.074400 for its recency-weighted reference. This small difference does not support an added recovery benefit. The contrast must be against the appropriate weighted reference, not merely the original expansion-only model.

The later 6–24-hour slice reverses part of the early improvement. Signed daylight WIS is 0.100373 versus 0.099327 for raw forecasts; the bounded adaptive method has 88.06% coverage for nominal 90% intervals. These regressions must accompany the early findings. Selecting only early recovery would give an incomplete account.

The [run report](../runs/nist_2015_calibration_v2/README.md) provides all phase/split results. The [paired event diagnostics](../runs/nist_2015_calibration_v2/EVENT_DIAGNOSTICS.md) resample event means rather than overlapping forecast rows. With only eight events per slice, the bootstrap is an exploratory diagnostic conditional on this one site and schedule; it does not establish cross-site reliability or final-test significance.

The [supporting spreadsheet](Development_Evidence.xlsx) includes every plotted event comparison, individual event differences, run metrics, new-data qualification counts and a source inventory. It explicitly separates the 2015 DC forecasting experiment from the 2016 AC data audits.

![Paired development comparisons](../runs/nist_2015_calibration_v2/event_comparisons.png)

## Reproducibility and verification

The test suite now has **31 passing tests**, including signed contraction, nested intervals, delayed adaptive feedback, daylight-only score pools, duplicate labels, source-unit conversion, UTC-contract conflicts, missing targets and causal replay. Saved forecasts passed finite/order, uniqueness, same-base and unchanged-median checks. These checks support implementation integrity, not scientific generalization.

Exact source snapshots were archived beside the original pilot, daytime probe and calibration-v2 run. A later guard correction prevents a rejected unavailable label from advancing the calibration clock; the v2 run never supplied such invalid calls, and its original source bytes remain archived. The original PRD and completed forecast files remain unchanged.

## Next research decisions

Build comparable full-season training histories for the two AC targets, and improve the base model before adding algorithmic complexity. Validate Colorado's time convention and quantify alignment/quality-threshold sensitivity. Then reproduce the strongest missing-data and conformal comparators, introduce gradual backfill and delayed receipt policies, and fix a multi-seed protocol before accessing final performance results.

The current evidence supports continuing the research but not declaring an algorithmic contribution. The manuscript should ultimately explain a verified computing problem and its measured consequences. If the recovery candidate does not outperform appropriate baselines, retain the negative result and assess whether the reproducible evaluation findings themselves constitute a sufficiently substantial conference contribution.

## Sources

[^1]: IEEE CCWC. [Submissions](https://ieee-ccwc.org/submissions/). 2027 edition; checked September 11, 2026.
[^2]: IEEE CCWC. [Call for Papers](https://ieee-ccwc.org/call-for-papers/). 2027 edition; checked September 11, 2026.
[^3]: National Institute of Standards and Technology. [Data Dictionary for NIST Photovoltaic Array and Weather Station Data](https://www.nist.gov/document/datadictionarysupplementalcontentpdf). Selected instrument definitions, especially AC real power and irradiance; accessed September 11, 2026.
[^4]: Boyd, M. [Performance Data from the NIST Photovoltaic Arrays and Weather Station](https://nvlpubs.nist.gov/nistpubs/jres/122/jres.122.040.pdf). Journal of Research of NIST 122, Article 40, 2017. DOI 10.6028/jres.122.040. Section 3 documents time and aggregation conventions; aggregate availability claims are not substituted for channel-specific audit results.
[^5]: OpenEDI. [PVDAQ data documentation](https://github.com/openEDI/documentation/blob/main/pvdaq.md). Native and UTC timestamp fields, units and instrument-alignment metadata. Exact catalog and site metadata snapshots are retained locally; derived Colorado timing remains a qualified assumption.
[^6]: Romano, Y., Patterson, E., and Candès, E. [Conformalized Quantile Regression](https://arxiv.org/abs/1905.03222). 2019. Signed conformity scores and interval construction; rolling/weighted adaptations here are empirical.
[^7]: Gibbs, I., and Candès, E. [Adaptive Conformal Inference Under Distribution Shift](https://arxiv.org/abs/2106.00170). 2021. Adaptive miscoverage update and boundary behavior; the bounded delayed variant here is not asserted to inherit its guarantees.
