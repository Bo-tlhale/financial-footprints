# Financial Footprints

Financial Footprints is a privacy-conscious personal finance data science project. Its completed first stage converts supported text-based ABSA cheque-account statements into a validated, analysis-ready transaction dataset. Broader household-expenditure research and analytical modelling are planned separately.

## Problem statement

Manual transcription of bank-statement PDFs is slow, difficult to reproduce and vulnerable to financial errors. Financial Footprints creates a deterministic local extraction process with explicit balance and statement-summary checks before any output is accepted.

## Objectives

- Build a reproducible pipeline from statement PDFs to structured transactions.
- Preserve transaction provenance, monetary direction and bank charges.
- Fail safely when extraction or reconciliation is unreliable.
- Protect private source data in a public portfolio repository.
- Establish a maintainable foundation for later financial-behaviour research.

## Research direction

Planned work will study personal expenditure patterns and, separately, public South African household-expenditure datasets. Transaction categorisation, exploratory analysis, statistical analysis, modelling and dashboards are not implemented yet.

## Status

| Area | Status |
| --- | --- |
| ABSA PDF extraction and financial reconciliation | Completed for two tested consecutive statement periods |
| Deterministic multi-statement consolidation | Completed |
| Identical-file skipping and overlap review flags | Completed |
| Broader layout and bank support | Planned |
| Categorisation, analysis, modelling and dashboards | Planned |

## Technology stack

- Python 3.10+
- PyMuPDF for positioned PDF text extraction
- `Decimal` for monetary calculations
- pytest for automated testing
- CSV and JSON outputs for portability and auditability

## Architecture

The root `statement_extractor.py` is a compatibility wrapper. The implementation lives in `src/extraction/statement_extractor.py`. Each unique input is extracted and reconciled in memory first. Only after every statement passes are staged output files moved into place, protecting an existing valid dataset from extraction or validation failures.

Statements are processed in deterministic filename order by the CLI. Consolidated transactions are ordered chronologically, with statement source order and original row order resolving equal dates. Byte-identical PDFs are skipped. Date-range overlaps and transaction candidates that look identical across different statements are reported for human review and are never silently removed.

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
|   |-- preprocessing/
|   |-- categorisation/
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

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use synthetic records and generated PDFs. A private local regression can be enabled without committing its source:

```powershell
$env:FINANCIAL_FOOTPRINTS_PRIVATE_TEST_PDF="data/raw/your-statement.pdf"
.\.venv\Scripts\python.exe -m pytest -q
```

## Privacy

Real statements, private CSVs, validation reports, environment files, caches and private notebooks are excluded by `.gitignore`. Extracted descriptions are partially redacted, but exports must still be treated as private. Before publishing, also inspect Git history: adding an ignore rule does not remove a file that was previously committed.

This directory currently has no Git metadata available, so tracked-file and history checks cannot be performed here.

## Development roadmap

1. Validate additional months and ABSA layout variants with manual sampling.
2. Add synthetic PDF fixtures covering more layout changes.
3. Design preprocessing and data-quality contracts.
4. Develop transaction categorisation with an auditable labelled dataset.
5. Add exploratory and statistical analysis using private and public datasets separately.
6. Evaluate modelling and visualisation only after data quality is established.

See [docs/PROCESS.md](docs/PROCESS.md) for the chronological engineering record and current limitations.
