import csv
import subprocess
import sys
from pathlib import Path

import pytest

from src.categorisation.category_validator import (
    OUTPUT_COLUMNS,
    REVIEW_COLUMNS,
    CategoryValidationError,
    MerchantRule,
    load_category_hierarchy,
    load_merchant_rules,
)
from src.categorisation.merchant_normaliser import identify_merchant
from src.categorisation.pipeline import categorise_csv, categorise_records
from src.categorisation.transaction_classifier import classify_transaction
from src.preprocessing.transaction_validator import (
    OUTPUT_COLUMNS as PREPROCESSED_COLUMNS,
)

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ROOT / 'config' / 'categories.yaml'
RULES = ROOT / 'config' / 'merchant_rules.yaml'


def preprocessed_row(**overrides):
    row = {
        'transaction_id': 'synthetic-001',
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


def write_csv(path, rows, fieldnames=PREPROCESSED_COLUMNS):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, extrasaction='ignore',
        )
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


@pytest.fixture(scope='module')
def hierarchy():
    return load_category_hierarchy(CATEGORIES)


@pytest.fixture(scope='module')
def rules(hierarchy):
    return load_merchant_rules(RULES, hierarchy)


@pytest.mark.parametrize(('description', 'merchant'), [
    ('uber eats', 'Uber Eats'),
    ('DL*UBER EATS', 'Uber Eats'),
    ('pnp hpr', 'Pick n Pay'),
    ('checkers sixty60 order', 'Checkers Sixty60'),
    ('gautrain e commerce', 'Gautrain'),
    ('google youtubepremium', 'YouTube Premium'),
    ('mr d food', 'Mr D Food'),
])
def test_merchant_aliases_and_case_insensitive_matching(rules, description, merchant):
    assert identify_merchant(description, rules)['merchant'] == merchant


def test_overlapping_uber_pattern_prefers_uber_eats(rules):
    match = identify_merchant('dl*uber eats johannesburg', rules)
    assert match['merchant'] == 'Uber Eats'
    assert match['subcategory'] == 'Food Delivery'


def test_unknown_merchant_is_not_invented(rules):
    assert identify_merchant('independent synthetic vendor', rules) is None


def test_exact_rule_matches_case_insensitively():
    rule = MerchantRule(
        'exact', 'Example Store', 'exact', 'Example Store',
        'Shopping', 'General Retail', 'high', 1, False, '',
    )
    result = identify_merchant('EXAMPLE STORE', (rule,))
    assert result['merchant'] == 'Example Store'


def test_broad_retailer_identifies_merchant_but_not_category(rules):
    result = classify_transaction(
        preprocessed_row(cleaned_description='woolworths example'), rules,
    )
    assert result['clean_merchant'] == 'Woolworths'
    assert result['category'] == ''
    assert result['category_review_required'] is True
    assert result['spending_classification_status'] == 'requires_review'


def test_equal_specificity_conflict_is_flagged_at_runtime():
    shared = dict(
        match_type='regex', category='Transport', subcategory='Fuel',
        confidence='medium', priority=5, review_required=False,
        explanation='',
    )
    rules = (
        MerchantRule('a', 'shop.', merchant='First', **shared),
        MerchantRule('b', 'shopx', merchant='Second', **shared),
    )
    result = identify_merchant('shopx', rules)
    assert result['ambiguous'] is True
    assert result['review_required'] is True
    assert result['merchant'] == ''


def test_invalid_category_rule_is_rejected(tmp_path, hierarchy):
    path = tmp_path / 'rules.yaml'
    path.write_text(
        'version: 1\nrules:\n  - id: bad\n    pattern: bad\n'
        '    match_type: exact\n    merchant: Bad\n    category: Invalid\n'
        '    subcategory: Invalid\n    confidence: high\n    priority: 1\n',
        encoding='utf-8',
    )
    with pytest.raises(CategoryValidationError, match='invalid category'):
        load_merchant_rules(path, hierarchy)


