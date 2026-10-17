# Public expenditure data dictionary

## Source and observation grain

The public-data stage uses Statistics South Africa's **Income and Expenditure Survey (IES) 2022/23**. The real Stata files contain 1,128,279 total records, 19,940 household records, 19,940 geography records, 70,339 person records and 48,038 PersonIncome records. Geography, households, person and total are version 1.2; PersonIncome is version 1.1.

The total file's expenditure grain is an expenditure unit. Multiple rows for one household and detailed COICOP code are permitted; it is neither a bank-transaction table nor a household summary. `UQNO` is the household join key and `PERSON_ID` is the person join key. String identifiers are authoritative because identifiers are labels, not quantities.

## Processed outputs

### `ies_2022_2023_expenditure.csv`

| Field | Meaning |
|---|---|
| `uqno`, `uqno_num` | Household identifier and numeric compatibility field |
| `coicop` | Eight-digit detailed Stats SA COICOP item code |
| `coicop_type` | Consumption, income, saving, tax, transfer, debt or other published record type |
| `division`, `group`, `class`, `subclass`, `sixth_group` | Published hierarchy retained as fixed-width strings |
| `valueannualized_adj` | Unweighted item value, annualised and adjusted to May 2023 prices |
| `valueannualized_adj_wgt` | Survey-weighted annualised value at May 2023 prices |
| `*_description` | Labels joined from the official workbook; synonymous duplicate item labels are separated by ` / ` |
| `province`, `metro_code`, `settlement_type`, `survey_date` | Geography joined many-to-one by `uqno` |
| `codebook_match_status` | `matched`, `coicop_type_conflict`, or `code_absent_from_codebook` |
| `personal_category`, `personal_subcategory` | Conservative project crosswalk; blank means no defensible mapping |
| `comparability` | `adjustment_required` or `not_comparable` |
| `mapping_rule_id`, `mapping_rationale` | Auditable rule and its limitation |

Stata stores hierarchy fields numerically. Processing restores leading zeroes to widths 8, 2, 3, 4, 5 and 6 for COICOP, division, group, class, subclass and sixth group. Source monetary values are retained without imputation.

### `ies_2022_2023_households.csv`

This one-row-per-household table retains `UQNO`, `UQNO_NUM`, `HSIZE`, household-head characteristics, `HHOLD_WGT`, annual expenditure/income, in-kind measures, weighted measures, per-capita measures, deciles and quintiles. It adds geography, `PERSON_RECORD_COUNT`, and `SINGLE_PERSON_HOUSEHOLD`. The last field is derived only from published `HSIZE == 1`; all 19,940 `HSIZE` values matched the number of person records.

### `ies_2022_2023_persons.csv`

This one-row-per-person table retains `PERSON_ID`, its parent `UQNO`, person number, sex, age, population group, household relationship, marital status, education, selected labour variables, main income source and `PERSNS_WGT`. Geography is joined many-to-one by `UQNO`. It contains no household expenditure.

### `ies_2022_2023_person_income.csv`

This preserves the PersonIncome observation grain: `PERSON_ID`, detailed `COICOP`, income quintile, annualised income and weighted annualised income, plus the validated parent `UQNO`. Multiple income observations per person are retained. Ninety-one exact duplicate source rows are reported and not silently deleted.

### `ies_2022_2023_quality_report.json`

The report records discovered files and hashes, source schemas and types, missingness, duplicates, monetary ranges, relationship coverage, single-person household count, COICOP and mapping coverage, output hashes, warnings and final status.

## Nulls, zeroes, duplicates and codebook exceptions

Blank monetary values remain blank and numeric zero remains zero. Non-finite values fail validation. Negative core monetary values fail because official metadata documents positive ranges. Values are parsed with `Decimal` during expenditure processing.

The real files contain no system-missing, zero or negative values in the validated core monetary fields. Survey response codes such as `8`, `88` and `8888` are published categorical codes and are retained; they are not converted to nulls.

The total file has 187,354 repeated `(uqno, coicop)` occurrences beyond the first occurrence of each key. These are retained because the documented grain is an expenditure unit. PersonIncome has 91 exact duplicate occurrences beyond the first; those are also retained and reported.

The total file contains 885 distinct detailed codes. Two codes (`04230900`, `50600800`) are absent from the supplied workbook, and nine codes have source COICOP types that conflict with it. The records remain intact, are explicitly flagged and never receive invented labels.

## Amount use

Use `valueannualized_adj` for sampled-household annual values. Use weighted fields only for survey-population estimates with an explicit estimator and denominator. Do not average weighted values, add consumption to income/debt records, or treat household expenditure as one person's bank-card spending.

## Provenance

`config/public_data_sources.yaml` pins the catalog identity, DOI, URLs, versions, licence and SHA-256 digests of all five Stata files plus the metadata and COICOP workbook. Raw and processed data are intentionally ignored by Git.
