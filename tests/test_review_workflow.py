import csv
import subprocess
import sys
from pathlib import Path

import pytest

from src.categorisation.category_validator import (
    OUTPUT_COLUMNS,
    REVIEW_COLUMNS,
    CategoryValidationError,
)
from src.categorisation.curated_pipeline import (
    CURATED_COLUMNS,
    generate_curated_csv,
)
from src.categorisation.pipeline import categorise_csv
from src.categorisation.review_manager import (
    CORRECTION_COLUMNS,
    import_reviews,
    load_correction_store,
)
from src.categorisation.category_validator import load_category_hierarchy
from src.preprocessing.transaction_validator import (
    OUTPUT_COLUMNS as PREPROCESSED_COLUMNS,
)

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ROOT / 'config' / 'categories.yaml'
RULES = ROOT / 'config' / 'merchant_rules.yaml'


def preprocessed_row(**overrides):
    row = {
        'transaction_id': 'synthetic-review-001',
        'transaction_date': '2026-01-02',
        'effective_date': '',
        'transaction_type': 'Pos Purchase',
        'description': 'Synthetic Merchant',
        'debit': '10.00',
        'credit': '0.00',
        'fee': '0.00',
        'balance': '90.00',
        'source_file': 'synthetic-statement.pdf',
        'page_number': '1',
        'cleaned_description': 'synthetic merchant',
        'movement_type': 'Purchase',
        'movement_classification_method': 'bank_transaction_type',
        'movement_review_required': 'False',
    }
    row.update(overrides)
    if 'cleaned_description' in overrides and 'description' not in overrides:
        row['description'] = overrides['cleaned_description']
    return row


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def workspace(tmp_path, rows=None):
    source = tmp_path / 'preprocessed.csv'
    categorised = tmp_path / 'categorised.csv'
    review = tmp_path / 'review.csv'
    corrections = tmp_path / 'corrections.csv'
    curated = tmp_path / 'curated.csv'
    rows = rows or [preprocessed_row(cleaned_description='netflix')]
    write_csv(source, PREPROCESSED_COLUMNS, rows)
    categorise_csv(source, categorised, review, CATEGORIES, RULES)
    return source, categorised, review, corrections, curated


def edit_review(path, transaction_id, **changes):
    fields, records = read_csv(path)
    for record in records:
        if record['transaction_id'] == transaction_id:
            record.update(changes)
            break
    write_csv(path, fields, records)


def import_current(review, categorised, corrections, **kwargs):
    return import_reviews(
        review, categorised, corrections, CATEGORIES,
        now='2026-10-16T12:00:00+00:00', **kwargs,
    )


def test_generated_review_is_editable_pending_and_formula_safe(tmp_path):
    _, _, review, _, _ = workspace(tmp_path, [
        preprocessed_row(description='=2+2', cleaned_description='=2+2'),
    ])
    fields, records = read_csv(review)
    assert fields == REVIEW_COLUMNS
    assert records[0]['original_description'] == "'=2+2"
    assert records[0]['review_status'] == 'pending'
    assert records[0]['decision_version'] == '0'
    assert records[0]['reviewed_category'] == ''


def test_approve_suggestion_and_generate_curated_output(tmp_path):
    _, categorised, review, corrections, curated = workspace(tmp_path)
    edit_review(review, 'synthetic-review-001', review_status='approved')
    summary = import_current(review, categorised, corrections)
    assert summary['added'] == 1
    curated_summary = generate_curated_csv(
        categorised, corrections, curated, CATEGORIES,
    )
    fields, records = read_csv(curated)
    assert fields == CURATED_COLUMNS
    assert records[0]['final_merchant'] == 'Netflix'
    assert records[0]['final_category'] == 'Subscriptions'
    assert records[0]['classification_source'] == 'manual_approval'
    assert records[0]['review_status'] == 'approved'
    assert curated_summary['manual_approvals'] == 1


