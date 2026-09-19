# Reserved-year data qualification

On September 12, 2026, the public 2017 PVDAQ partitions were acquired and normalized for the two previously chosen geographic sites. **No forecast performance on 2017 has been examined.** Acquisition and completeness screening are distinct from selecting models or claims using evaluation errors. The final protocol is still pending.

| Source | Daily files | Download size | Complete PV hours | Complete daylight joint hours | Daylight bins |
| --- | ---: | ---: | ---: | ---: | ---: |
| NIST 4902, 2017 | 365 | 123.8 MB | 8,560 | 4,268 | 4,404 |
| Colorado 4, 2017 | 353 | 67.9 MB | 8,444 | 4,267 | 4,401 |

Counts refer to each source calendar's normalized UTC extent, including shifted year-boundary bins. The final forecast protocol must impose its own exact UTC evaluation bounds. Both streams require 60 valid minute samples per hour. No minute rows are excluded by the current broad engineering bounds in either 2017 source. NIST has 365 negative hourly signed means whose nonnegative-component targets become zero; Colorado has none. These are data-contract quantities, not performance results.

The public snapshots and every object checksum are under `data/raw/pvdaq_{4902,4}_2017/`; normalized data, audits and contracts are under `data/processed/{nist,colorado}_ac_2017/`. The target/channel/unit choices were determined from earlier source qualification.

NIST source UTC is cross-checked against native fixed EST. Colorado uses the qualified fixed-seven-hour conversion. The adapter's inherited timestamp-source phrase mentions an “uninterrupted local minute grid”; this refers to the earlier development-grid justification, **not** a finding that 2017 is complete. The 2017 Colorado snapshot has only 353 daily files and real missing periods. Its interval alignment is still unspecified, so timing sensitivity remains necessary. Do not silently remove this uncertainty from the final paper.

The adapter's generic `status` wording labels normalized outputs as development artifacts. The actual split policy is governed by the research protocol: these 2017 targets are reserved for post-freeze forecasting evaluation, and the present action qualifies source availability only. Before final evaluation, retain this qualification record alongside the immutable protocol and selected input hashes.
