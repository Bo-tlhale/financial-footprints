"""Extract and reconcile supported ABSA cheque-account PDF statements."""

import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pymupdf

DATE = re.compile(r"^\d{1,2}/\d{2}/\d{4}$")
MONEY = re.compile(r"^-?\d[\d ]*\.\d{2}-?$")
EFFECTIVE = re.compile(r"^\(Effective\s+\d{1,2}/\d{2}/\d{4}\)$", re.I)
OUTPUT_COLUMNS = [
    'transaction_id', 'transaction_date', 'effective_date', 'transaction_type',
    'description', 'debit', 'credit', 'fee', 'balance', 'source_file',
    'page_number',
]


def parse_statement_date(value, *, source, page):
    """Validate posting dates and provide an actionable location on failure."""
    try:
        return datetime.strptime(value, '%d/%m/%Y').date().isoformat()
    except ValueError as exc:
        raise ValueError(
            f"{source.name}: invalid posting date {value!r} on page {page}. "
            "Review the PDF before extracting. No output was replaced."
        ) from exc


def parse_effective_date(value, *, source, page):
    """Treat ABSA's all-zero supplementary effective date as unavailable."""
    if value == '00/00/0000':
        return ''
    return parse_statement_date(value, source=source, page=page)


def read_money(value):
    text = value.replace(' ', '').replace(',', '.').strip()
    negative = text.endswith('-') or text.startswith('-')
    try:
        return -Decimal(text.strip('-')) if negative else Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f'Invalid monetary value: {value!r}') from exc


def lines_on_page(page):
    """Group positioned PDF words by text baseline, sorted left to right."""
    groups = {}
    for x0, y0, x1, y1, word, *_ in page.get_text('words', sort=True):
        if y0 > 785 or x0 < 24:
            continue
        groups.setdefault(round(y0, 1), []).append((x0, word))
    return [(y, sorted(items)) for y, items in sorted(groups.items())]


def text_in(items, left, right):
    return ' '.join(word for x, word in items if left <= x < right).strip()


def safe_description(text):
    """Redact common identifiers while retaining useful transaction narrative."""
    text = re.sub(r'Card No\.\s*\d+', 'Card No. [REDACTED]', text, flags=re.I)
    text = re.sub(r'(?<!\d)\d{8,}(?!\d)', '[REDACTED]', text)
    text = re.sub(r'\b(?:0\d{2}[ -]?\d{3}[ -]?\d{4})\b', '[REDACTED]', text)
    return ' '.join(text.split())


def extract_pdf(path):
    transactions = []
    pending = None
    inside = False
    with pymupdf.open(path) as document:
        for page_index, page in enumerate(document):
            for _, items in lines_on_page(page):
                left = text_in(items, 25, 82)
                joined = ' '.join(word for _, word in items)
                if 'Your transactions' in joined:
                    inside = True
                    continue
                if DATE.fullmatch(left) and inside:
                    if pending:
                        transactions.append(pending)
                    rowtype = text_in(items, 84, 192)
                    fee = text_in(items, 300, 358)
                    debit = text_in(items, 358, 443)
                    credit = text_in(items, 443, 525)
                    balance = text_in(items, 525, 593)
                    if not MONEY.fullmatch(balance):
                        pending = None
                        continue
                    pending = {
                        'transaction_date': parse_statement_date(
                            left, source=path, page=page_index + 1
                        ),
                        'transaction_type': rowtype,
                        'settlement': text_in(items, 192, 300),
                        'description_parts': [],
                        'effective_date': '',
                        'fee': read_money(fee) if MONEY.fullmatch(fee) else Decimal('0'),
                        'debit': read_money(debit) if MONEY.fullmatch(debit) else Decimal('0'),
                        'credit': read_money(credit) if MONEY.fullmatch(credit) else Decimal('0'),
                        'balance': read_money(balance),
                        'page_number': page_index + 1,
                    }
                    if (pending['transaction_type'].lower() == 'transaction fee'
                            and pending['debit'] > 0):
                        pending['fee'] += pending['debit']
                        pending['debit'] = Decimal('0')
                    continue
                if pending and inside:
                    continuation = text_in(items, 94, 299)
                    if (continuation
                            and not joined.startswith((
                                'Page ', 'CSP', 'Our Privacy', 'Your transactions',
                                'Date ', 'ABSA Bank',
                            ))
                            and 'account statement' not in joined.lower()
                            and 'TRANSACTION' not in joined.upper()):
                        if EFFECTIVE.fullmatch(continuation):
                            effective = re.search(
                                r'\d{1,2}/\d{2}/\d{4}', continuation
                            ).group()
                            pending['effective_date'] = parse_effective_date(
                                effective, source=path, page=page_index + 1
                            )
                        else:
                            pending['description_parts'].append(continuation)
    if pending:
        transactions.append(pending)
    if not transactions:
        raise ValueError(
            f'{path.name}: no transactions found; the PDF may use an unsupported '
            'layout or contain scanned images. No output was replaced.'
        )
    return transactions


