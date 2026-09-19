
# Second-contributor reproduction record

**Current status: not performed by a second contributor.** This is a review procedure and blank record, not a sign-off. The original PRD requires a second contributor to reproduce the principal tables from fixed configuration and artifacts. Automated tests, same-agent reruns and the package builder's checks do not satisfy that human requirement.

Use the completed research archive, after its manifest and final evidence exist. Follow `README.md` to create a fresh environment and install the archived resolved dependencies. Keep the supplied evidence unchanged. All commands below run from the archive root; use a new output directory if the example name already exists.

1. Record the received archive's SHA-256, reviewer name, review date, operating system, Python version and dependency installation outcome. Verify the archive against its supplied manifest. A matching hash establishes file identity, not scientific correctness.
2. Read `MODEL_CARD.md`, `DATA_AVAILABILITY.md`, the frozen protocol and the declared public-lock derivation. Confirm that the paper studies recorded AC targets and simulated receipts at two fixed sites.
3. Run the principal-table reproduction command:

   ```sh
   MPLCONFIGDIR=/tmp/solar-recovery-mpl .venv/bin/python -m research.analyze_final_evaluation runs/final_2017_v4 --output runs/second_contributor_tables
   ```

4. Inspect `runs/second_contributor_tables/reproduction_comparison.json`. All eight table comparisons must match at the recorded tolerance. Retain this file and the command output. Any failure is a finding to investigate, not permission to alter the reference data or relax the comparison.
5. Check the four primary site/phase contrasts in `Contrasts.csv` against the paper: recorded-AC population, faulted-primary pool, recovery minus availability, 0–6 and 6–24 hours, seven-day blocks. Confirm the sign convention, units, intervals and event-support limitations. Also inspect the 14/28-day and declared sensitivity results; unfavorable findings must remain visible.
6. Check the manuscript's other quantitative claims against `paper/claim_evidence.json` and its exact source rows. Distinguish point-estimate engineering thresholds from interval evidence. Review the imputation/adaptive-method adaptations and the limits of the two-site design.
7. Record the actual scope completed. Table reproduction from archived forecasts does not establish that model fitting, raw-data normalization or receipt simulation was independently rerun. Full refit/replay and raw-snapshot restoration commands are provided separately in `README.md` if the reviewer chooses that larger scope.

Copy and complete this record in a separate review file; do not replace original manifests:

| Field | Reviewer entry |
|---|---|
| Reviewer and date | Pending |
| Archive filename and SHA-256 | Pending |
| Environment and installation outcome | Pending |
| Command and output directory | Pending |
| Comparison record SHA-256 | Pending |
| Eight principal tables reproduced | Pending |
| Four primary contrasts checked against manuscript | Pending |
| Other quantitative claims checked | Pending |
| Negative findings and limitations retained | Pending |
| Scope beyond table reproduction, if any | Pending |
| Discrepancies and required corrections | Pending |
| Reproduction conclusion | Pending |

This record does not confirm author consent, choose a code license or authorize publication/submission. Those remain separate author decisions.
