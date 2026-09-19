# Reproducing the staff-review diagnostic

These are post-exposure descriptive checks. They do not modify the frozen experiment or define a replacement evaluation population.

From the repository root, `python3 -m research.staff_review_v2.diagnose_recorded_power` verifies the original 83-file lock and generates the four diagnostic CSVs. The script deliberately refuses to overwrite the retained `diagnostics/` directory. For a fresh independent run, use an isolated copy without that generated directory, preserving the original artifacts in this workspace.

Rebuild the source-regime figure, workbook and raw-hour check into any fresh output directory:

```sh
MPLCONFIGDIR=/private/tmp/solar-review-mpl XDG_CACHE_HOME=/private/tmp/solar-review-cache python3 research/staff_review_v2/build_diagnostic_artifacts.py --output /private/tmp/solar-staff-review-reproduction
```

The figure uses the primary-variant monthly source CSV. The workbook retains all four tables and a Sources sheet. Workbook values were compared with their source CSVs to 1e-12 tolerance, and the raw-hour JSON was reproduced exactly. PDF creation metadata can change between builds; numerical/source identity is checked separately from binary artifact hashes.

`review_manifest.json` records the delivered artifact hashes and qualifications. The original 159-claim ledger and separate 19-claim post-hoc ledger were both checked using `research.package_submission.verify_claim_ledger`. The seven-page paper was rebuilt, mechanically audited and visually inspected. The final render directory is `paper/build/rendered_staff_v2_balanced/`.

Existing `dist/*_v1` archives preserve the earlier manuscript and do not include this review. Before any later release, packaging must include this diagnostic, its code, the supplementary claim ledger and relevant CSV dependencies, then rerun package verification. This review does not create an independent human-reproduction signoff or authorize submission.
