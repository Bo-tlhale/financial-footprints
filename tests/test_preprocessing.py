import csv
from pathlib import Path

import pytest

from src.extraction.statement_extractor import OUTPUT_COLUMNS as EXTRACTED_COLUMNS
from src.preprocessing.movement_classifier import classify_movement
from src.preprocessing.pipeline import preprocess_csv, preprocess_records
from src.preprocessing.transaction_cleaner import (
    clean_description,
    normalize_effective_date,
    normalize_posting_date,
)
from src.preprocessing.transaction_validator import (
    ADDED_COLUMNS,
    TransactionValidationError,
)


def source_row(**overrides):
    row = {
        'transaction_id': 'synthetic-001',
        'transaction_date': '2026-01-02',
        'effective_date': '',
        'transaction_type': 'Pos Purchase',
        'description': 'Example Store',
        'debit': '10.00',
        'credit': '0.00',
        'fee': '0.00',
        'balance': '90.00',
        'source_file': 'synthetic-statement.pdf',
        'page_number': '1',
    }
    row.update(overrides)
    return row


def write_source(path, rows, fieldnames=None):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames or EXTRACTED_COLUMNS,
            extrasaction='ignore',
        )
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def test_date_standardisation_and_missing_effective_date():
    assert normalize_posting_date(' 2026-01-02 ') == '2026-01-02'
    assert normalize_effective_date('') == ''
    assert normalize_effective_date('00/00/0000') == ''
    assert normalize_effective_date(' 2026-01-01 ') == '2026-01-01'
    with pytest.raises(ValueError, match='invalid transaction_date'):
        normalize_posting_date('02/01/2026')


def test_description_cleaning_preserves_meaning_and_normalises_whitespace():
    assert clean_description('  Example\tSTORE \n Reference  ') == (
        'example store reference'
    )


def test_preprocessing_preserves_original_financial_fields():
    source = source_row(transaction_date=' 2026-01-02 ',
                        description='  Example   Store ')
    output = preprocess_records([source])[0]
    for field in ('debit', 'credit', 'fee', 'balance'):
        assert output[field] == source[field]
    assert output['description'] == source['description']
    assert output['transaction_id'] == source['transaction_id']
    assert output['transaction_date'] == '2026-01-02'
    assert output['cleaned_description'] == 'example store'


@pytest.mark.parametrize(
    ('transaction_type', 'description', 'debit', 'credit', 'fee',
     'expected_type', 'expected_method', 'review'),
    [
        ('Pos Purchase', 'Example Store', '10.00', '0.00', '0.00',
         'Purchase', 'bank_transaction_type', False),
        ('Overseas Purchase', 'Example International Vendor', '10.00', '0.00', '0.00',
         'Purchase', 'bank_transaction_type', False),
        ('Payshap Ext Credit', 'Example Sender', '0.00', '10.00', '0.00',
         'Incoming Transfer', 'bank_transaction_type', False),
        ('Digital Payment Dt', 'Example Recipient', '10.00', '0.00', '0.00',
         'Outgoing Transfer', 'bank_transaction_type', False),
        ('Acb Credit', 'Monthly salary', '0.00', '10.00', '0.00',
         'Income', 'description_rule', False),
        ('Pos O/Sea Refund', 'Example Refund', '0.00', '10.00', '0.00',
         'Refund', 'bank_transaction_type', False),
        ('Transaction Fee', 'Service charge', '0.00', '0.00', '2.00',
         'Bank Fee', 'bank_transaction_type', False),
        ('Atm Withdrawal', 'Example ATM', '10.00', '0.00', '0.00',
         'Cash Withdrawal', 'bank_transaction_type', False),
        ('Cashsend Mobile', 'Example Recipient', '10.00', '0.00', '0.00',
         'Outgoing Transfer', 'bank_transaction_type', False),
        ('Can Cashsend Mb', 'Cancelled transfer', '0.00', '10.00', '0.00',
         'Reversal', 'bank_transaction_type', False),
        ('Can Cashsend Ib', 'Cancelled transfer', '0.00', '10.00', '0.00',
         'Reversal', 'bank_transaction_type', False),
        ('Notific Fee Sms', 'Notification', '0.00', '0.00', '0.00',
         'Informational', 'bank_transaction_type', False),
        ('Unmapped Type', 'No reliable evidence', '10.00', '0.00', '0.00',
         'Unknown', 'unclassified', True),
        ('Int Debit Order To', 'Ambiguous debit order', '10.00', '0.00', '0.00',
         'Unknown', 'unclassified', True),
        ('Unmapped Fee', 'Unmapped service charge', '0.00', '0.00', '1.00',
         'Bank Fee', 'manual_rule', True),
        ('Unmapped Notice', 'Unmapped notice', '0.00', '0.00', '0.00',
         'Informational', 'manual_rule', True),
    ],
)
def test_movement_classification(
        transaction_type, description, debit, credit, fee,
        expected_type, expected_method, review):
    row = source_row(
        transaction_type=transaction_type,
        description=description,
        debit=debit,
        credit=credit,
        fee=fee,
    )
    row['cleaned_description'] = clean_description(description)
    result = classify_movement(row)
    assert result == {
        'movement_type': expected_type,
        'movement_classification_method': expected_method,
        'movement_review_required': review,
    }


