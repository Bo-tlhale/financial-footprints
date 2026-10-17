"""CLI pipeline for reproducible IES 2022/23 expenditure preparation."""

import argparse
import csv
import json
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from .acquisition import sha256_file
from .codebook import CodebookError, load_coicop_codebook
from .data_profiler import ExpenditureProfiler
from .expenditure_cleaner import (
    OUTPUT_COLUMNS, ExpenditureDataError, clean_row, resolve_schema,
)
from .expenditure_validator import validate_paths, validate_profile
from .mapping import MappingError, load_mapping


def _normalise_header(name):
    return name.strip().lower().replace(' ', '_')


def _iter_source(path, chunksize=50_000):
    path = Path(path)
    if path.suffix.lower() == '.csv':
        handle = path.open(encoding='utf-8-sig', newline='')
        reader = csv.DictReader(handle)
        try:
            yield list(reader.fieldnames or []), reader
        finally:
            handle.close()
        return
    if path.suffix.lower() != '.dta':
        raise ExpenditureDataError(f'unsupported source format: {path.suffix}')
    reader = pd.read_stata(
        path, iterator=True, chunksize=chunksize,
        convert_categoricals=False, preserve_dtypes=True)
    first = True
    try:
        for frame in reader:
            columns = list(frame.columns)
            rows = frame.to_dict(orient='records')
            yield columns if first else None, rows
            first = False
    finally:
        reader._close_file()


def load_geography(path):
    if path is None:
        return {}
    aliases = {
        'uqno': {'uqno'}, 'province': {'province'}, 'metro_code': {'metro_code'},
        'settlement_type': {'settlement_type'}, 'survey_date': {'surveydate', 'survey_date'},
    }
    result = {}
    source_chunks = _iter_source(path)
    saw_rows = False
    for fieldnames, reader in source_chunks:
        if fieldnames is not None:
            normalized = {_normalise_header(name): name for name in fieldnames}
            schema = {}
            for field, names in aliases.items():
                found = [normalized[name] for name in names if name in normalized]
                if found:
                    schema[field] = found[0]
            if set(aliases) - schema.keys():
                raise ExpenditureDataError(
                    f'missing geography columns: {sorted(set(aliases) - schema.keys())}')
        for raw in reader:
            saw_rows = True
            row = {field: str(raw.get(source, '')).strip() for field, source in schema.items()}
            row = {field: ('' if value in {'nan', '<NA>'} else value)
                   for field, value in row.items()}
            if not row['uqno'] or row['uqno'] in result:
                raise ExpenditureDataError('geography uqno values must be present and unique')
            result[row['uqno']] = row
    if not saw_rows:
        raise ExpenditureDataError('geography file contains no records')
    return result


def _stage_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', newline='\n', delete=False,
        dir=path.parent, prefix=f'.{path.name}.', suffix='.tmp')
    try:
        with handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write('\n')
        return Path(handle.name)
    except Exception:
        Path(handle.name).unlink(missing_ok=True)
        raise


def _replace_pair(pairs):
    backups = []
    replaced = []
    try:
        for _, destination in pairs:
            backup = None
            if destination.exists():
                handle = tempfile.NamedTemporaryFile(
                    delete=False, dir=destination.parent,
                    prefix=f'.{destination.name}.', suffix='.backup')
                handle.close()
                backup = Path(handle.name)
                shutil.copy2(destination, backup)
            backups.append((destination, backup))
        for staged, destination in pairs:
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
        for staged, _ in pairs:
            staged.unlink(missing_ok=True)


