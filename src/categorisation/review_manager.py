"""Validate edited review CSVs and persist transaction-level decisions."""

import argparse
import csv
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .category_validator import (
    OUTPUT_COLUMNS,
    REVIEW_COLUMNS,
    CategoryValidationError,
    load_category_hierarchy,
    validate_input_records,
    validate_output_records,
)
from .transaction_classifier import NON_EXPENSE_MOVEMENTS
from src.preprocessing.transaction_validator import (
    OUTPUT_COLUMNS as PREPROCESSED_COLUMNS,
)

DEFAULT_CATEGORIES = Path('config/categories.yaml')
DEFAULT_SOURCE = Path('data/private/categorised_transactions.csv')
DEFAULT_REVIEW = Path('data/private/classification_review.csv')
DEFAULT_CORRECTIONS = Path('data/private/classification_corrections.csv')

REVIEW_STATUSES = {'pending', 'approved', 'corrected', 'deferred'}
SAVED_STATUSES = REVIEW_STATUSES - {'pending'}
CORRECTION_COLUMNS = [
    'transaction_id',
    'record_fingerprint',
    'reviewed_merchant',
    'reviewed_category',
    'reviewed_subcategory',
    'review_status',
    'review_notes',
    'decision_version',
    'updated_at_utc',
]
FORMULA_PREFIXES = ('=', '+', '-', '@')


def spreadsheet_safe(value):
    """Make generated review text inert when opened in spreadsheet software."""
    text = str(value or '')
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


def record_fingerprint(record):
    """Bind a decision to immutable content while allowing source-file renames."""
    fields = [field for field in PREPROCESSED_COLUMNS if field != 'source_file']
    payload = {field: str(record.get(field) or '') for field in fields}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def build_review_decision_fields(correction, source=None):
    if correction is None:
        return {
            'reviewed_merchant': '',
            'reviewed_category': '',
            'reviewed_subcategory': '',
            'review_status': 'pending',
            'review_notes': '',
            'decision_version': '0',
        }
    status = correction['review_status']
    suggestion_changed = source is not None and status == 'approved' and (
        correction['reviewed_merchant'],
        correction['reviewed_category'],
        correction['reviewed_subcategory'],
    ) != (
        source['clean_merchant'], source['category'], source['subcategory'],
    )
    if suggestion_changed:
        note = correction['review_notes']
        warning = 'Saved approval differs from the current suggestion; review again.'
        return {
            'reviewed_merchant': '',
            'reviewed_category': '',
            'reviewed_subcategory': '',
            'review_status': 'pending',
            'review_notes': f'{note} {warning}'.strip(),
            'decision_version': correction['decision_version'],
        }
    expose_values = status == 'corrected'
    return {
        'reviewed_merchant': (
            correction['reviewed_merchant'] if expose_values else ''
        ),
        'reviewed_category': (
            correction['reviewed_category'] if expose_values else ''
        ),
        'reviewed_subcategory': (
            correction['reviewed_subcategory'] if expose_values else ''
        ),
        'review_status': status,
        'review_notes': correction['review_notes'],
        'decision_version': correction['decision_version'],
    }


def _read_csv(path, expected_columns, label):
    path = Path(path)
    if not path.is_file():
        raise CategoryValidationError(f'{label} file does not exist: {path}')
    try:
        with path.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle, strict=True)
            if list(reader.fieldnames or []) != list(expected_columns):
                raise CategoryValidationError(f'unsupported {label} schema')
            records = list(reader)
    except UnicodeError as exc:
        raise CategoryValidationError(f'{label} file is not valid UTF-8') from exc
    except csv.Error as exc:
        raise CategoryValidationError(f'malformed {label} CSV') from exc
    for row_number, record in enumerate(records, start=2):
        if None in record:
            raise CategoryValidationError(
                f'{label} row {row_number}: too many fields'
            )
        if any(value is None for value in record.values()):
            raise CategoryValidationError(
                f'{label} row {row_number}: missing fields'
            )
    return records


