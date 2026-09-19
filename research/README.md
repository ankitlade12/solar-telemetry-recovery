# Research protocols, analysis, and findings

The completed study consists of an original two-system evaluation and a separately frozen replication on Colorado system 10. The [main README](../README.md) summarizes the question and findings; the [artifact guide](../ARTIFACT_GUIDE.md) gives reproduction commands.

## Current evidence

| Record | Purpose |
| --- | --- |
| [Final evaluation protocol](FINAL_EVALUATION_PROTOCOL.md) | Original design, timing rules, comparisons, and inferential plan |
| [Original findings](FINAL_FINDINGS.md) | Original two-system results and limitations |
| [Producing-system protocol](PRODUCING_SYSTEM_EXTENSION_PROTOCOL.md) | Separately declared replication after original-result exposure |
| [Replication findings](PRODUCING_EXTENSION_FINDINGS.md) | System-10 results, sensitivities, and interpretation |
| [Source diagnostic](staff_review_v2/STAFF_RESEARCH_AND_IEEE_REVIEW.md) | Post-hoc audit of Colorado system 4 and associated claim limitations |
| [Method crosswalk](CLOSEST_METHOD_CROSSWALK.md) | Implemented comparators and differences from related methods |
| [Post-freeze analysis log](POST_FREEZE_ANALYSIS_LOG.md) | Dated analysis and provenance history |

`FINAL_PROTOCOL_LOCK.json` and `PRODUCING_EXTENSION_LOCK_V1.json` identify the exact frozen dependencies. Source qualification records retain admitted and excluded candidates. These are research evidence, even when they describe an earlier stage of the project.

## Main commands

- `final_evaluation.py` and `producing_extension.py`: frozen model fitting and replay.
- `verify_final_evaluation.py` and `verify_producing_extension.py`: verify recorded results and information access.
- `analyze_final_evaluation.py` and `analyze_producing_extension.py`: scoring, paired block intervals, diagnostics, and table reproduction.
- `integrate_extension_evidence.py`: generate the manuscript tables and measured figures from verified results.
- `restore_snapshot.py`: restore raw public objects from recorded acquisition manifests.
- `package_current_review.py` and `package_current_public.py`: assemble local archives from checked evidence.

Use the exact commands and output-directory guidance in the artifact guide. Do not rerun completed experiments into their original directories.

## Development and source history

[Annual development](ANNUAL_DEVELOPMENT_PROTOCOL.md), [development findings](DEVELOPMENT_V2_FINDINGS.md), [pilot findings](PILOT_FINDINGS.md), and [data feasibility](PVDAQ_DATA_FEASIBILITY.md) document choices preceding the final evaluation. The initial [research assessment](CCWC_Research_Assessment.md) and [research plan](RESEARCH_PLAN.md) are historical planning documents; their proposed work and venue information are not current status reports.

Dated test records, source investigations, and revision manifests describe the files and checks recorded at that time. Current instructions are maintained in the repository, paper, and release READMEs. Superseded manuscript backups, package handoffs, and generated distribution copies have been removed from the working tree.
