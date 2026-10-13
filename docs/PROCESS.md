# Financial Footprints engineering process and decision log

## Stage 1: Problem identification

**Objective:** Replace repetitive, error-prone manual conversion of bank-statement PDFs with a reproducible local process.

**Methodology:** Define a narrow extraction stage before preprocessing or analysis.

**Challenge:** A plausible CSV can still contain financially incorrect rows.

**Decision:** Treat financial reconciliation as a required extraction outcome, not an optional downstream check.

**Outcome:** The project began as a bank-layout-specific data engineering component.

**Remaining limitation:** Input support is intentionally narrow.

## Stage 2: Initial data assessment

**Objective:** Understand the selectable-text ABSA cheque-statement layout.

**Methodology:** Examine transaction columns, positioned words, repeated page headers, multiline descriptions, page transitions and the financial summary.

**Challenge:** Descriptions and effective-date metadata occupy lines below their transaction rows and can continue on another page.

**Decision:** Group words by baseline and retain a pending transaction across page boundaries.

**Testing and validation:** Representative rows were compared with statement layout and running balances.

**Outcome:** Stable coordinate ranges were identified for the two tested consecutive statement periods.

**Remaining limitation:** Scanned PDFs and unrelated layouts are unsupported.

## Stage 3: Extractor development

**Objective:** Convert statement transactions into consistent structured records.

**Implementation:** Added posting date, available effective date, transaction type, description, debit, credit, charge, balance, source filename and page number. Transaction fees are separated from ordinary debit spending. Informational zero-movement rows are preserved.

**Challenge:** Narrative lines can contain identifiers.

**Decision:** Apply basic identifier redaction while treating every export as private.

**Testing and validation:** Synthetic tests cover money direction, description redaction, multiline descriptions and page transitions.

**Outcome:** The extractor produces CSV-ready records with source provenance.

**Remaining limitation:** Narrative redaction is not a guarantee of anonymisation.

## Stage 4: Error investigation

**Objective:** Resolve failures caused by `00/00/0000` in international-payment information.

**Methodology:** Locate the value in positioned text and distinguish the main posting-date column from supplementary `(Effective ...)` metadata.

**Challenge:** Applying posting-date validation to supplementary placeholders stopped otherwise valid statements.

**Decision:** Convert only the all-zero effective-date placeholder to a missing value. Continue rejecting invalid posting dates and other malformed effective dates.

**Testing and validation:** Synthetic date and international-fee tests confirm the distinction.

**Outcome:** International-payment fee rows retain their valid posting date and reconcile correctly.

**Remaining limitation:** Other undocumented placeholder formats are not assumed to be valid.

## Stage 5: Financial validation

**Objective:** Prevent financially inconsistent datasets from being exported.

**Implementation:** Use `Decimal`; validate every running balance; reconcile opening balance, closing balance, credits, withdrawals, sundry debits and charges with the statement summary.

**Challenge:** ABSA lists cancelled CashSend debits and reversals in transaction history but excludes a matched pair from published debit and credit totals.

**Decision:** Match only same-date, same-amount `Cashsend Mobile` and `Can Cashsend Mb` pairs for summary reconciliation. Preserve both source transactions in the CSV and never change their amounts.

**Testing and validation:** Synthetic tests cover balance failures, summary differences and matched cancellations.

**Outcome:** Reconciliation failures provide extracted and expected totals and prevent output replacement.

**Remaining limitation:** New cancellation labels require explicit validation before support is expanded.

## Stage 6: Multi-statement testing

**Objective:** Build one deterministic dataset from multiple statements.

**Implementation:** Process all PDFs, skip byte-identical files, retain source provenance and sort by posting date with source and row order as tie-breakers.

**Challenge:** Overlapping periods can contain repeated transactions, while identical-looking transactions can also be legitimate.

**Decision:** Flag overlapping date ranges and cross-statement duplicate candidates in the validation report; do not automatically delete them.

**Testing and validation:** The extractor was exercised against two consecutive private ABSA statements. Synthetic tests cover source ordering, identical-file skipping and overlap candidates.

**Outcome:** Both tested statements can be regenerated as one validated dataset.

**Remaining limitation:** Potential duplicates from overlapping statements require human review.

## Stage 7: Repository restructuring

**Objective:** Establish a GitHub-ready architecture without breaking the existing command.

**Implementation:** Moved the implementation into `src/extraction/`, retained a lightweight root CLI, added scoped future-stage directories and strengthened `.gitignore`. CSV and JSON are staged only after every unique input validates, then moved into place.

**Challenge:** Existing valid outputs must survive a later failed run.

**Decision:** Complete extraction and validation before writing temporary output files. Replace destinations only after staging succeeds.

**Testing and validation:** Automated tests cover imports, CLI input resolution, extraction details, reconciliation, consolidation and preservation of existing outputs after failure. The root command is also verified against the private local inputs without publishing their contents.

**Outcome:** Extraction is isolated as a package while command-line compatibility is preserved.

**Remaining limitations:** The current workspace is not a Git repository, so previously tracked sensitive files and Git history cannot be audited. Atomic replacement protects against validation and staging failures; replacing two separate destination files cannot be a single filesystem transaction.

## Next development step

Validate additional statement months and layout variants with manual stratified sampling, then define preprocessing data contracts. Categorisation and analysis should remain out of scope until extraction coverage is broader.

## Stage 8: Project identity and Git preparation

**Objective:** Adopt the Financial Footprints project identity and prepare the repository for GitHub publication.

**Implementation:** Updated project-facing names in documentation and package descriptions while preserving the established extractor command and file layout. Renamed the private regression-test environment variable and retained the previous variable as a compatibility fallback.

**Challenge:** The target GitHub repository does not yet exist, and the GitHub CLI is not installed locally.

**Decision:** Prepare and audit the local repository first. Do not create a commit or publish files until the milestone review is approved.

**Testing and validation:** The complete suite passed with 12 tests and one optional private regression skipped. The compatible root command processed both local statements, produced 150 consolidated transactions and passed full reconciliation. The proposed Git file set was inspected separately from ignored private inputs and outputs.

**Outcome:** The local project is stable under the Financial Footprints identity and ready for milestone review.

**Remaining limitations:** Remote repository creation and the first push remain separate actions after approval.
