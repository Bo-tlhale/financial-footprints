# Documentation index

Each document has one purpose so project setup, methodology, findings and historical decisions do not compete for attention.

| Document | Purpose |
| --- | --- |
| [README](../README.md) | Project status, structure, installation and commands |
| [PROCESS](PROCESS.md) | Chronological engineering decisions, problems and validation outcomes |
| [DATA_DICTIONARY](DATA_DICTIONARY.md) | Stats SA processed-table grain, fields and amount semantics |
| [COMPARISON_METHODOLOGY](COMPARISON_METHODOLOGY.md) | Rules and limitations for any personal-versus-household context |
| [EDA_METHODOLOGY](EDA_METHODOLOGY.md) | Checkpoint 6 estimands, metrics, exclusions, weighting and reproduction |
| [EDA_FINDINGS](EDA_FINDINGS.md) | Privacy-safe evidence, interpretation and limitations |
| [STATISTICAL_METHODOLOGY](STATISTICAL_METHODOLOGY.md) | Checkpoint 7 research design, weighted methods, outlier/recurrence rules and model specification |
| [STATISTICAL_FINDINGS](STATISTICAL_FINDINGS.md) | Privacy-safe statistical evidence, model diagnostics and limitations |

Generated outputs have separate destinations:

- `reports/private/` contains ignored personal results and charts.
- `reports/public/` contains reproducible aggregate Stats SA tables, metrics and charts.
- `notebooks/` contains output-free explanatory entry points.
- `reports/public/statistics/` and `reports/public/statistics_model/` contain aggregate Checkpoint 7 results.

Source code is grouped by pipeline stage under `src/`. Configuration is kept under `config/`. Raw and processed data remain under `data/`; no official or personal source file belongs at the repository root.