def validate(transactions):
    issues = []
    opening = transactions[0]['balance']
    if transactions[0]['transaction_type'].lower() != 'bal brought forward':
        issues.append('Opening balance row not identified')
    for index in range(1, len(transactions)):
        previous, current = transactions[index - 1], transactions[index]
        expected = (
            previous['balance'] + current['credit']
            - current['debit'] - current['fee']
        )
        if expected != current['balance']:
            issues.append(
                f"Balance mismatch near row {index + 1} "
                f"(page {current['page_number']}): expected {expected:.2f}, "
                f"found {current['balance']:.2f}"
            )
    return {
        'rows_including_opening': len(transactions),
        'transactions': len(transactions) - 1,
        'opening_balance': opening,
        'closing_balance': transactions[-1]['balance'],
        'sum_debits': sum((row['debit'] for row in transactions), Decimal(0)),
        'sum_credits': sum((row['credit'] for row in transactions), Decimal(0)),
        'sum_fees': sum((row['fee'] for row in transactions), Decimal(0)),
        'issues': issues,
    }


def statement_summary(path):
    """Read expected totals from ABSA's selectable-text account summary."""
    with pymupdf.open(path) as document:
        text = document[0].get_text('text')
    if 'Account Summary:' not in text:
        raise ValueError(f'{path.name}: account summary not found')
    section = text.split('Account Summary:', 1)[1].split('Your transactions', 1)[0]
    labels = {
        'opening': 'Balance Brought Forward',
        'credits': 'Sundry Credits',
        'withdrawals': 'Cash, Cheque and ATM Withdrawals',
        'sundry_debits': 'Sundry Debits',
        'charges': 'Charges',
        'closing': 'Balance',
    }
    lines = [line.strip() for line in section.splitlines() if line.strip()]
    result = {}
    for field, label in labels.items():
        matches = [index for index, value in enumerate(lines) if value == label]
        if len(matches) != 1 or matches[0] + 1 >= len(lines):
            raise ValueError(
                f'{path.name}: missing or duplicated account-summary field: {field}'
            )
        raw = lines[matches[0] + 1]
        if not re.fullmatch(r'[\d ]+[,\.]\d{2}-?', raw):
            raise ValueError(f'{path.name}: malformed account-summary field: {field}')
        result[field] = abs(read_money(raw))
    return result


def _cancelled_cashsend_pairs(rows):
    cancelled_debits = set()
    cancellation_credits = set()
    for credit_index, credit_row in enumerate(rows):
        if (credit_row['transaction_type'].lower() != 'can cashsend mb'
                or credit_row['credit'] <= 0):
            continue
        for debit_index in range(credit_index - 1, -1, -1):
            debit_row = rows[debit_index]
            if (debit_index not in cancelled_debits
                    and debit_row['transaction_type'].lower() == 'cashsend mobile'
                    and debit_row['transaction_date'] == credit_row['transaction_date']
                    and debit_row['debit'] == credit_row['credit']):
                cancelled_debits.add(debit_index)
                cancellation_credits.add(credit_index)
                break
    return cancelled_debits, cancellation_credits


