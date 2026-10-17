# Personal-versus-household expenditure comparison methodology

## What can be compared

The personal dataset records one account's observed transactions. IES records estimated annual household expenditure collected through diaries and recall, adjusted to May 2023 prices. They differ in person coverage, payment channels, recall periods, weighting and price basis. Consequently, the crosswalk does **not** assert direct equivalence: every mapped category is labelled `adjustment_required`; everything else is `not_comparable`.

Before a later analysis, personal transactions must be restricted to the matching period, annualised only when coverage is complete enough to justify it, and expressed in a comparable May 2023 price basis. Household size and survey weights must be handled explicitly. A single household observation is not a benchmark for a single account holder.

## Individual and household readiness

The real household and person files have complete relationships: 19,940 household IDs match geography, all 70,339 persons match a household, and all 48,038 PersonIncome observations match a person. Published household size agrees with person-record counts for every household. The processed household table identifies 4,652 single-person households.

Single-person households offer a narrower future comparison population, but they still do not establish equivalence. Their expenditure includes all acquisition channels captured by diary and recall; the personal dataset covers one bank account and may omit cash, other accounts and other payment instruments. Person characteristics and PersonIncome can support stratification, but expenditure remains at household/expenditure-unit level and is never copied onto person rows.

## Crosswalk decisions

The executable source of truth is `config/expenditure_mapping.yaml`. Narrow group rules take precedence over division rules.

| IES scope | Personal scope | Decision |
|---|---|---|
| Division 01 food and non-alcoholic beverages | Groceries | Map with adjustment; household acquisitions include channels not visible in bank transactions |
| Division 03 clothing and footwear | Shopping | Map with adjustment |
| Group 045 electricity, gas and fuels | Utilities & Communication | Map with adjustment; it is broader than electricity |
| Division 06 health | Healthcare | Map with adjustment; goods, services and household pooling differ |
| Division 07 transport | Transport | Map with adjustment; includes vehicle purchases and operation |
| Groups 081/082/083 | Shopping, Subscriptions, Utilities & Communication | Split equipment, software and services; all need adjustment |
| Division 09 recreation and culture | Entertainment | Map with adjustment; includes goods, pets, books and holidays |
| Group 111 food-serving services | Food & Dining | Map with adjustment |
| Group 122 financial services | Financial Charges | Map with adjustment; broader than bank fees |
| Groups 131/132 personal care/effects | Shopping | Map with adjustment |

Alcohol/tobacco, housing and imputed rent, furnishings, education, accommodation, insurance, social protection and other mixed services remain unmapped. COICOP types for income, in-kind income, savings, taxes, transfers, debts and non-CPI records are never treated as personal spending merely because an item code resembles a consumption category.

## Safe analytical rules

1. Filter to `coicop_type == 1` for ordinary consumption unless a different, documented estimand is intended.
2. Report mapped coverage and the unmapped share alongside any result.
3. Aggregate unweighted values within household before calculating household statistics.
4. Use survey weights only with an explicit population estimator; never average `valueannualized_adj_wgt`.
5. Describe results as contextual household benchmarks, not evidence that the personal account holder overspent or underspent.
6. Treat the 2022/23 survey and 2026 bank periods as non-contemporaneous. Do not compare nominal amounts until an official price index, reference month and adjustment procedure are selected.
7. For spending-share comparisons, define both denominators over the same mapped consumption scope and report that 365,379 total-file rows are currently `not_comparable`.

Checkpoint 5 prepares data only. Charts, descriptive findings and personal comparisons belong to a later EDA checkpoint.