def test_conflicting_patterns_are_rejected(tmp_path, hierarchy):
    path = tmp_path / 'rules.yaml'
    path.write_text(
        'version: 1\nrules:\n'
        '  - {id: first, pattern: shop, match_type: exact, merchant: One, '
        'category: Transport, subcategory: Fuel, confidence: high, priority: 1}\n'
        '  - {id: second, pattern: SHOP, match_type: exact, merchant: Two, '
        'category: Transport, subcategory: Fuel, confidence: high, priority: 1}\n',
        encoding='utf-8',
    )
    with pytest.raises(CategoryValidationError, match='conflicting merchant rules'):
        load_merchant_rules(path, hierarchy)


@pytest.mark.parametrize(('description', 'category', 'subcategory'), [
    ('uber eats', 'Food & Dining', 'Food Delivery'),
    ('pnp', 'Groceries', 'Supermarkets'),
    ('uber trip', 'Transport', 'Ride-Hailing'),
    ('youtube premium', 'Subscriptions', 'Streaming'),
    ('mediclinic', 'Healthcare', 'Medical Services'),
    ('ster-kinekor', 'Entertainment', 'Cinema'),
])
def test_supported_expense_categories(rules, description, category, subcategory):
    result = classify_transaction(
        preprocessed_row(cleaned_description=description), rules,
    )
    assert (result['category'], result['subcategory']) == (category, subcategory)
    assert result['classification_method'] == 'merchant_rule'


def test_bank_fee_uses_transaction_rule(rules):
    result = classify_transaction(
        preprocessed_row(
            movement_type='Bank Fee', transaction_type='Transaction Fee',
            debit='0.00', fee='5.00', cleaned_description='service fee',
        ),
        rules,
    )
    assert result['category'] == 'Financial Charges'
    assert result['subcategory'] == 'Transaction Fees'
    assert result['classification_method'] == 'transaction_rule'
    assert result['category_review_required'] is False


def test_airtime_uses_transaction_rule(rules):
    result = classify_transaction(
        preprocessed_row(transaction_type='Airtime Debit'), rules,
    )
    assert result['category'] == 'Utilities & Communication'
    assert result['subcategory'] == 'Airtime'


@pytest.mark.parametrize('movement', [
    'Income', 'Incoming Transfer', 'Outgoing Transfer', 'Refund',
    'Cash Withdrawal', 'Reversal', 'Informational',
])
def test_non_expense_movements_are_excluded(rules, movement):
    result = classify_transaction(preprocessed_row(movement_type=movement), rules)
    assert result['category'] == ''
    assert result['classification_method'] == 'movement_exclusion'
    assert result['spending_classification_status'] == 'not_applicable'
    assert result['category_review_required'] is False


def test_unknown_movement_requires_review(rules):
    result = classify_transaction(preprocessed_row(movement_type='Unknown'), rules)
    assert result['category'] == 'Uncategorised'
    assert result['classification_confidence'] == 'unknown'
    assert result['category_review_required'] is True


def test_categorisation_preserves_every_source_field(rules):
    source = preprocessed_row(cleaned_description='netflix.com')
    output = categorise_records([source], rules)[0]
    assert list(output) == OUTPUT_COLUMNS
    for field in PREPROCESSED_COLUMNS:
        assert output[field] == source[field]


def test_pipeline_outputs_and_review_schema(tmp_path):
    source = tmp_path / 'source.csv'
    output = tmp_path / 'categorised.csv'
    review = tmp_path / 'review.csv'
    rows = [
        preprocessed_row(cleaned_description='netflix'),
        preprocessed_row(
            transaction_id='synthetic-002', movement_type='Refund',
            debit='0.00', credit='10.00', cleaned_description='refund',
        ),
    ]
    write_csv(source, rows)
    summary = categorise_csv(source, output, review, CATEGORIES, RULES)
    output_fields, output_rows = read_csv(output)
    review_fields, review_rows = read_csv(review)
    assert output_fields == OUTPUT_COLUMNS
    assert review_fields == REVIEW_COLUMNS
    assert len(output_rows) == len(review_rows) == len(rows)
    assert review_rows[0]['transaction_id'] == rows[0]['transaction_id']
    assert review_rows[0]['original_description'] == rows[0]['description']
    assert summary['validation_status'] == 'passed'


