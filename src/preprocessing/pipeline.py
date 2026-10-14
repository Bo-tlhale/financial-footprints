"""CLI pipeline for transaction preprocessing and movement classification."""

import argparse
import csv
import os
import tempfile
from pathlib import Path

from .movement_classifier import classify_movement
from .transaction_cleaner import clean_record
from .transaction_validator import (
    OUTPUT_COLUMNS,
    TransactionValidationError,
    validate_output_records,
    validate_source_records,
    validate_source_schema,
)


def load_source(path):
    if not path.exists():
        raise TransactionValidationError(f'input file does not exist: {path}')
    if not path.is_file():
        raise TransactionValidationError(f'input path is not a file: {path}')
    with path.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        validate_source_schema(reader.fieldnames)
        records = list(reader)
    source_summary = validate_source_records(records)
    return records, source_summary


def preprocess_records(records):
    output = []
    for record in records:
        processed = clean_record(record)
        classification = classify_movement(processed)
        if not processed['cleaned_description']:
            classification['movement_review_required'] = True
        processed.update(classification)
        output.append(processed)
    return output


def _write_staged_csv(output_path, records):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', newline='', delete=False,
        dir=output_path.parent, prefix=f'.{output_path.name}.', suffix='.tmp',
    )
    try:
        with temporary:
            writer = csv.DictWriter(temporary, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(records)
        return Path(temporary.name)
    except Exception:
        Path(temporary.name).unlink(missing_ok=True)
        raise


def preprocess_csv(input_path, output_path):
    """Preprocess a consolidated CSV and atomically replace a validated output."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise TransactionValidationError('input and output paths must be different')
    source_records, source_summary = load_source(input_path)
    output_records = preprocess_records(source_records)
    validation_summary = validate_output_records(source_records, output_records)
    staged = _write_staged_csv(output_path, output_records)
    try:
        os.replace(staged, output_path)
    finally:
        staged.unlink(missing_ok=True)
    return {**source_summary, **validation_summary}


def _print_summary(summary, output_path):
    print(
        f'Processed {summary["input_records"]} transactions; '
        f'{summary["output_records"]} written.'
    )
    print(
        f'Review required: {summary["review_required"]}; '
        f'Unknown: {summary["unknown"]}; '
        f'missing descriptions: {summary["missing_descriptions"]}.'
    )
    counts = ', '.join(
        f'{name}={count}' for name, count in summary['movement_counts'].items()
    )
    print(f'Movement counts: {counts}')
    print(f'Created validated preprocessing output: {output_path}')


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Preprocess extracted transactions and classify movements'
    )
    parser.add_argument('--input', required=True, type=Path,
                        help='consolidated extractor CSV')
    parser.add_argument('--output', required=True, type=Path,
                        help='private preprocessed CSV output path')
    args = parser.parse_args(argv)
    try:
        summary = preprocess_csv(args.input, args.output)
    except (OSError, TransactionValidationError, ValueError) as exc:
        parser.exit(1, f'error: {exc}\n')
    _print_summary(summary, args.output)


if __name__ == '__main__':
    main()
