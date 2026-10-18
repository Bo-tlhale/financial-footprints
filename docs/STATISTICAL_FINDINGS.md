# Statistical analysis findings

## Evidence boundary

The personal results below disclose only safe aggregate coverage. Merchant names, transaction amounts, unusual-observation rows and recurrence details remain private. Public results are weighted descriptive estimates from the IES household data. No result is a causal effect, hypothesis test or statistically significant difference.

## Personal account evidence (SRQ1-SRQ4)

The analysis reverified 235 covered dates and four uncovered dates: 27 April and 24-26 May 2026. Category analysis excludes 185 unresolved purchases worth R25,205.84 and covers R15,598.44, or 38.23% of R40,804.28 eligible purchase-plus-fee expenditure. This limited coverage materially constrains category concentration. Transaction-level purchase variability, daily variability including zero-purchase covered days, merchant concentration, unusual-observation candidates and recurring evidence were generated privately. Statistical flags are review prompts, not fraud findings; recurrence labels are not confirmed subscriptions.

## Household expenditure distribution (SRQ5)

The analytical population is 19,940 households representing 21.283 million weighted households under the released v1.2 weights. Weighted annual ordinary consumption has a median of R81,558, mean of R138,852, IQR of R109,034, 90th percentile of R306,043 and 99th percentile of R863,973. The weighted consumption Gini is 0.506. The highest-spending 10% account for 39.2% of weighted expenditure and the highest 20% for 56.4%. These describe consumption concentration, not income inequality.

## Household size, income and geography (SRQ6-SRQ8)

Weighted median total consumption rises from R57,930 for one-person households to R81,228 for two-person, R93,958 for three-to-four-person and R96,330 for five-plus-person households. Calculated median per-capita consumption falls across those groups, from R57,930 to R40,614, R27,163 and R15,186 respectively. This pattern does not by itself establish economies of scale.

Positive household income and ordinary consumption have a weighted log-Pearson correlation of 0.741 and weighted Spearman correlation of 0.707. The weighted median expenditure-income ratio is 0.886. Ratios above one can reflect the survey reference definitions, dissaving, borrowing, transfers, measurement error or timing; they are not automatically invalid observations.

Weighted median consumption ranges from R59,742 in North West to R129,793 in Western Cape; Gauteng is R93,607. All province tables report sample and weighted household coverage. Within-income composition changes are substantial: food's weighted share falls from 29.2% in quintile 1 to 10.4% in quintile 5, while transport rises from 7.7% to 19.9% and insurance/financial services from 3.4% to 13.4%. These are descriptive group patterns, not explanations of individual behaviour.

## Exploratory explanatory model (SRQ9)

The weighted log-linear model uses all 19,940 positive-outcome households. Its weighted R-squared is 0.559, log-scale RMSE 0.596 and log-scale MAE 0.457; the design-matrix condition number is 11.8. The income elasticity coefficient is 0.557 and the household-size elasticity coefficient is 0.065, conditional on the included province indicators. Deterministic half-sample estimates retain the same directions: income 0.566 and 0.548; household size 0.059 and 0.070. Province coefficients are associations relative to Western Cape after included adjustment, not causal effects or league-table proof.

The model is not a forecasting system. It has no train-test generalisation claim and reports no standard errors, confidence intervals or p-values because the released files do not expose the survey design variables needed for valid variance estimation.

## Methodological findings and limitations

- Expenditure is aggregated at household level before weighting; person rows are never used to duplicate household consumption.
- The released v1.2 weights sum to 21,282,823.756, while the supplied metadata prints 19,050,732.016. Results use the released weights without hidden rescaling and disclose the discrepancy.
- Public composition and geographic estimates are weighted point estimates only.
- Personal evidence covers one account, contains four uncovered dates and has incomplete classification coverage.
- No personal-versus-household amount comparison, formal significance claim, causal conclusion, fraud claim or expenditure forecast is supported.
