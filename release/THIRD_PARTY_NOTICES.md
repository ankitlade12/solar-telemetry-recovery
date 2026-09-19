# Attribution and third-party materials

Measured inputs derive from **Photovoltaic Data Acquisition (PVDAQ) Public Datasets**, by Chris Deline, Kirsten Perry, Michael Deceglie, Matthew Muller, William Sekulic and Dirk Jordan, 2021. The [official OEDI catalog](https://data.openei.org/submissions/4568) identifies DOI [10.25984/1846021](https://doi.org/10.25984/1846021) and Creative Commons Attribution 4.0. See the [CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/). Dataset authorship does not imply endorsement of this study.

The derived tables convert documented units, apply instrument-specific validity and completeness rules, aggregate minute measurements to hourly values, and clip the signed hourly AC mean at zero. Alternate quality and timestamp-alignment variants are identified in their contracts. Delivery timestamps and interruption schedules are generated for the experiment; they are not source-dataset network logs. Source keys, checksums and exclusion ledgers identify the transformations and original objects.

The IEEEtran class, bibliography style and upstream package retain their original notices and LPPL terms under `paper/vendor/`. Consult those notices for their exact scope. These terms do not grant rights over the toolkit's original code or the third-party data.

Dependency packages are installed separately under their respective licenses; their source distributions are not vendored here. The bibliography identifies related publications. Copies of external research papers are excluded from the release candidate. Original-code licensing is pending as stated in `release/RELEASE_STATUS.md`.
