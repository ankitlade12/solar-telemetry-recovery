# Colorado cross-channel source investigation

**The low 2017 AC signal is supported by coordinated changes in neighboring recorded channels, and the normalized AC values reproduce the raw archive.** A conversion error is therefore not a persuasive explanation for the observed regime. The evidence is consistent with a nonproducing or reconfigured measurement state, but it does not identify a physical cause or establish that the instruments remained valid.

The investigation verified the hashes of all 719 archived daily source objects from 2016 and 2017 and all 83 files in the original scientific lock. It joined raw minute channels, required 60 distinct finite samples for hourly averages, and independently compared raw AC/1000 with the existing normalized target. All 8,783 comparable 2016 hours and 8,444 comparable 2017 hours agree to floating-point precision: maximum absolute discrepancies are approximately 2.22e-16 and 1.11e-16 kW. No model was fitted and no forecast or source target was replaced.

## Channel evidence

The local metric catalog identifies 315 as AC power in W, 314 as DC power in W, 316/317 as DC voltage/current, 318/319 as AC voltage/current, 327 as power factor, and 313 as POA irradiance. The AC/DC power scale factors are 1 with zero offsets. The catalog and system metadata contain no dated maintenance or disconnection explanation.

For June 2016, the median DC voltage over complete bright hours is about 244.45 V. In June 2017 it is about 0.987 V. All 258 complete bright AC/DC hours in June 2017 have both AC and DC power below 10 W. The median DC power in those low-AC hours is approximately 0.0303 W, while median AC voltage remains approximately 122.48 V and median power factor approximately 0.1403. These are descriptions of archived channels, not measurements independently validated against a calibrated reference.

Raw minute electrical-product checks compare reported DC power with voltage times current, and reported AC power with voltage times current times power factor, before averaging. The median hourly absolute discrepancy during bright June 2017 hours is approximately 0.00117 W for DC and 0.0174 W for AC. Agreement is consistent with the recorded regime. It is not independent corroboration of plant state because channels may share sensors or calculations; aggregation and meter topology also limit interpretation of these identities.

## Observed transitions

The daily bright-hour summaries show producing readings before December 13, 2016, followed by a transition during that day. On December 14 the observed bright-hour AC maximum is approximately 2.85 W, DC voltage is near 1.45 V, and module temperature channel 321 carries the repeated physically implausible value -7999 throughout those hours. The temperature value is counted separately and omitted from diagnostic temperature averages; the original archived measurements remain unchanged.

The low-power pattern persists in the available 2017 observations. A coordinated change appears again on December 22, 2017; by December 23, observed bright-hour AC reaches approximately 800.18 W, median DC voltage is approximately 259.62 V, and the invalid module-temperature code is absent from those hours. Missing source dates, including early December 2017, prevent treating the archive as an uninterrupted event log. These dates locate observed changes, not verified maintenance actions or exact physical outage boundaries.

## Consequences for the paper

1. Retain the frozen recorded-AC experiment and its unfavorable results. The current paper already discloses the near-idle qualification; this investigation strengthens its source basis without changing the primary estimates.
2. Do not count Colorado 2017 as corroboration from a second normally producing system. AC, DC and module-temperature changes support concern about the operating/measurement regime, not a specific diagnosis.
3. Do not switch to DC power to rescue the evaluation. The neighboring DC signal is also near zero during the relevant regime, and a substituted target would define a different experiment.
4. Additional producing-site evidence is the practical next step. Nevada and Maine candidates are being screened under `research/EXTENSION_SOURCE_QUALIFICATION_PLAN.md`, selected without inspecting their forecast performance. The existing Colorado data remain in the record regardless of candidate outcomes.
5. Resolving the physical cause conclusively may require dated instrument or operator records. No organizer, dataset owner or other person has been contacted.

## Reproduction and evidence

Run `python3 research/investigate_colorado_channels.py --output <fresh-directory>` from the repository root. The executed version is retained as `code_snapshot.py`; the working script differs only by a clarified comment about the invalid temperature code. `manifest.json` records input hashes, output hashes, thresholds, limits and the original executed-code hash.

The principal evidence files are `hourly_cross_channel.csv`, `monthly_cross_channel.csv`, `daily_bright_regime.csv`, `normalization_crosscheck.csv` and `channel_catalog.csv`. Thresholds of POA above 200 W/m² and AC/DC below 10 W were selected after the original performance exposure for descriptive investigation. They are not new eligibility rules or physical fault labels. All claims in this note are local source-derived findings, and no extra significance test is asserted.

The earlier `colorado_channel_investigation_v1` attempt stopped before producing result tables because the acquisition manifest included a metadata Parquet alongside daily observations. The successful version explicitly selects daily measurement objects. That implementation failure changed no scientific input.