def test_known_type_with_inconsistent_direction_requires_review():
    row = source_row(
        transaction_type='Pos Purchase', debit='0.00', credit='10.00'
    )
    row['cleaned_description'] = clean_description(row['description'])
    assert classify_movement(row) == {
        'movement_type': 'Unknown',
        'movement_classification_method': 'unclassified',
        'movement_review_required': True,
    }


def test_missing_required_column_fails(tmp_path):
    source = tmp_path / 'source.csv'
    columns = [column for column in EXTRACTED_COLUMNS if column != 'fee']
    write_source(source, [source_row()], columns)
    with pytest.raises(TransactionValidationError, match='missing columns: fee'):
        preprocess_csv(source, tmp_path / 'output.csv')


@pytest.mark.parametrize('field,value', [
    ('debit', 'ten'), ('credit', 'NaN'), ('fee', '1.2'), ('balance', ''),
])
def test_invalid_monetary_values_fail(tmp_path, field, value):
    source = tmp_path / 'source.csv'
    write_source(source, [source_row(**{field: value})])
    with pytest.raises(TransactionValidationError, match=f'malformed {field}'):
        preprocess_csv(source, tmp_path / 'output.csv')


def test_duplicate_transaction_ids_fail(tmp_path):
    source = tmp_path / 'source.csv'
    write_source(source, [source_row(), source_row()])
    with pytest.raises(TransactionValidationError, match='duplicate transaction_id'):
        preprocess_csv(source, tmp_path / 'output.csv')


def test_missing_transaction_id_fails(tmp_path):
    source = tmp_path / 'source.csv'
    write_source(source, [source_row(transaction_id='')])
    with pytest.raises(TransactionValidationError, match='missing transaction_id'):
        preprocess_csv(source, tmp_path / 'output.csv')


@pytest.mark.parametrize('field,value,error', [
    ('transaction_date', '', 'invalid transaction_date'),
    ('transaction_date', '02/01/2026', 'invalid transaction_date'),
    ('effective_date', '31/02/2026', 'invalid effective_date'),
])
def test_invalid_dates_fail_pipeline(tmp_path, field, value, error):
    source = tmp_path / 'source.csv'
    write_source(source, [source_row(**{field: value})])
    with pytest.raises(TransactionValidationError, match=error):
        preprocess_csv(source, tmp_path / 'output.csv')


def test_empty_dataset_fails(tmp_path):
    source = tmp_path / 'source.csv'
    write_source(source, [])
    with pytest.raises(TransactionValidationError, match='source dataset is empty'):
        preprocess_csv(source, tmp_path / 'output.csv')


def test_missing_input_file_fails_clearly(tmp_path):
    with pytest.raises(TransactionValidationError, match='input file does not exist'):
        preprocess_csv(tmp_path / 'missing.csv', tmp_path / 'output.csv')


def test_pipeline_preserves_schema_count_order_and_values(tmp_path):
    source = tmp_path / 'transactions.csv'
    output = tmp_path / 'preprocessed_transactions.csv'
    rows = [
        source_row(transaction_id='synthetic-001'),
        source_row(
            transaction_id='synthetic-002', transaction_date='2026-01-03',
            transaction_type='Payshap Ext Credit', description='',
            debit='0.00', credit='25.00', balance='115.00', page_number='2',
        ),
    ]
    write_source(source, rows)
    summary = preprocess_csv(source, output)
    fieldnames, processed = read_csv(output)
    assert fieldnames == [*EXTRACTED_COLUMNS, *ADDED_COLUMNS]
    assert len(processed) == len(rows) == summary['input_records']
    assert [row['transaction_id'] for row in processed] == [
        'synthetic-001', 'synthetic-002'
    ]
    for source_record, output_record in zip(rows, processed):
        for field in EXTRACTED_COLUMNS:
            assert output_record[field] == source_record[field]
    assert summary['missing_descriptions'] == 1
    assert processed[0]['movement_review_required'] == 'False'
    assert processed[1]['movement_review_required'] == 'True'


def test_pipeline_output_is_deterministic(tmp_path):
    source = tmp_path / 'transactions.csv'
    output = tmp_path / 'preprocessed_transactions.csv'
    write_source(source, [source_row()])
    preprocess_csv(source, output)
    first = output.read_bytes()
    preprocess_csv(source, output)
    assert output.read_bytes() == first


def test_failed_pipeline_does_not_overwrite_valid_output(tmp_path):
    source = tmp_path / 'transactions.csv'
    output = tmp_path / 'preprocessed_transactions.csv'
    output.write_text('previous valid output', encoding='utf-8')
    write_source(source, [source_row(debit='invalid')])
    with pytest.raises(TransactionValidationError):
        preprocess_csv(source, output)
    assert output.read_text(encoding='utf-8') == 'previous valid output'


def test_pipeline_schema_matches_extractor_contract():
    assert EXTRACTED_COLUMNS == [
        'transaction_id', 'transaction_date', 'effective_date',
        'transaction_type', 'description', 'debit', 'credit', 'fee',
        'balance', 'source_file', 'page_number',
    ]
