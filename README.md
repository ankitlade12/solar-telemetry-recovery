# Receipt-Time Replay for Probabilistic Solar Forecasting During Telemetry Recovery

Research code and experimental evidence for probabilistic photovoltaic forecasting when measurements and calibration labels arrive late.

[Reproduce the experiments](ARTIFACT_GUIDE.md) · [Data and attribution](DATA_AVAILABILITY.md)

## Research question

When telemetry resumes after an interruption, current measurements, missing history, and labels for past forecasts may arrive at different times. Does the time elapsed since observed recovery improve probabilistic forecasts beyond calibration that already accounts for data availability?

We evaluate this question with a receipt-time replay that separates measurement time from arrival time. Forecasts use only information received by their issue time, and calibration updates occur only after the corresponding labels arrive. The experiments include asynchronous channel restoration, immediate and gradual backfill, permanent loss, and delayed label feedback.

## Study and findings

The original study uses PVDAQ systems 4902 (NIST, Maryland) and 4 (Colorado). A separately frozen replication adds nearby Colorado system 10 after the original results and source distributions were inspected. Models train on 2016 observations and are evaluated during February–December 2017, following January calibration warmup. Forecasts cover four horizons, with primary leads of 59, 119, 179, and 239 minutes to the end of the target hour.

| Experiment | Systems | Site/case combinations | Forecast records |
| --- | --- | ---: | ---: |
| Original study | NIST 4902 and Colorado 4 | 49 | 14,106,960 |
| Producing-system replication | Colorado 10 | 11 | 4,702,320 |

Recovery-age grouping does not demonstrate a stable improvement over matched availability-aware calibration. All three systems fail the proposed 5% improvement criterion. In the replication, the early-recovery contrast is inconclusive; the later window shows a small penalty for recovery grouping across the three block lengths examined. The contribution is a reproducible comparison of information availability during recovery and evidence that bounds the benefit of this particular calibration rule.

These results concern three recorded systems in two geographic settings and one evaluation year. Telemetry interruptions are simulated. Colorado system 4 has a predominantly near-idle recorded output regime, and system 10 does not add an independent climate. The study does not establish general forecasting superiority or formal conditional-coverage guarantees.

Detailed results: [original study](research/FINAL_FINDINGS.md), [replication](research/PRODUCING_EXTENSION_FINDINGS.md), and [model assumptions](MODEL_CARD.md).

## Repository contents

| Path | Contents |
| --- | --- |
| `paper/` (local only, excluded from Git) | Author manuscript, bibliography, presentation exports, and claim-to-evidence mappings |
| `solar_recovery/` | Data processing, receipt-time replay, forecasting, calibration, and scoring |
| `configs/` | Experiment configurations |
| [`research/`](research/README.md) | Frozen protocols, analysis commands, source qualification, and findings |
| `runs/final_2017_v4/` | Original forecasts, verification records, and analysis |
| `runs/producing_extension_v1/` | Replication forecasts, verification records, and analysis |
| `data/` | Local source snapshots, metadata, normalized inputs, and exclusion records |
| `tests/` | Checks for timing, information access, calibration, scoring, and reproduction |
| `examples/` | A small synthetic replay example |
| [`release/`](release/README.md) | Reproduction instructions and dependency locks for shareable artifacts |

Earlier development runs and frozen provenance remain at their recorded paths because they document model selection, exclusions, and unsuccessful experiments. Generated release bundles and superseded manuscript copies are not part of the working repository. Large data directories, fitted model files, and per-origin forecast arrays are excluded from Git; a source-only checkout requires the recorded inputs and run artifacts described in the artifact guide. Analysis tables, manifests, and figure sources are included.

## Getting started

Python 3.14 is the demonstrated environment. The package declares Python 3.11 or later, but reproduction on other versions has not been established. Run commands from the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-pilot.txt
python -m pytest -q
python -m examples.synthetic_replay --output runs/my_synthetic_example
```

The example uses entirely synthetic measurements and is not evidence for the paper's findings. Use a new output directory for each run.

## Reproducing the paper locally

The manuscript PDF, LaTeX source, and preparation files are intentionally excluded from GitHub. These commands require the separately retained local `paper/` directory as well as the run artifacts. Historical documentation may reference local manuscript paths that are absent from a Git checkout.

With the verified local run artifacts available, regenerate the four tables and two measured figures without refitting:

```sh
MPLCONFIGDIR=/tmp/solar-recovery-mpl python -m research.integrate_extension_evidence --output runs/my_paper_figures
```

The command checks both studies and their recorded table reproductions before exporting the presentation. The synthetic receipt timeline is supplied separately under `paper/figures/`. See the [artifact guide](ARTIFACT_GUIDE.md) for verification, statistical-table reproduction, source restoration, and full model refits.

To build the manuscript, install a TeX distribution providing `pdflatex` and `bibtex`, then run:

```sh
python -m pip install -r paper/requirements-paper.txt
python paper/build.py
python paper/audit.py --final --named
```

The local output is `paper/build/manuscript.pdf`. After manuscript changes, follow the locally retained `paper/README.md` to inspect the rendered pages and refresh the matching review records.

## Data and licensing

The experiments use the public PVDAQ dataset, DOI [10.25984/1846021](https://doi.org/10.25984/1846021). Source manifests and normalization contracts identify the exact inputs; [data availability](DATA_AVAILABILITY.md) describes attribution, transformations, and limitations.

This manuscript has not been submitted or published. A license for the original research code has not yet been selected. Third-party data and the vendored IEEEtran files retain their respective terms; see [third-party notices](release/THIRD_PARTY_NOTICES.md).
