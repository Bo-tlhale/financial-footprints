"""CLI pipeline for merchant identification and transaction categorisation."""

import argparse
import csv
import os
import shutil
import tempfile
from pathlib import Path

from .category_validator import (
    OUTPUT_COLUMNS,
    REVIEW_COLUMNS,
    CategoryValidationError,
    load_category_hierarchy,
    load_merchant_rules,
    validate_input_records,
    validate_input_schema,
    validate_output_records,
)
from .transaction_classifier import classify_transaction
from .review_manager import (
    build_review_decision_fields,
    load_correction_store,
    record_fingerprint,
    spreadsheet_safe,
)

DEFAULT_CATEGORIES = Path('config/categories.yaml')
DEFAULT_RULES = Path('config/merchant_rules.yaml')


def load_source(path):
    path = Path(path)
    if not path.is_file():
        raise CategoryValidationError(f'input file does not exist: {path}')
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        validate_input_schema(reader.fieldnames)
        records = list(reader)
    validate_input_records(records)
    return records


def categorise_records(records, rules):
    output = []
    for record in records:
        enriched = dict(record)
        enriched.update(classify_transaction(record, rules))
        output.append(enriched)
    return output


def build_review_records(records, corrections=None):
    corrections = corrections or {}
    review = []
    for record in records:
        correction = corrections.get(record['transaction_id'])
        if (
            correction is not None
            and correction['record_fingerprint'] != record_fingerprint(record)
        ):
            raise CategoryValidationError(
                'saved correction fingerprint does not match transaction '
                f'{record["transaction_id"]}'
            )
        row = {
            'transaction_id': record['transaction_id'],
            'transaction_date': record['transaction_date'],
            'original_description': spreadsheet_safe(record['description']),
            'clean_merchant': spreadsheet_safe(record['clean_merchant']),
            'movement_type': record['movement_type'],
            'suggested_category': record['category'],
            'suggested_subcategory': record['subcategory'],
            'classification_method': record['classification_method'],
            'classification_confidence': record['classification_confidence'],
            'review_required': record['category_review_required'],
        }
        row.update(build_review_decision_fields(
            correction, record,
        ))
        review.append(row)
    return review


def _stage_csv(path, fieldnames, records):
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


def _review_can_be_replaced(review_path, staged_review, allow_changed_review):
    if not review_path.exists() or allow_changed_review:
        return
    if review_path.read_bytes() != staged_review.read_bytes():
        raise CategoryValidationError(
            'existing classification review differs from the generated review; '
            'inspect it or rerun with --overwrite-review'
        )


def _replace_pair(staged_pairs):
    backups = []
    replaced = []
    try:
        for staged, destination in staged_pairs:
            backup = None
            if destination.exists():
                handle = tempfile.NamedTemporaryFile(
                    delete=False, dir=destination.parent,
                    prefix=f'.{destination.name}.', suffix='.backup',
                )
                handle.close()
                backup = Path(handle.name)
                shutil.copy2(destination, backup)
            backups.append((destination, backup))
        for staged, destination in staged_pairs:
            os.replace(staged, destination)
            replaced.append(destination)
    except Exception:
        for destination, backup in reversed(backups):
            if backup is not None and backup.exists():
                os.replace(backup, destination)
            elif destination in replaced:
                destination.unlink(missing_ok=True)
        raise
    finally:
        for _, backup in backups:
            if backup is not None:
                backup.unlink(missing_ok=True)
        for staged, _ in staged_pairs:
            staged.unlink(missing_ok=True)


def categorise_csv(
        input_path, output_path, review_path,
        categories_path=DEFAULT_CATEGORIES, rules_path=DEFAULT_RULES,
        allow_changed_review=False, corrections_path=None):
    input_path = Path(input_path)
    output_path = Path(output_path)
    review_path = Path(review_path)
    resolved = [path.resolve() for path in (input_path, output_path, review_path)]
    if len(set(resolved)) != 3:
        raise CategoryValidationError('input, output and review paths must be different')
    if (
        corrections_path is not None
        and Path(corrections_path).resolve() in resolved
    ):
        raise CategoryValidationError(
            'correction store must differ from input, output and review paths'
        )
    hierarchy = load_category_hierarchy(categories_path)
    rules = load_merchant_rules(rules_path, hierarchy)
    source = load_source(input_path)
    categorised = categorise_records(source, rules)
    summary = validate_output_records(source, categorised, hierarchy)
    corrections = {}
    if corrections_path is not None and Path(corrections_path).exists():
        corrections = load_correction_store(corrections_path, hierarchy)
    review = build_review_records(categorised, corrections)
    staged_output = _stage_csv(output_path, OUTPUT_COLUMNS, categorised)
    staged_review = None
    try:
        staged_review = _stage_csv(review_path, REVIEW_COLUMNS, review)
        _review_can_be_replaced(
            review_path, staged_review, allow_changed_review,
        )
        _replace_pair([
            (staged_output, output_path),
            (staged_review, review_path),
        ])
    finally:
        staged_output.unlink(missing_ok=True)
        if staged_review is not None:
            staged_review.unlink(missing_ok=True)
    return summary


def _print_summary(summary, output_path, review_path):
    print(f'Processed {summary["processed"]} transactions.')
    print(
        f'Merchants identified: {summary["merchants_identified"]}; '
        f'categorised: {summary["categorised"]}; '
        f'review required: {summary["review_required"]}; '
        f'excluded by movement: {summary["excluded"]}.'
    )
    print(f'Validation status: {summary["validation_status"]}.')
    print(f'Created categorised output: {output_path}')
    print(f'Created classification review: {review_path}')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Identify merchants and categorise eligible expenditure'
    )
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--review', required=True, type=Path)
    parser.add_argument('--categories', type=Path, default=DEFAULT_CATEGORIES)
    parser.add_argument('--rules', type=Path, default=DEFAULT_RULES)
    parser.add_argument(
        '--corrections', type=Path,
        default=Path('data/private/classification_corrections.csv'),
        help='private correction store used to retain imported decisions',
    )
    parser.add_argument(
        '--overwrite-review', action='store_true',
        help='replace a differing existing review file after manual inspection',
    )
    args = parser.parse_args(argv)
    try:
        summary = categorise_csv(
            args.input, args.output, args.review,
            args.categories, args.rules, args.overwrite_review,
            args.corrections,
        )
    except (OSError, CategoryValidationError, ValueError) as exc:
        parser.exit(1, f'error: {exc}\n')
    _print_summary(summary, args.output, args.review)


if __name__ == '__main__':
    main()
