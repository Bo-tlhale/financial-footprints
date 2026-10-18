# Statistical analysis methodology

## Scope and research design

Checkpoint 7 extends the validated Checkpoint 6 datasets. It keeps personal bank activity and public household survey expenditure as separate populations and makes no causal, forecasting or statistical-significance claims.

| Question | Source and unit | Variables and inclusion rules | Method and output | Main limitation |
| --- | --- | --- | --- | --- |
| SRQ1: variability | Curated private data; purchase transaction and covered day | Purchase debit; all 235 covered days, including zero-purchase days | Mean, median, standard deviation, IQR, percentiles and skewness | One account and a short, interrupted period |
| SRQ2: concentration | Curated private data; resolved eligible transaction or merchant-identified purchase | Resolved purchase/bank-fee category amounts; merchant-identified purchase debits | Shares, top-k shares and descriptive concentration | 185 unresolved purchases are outside category results |
| SRQ3: unusual observations | Curated private data; purchase transaction | Purchase debits retained unchanged | Global 1.5-IQR and MAD rules; category IQR only where n >= 20 | Candidates are not fraud or harmful-spending findings |
| SRQ4: recurrence | Curated private data; merchant pattern | At least two merchant-identified purchases | Amount-deviation, 20-40-day interval share and interval MAD; transparent evidence labels | Short history cannot confirm contracts or missing future payments |
| SRQ5: inequality | IES; household | Annual ordinary consumption, `coicop_type == 1`, aggregated to `UQNO`; positive `HHOLD_WGT` | Weighted percentiles, IQR, variance, Gini, Lorenz curve and top shares | Consumption inequality is not income inequality |
| SRQ6: composition | IES; household | Published `HSIZE`; total and calculated per-capita consumption | Weighted group distributions and Gini | Per-capita values do not model economies of scale |
| SRQ7: associations | IES; household | Published household `INCOME`, size and ordinary consumption; positive income/expenditure | Weighted log Pearson, weighted Spearman and expenditure-income ratios | Descriptive association only |
| SRQ8: group composition | IES; household by COICOP division | Income quintile, province and household-aggregated division values | Weighted composition shares and group distributions | No design-based uncertainty estimates |
| SRQ9: explanatory model | IES; household | Positive consumption/income/size, province and `HHOLD_WGT` | Exploratory weighted log-linear regression and deterministic half-sample stability | Coefficients lack design-corrected inference and are not causal |

## Personal definitions

Purchase distributions use all rows classified as `Purchase`. Daily variability uses every date inside the reconciled statement intervals, excluding only the four documented uncovered dates; dates with no purchase receive zero. Category concentration uses resolved purchase and bank-fee expenditure, matching the Checkpoint 6 eligible-expenditure denominator. Every private summary carries the count and rand value of unresolved purchases and the covered percentage. Merchant concentration instead uses merchant-identified purchase expenditure and reports its own coverage.

An observation is flagged when its amount exceeds the global upper 1.5-IQR fence, has an absolute robust MAD score above 3.5, or exceeds a category-specific upper fence in a category with at least 20 purchases. Sparse-category thresholds are marked unsupported. Rows are retained and no classification is changed.

Recurring evidence is assessed per stable merchant label. A strong candidate needs at least three observations, median amount deviation no greater than 5%, at least 75% of intervals between 20 and 40 days, and interval MAD no greater than seven days. A possible candidate uses looser 15% and 50% thresholds. Everything else is insufficient evidence.

## Survey weighting and household grain

The 956,234 ordinary-consumption expenditure records are summed to household before joining the one household record and applying `HHOLD_WGT`. No household expenditure is replicated across person records, and the preweighted item field is not averaged. Missing expenditure is checked after the household join; valid zeros would be retained in descriptive distributions. The real analytical population has no missing or zero ordinary-consumption totals and all weights are positive.

The released v1.2 household file's weights sum to 21,282,823.756. The locally supplied official metadata reports 19,050,732.016. The pipeline exposes this discrepancy and uses the released record-level weights without undocumented renormalisation. The official methodology describes strata, primary sampling units and variance units, but those variables and replicate weights are absent from the released analytical files inspected here. A weight alone does not establish independent observations. Consequently, this checkpoint reports weighted point estimates but no confidence intervals, p-values, significance tests or survey-design regression standard errors.

## Model specification

The model explains, rather than predicts, log annual ordinary household consumption using centered log household income, centered log household size and province indicators, with Western Cape as the reference. `HHOLD_WGT` is normalised to mean one for numerical fitting. All outcome and predictor values are positive in the real analytical population.

Published expenditure fields are excluded as outcome leakage; income quintile is excluded because it is derived from income; PersonIncome has the wrong individual unit; and settlement type is excluded because local code frequencies conflict with the metadata label ordering. No train-test split is used because prediction is not the objective. Fit is described with weighted R-squared, log-scale RMSE/MAE, residual mean, condition number, aggregate fitted-decile calibration and deterministic SHA-256 half-sample coefficient stability. These checks do not create valid survey-design inference.

## Reproduction and output safety

```powershell
python -m src.analysis.statistics.pipeline --track personal
python -m src.analysis.statistics.pipeline --track public
python -m src.analysis.statistics.pipeline --track modelling
```

Private transaction-level tables and figures are written only to ignored `reports/private/statistics/`. Public outputs contain aggregate tables, metrics and charts under `reports/public/statistics/` and `reports/public/statistics_model/`; the published Lorenz table is interpolated to 101 population-share points rather than exposing household-level rows. Each destination is staged and atomically replaced only after a successful run. The notebooks are output-free entry points; reusable calculations live in `src/analysis/statistics/`.
