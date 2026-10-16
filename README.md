# Financial Footprints

Financial Footprints is a privacy-conscious personal finance data science project. It converts supported text-based ABSA cheque-account statements into validated transactions, prepares those records with transparent movement classification, and applies auditable merchant and spending-category rules. Broader household-expenditure research and analytical modelling are planned separately.

## Problem statement

Manual transcription of bank-statement PDFs is slow, difficult to reproduce and vulnerable to financial errors. Financial Footprints creates a deterministic local extraction process with explicit balance and statement-summary checks before any output is accepted.

## Objectives

- Build a reproducible pipeline from statement PDFs to structured transactions.
- Preserve transaction provenance, monetary direction and bank charges.
- Fail safely when extraction or reconciliation is unreliable.
- Protect private source data in a public portfolio repository.
- Establish a maintainable foundation for later financial-behaviour research.

## Research direction

Planned work will study personal expenditure patterns and, separately, public South African household-expenditure datasets. Exploratory analysis, statistical analysis, modelling and dashboards are not implemented yet.

## Status

| Area | Status |
| --- | --- |
| ABSA PDF extraction and financial reconciliation | Completed for two tested consecutive statement periods |
| Deterministic multi-statement consolidation | Completed |
| Identical-file skipping and overlap review flags | Completed |
| Transaction preprocessing and movement classification | Completed |
| Merchant identification and transaction categorisation | Completed |
| Broader layout and bank support | Planned |
| Analysis, modelling and dashboards | Planned |

## Technology stack

- Python 3.10+
- PyMuPDF for positioned PDF text extraction
- `Decimal` for monetary calculations
- PyYAML for validated, editable category and merchant rules
- pytest for automated testing
- CSV and JSON outputs for portability and auditability

## Architecture

The root `statement_extractor.py` is a compatibility wrapper. The implementation lives in `src/extraction/statement_extractor.py`. Each unique input is extracted and reconciled in memory first. Only after every statement passes are staged output files moved into place, protecting an existing valid dataset from extraction or validation failures.

Statements are processed in deterministic filename order by the CLI. Consolidated transactions are ordered chronologically, with statement source order and original row order resolving equal dates. Byte-identical PDFs are skipped. Date-range overlaps and transaction candidates that look identical across different statements are reported for human review and are never silently removed.

The preprocessing package under `src/preprocessing/` validates the extractor schema, standardizes dates and descriptions, classifies financial movement, verifies that source values remain intact, and atomically replaces its output only after all checks pass.

The categorisation package under `src/categorisation/` validates YAML configuration, identifies merchants from cleaned descriptions, categorises eligible expenditure, excludes non-spending movements, preserves all source fields and stages both output CSVs before replacement.

## Repository structure