def load_categorised_source(path, hierarchy):
    records = _read_csv(path, OUTPUT_COLUMNS, 'categorised source')
    source = [
        {field: record[field] for field in PREPROCESSED_COLUMNS}
        for record in records
    ]
    validate_input_records(source)
    normalized = []
    for row_number, record in enumerate(records, start=2):
        if record['category_review_required'] not in {'True', 'False'}:
            raise CategoryValidationError(
                f'row {row_number}: invalid automatic review flag'
            )
        converted = dict(record)
        converted['category_review_required'] = (
            record['category_review_required'] == 'True'
        )
        normalized.append(converted)
    validate_output_records(source, normalized, hierarchy)
    return records


def _validate_text(value, field, row_number):
    value = str(value or '').strip()
    if value.startswith(FORMULA_PREFIXES):
        raise CategoryValidationError(
            f'row {row_number}: {field} begins with an unsafe spreadsheet formula character'
        )
    return value


def _validate_category(category, subcategory, hierarchy, row_number):
    if bool(category) != bool(subcategory):
        raise CategoryValidationError(
            f'row {row_number}: category and subcategory must resolve together'
        )
    if category and (
        category not in hierarchy or subcategory not in hierarchy[category]
    ):
        raise CategoryValidationError(
            f'row {row_number}: invalid category and subcategory combination'
        )


def load_correction_store(path, hierarchy):
    path = Path(path)
    if not path.exists():
        return {}
    records = _read_csv(path, CORRECTION_COLUMNS, 'correction store')
    corrections = {}
    for row_number, record in enumerate(records, start=2):
        transaction_id = record['transaction_id'].strip()
        if not transaction_id:
            raise CategoryValidationError(
                f'correction store row {row_number}: missing transaction_id'
            )
        if transaction_id in corrections:
            raise CategoryValidationError(
                f'duplicate correction transaction_id: {transaction_id}'
            )
        if record['review_status'] not in SAVED_STATUSES:
            raise CategoryValidationError(
                f'correction store row {row_number}: invalid review_status'
            )
        try:
            version = int(record['decision_version'])
            if version < 1 or str(version) != record['decision_version']:
                raise ValueError
        except ValueError as exc:
            raise CategoryValidationError(
                f'correction store row {row_number}: invalid decision_version'
            ) from exc
        if not re.fullmatch(r'[0-9a-f]{64}', record['record_fingerprint']):
            raise CategoryValidationError(
                f'correction store row {row_number}: invalid record_fingerprint'
            )
        try:
            updated = datetime.fromisoformat(record['updated_at_utc'])
            if updated.tzinfo is None:
                raise ValueError
        except ValueError as exc:
            raise CategoryValidationError(
                f'correction store row {row_number}: invalid updated_at_utc'
            ) from exc
        _validate_text(
            record['reviewed_merchant'], 'reviewed_merchant', row_number,
        )
        _validate_text(record['review_notes'], 'review_notes', row_number)
        _validate_category(
            record['reviewed_category'], record['reviewed_subcategory'],
            hierarchy, row_number,
        )
        corrections[transaction_id] = record
    return corrections


def _validate_store_bindings(corrections, source_by_id):
    stale = sorted(set(corrections) - set(source_by_id))
    if stale:
        raise CategoryValidationError(
            f'correction store contains {len(stale)} transaction(s) absent from the source dataset'
        )
    for transaction_id, correction in corrections.items():
        if correction['record_fingerprint'] != record_fingerprint(
                source_by_id[transaction_id]):
            raise CategoryValidationError(
                f'correction fingerprint does not match transaction {transaction_id}'
            )


