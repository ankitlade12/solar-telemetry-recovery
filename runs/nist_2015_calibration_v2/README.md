# Signed calibration development ablation

The same frozen base forecasts, delivered features, targets and daytime-restoration schedule are used for every method. This isolates calibration choices; no new model is trained and no untouched test period is used. All results are development evidence.

## First six recovery hours

| method | n | nwis | coverage50 | coverage80 | coverage90 | width90_kw | repair_fraction | events |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| aci_bounded_day | 135 | 0.0740 | 0.5926 | 0.9037 | 0.9556 | 144.1491 | 0.8296 | 8 |
| context_day | 135 | 0.0736 | 0.5704 | 0.9185 | 0.9778 | 145.4954 | 0.7704 | 8 |
| expand_all | 135 | 0.0766 | 0.9037 | 0.9630 | 0.9926 | 153.1756 | 0.0000 | 8 |
| expand_day | 135 | 0.0767 | 0.9037 | 0.9630 | 0.9926 | 153.1756 | 0.0444 | 8 |
| mask_day | 135 | 0.0742 | 0.7185 | 0.9407 | 0.9926 | 150.0637 | 0.6593 | 8 |
| raw | 135 | 0.0766 | 0.9037 | 0.9630 | 0.9926 | 153.1756 | 0.0000 | 8 |
| recency_day | 135 | 0.0744 | 0.7259 | 0.9481 | 0.9926 | 150.0113 | 0.6889 | 8 |
| recovery_day | 135 | 0.0745 | 0.7111 | 0.9556 | 0.9926 | 149.8666 | 0.6593 | 8 |
| signed_all | 135 | 0.0766 | 0.9037 | 0.9630 | 0.9926 | 153.1756 | 0.0000 | 8 |
| signed_day | 135 | 0.0740 | 0.7481 | 0.9556 | 0.9926 | 149.5622 | 0.6815 | 8 |

Lower normalized WIS is better; coverage50/80/90 targets are 0.50/0.80/0.90. Forecast records overlap across horizons. Complete phase/split metrics are in `metrics.csv`; no significance or novelty claim follows from this table.

## Controlled comparisons

- `expand_all` versus `signed_all`: permit signed correction with the same all-hours uniform pool.
- `expand_day` versus `signed_day`: the same sign comparison with daylight-only feedback.
- `signed_all` versus `signed_day`: isolate the daylight scope.
- `signed_day` versus `recency_day`: isolate recency weights.
- `recency_day` versus `context_day`, `mask_day` or `recovery_day`: additional conditioning with the same recency-weighted global component.
- `signed_day` versus `aci_bounded_day`: fixed versus receipt-gated adaptive miscoverage levels, both with uniform rolling pools.

Signed adjustment is followed by outward interval nesting and median containment, then nonnegative clipping. Repairs are counted. This keeps interval identities and does not move the base median. Calibration uses only labels delivered by each origin and stores the originally issued interval for adaptive feedback.

The adaptive comparator clips miscoverage levels to [0.01, 0.99] and caps requested score quantiles at the largest available score. It is a finite engineering variant, not an exact reproduction of the original ACI's possible unbounded/empty sets. Neither its original guarantee nor ordinary split-conformal exchangeability coverage is claimed. Context/mask/recovery variants are transparent empirical comparators, not replacements for faithful published-method reproduction.

## Provenance

`manifest.json` records parent/data/code hashes, parameters, validation checks and adaptive clipping counts. `forecasts.parquet` records final/base quantiles, pool support, signed corrections, adaptive levels and evaluator truth added after prediction. The original pilot artifacts remain unchanged. Run `python3 -m research.run_calibration_v2` only into a fresh output directory (the module's `run(output=...)` accepts a new path).

References: Romano, Patterson and Candès, [Conformalized Quantile Regression](https://arxiv.org/abs/1905.03222), 2019; Gibbs and Candès, [Adaptive Conformal Inference Under Distribution Shift](https://arxiv.org/abs/2106.00170), 2021. Weighted, delayed and bounded adaptations here are explicitly empirical.