```text
financial-footprints/
|-- data/
|   |-- raw/          # ignored private statement PDFs
|   |-- private/      # ignored generated transactions and reports
|   |-- public/       # future public datasets
|   `-- synthetic/    # safe synthetic fixtures
|-- src/
|   |-- extraction/   # implemented statement pipeline
|   |-- preprocessing/ # cleaning, validation and movement classification
|   |-- categorisation/ # merchant identification and expense categories
|   |-- analysis/
|   `-- modelling/
|-- notebooks/
|-- dashboards/
|-- reports/
|-- tests/
|-- docs/PROCESS.md
|-- statement_extractor.py
|-- requirements.txt
`-- README.md
```

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## PDF extraction

Place supported statement PDFs in `data/raw/`, then run from the repository root:

```powershell
python statement_extractor.py --input "data/raw" --output "data/private/transactions.csv" --report "data/private/validation.json"
```

The input can also be one PDF. Output directories are created automatically. Regeneration replaces the master outputs rather than appending to them.

## Expected outputs

`data/private/transactions.csv` contains:

```text
transaction_id,transaction_date,effective_date,transaction_type,description,debit,credit,fee,balance,source_file,page_number
```

`data/private/validation.json` records per-statement reconciliation, identical files skipped, overlapping periods and potential cross-statement duplicate candidates. An all-zero supplementary effective date is stored as missing; it never replaces the valid posting date.

## Transaction preprocessing

Preprocessing converts the reconciled extractor output into an analysis-ready dataset without changing the underlying financial records.

Run from the repository root:

```powershell
python -m src.preprocessing.pipeline --input "data/private/transactions.csv" --output "data/private/preprocessed_transactions.csv"
```

The pipeline validates the exact extractor schema, transaction IDs, ISO dates, two-decimal monetary fields, source references and duplicate IDs. It preserves the original columns and appends:

```text
cleaned_description,movement_type,movement_classification_method,movement_review_required
```

`cleaned_description` normalizes casing, whitespace and control characters while leaving `description` unchanged. `movement_type` describes financial movement rather than spending category.

### Movement rules

The classifier uses deterministic rules in this order:

1. Validated bank transaction types identify purchases, transfers, refunds, cash withdrawals, fees, reversals and informational entries.
2. Narrow description rules identify explicit salary, payroll, pension, refund or reversal wording.
3. Financial-field rules identify otherwise unmapped fee-only or zero-movement rows and flag them for review.
4. Unsupported or directionally inconsistent records become `Unknown` and require review.

An incoming credit is not automatically treated as income, and a debit is not automatically treated as a purchase. Debit orders remain `Unknown` until a reliable movement rule is established. Merchant identification and expense categorisation remain separate concerns handled by the next pipeline stage.

The output is `data/private/preprocessed_transactions.csv`. It is ignored by Git and can be opened directly in VS Code or Excel. A failed run does not overwrite a previously validated output.

## Merchant identification and categorisation

Run the categorisation pipeline from the repository root after preprocessing:

```powershell
python -m src.categorisation.pipeline --input "data/private/preprocessed_transactions.csv" --output "data/private/categorised_transactions.csv" --review "data/private/classification_review.csv"
```

The validated hierarchy is defined in `config/categories.yaml`; public merchant aliases and carefully bounded regular expressions live in `config/merchant_rules.yaml`. Rules are ordered deterministically by priority, specificity and rule ID. Identical patterns are rejected as duplicates or conflicts, while equally ranked overlapping matches with different outcomes are left unclassified and flagged for review.

The categorised dataset preserves all 15 preprocessing fields and appends:

```text
clean_merchant,category,subcategory,classification_method,classification_confidence,category_review_required,spending_classification_status
```

Classification methods are `merchant_rule`, `transaction_rule`, `movement_exclusion` and `unclassified`. Confidence is an interpretable rule label (`high`, `medium`, `low` or `unknown`), not a statistical probability.

### Category hierarchy

- Food & Dining: Restaurants, Fast Food, Food Delivery
- Groceries: Supermarkets, Convenience Stores
- Transport: Ride-Hailing, Public Transport, Fuel
- Shopping: Clothing, Electronics, General Retail
- Healthcare: Pharmacy, Medical Services
- Entertainment: Cinema, Events, Leisure
- Subscriptions: Streaming, Software, Memberships
- Utilities & Communication: Airtime, Mobile Data, Electricity
- Financial Charges: Bank Fees, Transaction Fees
- Other Expenses: Miscellaneous
- Uncategorised: Needs Review

Only `Purchase` and `Bank Fee` movements are eligible for current spending categorisation. Income, transfers, refunds, cash withdrawals, reversals and informational records receive `not_applicable`; they retain their movement type and are not counted as new expenditure. Unknown movements require review. A known merchant does not guarantee a known purchase category: broad retailers can receive a merchant name with a blank category and a review flag.

`data/private/classification_review.csv` contains all records in source order with compact, human-readable suggestions and transaction traceability. It is intended for inspection only in this checkpoint. Persistent corrections and review imports are deliberately deferred. A differing existing review file is not overwritten unless it has been inspected and the command is rerun with `--overwrite-review`.

Both generated CSVs are ignored by Git. Configuration under `config/` must contain only generic public merchant rules; private counterparties or mappings belong in ignored private configuration.

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use synthetic records and generated PDFs. A private local regression can be enabled without committing its source:

```powershell
$env:FINANCIAL_FOOTPRINTS_PRIVATE_TEST_PDF="data/raw/your-statement.pdf"
.\.venv\Scripts\python.exe -m pytest -q
```

The suite covers extraction, preprocessing, configuration validation, merchant aliases and overlaps, category decisions, movement exclusions, review output, deterministic processing, paired output safety and financial-record preservation.

## Privacy

Real statements, private CSVs, private merchant mappings, validation reports, environment files, caches and private notebooks are excluded by `.gitignore`. Extracted descriptions are partially redacted, but exports must still be treated as private. Before publishing, also inspect Git history: adding an ignore rule does not remove a file that was previously committed.

The repository is hosted at [Bo-tlhale/financial-footprints](https://github.com/Bo-tlhale/financial-footprints). Private PDFs and generated CSV/JSON files are not tracked.

## Development roadmap

1. Validate additional months and ABSA layout variants with manual sampling.
2. Add synthetic PDF fixtures covering more layout changes.
3. Review classification suggestions and implement persistent manual corrections.
4. Add exploratory and statistical analysis using private and public datasets separately.
5. Evaluate modelling and visualisation only after data quality is established.

Current merchant coverage is intentionally limited to generic, validated public-brand patterns. Unrecognised merchants and ambiguous multi-category retailers remain visible for review. Rules do not infer basket contents, link refunds to earlier purchases, classify cash spending after withdrawal, or learn from corrections yet.

See [docs/PROCESS.md](docs/PROCESS.md) for the chronological engineering record and current limitations.
