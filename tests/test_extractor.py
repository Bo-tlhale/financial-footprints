import csv
import json
import os
from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest

from src.extraction import statement_extractor as extractor
from src.extraction.statement_extractor import (
    export, extract_pdf, parse_effective_date, parse_statement_date, read_money,
    reconcile, safe_description, statement_summary, validate,
)


def transaction(date, transaction_type, balance, *, debit='0', credit='0',
                fee='0', description='Synthetic merchant', page=1,
                effective_date=''):
    return {
        'transaction_date': date, 'transaction_type': transaction_type,
        'settlement': '',
        'description_parts': [description] if description else [],
        'effective_date': effective_date, 'debit': Decimal(debit),
        'credit': Decimal(credit), 'fee': Decimal(fee),
        'balance': Decimal(balance), 'page_number': page,
    }


def summary_for(rows, **overrides):
    withdrawal_types = {'atm withdrawal', 'sas atm withdrawal'}
    values = {
        'opening': rows[0]['balance'], 'closing': rows[-1]['balance'],
        'credits': sum((row['credit'] for row in rows), Decimal(0)),
        'withdrawals': sum((row['debit'] for row in rows
                            if row['transaction_type'].lower() in withdrawal_types), Decimal(0)),
        'sundry_debits': sum((row['debit'] for row in rows
                             if row['transaction_type'].lower() not in withdrawal_types), Decimal(0)),
        'charges': sum((row['fee'] for row in rows), Decimal(0)),
    }
    values.update(overrides)
    return values


def test_money_formats_and_direction():
    assert read_money('1 205.50') == Decimal('1205.50')
    assert read_money('1 205,50-') == Decimal('-1205.50')
    rows = [
        transaction('2026-01-01', 'Bal Brought Forward', '100.00'),
        transaction('2026-01-02', 'Purchase', '90.00', debit='10.00'),
        transaction('2026-01-03', 'Credit', '95.00', credit='5.00'),
    ]
    assert not validate(rows)['issues']


def test_posting_and_effective_date_validation():
    source = Path('synthetic-statement.pdf')
    assert parse_statement_date('01/02/2026', source=source, page=1) == '2026-02-01'
    assert parse_effective_date('00/00/0000', source=source, page=1) == ''
    with pytest.raises(ValueError, match='invalid posting date'):
        parse_effective_date('31/02/2026', source=source, page=1)


def test_description_redacts_common_identifiers():
    value = safe_description(
        'Card No. 1234 Example Store phone 0721234567 reference 123456789012'
    )
    assert '1234' not in value
    assert '0721234567' not in value
    assert '123456789012' not in value
    assert 'Example Store' in value


class FakePage:
    def __init__(self, lines):
        self.words = []
        for y, positioned_words in lines:
            for index, (x, word) in enumerate(positioned_words):
                self.words.append((x, y, x + 20, y + 8, word, 0, 0, index))

    def get_text(self, kind, sort=False):
        assert kind == 'words'
        return self.words


class FakeDocument:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __iter__(self):
        return iter(self.pages)


def test_multiline_page_transition_and_international_fee(monkeypatch):
    pages = [
        FakePage([
            (5, [(90, 'Your'), (120, 'transactions')]),
            (20, [(30, '01/01/2026'), (90, 'Bal'), (115, 'Brought'),
                  (150, 'Forward'), (530, '100.00')]),
            (30, [(100, 'First'), (130, 'description')]),
        ]),
        FakePage([
            (10, [(100, 'continues'), (145, 'here')]),
            (20, [(30, '02/01/2026'), (90, 'Transaction'), (145, 'Fee'),
                  (360, '2.00'), (530, '98.00')]),
            (30, [(100, '(Effective'), (155, '00/00/0000)')]),
        ]),
    ]
    monkeypatch.setattr(pymupdf, 'open', lambda _: FakeDocument(pages))
    rows = extract_pdf(Path('synthetic.pdf'))
    assert rows[0]['description_parts'] == ['First description', 'continues here']
    assert rows[0]['page_number'] == 1
    assert rows[1]['fee'] == Decimal('2.00')
    assert rows[1]['debit'] == Decimal('0')
    assert rows[1]['effective_date'] == ''


def test_balance_mismatch_is_diagnostic():
    rows = [
        transaction('2026-01-01', 'Bal Brought Forward', '100.00'),
        transaction('2026-01-02', 'Purchase', '95.00', debit='6.00', page=2),
    ]
    assert validate(rows)['issues'] == [
        'Balance mismatch near row 2 (page 2): expected 94.00, found 95.00'
    ]


def test_reconciliation_detects_summary_difference():
    rows = [
        transaction('2026-01-01', 'Bal Brought Forward', '100.00'),
        transaction('2026-01-02', 'Purchase', '90.00', debit='10.00'),
    ]
    result = reconcile(rows, summary_for(rows, sundry_debits=Decimal('11.00')))
    assert any('Sundry debit total' in issue for issue in result['issues'])


def test_reconciliation_excludes_cancelled_cashsend_pair_from_summary():
    rows = [
        transaction('2026-01-01', 'Bal Brought Forward', '200.00'),
        transaction('2026-01-02', 'Cashsend Mobile', '50.00', debit='150.00'),
        transaction('2026-01-02', 'Can Cashsend Mb', '200.00', credit='150.00'),
        transaction('2026-01-03', 'Purchase', '180.00', debit='20.00'),
    ]
    expected = summary_for(rows, credits=Decimal('0'),
                           sundry_debits=Decimal('20.00'))
    result = reconcile(rows, expected)
    assert not result['issues']
    assert result['cancelled_cashsend_pairs'] == 1


