# Financial Footprints

Financial Footprints is a privacy-conscious Python data project that turns supported bank statements into validated transactions and studies those records separately from South African household expenditure microdata.

The project now includes extraction, preprocessing, categorisation, manual-review support, Stats SA IES 2022/23 integration, exploratory analysis, and reproducible statistical analysis with an interpretable household model.

## Current status

| Checkpoint | Outcome |
| --- | --- |
| 1. Statement extraction | Complete |
| 2. Transaction preprocessing | Complete |
| 3. Merchant and category rules | Complete |
| 4. Manual review and curated data | Complete; local decisions remain private |
| 5. Stats SA IES integration | Complete against all five official Stata files |
| 6. Exploratory data analysis | Complete |
| 7. Statistical analysis and modelling | Complete and ready for review |
| 8. Dashboard and final presentation | Not started |

Checkpoints 6 and 7 retain two independent tracks:

- Personal account behaviour: movement composition, resolved spending categories, time patterns, merchant concentration, and recurring-payment candidates.
- Household expenditure: weighted and unweighted consumption distributions, COICOP shares, household composition, single-person households, provinces, and published household income quintiles.

The project does not equate one bank account with one survey household. The current personal and public datasets also have different periods and price bases, so no nominal-rand comparison is published.

## Repository layout

```text
financial-footprints/
|-- config/                 # category, merchant, mapping, and source definitions
|-- data/
|   |-- raw/                # ignored private statement PDFs
|   |-- private/            # ignored private transaction tables
|   |-- public/
|   |   |-- raw/            # ignored official source files
|   |   `-- processed/      # ignored validated survey tables
|   `-- synthetic/          # privacy-safe fixtures
|-- docs/                   # methodology, findings, dictionary, and decision log
|-- notebooks/              # output-free EDA entry points
|-- reports/
|   |-- private/            # ignored private metrics and charts
|   `-- public/             # aggregate public EDA outputs
|-- src/
|   |-- extraction/
|   |-- preprocessing/
|   |-- categorisation/
|   |-- public_data/
|   `-- analysis/
|-- tests/
|-- statement_extractor.py  # compatibility CLI wrapper
|-- requirements.txt
`-- README.md
```

Start with [the documentation index](docs/INDEX.md). The README provides setup and entry points; detailed reasoning is kept in the focused documents under `docs/`.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Pipeline

### 1. Extract statements

```powershell
python statement_extractor.py --input "data/raw" --output "data/private/transactions.csv" --report "data/private/validation.json"
```

### 2. Preprocess financial movements

```powershell
python -m src.preprocessing.pipeline --input "data/private/transactions.csv" --output "data/private/preprocessed_transactions.csv"
```

### 3. Categorise and prepare manual review

```powershell
python -m src.categorisation.pipeline --input "data/private/preprocessed_transactions.csv" --output "data/private/categorised_transactions.csv" --review "data/private/classification_review.csv"
```

After reviewing the CSV, import decisions and generate the curated dataset:

```powershell
python -m src.categorisation.review_manager --review "data/private/classification_review.csv" --source "data/private/categorised_transactions.csv" --corrections "data/private/classification_corrections.csv"
python -m src.categorisation.curated_pipeline --input "data/private/categorised_transactions.csv" --corrections "data/private/classification_corrections.csv" --output "data/private/curated_transactions.csv"
```

### 4. Prepare Stats SA IES data

Place the authorised downloads in the documented `data/public/raw/` subdirectories, then run:

```powershell
python -m src.public_data.pipeline --input "data/public/raw" --output "data/public/processed"
```

The repository does not redistribute the official microdata, metadata PDF, or COICOP workbook. Source identities and hashes are pinned in `config/public_data_sources.yaml`.

### 5. Run exploratory analysis

```powershell
python -m src.analysis.pipeline --track personal
python -m src.analysis.pipeline --track public
python -m src.analysis.pipeline --track all
```

Personal outputs are written to the ignored `reports/private/` directory. Public aggregate tables and charts are written to `reports/public/`. Each track stages a complete output directory before replacement, so a failed run does not leave a partial report.

The notebooks are concise, output-free entry points:

- `notebooks/01_personal_expenditure_eda.ipynb`
- `notebooks/02_sa_household_expenditure_eda.ipynb`

Substantial calculations live in `src/analysis/`, not in notebook cells.

### 6. Run statistical analysis

```powershell
python -m src.analysis.statistics.pipeline --track personal
python -m src.analysis.statistics.pipeline --track public
python -m src.analysis.statistics.pipeline --track modelling
```

The personal command writes only to ignored `reports/private/statistics/`. The public commands generate aggregate CSV, JSON and PNG outputs under `reports/public/statistics/` and `reports/public/statistics_model/`. The model is an exploratory weighted log-linear association model; it is not a forecast and reports no p-values or confidence intervals.

Checkpoint 7 notebooks are output-free entry points:

- `notebooks/03_personal_statistical_analysis.ipynb`
- `notebooks/04_household_statistical_analysis.ipynb`
- `notebooks/05_household_modelling.ipynb`

## Verified EDA coverage

The private track processed 595 transactions from eight reconciled statement periods spanning 31 January to 26 September 2026. The statements cover 235 days and leave four uncovered dates: 27 April and 24–26 May. Two hundred and five rows still require classification review. Category findings exclude 185 unresolved purchases worth R25,205.84 and cover R15,598.44, or 38.23% of the R40,804.28 eligible expenditure. No personal transaction descriptions, merchant rankings, or account balances are published.

The public track verified 1,128,279 expenditure records, 19,940 households, 70,339 persons, 48,038 person-income observations, and 4,652 single-person households. It uses 956,234 ordinary-consumption records (`coicop_type == 1`). See [the findings](docs/EDA_FINDINGS.md) for the publishable results and qualifications.

## Testing

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=.pytest-tmp
```

Tests use synthetic fixtures for private financial records and survey relationships. The optional private regression test runs only when its local source files are available.

## Privacy and research boundaries

- Private PDFs, transactions, review decisions, reports, charts, and merchant detail are ignored by Git.
- Public raw and processed microdata remain local and ignored.
- Public repository outputs contain aggregate survey results only.
- Ordinary account debits are not automatically called spending.
- Household expenditure is aggregated before household statistics and is never duplicated across person rows.
- Weighted point estimates use `HHOLD_WGT`; unsupported confidence intervals and p-values are not reported.
- The 2026 personal data and May-2023-price survey data are not directly compared.

## Documentation

- [Documentation index](docs/INDEX.md)
- [Engineering process and decision log](docs/PROCESS.md)
- [Public data dictionary](docs/DATA_DICTIONARY.md)
- [Personal-versus-household comparison methodology](docs/COMPARISON_METHODOLOGY.md)
- [EDA methodology](docs/EDA_METHODOLOGY.md)
- [Publishable EDA findings](docs/EDA_FINDINGS.md)
- [Statistical methodology](docs/STATISTICAL_METHODOLOGY.md)
- [Statistical findings](docs/STATISTICAL_FINDINGS.md)
