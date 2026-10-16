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

**Remaining limitations:** At that stage the workspace had not yet been initialized as a Git repository, so tracked sensitive files and history could not be audited. Atomic replacement protects against validation and staging failures; replacing two separate destination files cannot be a single filesystem transaction.

## Next development step

Validate additional statement months and layout variants with manual stratified sampling, then define preprocessing data contracts. Categorisation and analysis should remain out of scope until extraction coverage is broader.

## Stage 8: Project identity and Git preparation

**Objective:** Adopt the Financial Footprints project identity and prepare the repository for GitHub publication.

**Implementation:** Updated project-facing names in documentation and package descriptions while preserving the established extractor command and file layout. Renamed the private regression-test environment variable and retained the previous variable as a compatibility fallback.

**Challenge:** At the start of this stage, the target GitHub repository did not yet exist and the GitHub CLI was not installed locally.

**Decision:** Prepare and audit the local repository first. Do not create a commit or publish files until the milestone review is approved.

**Testing and validation:** The complete suite passed with 12 tests and one optional private regression skipped. The compatible root command processed both local statements, produced 150 consolidated transactions and passed full reconciliation. The proposed Git file set was inspected separately from ignored private inputs and outputs.

**Outcome:** The local project is stable under the Financial Footprints identity and ready for milestone review.

**Remaining limitations:** This was resolved after milestone approval: the repository was created and the initial commit was pushed to `Bo-tlhale/financial-footprints`.

## Checkpoint 2: Transaction preprocessing and movement classification

**Objective:** Transform the reconciled extractor CSV into a clean, validated dataset with transparent financial-movement labels while preserving every source record.

**Problem identified:** The extractor output is financially reconciled but still needs standardized analytical fields. A debit cannot safely be treated as spending, and a credit cannot safely be treated as income.

**Initial data assessment:** The verified source schema contains 11 columns. Charges are stored in `fee`, not `debit`. Missing effective dates are empty strings. Informational entries remain as zero-movement rows. The private integration source contained 150 unique transaction IDs, 63 missing effective dates, no missing descriptions and four zero-movement records.

**Approach selected:** Add separate cleaning, validation, classification and pipeline modules. Preserve source columns, append four preprocessing fields and fail before output replacement when a critical validation check fails.

**Implementation:**

- Standardized posting and effective dates to ISO 8601.
- Converted `00/00/0000` effective-date placeholders to missing values without weakening posting-date validation.
- Added a lower-case, whitespace-normalized `cleaned_description` while preserving `description`.
- Validated exact source schema, IDs, two-decimal monetary strings, page references and duplicate IDs.
- Added deterministic movement types, classification methods and boolean review flags.
- Added atomic CSV output at `data/private/preprocessed_transactions.csv`.
- Added concise aggregate console reporting without transaction descriptions or amounts.

**Architectural decisions:** Bank transaction type is the primary evidence. Narrow description rules apply only to explicit income, refund or reversal wording. Direction alone never establishes spending or income. Unknown and inconsistent records remain represented and require review. The pipeline does not perform merchant identification or expense categorisation.

**Challenges encountered:** The first automated run exposed a synthetic fixture writer that rejected the intentionally omitted schema column before the pipeline could validate it. The fixture was corrected without weakening pipeline checks. The first module CLI run also exposed an eager package import that caused a `runpy` warning; removing the import made module execution clean.

**Solutions and refinements:** Review flags are stored as booleans and serialized as `True` or `False`. Direct bank-type rules require the expected debit, credit or fee direction. Debit orders remain `Unknown` because their analytical meaning cannot be inferred safely from the current data.

**Testing methodology:** Synthetic tests cover dates, missing effective dates, description cleaning, money preservation, schemas, invalid numeric values, duplicate IDs, empty inputs, all supported movement types, ambiguous records, deterministic output, record ordering, financial invariants and safe failure. The complete Checkpoint 1 extraction suite runs alongside these tests.

**Validation results:** The full automated suite passed with 47 tests and one optional private regression skipped. Private integration preserved all 150 records, IDs, descriptions, source references and financial fields. Two ambiguous debit-order records were classified as `Unknown` and flagged for review. Repeated runs produced identical output hashes.

**Remaining limitations:** Rules cover the transaction types observed in the two verified statements plus explicitly tested description terms. New bank labels and ambiguous descriptions require review. Movement classification is not merchant normalization or expense categorisation.

**Final checkpoint outcome:** Checkpoint 2 meets the preprocessing, classification, determinism, integrity, privacy and safe-output acceptance criteria and is ready for review before commit.

## Checkpoint 3: Merchant identification and transaction categorisation

**Objective:** Enrich the validated preprocessing output with deterministic merchant identities and conservative expense categories while preserving every financial record and separating spend from other movement types.

