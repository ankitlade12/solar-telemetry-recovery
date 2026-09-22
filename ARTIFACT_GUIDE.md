# Reproducing the solar telemetry recovery study

Run all commands from the repository root in the environment described in the [README](README.md). Use fresh output directories: experiment and analysis commands intentionally refuse to overwrite recorded results. The locally retained paper (`paper/build/manuscript.pdf`) reports the original study and the later producing-system replication separately.

The Git repository includes code, analysis tables, and provenance records. The entire `paper/` directory (PDF, LaTeX source, presentation exports, and preparation records) is retained locally and intentionally excluded from GitHub. Manuscript commands and historical links into that directory require the local author workspace. Raw and normalized data, fitted models (`.pkl`), and per-origin arrays (`.parquet`) remain local. The saved-forecast verification and reproduction commands below require those artifacts; they cannot run from a source-only checkout without restoring the required inputs or recreating the runs. The synthetic example does not require measured-data artifacts.

## Evidence map

| Evidence | Original study | Replication |
| --- | --- | --- |
| Protocol | [Final evaluation](research/FINAL_EVALUATION_PROTOCOL.md) | [Producing-system protocol](research/PRODUCING_SYSTEM_EXTENSION_PROTOCOL.md) |
| Internal freeze | `research/FINAL_PROTOCOL_LOCK.json` | `research/PRODUCING_EXTENSION_LOCK_V1.json` |
| Configuration | `configs/final_evaluation_v4.json` | `configs/producing_extension_v1.json` |
| Verified run | `runs/final_2017_v4/` | `runs/producing_extension_v1/` |
| Analysis | `runs/final_2017_v4/analysis/` | `runs/producing_extension_v1/analysis/` |
| Table reproduction | `runs/final_evidence_exports_v1/reproduced_tables/` | `runs/producing_extension_reproduced_v1/` |
| Findings | [Original findings](research/FINAL_FINDINGS.md) | [Replication findings](research/PRODUCING_EXTENSION_FINDINGS.md) |

Both analyses retain scores, coverage, widths, counts, paired calendar-block intervals, diagnostic tables, and supporting workbooks. The 7-, 14-, and 28-day blocks preserve common-weather scenarios within each system. Forecast rows, overlapping horizons, and replay seeds are not independent experimental samples.

The manuscript's current presentation is in `paper/integrated_evidence_v2/`. Its three claim ledgers are `paper/claim_evidence.json`, `paper/claim_evidence_posthoc_v2.json`, and `paper/claim_evidence_integrated.json`; each claim identifies a hashed source table and row selector. Earlier exports in `paper/generated/` and `paper/extension_evidence_v1/` retain the separate-study evidence.

## Verify saved forecasts

The original private-workspace checks below require the planning document, which has been removed from this repository. Their commands are retained for complete historical workspaces; use the public dependency views under **Refit and replay** for reproduction without that document.

```sh
python -m research.verify_final_evaluation runs/final_2017_v4
python -m research.verify_producing_extension runs/producing_extension_v1
```

These checks cover target values, score arithmetic, quantile validity, receipt-gated information, update counts, and recorded dependencies. They do not rerun model fitting. The original records document 14,106,960 forecasts and 874,300 direct history-slot checks; the replication records document 4,702,320 forecasts and 192,700 checks.

## Recompute statistical tables

Recompute the principal tables from saved forecasts without refitting models:

```sh
MPLCONFIGDIR=/tmp/solar-recovery-mpl python -m research.analyze_final_evaluation runs/final_2017_v4 --output runs/my_original_tables
MPLCONFIGDIR=/tmp/solar-recovery-mpl python -m research.analyze_producing_extension runs/producing_extension_v1 --output runs/my_replication_tables
```

Each command authenticates its input evidence and compares eight principal tables with the recorded analysis. This includes aggregation and bootstrap computation, so it takes longer than exporting the existing presentation. A procedure for a separate researcher is in [independent reproduction](release/INDEPENDENT_REPRODUCTION.md).

To regenerate the manuscript presentation from the verified analyses:

```sh
MPLCONFIGDIR=/tmp/solar-recovery-mpl python -m research.integrate_extension_evidence --output runs/my_paper_figures
```

The four tables and two measured figures are generated without pooling system-specific inference. `paper/figures/receipt_timeline.pdf` is an explicitly synthetic illustration; its source data and generator are recorded alongside the figure and in `research/make_receipt_timeline.py`.

## Refit and replay

Full reproduction requires the normalized inputs and every dependency identified by the locks. It is substantially more expensive than table reproduction. The public dependency views omit the private planning document while retaining the scientific dependencies and parent-lock identities.

```sh
python -m research.final_evaluation --freeze release/DEPENDENCY_LOCK.json --output runs/my_original_refit
python -m research.verify_final_evaluation runs/my_original_refit --release-lock release/DEPENDENCY_LOCK.json
MPLCONFIGDIR=/tmp/solar-recovery-mpl python -m research.analyze_final_evaluation runs/my_original_refit

python -m research.reproduce_public_extension --output runs/my_replication_refit
python -m research.verify_public_extension runs/my_replication_refit
MPLCONFIGDIR=/tmp/solar-recovery-mpl python -m research.analyze_producing_extension runs/my_replication_refit
```

The original design has 49 site/case combinations; the replication has eleven. New reproduction manifests have their own provenance. Compare numerical results rather than expecting run identifiers and every manifest field to match the original execution.

## Restore source data

The raw PVDAQ snapshots and normalized inputs are local artifacts, not files tracked by Git. Exact public object locations, sizes, and hashes are retained in the acquisition manifests. For example:

```sh
python -m research.restore_snapshot --manifest data/raw/pvdaq_4902_2017/manifest.json --max-mb 200
```

Repeat with the required system/year manifests. The restorer checks acquired bytes against the recorded hashes. Normalization also depends on instrument-specific contracts, timestamp interpretation, completeness rules, and recorded quality exclusions; downloading raw objects alone does not recreate a complete frozen input set. See [data availability](DATA_AVAILABILITY.md) and the protocol locks for the required files.

## Manuscript and local packaging

Build and inspect the manuscript using [paper/README.md](paper/README.md). The current PDF, source hashes, metadata, and mechanical and visual checks must refer to the same revision before packaging.

```sh
python -m research.package_current_review --declaration paper/current_review_declaration_v2.json --output dist/my_review
python -m research.package_current_public --review-manifest dist/my_review/manifest.json --output dist/my_public_candidate
```

The review packager above builds a private archive and requires the removed planning document. It cannot run from this cleaned workspace without restoring that file; the public packager then requires its completed review manifest. The public refit and analysis commands do not need the planning document. Generated archives are ignored by Git. No current archive is supplied in this cleaned workspace. Release terms are described in [release status](release/RELEASE_STATUS.md).

## Development history

The pilot and 2015/2016 development runs document how the final method and protocol were selected. They include failed fits, source exclusions, and exploratory timing changes. Their original paths and scientific records are retained so that the frozen study remains auditable. They should not be interpreted as additional held-out experiments. Start with the [research index](research/README.md) when examining that history.
