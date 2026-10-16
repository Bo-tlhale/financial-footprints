"""Generate a validated analytical dataset from automatic and saved decisions."""

import argparse
import csv
import os
import tempfile
from pathlib import Path

from .category_validator import CategoryValidationError, load_category_hierarchy
from .review_manager import (
    DEFAULT_CATEGORIES,
    DEFAULT_CORRECTIONS,
    DEFAULT_SOURCE,
    _validate_category,
    _validate_store_bindings,
    load_categorised_source,
    load_correction_store,
)
from .transaction_classifier import NON_EXPENSE_MOVEMENTS
from src.preprocessing.transaction_validator import (
    OUTPUT_COLUMNS as PREPROCESSED_COLUMNS,
)

DEFAULT_OUTPUT = Path('data/private/curated_transactions.csv')
CURATED_COLUMNS = [
    *PREPROCESSED_COLUMNS,
    'automatic_merchant',
    'automatic_category',
    'automatic_subcategory',
    'classification_method',
    'classification_confidence',
    'automatic_review_required',
    'spending_classification_status',
    'final_merchant',
    'final_category',
    'final_subcategory',
    'classification_source',
    'review_status',
    'review_required',
]


def curate_records(source, corrections, hierarchy):
    source_by_id = {record['transaction_id']: record for record in source}
    _validate_store_bindings(corrections, source_by_id)
    output = []
    for row_number, record in enumerate(source, start=2):
        correction = corrections.get(record['transaction_id'])
        automatic = (
            record['clean_merchant'], record['category'], record['subcategory'],
        )
        if correction is None:
            final = automatic
            review_status = 'pending'
            if record['movement_type'] in NON_EXPENSE_MOVEMENTS:
                classification_source = 'automatic'
            else:
                classification_source = (
                    'unclassified' if not record['category']
                    or record['category'] == 'Uncategorised' else 'automatic'
                )
        else:
            final = (
                correction['reviewed_merchant'],
                correction['reviewed_category'],
                correction['reviewed_subcategory'],
            )
            review_status = correction['review_status']
            classification_source = {
                'approved': 'manual_approval',
                'corrected': 'manual_correction',
                'deferred': 'deferred',
            }[review_status]
        _validate_category(final[1], final[2], hierarchy, row_number)
        if record['movement_type'] in NON_EXPENSE_MOVEMENTS and (final[1] or final[2]):
            raise CategoryValidationError(
                f'row {row_number}: excluded movement has a spending category'
            )
        if review_status == 'deferred':
            unresolved = True
        elif record['movement_type'] in NON_EXPENSE_MOVEMENTS:
            unresolved = False
        else:
            unresolved = (
                record['movement_type'] == 'Unknown'
                or not final[1]
                or final[1] == 'Uncategorised'
                or (
                    correction is None
                    and record['category_review_required'] == 'True'
                )
            )
        curated = {
            field: record[field] for field in PREPROCESSED_COLUMNS
        }
        curated.update({
            'automatic_merchant': automatic[0],
            'automatic_category': automatic[1],
            'automatic_subcategory': automatic[2],
            'classification_method': record['classification_method'],
            'classification_confidence': record['classification_confidence'],
            'automatic_review_required': record['category_review_required'],
            'spending_classification_status': record['spending_classification_status'],
            'final_merchant': final[0],
            'final_category': final[1],
            'final_subcategory': final[2],
            'classification_source': classification_source,
            'review_status': review_status,
            'review_required': unresolved,
        })
        output.append(curated)
    return output


def validate_curated_records(source, curated, hierarchy):
    if len(source) != len(curated):
        raise CategoryValidationError('record count changed during curation')
    seen = set()
    for row_number, (original, output) in enumerate(zip(source, curated), start=2):
        if list(output) != CURATED_COLUMNS:
            raise CategoryValidationError(f'row {row_number}: invalid curated schema')
        for field in PREPROCESSED_COLUMNS:
            if output[field] != original[field]:
                raise CategoryValidationError(
                    f'row {row_number}: source field {field} changed during curation'
                )
        transaction_id = output['transaction_id']
        if transaction_id in seen:
            raise CategoryValidationError('duplicate curated transaction_id')
        seen.add(transaction_id)
        _validate_category(
            output['final_category'], output['final_subcategory'],
            hierarchy, row_number,
        )
        if not isinstance(output['review_required'], bool):
            raise CategoryValidationError(f'row {row_number}: invalid review flag')
    return {
        'processed': len(curated),
        'manual_approvals': sum(
            row['classification_source'] == 'manual_approval' for row in curated
        ),
        'manual_corrections': sum(
            row['classification_source'] == 'manual_correction' for row in curated
        ),
        'deferred': sum(row['classification_source'] == 'deferred' for row in curated),
        'review_required': sum(row['review_required'] for row in curated),
        'validation_status': 'passed',
    }


def _stage_csv(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', newline='', delete=False,
        dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp',
    )
    try:
        with temporary:
            writer = csv.DictWriter(temporary, fieldnames=CURATED_COLUMNS)
            writer.writeheader()
            writer.writerows(records)
        return Path(temporary.name)
    except Exception:
        Path(temporary.name).unlink(missing_ok=True)
        raise


def generate_curated_csv(
        input_path, corrections_path, output_path,
        categories_path=DEFAULT_CATEGORIES):
    paths = [Path(value).resolve() for value in (
        input_path, corrections_path, output_path,
    )]
    if len(set(paths)) != 3:
        raise CategoryValidationError(
            'categorised input, correction store and curated output paths must differ'
        )
    hierarchy = load_category_hierarchy(categories_path)
    source = load_categorised_source(input_path, hierarchy)
    corrections = load_correction_store(corrections_path, hierarchy)
    curated = curate_records(source, corrections, hierarchy)
    summary = validate_curated_records(source, curated, hierarchy)
    output_path = Path(output_path)
    staged = _stage_csv(output_path, curated)
    try:
        os.replace(staged, output_path)
    finally:
        staged.unlink(missing_ok=True)
    return summary


def _print_summary(summary, output_path):
    print(f'Processed {summary["processed"]} transactions.')
    print(
        f'Manual approvals: {summary["manual_approvals"]}; '
        f'manual corrections: {summary["manual_corrections"]}; '
        f'deferred: {summary["deferred"]}; '
        f'review required: {summary["review_required"]}.'
    )
    print(f'Validation status: {summary["validation_status"]}.')
    print(f'Created curated output: {output_path}')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Generate curated transactions from saved review decisions'
    )
    parser.add_argument('--input', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--corrections', type=Path, default=DEFAULT_CORRECTIONS)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--categories', type=Path, default=DEFAULT_CATEGORIES)
    args = parser.parse_args(argv)
    try:
        summary = generate_curated_csv(
            args.input, args.corrections, args.output, args.categories,
        )
    except (OSError, CategoryValidationError, ValueError) as exc:
        parser.exit(1, f'error: {exc}\n')
    _print_summary(summary, args.output)


if __name__ == '__main__':
    main()