def test_correct_merchant_category_and_subcategory_with_blank_fallback(tmp_path):
    _, categorised, review, corrections, curated = workspace(tmp_path)
    edit_review(
        review, 'synthetic-review-001',
        reviewed_merchant='Example Transport',
        reviewed_category='Transport',
        reviewed_subcategory='Ride-Hailing',
        review_status='corrected', review_notes='Synthetic correction',
    )
    import_current(review, categorised, corrections)
    generate_curated_csv(categorised, corrections, curated, CATEGORIES)
    _, records = read_csv(curated)
    assert records[0]['automatic_merchant'] == 'Netflix'
    assert records[0]['final_merchant'] == 'Example Transport'
    assert records[0]['final_category'] == 'Transport'
    assert records[0]['final_subcategory'] == 'Ride-Hailing'
    assert records[0]['classification_source'] == 'manual_correction'
    categorise_csv(
        tmp_path / 'preprocessed.csv', categorised, review, CATEGORIES, RULES,
        allow_changed_review=True, corrections_path=corrections,
    )
    _, refreshed = read_csv(review)
    assert refreshed[0]['review_status'] == 'corrected'
    assert refreshed[0]['reviewed_merchant'] == 'Example Transport'
    assert refreshed[0]['decision_version'] == '1'


def test_correct_only_merchant_does_not_erase_valid_category(tmp_path):
    _, categorised, review, corrections, curated = workspace(tmp_path)
    edit_review(
        review, 'synthetic-review-001',
        reviewed_merchant='Example Streaming', review_status='corrected',
    )
    import_current(review, categorised, corrections)
    generate_curated_csv(categorised, corrections, curated, CATEGORIES)
    _, records = read_csv(curated)
    assert records[0]['final_merchant'] == 'Example Streaming'
    assert records[0]['final_category'] == 'Subscriptions'
    assert records[0]['final_subcategory'] == 'Streaming'


def test_deferred_persists_while_pending_is_not_saved(tmp_path):
    rows = [
        preprocessed_row(cleaned_description='netflix'),
        preprocessed_row(
            transaction_id='synthetic-review-002',
            cleaned_description='unknown synthetic shop',
        ),
    ]
    _, categorised, review, corrections, curated = workspace(tmp_path, rows)
    edit_review(review, 'synthetic-review-002', review_status='deferred')
    summary = import_current(review, categorised, corrections)
    assert summary['pending'] == 1
    assert summary['deferred'] == 1
    _, saved = read_csv(corrections)
    assert [row['transaction_id'] for row in saved] == ['synthetic-review-002']
    generate_curated_csv(categorised, corrections, curated, CATEGORIES)
    _, output = read_csv(curated)
    by_id = {row['transaction_id']: row for row in output}
    assert by_id['synthetic-review-001']['review_status'] == 'pending'
    assert by_id['synthetic-review-002']['classification_source'] == 'deferred'
    assert by_id['synthetic-review-002']['review_required'] == 'True'


@pytest.mark.parametrize('status', ['accepted', 'done', 'APPROVED!'])
def test_invalid_status_is_rejected_without_writing_store(tmp_path, status):
    _, categorised, review, corrections, _ = workspace(tmp_path)
    edit_review(review, 'synthetic-review-001', review_status=status)
    with pytest.raises(CategoryValidationError, match='invalid review_status'):
        import_current(review, categorised, corrections)
    assert not corrections.exists()


def test_invalid_category_combination_is_rejected(tmp_path):
    _, categorised, review, corrections, _ = workspace(tmp_path)
    edit_review(
        review, 'synthetic-review-001', review_status='corrected',
        reviewed_category='Groceries', reviewed_subcategory='Cinema',
    )
    with pytest.raises(CategoryValidationError, match='invalid category'):
        import_current(review, categorised, corrections)
    assert not corrections.exists()


def test_duplicate_review_ids_are_rejected(tmp_path):
    _, categorised, review, corrections, _ = workspace(tmp_path)
    fields, records = read_csv(review)
    write_csv(review, fields, [records[0], records[0]])
    with pytest.raises(CategoryValidationError, match='duplicate transaction_id'):
        import_current(review, categorised, corrections)


def test_review_import_paths_must_be_distinct(tmp_path):
    _, categorised, review, _, _ = workspace(tmp_path)
    with pytest.raises(CategoryValidationError, match='paths must differ'):
        import_current(review, categorised, review)