def _expected_review_snapshot(source):
    return {
        'transaction_date': source['transaction_date'],
        'original_description': spreadsheet_safe(source['description']),
        'clean_merchant': spreadsheet_safe(source['clean_merchant']),
        'movement_type': source['movement_type'],
        'suggested_category': source['category'],
        'suggested_subcategory': source['subcategory'],
        'classification_method': source['classification_method'],
        'classification_confidence': source['classification_confidence'],
        'review_required': str(source['category_review_required']),
    }


def _decision_from_review(record, source, hierarchy, row_number, now):
    status = record['review_status'].strip().casefold()
    if status not in REVIEW_STATUSES:
        raise CategoryValidationError(
            f'row {row_number}: invalid review_status {record["review_status"]!r}'
        )
    try:
        version = int(record['decision_version'])
        if version < 0 or str(version) != record['decision_version'].strip():
            raise ValueError
    except ValueError as exc:
        raise CategoryValidationError(
            f'row {row_number}: invalid decision_version'
        ) from exc
    merchant = _validate_text(
        record['reviewed_merchant'], 'reviewed_merchant', row_number,
    )
    category = record['reviewed_category'].strip()
    subcategory = record['reviewed_subcategory'].strip()
    notes = _validate_text(record['review_notes'], 'review_notes', row_number)
    if status == 'pending':
        if merchant or category or subcategory:
            raise CategoryValidationError(
                f'row {row_number}: pending review cannot contain correction values'
            )
        return None, version
    if status == 'deferred':
        if merchant or category or subcategory:
            raise CategoryValidationError(
                f'row {row_number}: deferred review cannot contain correction values'
            )
        final_merchant = source['clean_merchant']
        final_category = source['category']
        final_subcategory = source['subcategory']
    elif status == 'approved':
        for value, source_value in (
            (merchant, source['clean_merchant']),
            (category, source['category']),
            (subcategory, source['subcategory']),
        ):
            if value and value != source_value:
                raise CategoryValidationError(
                    f'row {row_number}: approved review conflicts with its suggestion'
                )
        final_merchant = source['clean_merchant']
        final_category = source['category']
        final_subcategory = source['subcategory']
    else:
        final_merchant = merchant or source['clean_merchant']
        final_category = category or source['category']
        final_subcategory = subcategory or source['subcategory']
        if (
            final_merchant, final_category, final_subcategory
        ) == (
            source['clean_merchant'], source['category'], source['subcategory']
        ):
            raise CategoryValidationError(
                f'row {row_number}: corrected review does not change a suggestion'
            )
    _validate_category(final_category, final_subcategory, hierarchy, row_number)
    if source['movement_type'] in NON_EXPENSE_MOVEMENTS and (
            final_category or final_subcategory):
        raise CategoryValidationError(
            f'row {row_number}: excluded movement cannot receive a spending category'
        )
    return {
        'transaction_id': source['transaction_id'],
        'record_fingerprint': record_fingerprint(source),
        'reviewed_merchant': final_merchant,
        'reviewed_category': final_category,
        'reviewed_subcategory': final_subcategory,
        'review_status': status,
        'review_notes': notes,
        'decision_version': '',
        'updated_at_utc': now,
    }, version


def _stage_csv(path, fieldnames, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', newline='', delete=False,
        dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp',
    )
    try:
        with temporary:
            writer = csv.DictWriter(temporary, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)
        return Path(temporary.name)
    except Exception:
        Path(temporary.name).unlink(missing_ok=True)
        raise


def _replace_file(staged, destination):
    try:
        os.replace(staged, destination)
    finally:
        staged.unlink(missing_ok=True)