def test_statement_summary_from_synthetic_pdf(tmp_path):
    pdf = tmp_path / 'synthetic.pdf'
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), '\n'.join([
        'Account Summary:', 'Balance Brought Forward', '100,00',
        'Sundry Credits', '20,00', 'Cash, Cheque and ATM Withdrawals',
        '0,00', 'Sundry Debits', '15,00', 'Charges', '5,00',
        'Balance', '100,00', 'Your transactions',
    ]))
    document.save(pdf)
    document.close()
    assert statement_summary(pdf) == {
        'opening': Decimal('100.00'), 'credits': Decimal('20.00'),
        'withdrawals': Decimal('0.00'), 'sundry_debits': Decimal('15.00'),
        'charges': Decimal('5.00'), 'closing': Decimal('100.00'),
    }


def test_no_csv_created_on_invalid_pdf(tmp_path):
    pdf = tmp_path / 'unsupported.pdf'
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), 'Synthetic invoice, not a bank statement')
    document.save(pdf)
    document.close()
    with pytest.raises(ValueError):
        export([pdf], tmp_path / 'private.csv')
    assert not (tmp_path / 'private.csv').exists()


def test_consolidation_is_ordered_skips_identical_and_flags_overlap(
        tmp_path, monkeypatch):
    first = tmp_path / 'first.pdf'
    second = tmp_path / 'second.pdf'
    duplicate = tmp_path / 'duplicate.pdf'
    first.write_bytes(b'first synthetic PDF')
    second.write_bytes(b'second synthetic PDF')
    duplicate.write_bytes(first.read_bytes())
    first_rows = [
        transaction('2026-01-01', 'Bal Brought Forward', '100.00'),
        transaction('2026-01-03', 'Purchase', '90.00', debit='10.00'),
    ]
    second_rows = [
        transaction('2026-01-02', 'Bal Brought Forward', '100.00'),
        transaction('2026-01-03', 'Purchase', '90.00', debit='10.00'),
        transaction('2026-01-04', 'Credit', '95.00', credit='5.00'),
    ]
    data = {
        first.name: (first_rows, reconcile(first_rows, summary_for(first_rows))),
        second.name: (second_rows, reconcile(second_rows, summary_for(second_rows))),
    }
    monkeypatch.setattr(extractor, 'process_statement', lambda source: data[source.name])
    output = tmp_path / 'transactions.csv'
    report_path = tmp_path / 'validation.json'
    report = export([second, first, duplicate], output, report_path)
    with output.open(encoding='utf-8', newline='') as handle:
        records = list(csv.DictReader(handle))
    assert [row['transaction_date'] for row in records] == [
        '2026-01-03', '2026-01-03', '2026-01-04'
    ]
    assert [row['source_file'] for row in records[:2]] == [second.name, first.name]
    assert len(report['skipped_identical_files']) == 1
    assert len(report['statement_overlaps']) == 1
    assert len(report['potential_duplicate_transactions']) == 1
    assert json.loads(report_path.read_text(encoding='utf-8')) == report
    first_csv = output.read_bytes()
    first_report = report_path.read_bytes()

    export([second, first, duplicate], output, report_path)

    assert output.read_bytes() == first_csv
    assert report_path.read_bytes() == first_report


def test_failed_statement_preserves_existing_outputs(tmp_path, monkeypatch):
    valid = tmp_path / 'valid.pdf'
    invalid = tmp_path / 'invalid.pdf'
    valid.write_bytes(b'valid synthetic PDF')
    invalid.write_bytes(b'invalid synthetic PDF')
    output = tmp_path / 'transactions.csv'
    report = tmp_path / 'validation.json'
    output.write_text('previous valid csv', encoding='utf-8')
    report.write_text('{"status":"previous"}', encoding='utf-8')
    rows = [
        transaction('2026-01-01', 'Bal Brought Forward', '10.00'),
        transaction('2026-01-02', 'Purchase', '9.00', debit='1.00'),
    ]

    def process(source):
        if source == invalid:
            raise ValueError('synthetic validation failure')
        return rows, reconcile(rows, summary_for(rows))

    monkeypatch.setattr(extractor, 'process_statement', process)
    with pytest.raises(ValueError, match='synthetic validation failure'):
        export([valid, invalid], output, report)
    assert output.read_text(encoding='utf-8') == 'previous valid csv'
    assert report.read_text(encoding='utf-8') == '{"status":"previous"}'


def test_main_resolves_pdf_directory(tmp_path, monkeypatch):
    input_dir = tmp_path / 'raw'
    input_dir.mkdir()
    first = input_dir / 'B.PDF'
    second = input_dir / 'a.pdf'
    first.touch()
    second.touch()
    (input_dir / 'notes.txt').touch()
    captured = {}

    def fake_export(inputs, output_path, report_path):
        captured.update(inputs=inputs, output=output_path, report=report_path)

    monkeypatch.setattr(extractor, 'export', fake_export)
    output = tmp_path / 'transactions.csv'
    report = tmp_path / 'validation.json'
    extractor.main([
        '--input', str(input_dir), '--output', str(output), '--report', str(report),
    ])
    assert captured == {
        'inputs': [second, first], 'output': output, 'report': report,
    }


def test_real_statement_optional():
    value = (
        os.getenv('FINANCIAL_FOOTPRINTS_PRIVATE_TEST_PDF')
        or os.getenv('SPENDSTORY_PRIVATE_TEST_PDF')
    )
    if not value:
        pytest.skip('Optional local-only regression test')
    rows = extract_pdf(Path(value))
    result = reconcile(rows, statement_summary(Path(value)))
    assert not result['issues']
    assert result['transactions'] > 0
    assert any(row.get('effective_date') for row in rows)