def test_non_expense_movement_cannot_receive_spending_category(tmp_path):
    row = preprocessed_row(
        movement_type='Incoming Transfer', transaction_type='Transfer In',
        debit='0.00', credit='10.00', cleaned_description='synthetic transfer',
    )
    _, categorised, review, corrections, _ = workspace(tmp_path, [row])
    edit_review(
        review, row['transaction_id'], review_status='corrected',
        reviewed_category='Groceries', reviewed_subcategory='Supermarkets',
    )
    with pytest.raises(CategoryValidationError, match='excluded movement'):
        import_current(review, categorised, corrections)


def test_non_expense_movement_is_not_a_pending_category_review(tmp_path):
    row = preprocessed_row(
        movement_type='Incoming Transfer', transaction_type='Transfer In',
        debit='0.00', credit='10.00', cleaned_description='synthetic transfer',
    )
    _, categorised, _, corrections, curated = workspace(tmp_path, [row])
    generate_curated_csv(categorised, corrections, curated, CATEGORIES)
    _, output = read_csv(curated)
    assert output[0]['spending_classification_status'] == 'not_applicable'
    assert output[0]['classification_source'] == 'automatic'
    assert output[0]['review_required'] == 'False'


def test_reimport_is_idempotent_and_safe_update_uses_version(tmp_path):
    source, categorised, review, corrections, _ = workspace(tmp_path)
    edit_review(review, 'synthetic-review-001', review_status='approved')
    first = import_current(review, categorised, corrections)
    first_bytes = corrections.read_bytes()
    second = import_current(review, categorised, corrections)
    assert first['added'] == 1 and second['unchanged'] == 1
    assert corrections.read_bytes() == first_bytes
    categorise_csv(
        source, categorised, review, CATEGORIES, RULES,
        allow_changed_review=True, corrections_path=corrections,
    )
    edit_review(
        review, 'synthetic-review-001', review_status='corrected',
        reviewed_merchant='Example Streaming',
    )
    updated = import_current(review, categorised, corrections)
    assert updated['updated'] == 1
    saved = load_correction_store(
        corrections, load_category_hierarchy(CATEGORIES),
    )['synthetic-review-001']
    assert saved['decision_version'] == '2'
    assert saved['reviewed_merchant'] == 'Example Streaming'


def test_changed_automatic_suggestion_requires_approval_again(tmp_path):
    source, categorised, review, corrections, _ = workspace(tmp_path)
    edit_review(review, 'synthetic-review-001', review_status='approved')
    import_current(review, categorised, corrections)
    changed_rules = tmp_path / 'changed-rules.yaml'
    changed_rules.write_text(
        'version: 1\nrules:\n'
        '  - id: changed-netflix\n'
        '    pattern: netflix\n'
        '    match_type: regex\n'
        '    merchant: Example Video\n'
        '    category: Entertainment\n'
        '    subcategory: Cinema\n'
        '    confidence: high\n'
        '    priority: 100\n'
        '    review_required: false\n',
        encoding='utf-8',
    )
    categorise_csv(
        source, categorised, review, CATEGORIES, changed_rules,
        allow_changed_review=True, corrections_path=corrections,
    )
    _, refreshed = read_csv(review)
    assert refreshed[0]['clean_merchant'] == 'Example Video'
    assert refreshed[0]['review_status'] == 'pending'
    assert 'review again' in refreshed[0]['review_notes']
    summary = import_current(review, categorised, corrections)
    assert summary['pending'] == 1
    saved = load_correction_store(
        corrections, load_category_hierarchy(CATEGORIES),
    )['synthetic-review-001']
    assert saved['reviewed_merchant'] == 'Netflix'


def test_stale_review_conflict_requires_explicit_resolution(tmp_path):
    source, categorised, review, corrections, _ = workspace(tmp_path)
    fields, stale = read_csv(review)
    edit_review(review, 'synthetic-review-001', review_status='approved')
    import_current(review, categorised, corrections)
    stale[0].update({
        'review_status': 'corrected',
        'reviewed_merchant': 'Later Synthetic Merchant',
    })
    write_csv(review, fields, stale)
    with pytest.raises(CategoryValidationError, match='stale review conflicts'):
        import_current(review, categorised, corrections)
    summary = import_current(
        review, categorised, corrections, replace_existing=True,
    )
    assert summary['updated'] == 1
    categorise_csv(
        source, categorised, review, CATEGORIES, RULES,
        allow_changed_review=True, corrections_path=corrections,
    )
    _, refreshed = read_csv(review)
    assert refreshed[0]['decision_version'] == '2'


