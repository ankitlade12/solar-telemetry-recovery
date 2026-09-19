# Additional-site source screening

The four declared source snapshots were acquired into `data/raw/extension_v1/` and all manifest-listed object hashes were checked. No candidate forecasts, trained models or performance comparisons were generated. This screen is governed by the earlier `EXTENSION_SOURCE_QUALIFICATION_PLAN.md` and is separate from the frozen original experiment.

## Nevada 1367: not eligible under the current plan

The cataloged aggregate AC channel 3091 is entirely absent in January, February and December 2016, and January–February 2017. Presence of daily source files therefore did not imply presence of the required power channel. This fails the declared all-month paired-channel requirement.

The cataloged POA channel 4195 also needs interpretation: its monthly raw maxima range only from 27.4 to 93.0 in 2016 and 24.4 to 61.8 in 2017, despite recorded aggregate AC reaching hundreds of kilowatts. The catalog specifies W/m² with scale 1 and offset 0. This is a plausibility concern, not permission to invent a conversion factor or substitute a different variable. Native timestamps are populated but the selected rows contain no UTC timestamps. The native AC records also have minute-scale gaps and clock offsets that require a dedicated acquisition contract.

Do not include this candidate as a complete producing-site validation with the currently selected channels and years. Retain the source and failure record. An explicitly different channel/year selection would require its own documented rationale and qualification before forecast inspection.

## Maine 1239: useful candidate, further qualification required

The declared AC and POA channels are present in every calendar month of 2016 and 2017. Their dominant short inter-sample gap is 900 seconds. The source is therefore approximately quarter-hourly, not minute-resolution. Selected-channel duplicate-value conflicts are absent in the screen, but small irregularities in monthly counts still require exact-grid checks.

Channel 3015 is named `ac_power_metered_kW`; its catalog specifies W and scale 1000. Raw values reach tens of units on a 20.16 kW system, consistent with the name's kW interpretation, but a formal contract must state how the catalog transform is applied and avoid converting twice. POA channel 3018 spans plausible daytime magnitudes. No selected row has a supplied UTC timestamp; native-clock/DST and interval alignment remain unqualified.

A winter low-power period also needs explicit treatment. December 2016 raw AC never exceeds 0.02, while POA remains variable; January 2017 is low as well. Snow, operating state and instrument behavior cannot be distinguished from these fields alone. The evidence is substantially different from Colorado's dominant year-long near-idle regime, but it is not a reason to skip source-state screening or silently remove winter targets.

Next steps are exact quarter-hour grid and scale checks, a native-clock/DST investigation with stated alternatives, complete-hour construction that requires every expected native sample, and a monthly bright/near-idle diagnostic under the declared thresholds. Only then can this candidate be accepted, rejected or retained with bounded limitations in a separately frozen extension protocol.

## Evidence and limits

`monthly_channel_inventory.csv` retains all 96 site/year/month/channel rows, including zero-row months. `candidate_status.csv` records sample totals, nameplates, conflicts and missing UTC fields. `manifest.json` hashes the screening script, prior plan, acquired source manifests and output tables.

The screening program is `research/screen_extension_sources.py`; it refuses to run until all four acquisition manifests exist and refuses to overwrite its output. All value summaries are in raw stored units and native time. They are not forecast outcomes or a physical validation certificate. The official [PVDAQ data dictionary](https://github.com/openEDI/documentation/blob/main/pvdaq.md) describes variable cadence, native timestamps that can include DST, catalog scaling and system DC nameplate units; it does not settle these sites' missing timing details.
