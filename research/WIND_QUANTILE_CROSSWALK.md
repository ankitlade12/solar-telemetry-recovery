# Published adaptive wind quantiles: B6 scope supplement

Checked September 12, 2026, during the frozen final run and before inspecting final forecast performance. This supplement clarifies the existing B6 disposition; it changes no experiment or frozen file.

Honglin Wen's [version 3, April 24, 2024](https://arxiv.org/abs/2305.14662v3) uses shared, mask-dependent feature extraction followed by neural quantile outputs. The extraction stack multiplies intermediate features by observed-value indicators, retains input skip connections, and adds a mask-dependent bias. Higher quantiles add nonnegative neural outputs to preceding quantiles. Training minimizes summed pinball losses on observed targets. These details appear in [Sections 3–4, equations 19–26](https://arxiv.org/html/2305.14662v3).

Our implementation instead uses histogram gradient boosting with native missing-value handling, explicit health features and block-augmented training. It sorts independently fitted quantiles, and its calibration groups stored errors after label receipt. It has neither Wen's shared extraction stack nor its cumulative neural quantile parameterization. Consequently, these controls are not a reproduction or direct evaluation of that published algorithm.

The PRD permits a narrower claim when the complete B6 comparator cannot be reproduced credibly. The frozen study therefore tests the incremental effect of recovery grouping within matched empirical calibration rules. A finding against our availability or exact-mask control cannot establish superiority over Wen's model. A future direct comparison requires a separately frozen neural implementation, matched input/target access, development-only tuning, and explicit compute and quantile-order checks.