def prepare_expenditure(total_path, codebook_path, output_path, report_path,
                        geography_path=None,
                        mapping_path='config/expenditure_mapping.yaml',
                        source_version='1.2'):
    total_path, codebook_path = Path(total_path), Path(codebook_path)
    output_path, report_path = Path(output_path), Path(report_path)
    geography_path = Path(geography_path) if geography_path else None
    validate_paths(total_path, codebook_path, output_path, report_path, geography_path)
    codebook = load_coicop_codebook(codebook_path)
    mapping = load_mapping(mapping_path)
    geography = load_geography(geography_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staged = tempfile.NamedTemporaryFile(
        mode='w', encoding='utf-8', newline='', delete=False,
        dir=output_path.parent, prefix=f'.{output_path.name}.', suffix='.tmp')
    staged_path = Path(staged.name)
    profiler = ExpenditureProfiler()
    staged_report = None
    try:
        source_columns = None
        with staged:
            writer = csv.DictWriter(staged, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            line_number = 1
            for columns, rows in _iter_source(total_path):
                if columns is not None:
                    source_columns = columns
                    schema = resolve_schema(columns)
                for raw in rows:
                    line_number += 1
                    try:
                        row = clean_row(raw, schema, codebook, mapping, geography)
                    except ExpenditureDataError as exc:
                        raise ExpenditureDataError(f'line {line_number}: {exc}') from exc
                    profiler.add(row)
                    writer.writerow(row)
        profile = profiler.report()
        validate_profile(profile, geography_path is not None)
        report = {
            'dataset': 'Stats SA Income and Expenditure Survey 2022/23',
            'source_version': str(source_version),
            'integration_status': 'official_microdata_processed',
            'inputs': {
                'total': {'path': str(total_path), 'sha256': sha256_file(total_path)},
                'codebook': {'path': str(codebook_path), 'sha256': sha256_file(codebook_path)},
                'geography': None if geography_path is None else {
                    'path': str(geography_path), 'sha256': sha256_file(geography_path)},
            },
            'output_schema': OUTPUT_COLUMNS,
            'source_schema': source_columns,
            'field_types': {
                **{field: 'string' for field in OUTPUT_COLUMNS},
                'valueannualized_adj': 'decimal string',
                'valueannualized_adj_wgt': 'decimal string',
            },
            'profile': profile,
            'amount_semantics': {
                'valueannualized_adj': 'Annualised and CPI-adjusted to May 2023; unweighted.',
                'valueannualized_adj_wgt': 'Annualised, survey-weighted and CPI-adjusted to May 2023.',
                'aggregation_warning': 'Do not average weighted values or compare a household value directly with one person.',
            },
        }
        staged_report = _stage_json(report_path, report)
        _replace_pair([
            (staged_path, output_path),
            (staged_report, report_path),
        ])
        return report
    finally:
        staged_path.unlink(missing_ok=True)
        if staged_report is not None:
            staged_report.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Prepare Stats SA IES expenditure microdata')
    parser.add_argument(
        '--input', type=Path,
        help='organized public raw directory; discovers and integrates all five datasets')
    parser.add_argument('--total', type=Path)
    parser.add_argument('--geography', type=Path)
    parser.add_argument('--codebook', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--mapping', type=Path, default=Path('config/expenditure_mapping.yaml'))
    parser.add_argument('--source-version', default='1.2')
    args = parser.parse_args(argv)
    try:
        if args.input:
            if any((args.total, args.geography, args.codebook, args.report)):
                raise ExpenditureDataError(
                    '--input mode cannot be combined with individual source arguments')
            from .survey_integration import integrate_survey
            report = integrate_survey(args.input, args.output, args.mapping)
            profiles = report['source_profiles']
            print(
                f'Processed official IES files: total={profiles["total"]["row_count"]}, '
                f'households={profiles["households"]["row_count"]}, '
                f'persons={profiles["person"]["row_count"]}, '
                f'person income={profiles["personincome"]["row_count"]}.')
            print(f'Validation status: {report["status"]}.')
            print(f'Prepared public outputs: {args.output}')
            return
        if not all((args.total, args.codebook, args.report)):
            raise ExpenditureDataError(
                'provide --input for full integration, or --total, --codebook and --report')
        report = prepare_expenditure(
            args.total, args.codebook, args.output, args.report,
            args.geography, args.mapping, args.source_version)
    except (OSError, ExpenditureDataError, CodebookError, MappingError) as exc:
        parser.exit(1, f'error: {exc}\n')
    profile = report['profile']
    print(
        f'Processed {profile["row_count"]} expenditure records for '
        f'{profile["household_count"]} households.')
    print(f'Validation report: {args.report}')
    print(f'Prepared output: {args.output}')


if __name__ == '__main__':
    main()