**Dependency and repository assessment:** Checkpoint 2 was present in Git as commit `01cac2d` on `main`, matched `origin/main`, and the working tree was clean. Its private output contained 150 rows with the exact 15-column preprocessing schema, no missing cleaned descriptions and two `Unknown` movements. The extractor, preprocessing modules, tests, README, process log and ignore rules were reviewed before implementation.

**Problems identified:** Merchant descriptions contain aliases, processor prefixes and overlapping brand names. Merchant identity alone cannot prove what was purchased at supermarkets, pharmacies, department stores or fuel stations. Non-expense movements must not become spending merely because a description resembles a merchant. Two generated outputs also need safe replacement, and an existing human-edited review file must not be silently destroyed.

**Methodology:** Rule-based classification was selected before supervised machine learning because no sufficiently large, corrected and representative labelled dataset exists yet. Explicit rules are deterministic, inspectable and testable, and they expose uncertainty rather than turning plausible guesses into training labels.

**Configuration design:** `config/categories.yaml` defines a validated category/subcategory hierarchy. `config/merchant_rules.yaml` contains generic public-brand rules with IDs, exact or regular-expression patterns, normalized merchant names, optional category pairs, confidence, priority, review flags and explanations. Rules are ordered by descending priority and specificity, then rule ID. Repeated matching patterns are rejected; equally ranked overlapping matches with different outcomes are treated as ambiguous and flagged.

**Implementation:** Added separate configuration validation, merchant normalization, transaction classification and CLI pipeline modules under `src/categorisation/`. Output appends merchant, category, subcategory, method, confidence, review and spending-status fields. A compact review CSV retains transaction ID, date, original description, movement, suggestions and audit metadata. All source fields are compared with the preprocessed rows before output is accepted.

**Movement and ambiguity decisions:** Purchases and bank fees are currently expense-applicable. Bank fees and airtime use narrow transaction rules. Income, incoming and outgoing transfers, refunds, cash withdrawals, reversals and informational entries use `movement_exclusion` and receive no expense category. Unknown movements and unmatched purchases use `Uncategorised / Needs Review`. A broad known retailer may receive a merchant identity but no category. Medium-confidence supermarket and fuel-station defaults remain reviewable because actual basket contents are unknown.

**Output safety:** Both CSVs are fully staged after configuration, input and output validation. Existing destinations are backed up while the pair is replaced and restored on a replacement failure. A differing existing classification review is preserved unless `--overwrite-review` is explicitly supplied after inspection. No correction import or persistence was added.

**Challenges encountered:** PyYAML was not installed in the existing environment, so it was declared and installed before validation. The first test run exposed a synthetic ambiguity regex that did not match its intended string and a nested pytest temporary path whose parent did not exist. The managed Windows default pytest temp root was also inaccessible, so final tests used an explicit ignored workspace-local temp path. These test-environment issues were corrected without relaxing production validation.

**Automated testing:** Added 39 synthetic categorisation tests covering exact matches, aliases, case-insensitive and processor-prefixed matches, Uber/Uber Eats overlap, unknown and broad merchants, configuration conflicts, supported categories, all non-expense movement types, bank-fee and airtime rules, integrity, deterministic outputs, review schemas, paired-output rollback, changed-review protection, invalid schemas and configuration, missing input and CLI integration. The full suite passed with 86 tests and one optional private regression skipped.

**Private output validation:** The CLI processed 150 records, identified 40 merchants, assigned 53 supported non-placeholder categories, flagged 64 records and excluded 42 non-expense movements. Source and output counts were both 150, all transaction IDs remained unique, and all 15 preprocessed fields—including amounts, balances, dates, descriptions and source references—were unchanged. The categorised and review outputs each contained 150 rows. Repeated runs produced identical hashes for both files.

**Privacy verification:** Real descriptions and amounts were not printed during validation. Generated CSVs remain under ignored `data/private/`; global CSV/PDF rules remain active; private YAML mapping patterns are now ignored. Only generic public merchant-brand rules and synthetic tests are candidates for Git.

**Known limitations:** Public rule coverage is intentionally modest, so many purchases remain uncategorised pending review. Merchant rules cannot establish basket contents, cash-withdrawal usage or the original category of a refund. Confidence labels describe rule strength rather than statistical probabilities. Manual corrections, correction reapplication and learning from reviewed labels belong to Checkpoint 4.

**Final checkpoint outcome:** Checkpoint 3 produces validated, deterministic categorised and review datasets without changing source financial records. It is ready for the mandatory review checkpoint before any commit or push.

## Checkpoint 4: Manual Classification Review and Curated Data Preparation

**Objective:** Convert Checkpoint 3's inspection-only suggestions into an auditable human-in-the-loop workflow that persists transaction-level decisions and produces a curated dataset without changing extracted, preprocessed or automatically categorised records.

**Initial architecture assessment:** Checkpoint 3 was present as commit `1322237` on `main`, matched `origin/main`, and the working tree was clean. Categorisation already used one deterministic classification path, exact schemas, source-field integrity checks, a paired staged write and a guard against overwriting a changed review CSV. The extractor creates transaction IDs from the statement byte hash and original statement row index. Those IDs survive source-file renaming, input reordering and the addition of other statements, but change when statement bytes or row identity change.

