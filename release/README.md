# Research artifact reproduction

This directory provides the dependency views and instructions used to reproduce the solar telemetry recovery study from a shareable artifact. The manuscript includes the original NIST/Colorado-4 study and a separately declared Colorado-10 replication. See `README.md` and `ARTIFACT_GUIDE.md` at the repository root for the research question, findings, and evidence map.

## Environment and example

Run from the artifact root using Python 3.14, the demonstrated environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-pilot.txt
python -m pytest -q
python -m examples.synthetic_replay --output runs/my_example
```

The example is entirely synthetic. Measured-data reproduction requires the saved run artifacts or the normalized inputs identified by the dependency locks. Source-only code does not contain the large local data directories.

## Reproduce the recorded tables

```sh
MPLCONFIGDIR=/tmp/solar-recovery-mpl python -m research.analyze_final_evaluation runs/final_2017_v4 --output runs/my_original_tables
MPLCONFIGDIR=/tmp/solar-recovery-mpl python -m research.analyze_producing_extension runs/producing_extension_v1 --output runs/my_replication_tables
MPLCONFIGDIR=/tmp/solar-recovery-mpl python -m research.integrate_extension_evidence --output runs/my_paper_figures
```

Use fresh output directories. The analysis commands compare eight principal tables per study against the recorded results; the presentation command generates the integrated tables and measured figures. Independent review instructions and a blank record are in `release/INDEPENDENT_REPRODUCTION.md`.

## Full refit

`DEPENDENCY_LOCK.json` omits only the private planning document from the original 83-file freeze. `PRODUCING_EXTENSION_DEPENDENCY_LOCK.json` does the same for the 139-file replication freeze. These are derived reproduction views, not new prospective protocols. Scientific dependencies and parent identities remain authenticated.

```sh
python -m research.final_evaluation --freeze release/DEPENDENCY_LOCK.json --output runs/my_original_refit
python -m research.verify_final_evaluation runs/my_original_refit --release-lock release/DEPENDENCY_LOCK.json
MPLCONFIGDIR=/tmp/solar-recovery-mpl python -m research.analyze_final_evaluation runs/my_original_refit

python -m research.reproduce_public_extension --output runs/my_replication_refit
python -m research.verify_public_extension runs/my_replication_refit
MPLCONFIGDIR=/tmp/solar-recovery-mpl python -m research.analyze_producing_extension runs/my_replication_refit
```

Full fitting and replay take substantially more computation than regenerating tables. All required scientific inputs must be present. Exact raw public objects can be restored with `research.restore_snapshot` and their recorded acquisition manifests; see `DATA_AVAILABILITY.md`.

## Distribution status

No distribution archive accompanies the cleaned working tree. Previous package checks are historical records for their recorded hashes. Fresh local archives can be generated using the commands in `ARTIFACT_GUIDE.md`; they perform no upload or publication.

The original-code license and author release consent remain undecided. Third-party licenses and data attribution remain applicable. See `release/RELEASE_STATUS.md` and `release/THIRD_PARTY_NOTICES.md`.