def test_corrections_survive_new_statements_and_filename_changes(tmp_path):
    source, categorised, review, corrections, curated = workspace(tmp_path)
    edit_review(review, 'synthetic-review-001', review_status='approved')
    import_current(review, categorised, corrections)
    rows = [
        preprocessed_row(
            source_file='renamed-statement.pdf', cleaned_description='netflix',
        ),
        preprocessed_row(
            transaction_id='synthetic-review-002',
            transaction_date='2026-02-02', cleaned_description='uber trip',
            source_file='new-statement.pdf',
        ),
    ]
    write_csv(source, PREPROCESSED_COLUMNS, rows)
    categorise_csv(
        source, categorised, review, CATEGORIES, RULES,
        allow_changed_review=True, corrections_path=corrections,
    )
    generate_curated_csv(categorised, corrections, curated, CATEGORIES)
    _, output = read_csv(curated)
    by_id = {row['transaction_id']: row for row in output}
    assert len(output) == 2
    assert by_id['synthetic-review-001']['classification_source'] == 'manual_approval'
    assert by_id['synthetic-review-002']['review_status'] == 'pending'


def test_identical_looking_transactions_are_corrected_by_id_only(tmp_path):
    rows = [
        preprocessed_row(transaction_id='synthetic-review-001'),
        preprocessed_row(transaction_id='synthetic-review-002'),
    ]
    _, categorised, review, corrections, curated = workspace(tmp_path, rows)
    edit_review(
        review, 'synthetic-review-001', review_status='corrected',
        reviewed_merchant='First Instance Only',
    )
    import_current(review, categorised, corrections)
    generate_curated_csv(categorised, corrections, curated, CATEGORIES)
    _, output = read_csv(curated)
    by_id = {row['transaction_id']: row for row in output}
    assert by_id['synthetic-review-001']['final_merchant'] == 'First Instance Only'
    assert by_id['synthetic-review-002']['final_merchant'] == ''


def test_stale_correction_absent_from_source_is_detected(tmp_path):
    source, categorised, review, corrections, curated = workspace(tmp_path)
    edit_review(review, 'synthetic-review-001', review_status='approved')
    import_current(review, categorised, corrections)
    replacement = preprocessed_row(transaction_id='synthetic-review-002')
    write_csv(source, PREPROCESSED_COLUMNS, [replacement])
    categorise_csv(
        source, categorised, review, CATEGORIES, RULES,
        allow_changed_review=True,
    )
    with pytest.raises(CategoryValidationError, match='absent from the source'):
        generate_curated_csv(categorised, corrections, curated, CATEGORIES)


def test_review_snapshot_change_is_detected_as_stale(tmp_path):
    _, categorised, review, corrections, _ = workspace(tmp_path)
    edit_review(
        review, 'synthetic-review-001', review_status='approved',
        suggested_category='Groceries',
    )
    with pytest.raises(CategoryValidationError, match='stale or altered'):
        import_current(review, categorised, corrections)


def test_movement_type_cannot_be_modified_through_review(tmp_path):
    _, categorised, review, corrections, _ = workspace(tmp_path)
    edit_review(
        review, 'synthetic-review-001', review_status='approved',
        movement_type='Income',
    )
    with pytest.raises(CategoryValidationError, match='stale or altered'):
        import_current(review, categorised, corrections)


def test_subset_review_preserves_other_saved_decisions(tmp_path):
    rows = [
        preprocessed_row(transaction_id='synthetic-review-001'),
        preprocessed_row(
            transaction_id='synthetic-review-002', cleaned_description='uber trip',
        ),
    ]
    source, categorised, review, corrections, _ = workspace(tmp_path, rows)
    edit_review(review, 'synthetic-review-001', review_status='approved')
    edit_review(review, 'synthetic-review-002', review_status='approved')
    import_current(review, categorised, corrections)
    categorise_csv(
        source, categorised, review, CATEGORIES, RULES,
        allow_changed_review=True, corrections_path=corrections,
    )
    fields, refreshed = read_csv(review)
    write_csv(review, fields, [refreshed[0]])
    import_current(review, categorised, corrections)
    _, saved = read_csv(corrections)
    assert {row['transaction_id'] for row in saved} == {
        'synthetic-review-001', 'synthetic-review-002',
    }


