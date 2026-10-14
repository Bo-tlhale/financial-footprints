"""Schema and financial-integrity checks for preprocessing."""

import re
from collections import Counter
from decimal import Decimal, InvalidOperation

from src.extraction.statement_extractor import OUTPUT_COLUMNS as EXTRACTED_COLUMNS

from .transaction_cleaner import (
    clean_description,
    normalize_effective_date,
    normalize_posting_date,
)

ADDED_COLUMNS = [
    'cleaned_description',
    'movement_type',
    'movement_classification_method',
    'movement_review_required',
]
OUTPUT_COLUMNS = [*EXTRACTED_COLUMNS, *ADDED_COLUMNS]
MONEY_COLUMNS = ('debit', 'credit', 'fee', 'balance')
NONNEGATIVE_MONEY_COLUMNS = ('debit', 'credit', 'fee')
MONEY_PATTERN = re.compile(r'^-?\d+\.\d{2}$')
MOVEMENT_TYPES = {
    'Purchase', 'Income', 'Incoming Transfer', 'Outgoing Transfer', 'Refund',
    'Cash Withdrawal', 'Bank Fee', 'Reversal', 'Informational', 'Unknown',
}
CLASSIFICATION_METHODS = {
    'bank_transaction_type', 'description_rule', 'manual_rule', 'unclassified',
}


class TransactionValidationError(ValueError):
    """Raised when preprocessing cannot safely continue."""


def parse_money(value, *, field, row_number):
    text = '' if value is None else str(value).strip()
    if not MONEY_PATTERN.fullmatch(text):
        raise TransactionValidationError(
            f'row {row_number}: malformed {field}; expected a decimal with two places'
        )
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise TransactionValidationError(
            f'row {row_number}: invalid numeric value in {field}'
        ) from exc
    if not amount.is_finite():
        raise TransactionValidationError(
            f'row {row_number}: non-finite numeric value in {field}'
        )
    if field in NONNEGATIVE_MONEY_COLUMNS and amount < 0:
        raise TransactionValidationError(
            f'row {row_number}: {field} cannot be negative'
        )
    return amount


def validate_source_schema(fieldnames):
    actual = list(fieldnames or [])
    if actual != list(EXTRACTED_COLUMNS):
        missing = [column for column in EXTRACTED_COLUMNS if column not in actual]
        unexpected = [column for column in actual if column not in EXTRACTED_COLUMNS]
        details = []
        if missing:
            details.append('missing columns: ' + ', '.join(missing))
        if unexpected:
            details.append('unexpected columns: ' + ', '.join(unexpected))
        if not missing and not unexpected:
            details.append('columns are in an unsupported order')
        raise TransactionValidationError('unsupported source schema; ' + '; '.join(details))


def validate_source_records(records):
    if not records:
        raise TransactionValidationError('source dataset is empty')
    ids = []
    missing_descriptions = 0
    for row_number, record in enumerate(records, start=2):
        transaction_id = str(record.get('transaction_id', '')).strip()
        if not transaction_id:
            raise TransactionValidationError(
                f'row {row_number}: missing transaction_id'
            )
        ids.append(transaction_id)
        try:
            normalize_posting_date(record.get('transaction_date', ''))
            normalize_effective_date(record.get('effective_date', ''))
        except ValueError as exc:
            raise TransactionValidationError(f'row {row_number}: {exc}') from exc
        for field in MONEY_COLUMNS:
            parse_money(record.get(field), field=field, row_number=row_number)
        if not str(record.get('source_file', '')).strip():
            raise TransactionValidationError(f'row {row_number}: missing source_file')
        try:
            page_number = int(str(record.get('page_number', '')).strip())
        except ValueError as exc:
            raise TransactionValidationError(
                f'row {row_number}: invalid page_number'
            ) from exc
        if page_number < 1:
            raise TransactionValidationError(
                f'row {row_number}: page_number must be positive'
            )
        if not str(record.get('description', '')).strip():
            missing_descriptions += 1

    duplicates = sorted(identifier for identifier, count in Counter(ids).items()
                        if count > 1)
    if duplicates:
        raise TransactionValidationError(
            f'duplicate transaction_id values detected ({len(duplicates)})'
        )
    return {'records': len(records), 'missing_descriptions': missing_descriptions}


def validate_output_records(source_records, output_records):
    if len(source_records) != len(output_records):
        raise TransactionValidationError(
            'record count changed during preprocessing: '
            f'{len(source_records)} source, {len(output_records)} output'
        )
    review_required = 0
    movement_counts = Counter()
    for row_number, (source, output) in enumerate(
            zip(source_records, output_records), start=2):
        if set(output) != set(OUTPUT_COLUMNS):
            raise TransactionValidationError(
                f'row {row_number}: output schema is inconsistent'
            )
        if output['transaction_id'] != source['transaction_id']:
            raise TransactionValidationError(
                f'row {row_number}: transaction_id changed during preprocessing'
            )
        for field in ('debit', 'credit', 'fee', 'balance'):
            if output[field] != source[field]:
                raise TransactionValidationError(
                    f'row {row_number}: {field} changed during preprocessing'
                )
        for field in ('description', 'transaction_type', 'source_file', 'page_number'):
            if output[field] != source[field]:
                raise TransactionValidationError(
                    f'row {row_number}: source field {field} changed during preprocessing'
                )
        if output['transaction_date'] != normalize_posting_date(source['transaction_date']):
            raise TransactionValidationError(
                f'row {row_number}: transaction_date meaning changed'
            )
        if output['effective_date'] != normalize_effective_date(source['effective_date']):
            raise TransactionValidationError(
                f'row {row_number}: effective_date was not normalized correctly'
            )
        if output['cleaned_description'] != clean_description(source['description']):
            raise TransactionValidationError(
                f'row {row_number}: cleaned_description is inconsistent'
            )
        movement_type = output.get('movement_type')
        method = output.get('movement_classification_method')
        review = output.get('movement_review_required')
        if movement_type not in MOVEMENT_TYPES:
            raise TransactionValidationError(
                f'row {row_number}: invalid movement_type'
            )
        if method not in CLASSIFICATION_METHODS:
            raise TransactionValidationError(
                f'row {row_number}: invalid movement_classification_method'
            )
        if not isinstance(review, bool):
            raise TransactionValidationError(
                f'row {row_number}: invalid movement_review_required'
            )
        movement_counts[movement_type] += 1
        review_required += review
    return {
        'input_records': len(source_records),
        'output_records': len(output_records),
        'review_required': review_required,
        'unknown': movement_counts['Unknown'],
        'movement_counts': dict(sorted(movement_counts.items())),
    }
