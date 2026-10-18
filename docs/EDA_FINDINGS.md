# Exploratory data analysis findings

## Evidence boundary

This document publishes aggregate Stats SA findings and privacy-safe readiness results from the personal track. Personal amounts are limited to aggregate classification-coverage disclosures; it does not publish transaction descriptions, account balances, merchant rankings or recurring-payment details.

## Track A: personal account activity

The local analysis covers 595 transactions across eight reconciled statement periods spanning 31 January to 26 September 2026. The statements cover 235 days and leave four uncovered dates: 27 April and 24–26 May. Of the 595 records, 579 contain a financial movement. The movement classification contains 309 purchases, 81 bank fees, 47 incoming transfers, 96 outgoing transfers, 23 cash withdrawals, one refund, two reversals, 16 informational rows and 20 unknown movements.

The data are not ready for a complete category interpretation. Two hundred and five rows still require review. One hundred and eighty-five unresolved purchases worth R25,205.84 are excluded from category findings. The resolved category results cover R15,598.44, or 38.23% of the R40,804.28 eligible expenditure (purchase debits plus separately recorded bank fees). Two hundred and five purchase or bank-fee records currently meet the resolved-category criteria. No manual approvals or corrections have yet been imported.

The private pipeline generated the RQ1–RQ5 tables and charts locally. One possible recurring pattern was detected, but it is not published or treated as a confirmed subscription. January, April, May and September are partial or gapped calendar months. The available coverage does not support a reliable seasonality claim.

Conclusion: movement-level analysis is reproducible, but category, merchant and recurrence conclusions remain private and materially limited by unresolved review decisions and short coverage.

## Track B: South African household expenditure

### Data readiness

The analysis verified 1,128,279 expenditure records, 19,940 households, 70,339 persons, 48,038 person-income observations and 4,652 single-person households. Ordinary consumption contributes 956,234 expenditure-unit records.

### Household expenditure distribution

The unweighted sample median annual ordinary consumption is approximately R76,266, while the weighted population median is approximately R81,558. The weighted mean is approximately R138,852 and the weighted 90th percentile is approximately R306,043. The mean exceeds the median, consistent with a right-skewed expenditure distribution. These are point estimates at the survey's May 2023 price basis, without design-based confidence intervals.

Housing, water, electricity, gas and other fuels account for 32.4% of weighted ordinary consumption. Food and non-alcoholic beverages account for 16.9%, transport for 15.8%, and insurance and financial services for 9.7%. Together, housing, food and transport account for about 65.1% of the weighted ordinary-consumption total.

### Household composition

Weighted median annual ordinary consumption rises from approximately R57,930 for one-person households to R81,228 for two-person households, R93,958 for three-to-four-person households and R96,330 for households with five or more people. This is household expenditure, not observed per-person consumption. The flattening between the two larger groups does not establish an economy-of-scale effect without further analysis.

### Single-person households

The sample contains 4,652 single-person households. Their weighted median annual ordinary consumption is approximately R57,930 and their weighted mean is approximately R94,952. Housing has the largest weighted share at 35.5%, followed by food at 16.2% and transport at 14.8%.

Single-person survey households remain broader than one person's bank account because the survey includes expenditure channels and recall components not necessarily visible in the personal transaction data.

### Geography

The Gauteng sample contains 4,688 households, including 1,304 single-person households. Weighted provincial medians range from about R59,742 in North West to R129,793 in Western Cape; Gauteng's weighted median is approximately R93,607. These are descriptive province-level point estimates and do not identify causes of the differences.

### Household income and expenditure

Weighted mean ordinary consumption rises across the published household income quintiles, from approximately R50,100 in quintile 1 to R350,100 in quintile 5. The weighted correlation between log positive household income and log positive ordinary consumption is 0.741. This is a descriptive association. It is not evidence that income changes cause the observed expenditure differences.

### Comparison readiness

The mapped public categories represent about 55.0% of weighted ordinary consumption. Even so, neither a nominal amount comparison nor a category-composition comparison is published. The personal review is incomplete, the periods are non-contemporaneous, the price bases differ, and the personal unit is one account rather than a household.

## Limitations

- Survey weights support the reported population point estimates, but design-based variance estimates are not implemented.
- Provincial, household-size and income-quintile differences are descriptive.
- Public codebook exceptions remain preserved from Checkpoint 5.
- Personal coverage is short, private and incomplete across accounts and payment channels.
- No inflation adjustment, causal model, prediction, anomaly model or dashboard is part of Checkpoint 6.