@pytest.mark.parametrize('failure', ['missing', 'schema', 'encoding', 'malformed'])
def test_invalid_review_inputs_do_not_replace_existing_store(tmp_path, failure):
    _, categorised, review, corrections, _ = workspace(tmp_path)
    edit_review(review, 'synthetic-review-001', review_status='approved')
    import_current(review, categorised, corrections)
    before = corrections.read_bytes()
    if failure == 'missing':
        review.unlink()
    elif failure == 'schema':
        review.write_text('wrong,columns\n1,2\n', encoding='utf-8')
    elif failure == 'encoding':
        review.write_bytes(b'\xff\xfe\x00')
    else:
        review.write_text('"unterminated', encoding='utf-8')
    with pytest.raises((CategoryValidationError, UnicodeError)):
        import_current(review, categorised, corrections)
    assert corrections.read_bytes() == before


def test_failed_store_replace_preserves_existing_file(tmp_path, monkeypatch):
    _, categorised, review, corrections, _ = workspace(tmp_path)
    fields = CORRECTION_COLUMNS
    corrections.write_text(','.join(fields) + '\n', encoding='utf-8')
    before = corrections.read_bytes()
    edit_review(review, 'synthetic-review-001', review_status='approved')
    from src.categorisation import review_manager

    monkeypatch.setattr(
        review_manager.os, 'replace',
        lambda *_: (_ for _ in ()).throw(OSError('synthetic replace failure')),
    )
    with pytest.raises(OSError, match='synthetic replace failure'):
        import_current(review, categorised, corrections)
    assert corrections.read_bytes() == before


def test_failed_curated_replace_preserves_existing_file(tmp_path, monkeypatch):
    _, categorised, _, corrections, curated = workspace(tmp_path)
    curated.write_text('existing curated output', encoding='utf-8')
    before = curated.read_bytes()
    from src.categorisation import curated_pipeline

    monkeypatch.setattr(
        curated_pipeline.os, 'replace',
        lambda *_: (_ for _ in ()).throw(OSError('synthetic replace failure')),
    )
    with pytest.raises(OSError, match='synthetic replace failure'):
        generate_curated_csv(categorised, corrections, curated, CATEGORIES)
    assert curated.read_bytes() == before


def test_cli_import_and_curated_generation(tmp_path):
    _, categorised, review, corrections, curated = workspace(tmp_path)
    edit_review(review, 'synthetic-review-001', review_status='approved')
    imported = subprocess.run(
        [
            sys.executable, '-m', 'src.categorisation.review_manager',
            '--review', str(review), '--source', str(categorised),
            '--corrections', str(corrections), '--categories', str(CATEGORIES),
        ],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert imported.returncode == 0, imported.stderr
    assert 'Validation status: passed.' in imported.stdout
    generated = subprocess.run(
        [
            sys.executable, '-m', 'src.categorisation.curated_pipeline',
            '--input', str(categorised), '--corrections', str(corrections),
            '--output', str(curated), '--categories', str(CATEGORIES),
        ],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert generated.returncode == 0, generated.stderr
    assert 'Validation status: passed.' in generated.stdout
    assert curated.is_file()


def test_curated_output_preserves_financial_and_provenance_fields(tmp_path):
    rows = [
        preprocessed_row(cleaned_description='netflix'),
        preprocessed_row(
            transaction_id='synthetic-review-002',
            transaction_date='2026-01-03', debit='20.00', balance='70.00',
            page_number='2', cleaned_description='uber trip',
        ),
    ]
    _, categorised, _, corrections, curated = workspace(tmp_path, rows)
    generate_curated_csv(categorised, corrections, curated, CATEGORIES)
    _, output = read_csv(curated)
    assert len(output) == len(rows)
    assert len({record['transaction_id'] for record in output}) == len(rows)
    for original, result in zip(rows, output):
        for field in PREPROCESSED_COLUMNS:
            assert result[field] == original[field]