def reconcile(rows, expected):
    result = validate(rows)
    issues = result['issues']
    if rows[0]['balance'] != expected['opening']:
        issues.append('Opening balance differs from account summary')
    if rows[-1]['balance'] != expected['closing']:
        issues.append('Closing balance differs from account summary')

    cancelled_debits, cancellation_credits = _cancelled_cashsend_pairs(rows)
    summary_credit_total = sum(
        (row['credit'] for index, row in enumerate(rows)
         if index not in cancellation_credits), Decimal(0)
    )
    if summary_credit_total != expected['credits']:
        issues.append(
            f"Credit total differs from account summary "
            f"(extracted {summary_credit_total:.2f}, expected {expected['credits']:.2f})"
        )
    if result['sum_fees'] != expected['charges']:
        issues.append(
            f"Bank charges differ from account summary "
            f"(extracted {result['sum_fees']:.2f}, expected {expected['charges']:.2f})"
        )

    withdrawal_types = {'atm withdrawal', 'sas atm withdrawal'}
    withdrawal_total = sum(
        (row['debit'] for row in rows
         if row['transaction_type'].lower() in withdrawal_types), Decimal(0)
    )
    if withdrawal_total != expected['withdrawals']:
        issues.append(
            f"Cash/ATM withdrawal total differs from account summary "
            f"(extracted {withdrawal_total:.2f}, expected {expected['withdrawals']:.2f})"
        )
    summary_sundry_debit_total = sum(
        (row['debit'] for index, row in enumerate(rows)
         if index not in cancelled_debits
         and row['transaction_type'].lower() not in withdrawal_types), Decimal(0)
    )
    if summary_sundry_debit_total != expected['sundry_debits']:
        issues.append(
            f"Sundry debit total differs from account summary "
            f"(extracted {summary_sundry_debit_total:.2f}, "
            f"expected {expected['sundry_debits']:.2f})"
        )
    expected_closing = (
        expected['opening'] + expected['credits'] - expected['withdrawals']
        - expected['sundry_debits'] - expected['charges']
    )
    if expected_closing != expected['closing']:
        issues.append('Account summary arithmetic does not reconcile')

    result['informational_rows'] = sum(
        1 for row in rows[1:]
        if not (row['debit'] or row['credit'] or row['fee'])
    )
    result['summary_credit_total'] = summary_credit_total
    result['summary_debit_total'] = withdrawal_total + summary_sundry_debit_total
    result['cancelled_cashsend_pairs'] = len(cancellation_credits)
    return result


def process_statement(source):
    rows = extract_pdf(source)
    summary = reconcile(rows, statement_summary(source))
    if summary['issues']:
        raise ValueError(
            f'{source.name}: reconciliation failed: ' + '; '.join(summary['issues'][:8])
        )
    return rows, summary


def _statement_overlaps(reports):
    overlaps = []
    for left_index, left in enumerate(reports):
        for right in reports[left_index + 1:]:
            start = max(left['period_start'], right['period_start'])
            end = min(left['period_end'], right['period_end'])
            if start <= end:
                overlaps.append({
                    'source_files': [left['source_file'], right['source_file']],
                    'overlap_start': start,
                    'overlap_end': end,
                    'review_required': True,
                })
    return overlaps


def _potential_duplicate_groups(records):
    grouped = defaultdict(list)
    for record in records:
        signature = tuple(record[field] for field in (
            'transaction_date', 'transaction_type', 'description', 'debit',
            'credit', 'fee', 'balance',
        ))
        grouped[signature].append(record)
    candidates = []
    for matches in grouped.values():
        if len({record['source_file'] for record in matches}) > 1:
            candidates.append({
                'transaction_ids': [record['transaction_id'] for record in matches],
                'source_files': sorted({record['source_file'] for record in matches}),
                'transaction_date': matches[0]['transaction_date'],
                'review_required': True,
            })
    return sorted(candidates, key=lambda item: (item['transaction_date'], item['transaction_ids']))


def _stage_text(destination, writer):
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', newline='', delete=False,
        dir=destination.parent, prefix=f'.{destination.name}.', suffix='.tmp',
    )
    try:
        with handle:
            writer(handle)
        return Path(handle.name)
    except Exception:
        Path(handle.name).unlink(missing_ok=True)
        raise