**CSV review methodology:** The review CSV retains the generated transaction, merchant, movement, category, method, confidence and review evidence. It appends reviewed merchant, category, subcategory, status, notes and a decision version. New rows are always `pending`; the pipeline never invents approval. Supported decisions are `approved`, `corrected` and `deferred`. Blank corrected fields fall back to their automatic suggestion, while pending and deferred rows cannot contain correction values. Generated descriptions beginning with spreadsheet formula characters receive an inert leading apostrophe in the review view.

**Correction persistence design:** `data/private/classification_corrections.csv` stores only non-pending decisions. Each row is keyed by the stable transaction ID and bound to a SHA-256 fingerprint over immutable preprocessing fields except `source_file`. Excluding the filename permits statement renames; including the ID, dates, description, monetary values, balance, page and movement evidence prevents similar-looking transactions from sharing decisions. Imports are idempotent and preserve decisions omitted from a subset review. Per-transaction versions reject stale edits, while `--replace-existing` provides an explicit conflict-resolution path. The importer rejects duplicate IDs, unknown IDs, altered generated fields, orphaned corrections, fingerprint mismatches and malformed stores before writing.

**Classification precedence:** The curated pipeline validates the categorised source, locates a fingerprint-matched saved decision, applies the exact approved or corrected values, retains deferred or unresolved suggestions and then validates the complete output. Classification source is recorded as `automatic`, `manual_approval`, `manual_correction`, `unclassified` or `deferred`. If automatic rules change a previously approved outcome, review regeneration returns the row to `pending` with a warning but leaves the prior saved decision intact until the user explicitly reviews the new suggestion.

**Movement and category integrity:** Review fields cannot change `movement_type`. Ordinary spending categories are rejected for income, incoming and outgoing transfers, refunds, cash withdrawals, reversals and informational entries. Unknown movements remain reviewable even if a transaction-level category is supplied. The curated schema preserves every preprocessing column and separates automatic from final merchant/category values. Record count, IDs, dates, descriptions, amounts, balances and provenance are checked before output replacement.

**Safe file handling and privacy:** Review import fully validates all input before staging the correction store. Curated generation validates all source, decision and output records before atomic replacement. Existing files survive validation, staging or replacement failures. The earlier changed-review guard remains active; `--overwrite-review` is used only after edited decisions have been imported, and regeneration seeds the review from the private store. Review, correction and curated CSVs remain under ignored private paths, and console summaries contain only aggregate counts and paths.

**Challenges encountered and resolutions:** The first persistence test for renamed statements accidentally changed its synthetic description as well as its filename; the fingerprint correctly rejected it, and the fixture was corrected to isolate filename stability. Private aggregate validation then revealed that blank categories on deliberately excluded non-expense movements were being counted as unresolved. The curated review flag was refined to treat validated movement exclusions as resolved while keeping deferred rows unresolved. A separate design review found that a changed automatic suggestion could otherwise inherit an old `approved` status; refreshed approvals now return to pending without deleting the saved decision.

**Automated testing:** Added 30 synthetic review-workflow tests covering generated review usability, approvals, merchant and category corrections, blank-field fallback, pending and deferred rows, invalid statuses and category pairs, duplicate IDs, path separation, movement exclusions, movement immutability, idempotent imports, versioned updates, stale conflicts, explicit resolution, subset reviews, new statements, filename changes, identical-looking transactions, orphaned corrections, altered suggestion snapshots, missing and malformed input, invalid encoding, failed store and curated replacements, CLI execution and end-to-end financial-field preservation. The complete extraction, preprocessing, categorisation, review and curation suite passed with 116 tests and one optional private regression skipped.

**Private validation results:** The existing private preprocessing dataset contained 150 records. Checkpoint 4 regenerated 150 automatic categorisations and 150 review rows, identified 40 merchants, assigned 53 supported non-placeholder categories, flagged 64 category reviews and retained 42 movement exclusions. Curated generation with no invented manual decisions produced 150 records and 150 unique IDs; all preprocessing fields matched exactly with zero differences. No private transaction description or monetary value was printed.

**Outstanding limitations:** Manual decisions are transaction-specific and do not create global merchant rules or learn automatically. The correction store intentionally rejects a dataset that omits previously reviewed transactions; archival or deliberate correction deletion is not yet a workflow. Approved decisions remain bound to their saved values until a changed suggestion is reviewed. Movement-type corrections require a separate future preprocessing-review design. CSV editing still depends on users preserving headers, generated evidence fields and decision versions.

**Final checkpoint outcome:** Checkpoint 4 now supports safe CSV review, validated and persistent approvals/corrections, explicit stale-conflict handling and financially intact curated dataset generation. It is ready for the mandatory review checkpoint before any commit or push.
