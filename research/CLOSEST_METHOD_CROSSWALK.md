# Closest-method implementation crosswalk

Updated September 12, 2026 after inspecting the algorithm sections, not just the abstracts. This document prevents an empirical control from being mislabeled as a reproduction and separates published guarantees from this time-series replay.

## CACP: physical context and periodic tuning

Moradi et al. specify RBF, KNN and K-means calibration weights. Their context includes historical generation, calendar embeddings, normalized solar-day time and day-ahead HRRR weather forecasts. They periodically retune features and hyperparameters using past tuning/validation subsets. Their coverage discussion invokes operating-regime and distributional assumptions; it is not an unconditional guarantee for an arbitrary delivery replay.[^1]

Our `physical` control uses fixed RBF/recency weights with clock, target geometry, forecast location/width, current measured irradiance and visible missingness/age. It does not retrieve HRRR forecasts or perform daily feature selection. It is a specified physical-context control, not full CACP. The recovery variant must be compared with this otherwise matched control. A further availability-only grouping ablation is useful because the coarse recovery-state key also includes age and missing-fraction bins.

## CP-MDA: masks change the calibration predictions

Zaffran et al.'s CP-MDA-Exact selects calibration observations whose original missing coordinates are contained within the test mask, adds that mask, and recomputes imputation, model predictions and scores. CP-MDA-Nested instead forms union masks and also evaluates temporarily masked test inputs. These operations differ from looking up a stored score by its original mask. Theorems 5.3–5.4 state MCAR and additional assumptions; the nested variant has a further stochastic-domination condition and a technical qualification.[^2]

Our `mask50` control blends existing same-mask scores with a recency pool. It does not remask historical inputs or rerun the forecasting model. It must not be called CP-MDA, nor inherit the latter's guarantee. This distinction is substantive even when both methods are described informally as mask-aware calibration.

## Fan et al.: distributional imputation and density-ratio correction

The full AISTATS paper assumes i.i.d. calibration/test data and training-only model/imputer fitting. It preimputes calibration covariates, potentially using their observed responses, then masks them to match the test pattern. Its weighted construction uses mask-dependent density ratios that can depend on candidate response values and includes test-point mass at infinity. The acceptance-rejection version additionally requires a bounded ratio. Estimated-ratio error weakens the guarantee. “All missing data mechanisms” therefore does not mean assumption-free temporal coverage.[^3]

Our mask matching has neither distributional calibration imputation nor density-ratio correction. The implemented input MI baseline does not supply those missing steps. The full weighted/acceptance-rejection algorithms are not yet implemented here. A final paper may describe this as related work and limit its claims to the evaluated empirical strategies; it may not claim to outperform these algorithms without running them faithfully or documenting an explicit temporal adaptation.

## Closest PV multiple-imputation method

The PV study uses nearest-irradiance donor sampling and multiple-imputation variance aggregation, with separate single/multiple training and test-input setups. Its experiments assume observed irradiance. Our comparison adapts its single-training/multiple-test setup, uses observed-only labels and adds joint-channel donor rules. The exact differences and fixed tuning budget are in [the annual protocol](ANNUAL_DEVELOPMENT_PROTOCOL.md). No claim of a full reproduction is made.[^4]

## Consequence for the conference claim

The defensible current scope is an empirical investigation of receipt semantics, backlog and calibration behavior with explicit model controls. A new missing-data or conformal method is not established. Before freezing the final protocol, either implement additional exact comparators needed for a stronger algorithmic claim or retain the narrower **claim**, while still completing the full experiment, sensitivity, artifact and manuscript requirements. The final decision must be a dated protocol amendment, not a silent omission of PRD baselines.

## Sources

[^1]: Moradi et al., [Enhanced Renewable Energy Forecasting using Context-Aware Conformal Prediction](https://arxiv.org/html/2510.15780v2), sections III-B–III-D, version 2, 2026. Full context/weighting/tuning sections inspected.
[^2]: Zaffran et al., [Conformal Prediction with Missing Values](https://proceedings.mlr.press/v202/zaffran23a/zaffran23a.pdf), ICML 2023, algorithms 1–2 and theorems 5.3–5.4. These sections were inspected directly; this is not a claim to have independently proved the theorems.
[^3]: Fan, Park, Vo and Brunel, [Mask-Conditional Conformal Prediction: Valid Uncertainty For All Missing Data Mechanisms](https://proceedings.mlr.press/v300/fan26a.html), AISTATS 2026. Full linked PDF, pages 3–6, assumptions 1–2, theorems 1–2 and density-ratio estimator inspected. Public PDF and its checksum are retained locally under `research/sources/`; proofs/remaining appendices are not independently verified.
[^4]: Pashmchi, Benoit and Kanagawa, [Predictive Uncertainty in Short-Term PV Forecasting under Missing Data: A Multiple Imputation Approach](https://arxiv.org/abs/2603.15564), 2026 preprint, sections III–IV.