def export(inputs, output, report_path=None):
    """Validate all unique inputs, then atomically replace consolidated outputs."""
    output = Path(output)
    report_path = Path(report_path) if report_path is not None else None
    if report_path is not None and output.resolve() == report_path.resolve():
        raise ValueError('CSV output and JSON report paths must be different')

    records = []
    reports = []
    skipped_identical_files = []
    seen_hashes = {}
    for source_order, source in enumerate(map(Path, inputs)):
        file_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if file_hash in seen_hashes:
            skipped_identical_files.append({
                'source_file': source.name,
                'identical_to': seen_hashes[file_hash],
            })
            continue
        seen_hashes[file_hash] = source.name
        rows, summary = process_statement(source)
        transaction_rows = rows[1:] if (
            rows and rows[0]['transaction_type'].lower() == 'bal brought forward'
        ) else rows
        dates = [row['transaction_date'] for row in transaction_rows]
        reports.append({
            'source_file': source.name,
            'status': 'passed',
            'transactions': len(transaction_rows),
            'informational_rows': summary['informational_rows'],
            'period_start': min(dates),
            'period_end': max(dates),
            'opening_balance': str(summary['opening_balance']),
            'closing_balance': str(summary['closing_balance']),
            'credit_total': str(summary['summary_credit_total']),
            'debit_total': str(summary['summary_debit_total']),
            'charge_total': str(summary['sum_fees']),
            'cancelled_cashsend_pairs': summary['cancelled_cashsend_pairs'],
        })
        for row_index, row in enumerate(rows):
            if row_index == 0 and row['transaction_type'].lower() == 'bal brought forward':
                continue
            identifier = hashlib.sha256(
                f'{file_hash}|{row_index}'.encode('utf-8')
            ).hexdigest()[:20]
            records.append({
                'transaction_id': identifier,
                'transaction_date': row['transaction_date'],
                'effective_date': row['effective_date'],
                'transaction_type': row['transaction_type'],
                'description': safe_description(' '.join(row['description_parts'])),
                'debit': f'{row["debit"]:.2f}',
                'credit': f'{row["credit"]:.2f}',
                'fee': f'{row["fee"]:.2f}',
                'balance': f'{row["balance"]:.2f}',
                'source_file': source.name,
                'page_number': row['page_number'],
                '_source_order': source_order,
                '_row_index': row_index,
            })

    records.sort(key=lambda row: (
        row['transaction_date'], row['_source_order'], row['_row_index']
    ))
    overlaps = _statement_overlaps(reports)
    duplicate_candidates = _potential_duplicate_groups(records) if overlaps else []
    public_records = [
        {column: record[column] for column in OUTPUT_COLUMNS} for record in records
    ]
    report = {
        'status': 'passed',
        'statements': reports,
        'total_transactions': len(public_records),
        'skipped_identical_files': skipped_identical_files,
        'statement_overlaps': overlaps,
        'potential_duplicate_transactions': duplicate_candidates,
    }

    staged = []
    try:
        staged_csv = _stage_text(output, lambda handle: _write_csv(handle, public_records))
        staged.append(staged_csv)
        staged_report = None
        if report_path is not None:
            staged_report = _stage_text(
                report_path,
                lambda handle: json.dump(report, handle, indent=2),
            )
            staged.append(staged_report)
        os.replace(staged_csv, output)
        staged.remove(staged_csv)
        if staged_report is not None:
            os.replace(staged_report, report_path)
            staged.remove(staged_report)
    finally:
        for temporary in staged:
            temporary.unlink(missing_ok=True)

    for index, statement in enumerate(reports, start=1):
        print(
            f'Statement {index}: {statement["transactions"]} transactions; '
            'full reconciliation passed.'
        )
    print(f'Created consolidated CSV with {len(public_records)} transactions: {output}')
    if report_path is not None:
        print(f'Created validation report: {report_path}')
    if overlaps:
        print(
            f'Warning: {len(overlaps)} overlapping statement period(s) detected; '
            'review the validation report for potential duplicates.'
        )
    return report


def _write_csv(handle, records):
    writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
    writer.writeheader()
    writer.writerows(records)


def resolve_inputs(input_path, parser):
    if not input_path.exists():
        parser.error(f'input path does not exist: {input_path}')
    if input_path.is_file():
        if input_path.suffix.lower() != '.pdf':
            parser.error(f'input file is not a PDF: {input_path}')
        return [input_path]
    if input_path.is_dir():
        inputs = sorted(
            (path for path in input_path.iterdir()
             if path.is_file() and path.suffix.lower() == '.pdf'),
            key=lambda path: path.name.lower(),
        )
        if not inputs:
            parser.error(f'no PDF files found in input directory: {input_path}')
        return inputs
    parser.error(f'input path is neither a file nor a directory: {input_path}')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Extract supported ABSA cheque statements locally'
    )
    parser.add_argument('--input', required=True, type=Path,
                        help='PDF file or directory of PDFs')
    parser.add_argument('--output', required=True, type=Path,
                        help='private consolidated CSV output path')
    parser.add_argument('--report', type=Path,
                        help='private JSON validation report path')
    args = parser.parse_args(argv)
    inputs = resolve_inputs(args.input, parser)
    try:
        export(inputs, args.output, args.report)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'error: {exc}\n')


if __name__ == '__main__':
    main()