def test_pipeline_is_deterministic(tmp_path):
    source = tmp_path / 'source.csv'
    output = tmp_path / 'categorised.csv'
    review = tmp_path / 'review.csv'
    write_csv(source, [preprocessed_row(cleaned_description='uber eats')])
    categorise_csv(source, output, review, CATEGORIES, RULES)
    first = (output.read_bytes(), review.read_bytes())
    categorise_csv(source, output, review, CATEGORIES, RULES)
    assert (output.read_bytes(), review.read_bytes()) == first


def test_changed_review_is_not_overwritten_without_explicit_flag(tmp_path):
    source = tmp_path / 'source.csv'
    output = tmp_path / 'categorised.csv'
    review = tmp_path / 'review.csv'
    write_csv(source, [preprocessed_row(cleaned_description='netflix')])
    categorise_csv(source, output, review, CATEGORIES, RULES)
    original_output = output.read_bytes()
    review.write_text('user-maintained review\n', encoding='utf-8')
    with pytest.raises(CategoryValidationError, match='existing classification review'):
        categorise_csv(source, output, review, CATEGORIES, RULES)
    assert output.read_bytes() == original_output
    assert review.read_text(encoding='utf-8') == 'user-maintained review\n'


def test_invalid_configuration_preserves_existing_outputs(tmp_path):
    source = tmp_path / 'source.csv'
    output = tmp_path / 'categorised.csv'
    review = tmp_path / 'review.csv'
    bad_rules = tmp_path / 'bad-rules.yaml'
    write_csv(source, [preprocessed_row()])
    output.write_text('existing output', encoding='utf-8')
    review.write_text('existing review', encoding='utf-8')
    bad_rules.write_text('version: 1\nrules: invalid\n', encoding='utf-8')
    with pytest.raises(CategoryValidationError):
        categorise_csv(source, output, review, CATEGORIES, bad_rules)
    assert output.read_text(encoding='utf-8') == 'existing output'
    assert review.read_text(encoding='utf-8') == 'existing review'


def test_missing_input_is_reported(tmp_path):
    with pytest.raises(CategoryValidationError, match='input file does not exist'):
        categorise_csv(
            tmp_path / 'missing.csv', tmp_path / 'output.csv',
            tmp_path / 'review.csv', CATEGORIES, RULES,
        )


def test_invalid_input_schema_is_rejected(tmp_path):
    source = tmp_path / 'source.csv'
    write_csv(source, [preprocessed_row()], fieldnames=PREPROCESSED_COLUMNS[:-1])
    with pytest.raises(CategoryValidationError, match='unsupported preprocessed'):
        categorise_csv(
            source, tmp_path / 'output.csv', tmp_path / 'review.csv',
            CATEGORIES, RULES,
        )


def test_pair_replacement_failure_restores_both_outputs(tmp_path, monkeypatch):
    source = tmp_path / 'source.csv'
    output = tmp_path / 'categorised.csv'
    review = tmp_path / 'review.csv'
    write_csv(source, [preprocessed_row(cleaned_description='netflix')])
    output.write_text('prior output', encoding='utf-8')
    review.write_text('prior review', encoding='utf-8')

    from src.categorisation import pipeline

    real_replace = pipeline.os.replace

    def fail_review_replace(source_path, destination_path):
        source_path = Path(source_path)
        destination_path = Path(destination_path)
        if destination_path == review and source_path.suffix == '.tmp':
            raise OSError('synthetic second-output failure')
        return real_replace(source_path, destination_path)

    monkeypatch.setattr(pipeline.os, 'replace', fail_review_replace)
    with pytest.raises(OSError, match='synthetic second-output failure'):
        categorise_csv(
            source, output, review, CATEGORIES, RULES,
            allow_changed_review=True,
        )
    assert output.read_text(encoding='utf-8') == 'prior output'
    assert review.read_text(encoding='utf-8') == 'prior review'


def test_cli_integration(tmp_path):
    source = tmp_path / 'source.csv'
    output = tmp_path / 'categorised.csv'
    review = tmp_path / 'review.csv'
    write_csv(source, [preprocessed_row(cleaned_description='mr d food')])
    completed = subprocess.run(
        [
            sys.executable, '-m', 'src.categorisation.pipeline',
            '--input', str(source), '--output', str(output),
            '--review', str(review), '--categories', str(CATEGORIES),
            '--rules', str(RULES),
        ],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert 'Validation status: passed.' in completed.stdout
    assert output.is_file() and review.is_file()