def import_reviews(
        review_path, source_path, corrections_path,
        categories_path=DEFAULT_CATEGORIES, replace_existing=False, now=None):
    resolved = [Path(value).resolve() for value in (
        review_path, source_path, corrections_path,
    )]
    if len(set(resolved)) != 3:
        raise CategoryValidationError(
            'review, categorised source and correction store paths must differ'
        )
    hierarchy = load_category_hierarchy(categories_path)
    source = load_categorised_source(source_path, hierarchy)
    source_by_id = {record['transaction_id']: record for record in source}
    corrections = load_correction_store(corrections_path, hierarchy)
    _validate_store_bindings(corrections, source_by_id)
    reviews = _read_csv(review_path, REVIEW_COLUMNS, 'classification review')
    ids = [record['transaction_id'].strip() for record in reviews]
    if any(not value for value in ids):
        raise CategoryValidationError('classification review contains a blank transaction_id')
    if len(ids) != len(set(ids)):
        raise CategoryValidationError('classification review contains duplicate transaction_id values')
    timestamp = now or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    updated = dict(corrections)
    added = changed = unchanged = deferred = pending = 0
    for row_number, record in enumerate(reviews, start=2):
        transaction_id = record['transaction_id'].strip()
        if transaction_id not in source_by_id:
            raise CategoryValidationError(
                f'row {row_number}: transaction_id is absent from the source dataset'
            )
        source_record = source_by_id[transaction_id]
        expected = _expected_review_snapshot(source_record)
        for field, value in expected.items():
            if record[field] != value:
                raise CategoryValidationError(
                    f'row {row_number}: stale or altered generated field {field}'
                )
        decision, review_version = _decision_from_review(
            record, source_record, hierarchy, row_number, timestamp,
        )
        existing = corrections.get(transaction_id)
        if decision is None:
            pending += 1
            continue
        deferred += decision['review_status'] == 'deferred'
        signature_fields = [
            'record_fingerprint', 'reviewed_merchant', 'reviewed_category',
            'reviewed_subcategory', 'review_status', 'review_notes',
        ]
        same = existing is not None and all(
            existing[field] == decision[field] for field in signature_fields
        )
        if same:
            unchanged += 1
            continue
        if existing is None:
            if review_version != 0 and not replace_existing:
                raise CategoryValidationError(
                    f'row {row_number}: stale decision version for new correction'
                )
            decision['decision_version'] = '1'
            added += 1
        else:
            current_version = int(existing['decision_version'])
            if review_version != current_version and not replace_existing:
                raise CategoryValidationError(
                    f'row {row_number}: stale review conflicts with a newer saved decision'
                )
            decision['decision_version'] = str(current_version + 1)
            changed += 1
        updated[transaction_id] = decision
    if added or changed:
        staged = _stage_csv(corrections_path, CORRECTION_COLUMNS, updated.values())
        _replace_file(staged, Path(corrections_path))
    return {
        'reviewed_rows': len(reviews),
        'added': added,
        'updated': changed,
        'unchanged': unchanged,
        'pending': pending,
        'deferred': deferred,
        'validation_status': 'passed',
    }


def _print_summary(summary, corrections_path):
    print(
        f'Reviewed {summary["reviewed_rows"]} rows: '
        f'{summary["added"]} added, {summary["updated"]} updated, '
        f'{summary["unchanged"]} unchanged, {summary["pending"]} pending, '
        f'{summary["deferred"]} deferred.'
    )
    print(f'Validation status: {summary["validation_status"]}.')
    print(f'Correction store: {corrections_path}')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Import and validate manually reviewed classifications'
    )
    parser.add_argument('--review', type=Path, default=DEFAULT_REVIEW)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--corrections', type=Path, default=DEFAULT_CORRECTIONS)
    parser.add_argument('--categories', type=Path, default=DEFAULT_CATEGORIES)
    parser.add_argument(
        '--replace-existing', action='store_true',
        help='explicitly resolve a stale decision-version conflict',
    )
    args = parser.parse_args(argv)
    try:
        summary = import_reviews(
            args.review, args.source, args.corrections,
            args.categories, args.replace_existing,
        )
    except (OSError, CategoryValidationError, ValueError) as exc:
        parser.exit(1, f'error: {exc}\n')
    _print_summary(summary, args.corrections)


if __name__ == '__main__':
    main()
