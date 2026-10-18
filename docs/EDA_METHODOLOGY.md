# Exploratory data analysis methodology

## Scope

Checkpoint 6 implements two independent descriptive analyses. Track A studies the available transactions from one private bank account. Track B studies Stats SA IES 2022/23 household expenditure. The tracks share reusable statistical helpers but do not merge records.

## Track A: personal account activity

### Population and period

The source is `data/private/curated_transactions.csv`. The current local file contains 595 transactions from eight reconciled statement periods spanning 31 January through 26 September 2026. It represents the available activity in one account, not the account holder's complete finances. The periods cover 235 days and leave four uncovered dates: 27 April and 24–26 May.

Calendar months at either coverage boundary or intersecting a gap are marked partial or gapped. A month is labelled complete only when the statement coverage includes every calendar date. The available period remains too short and incomplete for a reliable seasonality claim.

### Movement and expenditure definitions

- A financially active row has a positive debit, credit or fee.
- Identified expenditure equals purchase debits plus separately recorded bank fees.
- Refunds and reversals remain separate credits. They are not silently netted against purchases.
- Incoming and outgoing transfers, cash withdrawals, informational rows and unknown movements are not ordinary consumption.
- Account balances are never counted as income or expenditure.

Category and subcategory results include only purchases or bank fees with a non-placeholder final category and `review_required == False`. Unresolved rows remain in the source and movement summaries. Every category output discloses the unresolved-purchase count and value plus the percentage of eligible expenditure represented by resolved categories. In the current run, 185 unresolved purchases worth R25,205.84 are excluded, and resolved categories cover R15,598.44 (38.23%) of R40,804.28 in eligible expenditure.

Merchant concentration uses only purchases with an identified merchant. Recurring candidates require at least two observations for the same merchant, broadly stable amounts within five percent or R1, and a plausible 20–40 day interval for at least half of consecutive observations. Two observations remain a possible pattern, not a confirmed subscription.

All arithmetic retains source values. `Decimal` is used for report-level monetary totals, with rounding only for presentation.

### Privacy

Personal CSV, JSON and PNG outputs are written to `reports/private/`, which Git ignores. The committed notebook contains no outputs. Public documentation limits monetary reporting to aggregate classification-coverage disclosures and contains no personal descriptions, transaction-level amounts, merchant rankings or balances.

## Track B: household expenditure

### Population and estimand

The source is the validated Checkpoint 5 output. The main estimand is annual household ordinary consumption at the documented May 2023 price basis. Only records where `coicop_type == 1` are included.

The expenditure file's grain is an expenditure unit. Item values are first summed by `uqno` to create one ordinary-consumption total per household. Division results are also aggregated within household before survey weighting. Household expenditure is never joined to person rows.

### Weighting

Population point estimates use the following procedure:

1. Sum unweighted `valueannualized_adj` records within household and analytical category.
2. Join the one-row-per-household `HHOLD_WGT` value.
3. Calculate weighted totals as the sum of household amount multiplied by household weight.
4. Calculate weighted means as weighted total divided by the sum of weights.
5. Calculate weighted quantiles after sorting household values and locating the requested cumulative-weight threshold.

The analysis does not average `valueannualized_adj_wgt`. It reports unweighted sample descriptions separately from weighted population point estimates. No survey design variance procedure is implemented because supported strata and cluster treatment has not been established. Confidence intervals, p-values and claims of statistical significance are therefore omitted.

### Research groups

Household size is grouped as one person, two people, three to four people, and five or more people. Per-capita fields are not interpreted as observed individual purchases.

Province codes use the standard published Stats SA coding retained by the processed geography file. Gauteng is code 7. Provincial results are descriptive sample and weighted point estimates, not causal effects.

Income analysis uses the published household `INCOME` and `INCOME_QUINTILE` fields. PersonIncome observations are not summed into household income. The reported income-expenditure association is a household-weighted Pearson correlation between log positive household income and log positive ordinary consumption. It is exploratory and non-causal.

## Cross-dataset readiness

No nominal amount comparison is currently supported. The personal data cover a short 2026 account period, while IES represents 2022/23 household expenditure adjusted to May 2023 prices. The observation units, channels and coverage differ, and personal classification review remains incomplete.

Mapped IES categories cover about 55.0% of weighted ordinary consumption, but a composition comparison is deferred until personal review coverage is adequate and both denominators can be aligned. No inflation adjustment is invented.

## Reproduction

```powershell
python -m src.analysis.pipeline --track personal
python -m src.analysis.pipeline --track public
python -m src.analysis.pipeline --track all
```

The public expenditure table is read in 100,000-row chunks. Output directories are staged and replaced only after every table and chart succeeds. The source datasets are never modified.
