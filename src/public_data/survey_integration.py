"""Discovery, relationship validation and analytical-table preparation for IES."""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from .acquisition import sha256_file
from .expenditure_cleaner import ExpenditureDataError
from .pipeline import _replace_pair, prepare_expenditure


EXPECTED = {
    'geography': 'ies-2022-2023-geography-v1.2',
    'households': 'ies-2022-2023-households-v1.2',
    'person': 'ies-2022-2023-person-v1.2',
    'personincome': 'ies-2022-2023-personincome-v1.1',
    'total': 'ies-2022-2023-total-v1.2',
}

HOUSEHOLD_COLUMNS = [
    'UQNO', 'UQNO_NUM', 'OTHER_PERSONS', 'PRESENT_STATUS', 'HEAD_SEX',
    'HEAD_AGE', 'HEAD_POPULATION', 'HEAD_EDUCATION', 'HEAD_MARITAL', 'HSIZE',
    'HHOLD_WGT', 'EXPENDITURE', 'INCOME', 'EXPENDITURE_INKIND',
    'INCOME_INKIND', 'EXPENDITURE_WEIGHTED', 'INCOME_WEIGHTED',
    'EXPENDITURE_INKIND_WEIGHTED', 'INCOME_INKIND_WEIGHTED',
    'EXPENDITURE_PCP', 'INCOME_PCP', 'EXPENDITURE_DECILE',
    'EXPENDITURE_PCP_DECILE', 'EXPENDITURE_QUINTILE',
    'EXPENDITURE_PCP_QUINTILE', 'INCOME_DECILE', 'INCOME_PCP_DECILE',
    'INCOME_QUINTILE', 'INCOME_PCP_QUINTILE',
]

PERSON_COLUMNS = [
    'UQNO', 'UQNO_NUM', 'PERSON_ID', 'PERSONNO', 'SEX', 'AGE', 'POPULATION',
    'HHC_RELATIONSHIP', 'HHC_MARITAL', 'MAIN_SOURCE_INCOME', 'EDUCATION',
    'LAB_WGE', 'LAB_BUS', 'LAB_VOL', 'LAB_LOOK', 'LAB_START', 'LAB_ACCJOB',
    'LAB_SECTOR', 'PERSNS_WGT',
]

GEOGRAPHY_COLUMNS = [
    'UQNO', 'METRO_CODE', 'PROVINCE', 'SETTLEMENT_TYPE', 'SURVEYDATE',
]


def discover_sources(input_dir):
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise ExpenditureDataError(f'public input directory does not exist: {input_dir}')
    files = [path for path in input_dir.rglob('*') if path.is_file()]
    result = {}
    for key, stem in EXPECTED.items():
        matches = [path for path in files
                   if path.stem.lower() == stem and path.suffix.lower() in {'.dta', '.csv'}]
        if not matches:
            raise ExpenditureDataError(f'missing official dataset: {stem}')
        hashes = {sha256_file(path) for path in matches}
        if len(hashes) > 1:
            raise ExpenditureDataError(f'conflicting duplicate downloads: {stem}')
        result[key] = sorted(matches, key=lambda path: (len(path.parts), str(path)))[-1]
    codebooks = [path for path in files
                 if path.suffix.lower() == '.xlsx' and 'coicop' in path.name.lower()]
    if not codebooks:
        raise ExpenditureDataError('missing official COICOP classification workbook')
    hashes = {sha256_file(path) for path in codebooks}
    if len(hashes) > 1:
        raise ExpenditureDataError('conflicting COICOP workbooks found')
    result['codebook'] = sorted(
        codebooks, key=lambda path: ('classifications' not in path.parts, str(path)))[0]
    return result


def _read_stata(path):
    if Path(path).suffix.lower() != '.dta':
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    return pd.read_stata(
        path, convert_categoricals=False, preserve_dtypes=True)


def _require_columns(frame, required, dataset):
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ExpenditureDataError(f'{dataset} is missing columns: {missing}')


def _frame_profile(frame, key_columns):
    missing = {column: int(count) for column, count in frame.isna().sum().items()}
    return {
        'row_count': int(len(frame)),
        'column_count': int(len(frame.columns)),
        'columns': list(frame.columns),
        'dtypes': {column: str(dtype) for column, dtype in frame.dtypes.items()},
        'missing_value_counts': missing,
        'exact_duplicate_rows': int(frame.duplicated().sum()),
        'duplicate_key_rows': int(frame.duplicated(key_columns, keep=False).sum()),
        'key_columns': key_columns,
    }


def _money_profile(frame, columns):
    result = {}
    for column in columns:
        values = pd.to_numeric(frame[column], errors='coerce')
        result[column] = {
            'missing': int(values.isna().sum()),
            'zero': int(values.eq(0).sum()),
            'negative': int(values.lt(0).sum()),
            'minimum': None if values.dropna().empty else float(values.min()),
            'maximum': None if values.dropna().empty else float(values.max()),
        }
    return result


def _write_csv(frame, path):
    frame.to_csv(path, index=False, lineterminator='\n')


def integrate_survey(input_dir, output_dir,
                     mapping_path='config/expenditure_mapping.yaml'):
    sources = discover_sources(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix='.ies-stage-', dir=output_dir.parent))
    try:
        geography = _read_stata(sources['geography'])
        households = _read_stata(sources['households'])
        persons = _read_stata(sources['person'])
        person_income = _read_stata(sources['personincome'])
        _require_columns(geography, GEOGRAPHY_COLUMNS, 'geography')
        _require_columns(households, HOUSEHOLD_COLUMNS, 'households')
        _require_columns(persons, PERSON_COLUMNS, 'person')
        _require_columns(
            person_income,
            ['PERSON_ID', 'COICOP', 'PINCOME_QUINTILE',
             'VALUEANNUALIZED_ADJ', 'VALUEANNUALIZED_ADJ_WGT'],
            'personincome')
        if geography['UQNO'].duplicated().any() or households['UQNO'].duplicated().any():
            raise ExpenditureDataError('geography and household UQNO values must be unique')
        if persons['PERSON_ID'].duplicated().any():
            raise ExpenditureDataError('person identifiers must be unique')

        household_ids = set(households['UQNO'])
        geography_ids = set(geography['UQNO'])
        person_household_ids = set(persons['UQNO'])
        missing_geography = household_ids - geography_ids
        missing_person_households = person_household_ids - household_ids
        if missing_geography or missing_person_households:
            raise ExpenditureDataError('household/person/geography keys do not have full coverage')
        person_ids = set(persons['PERSON_ID'])
        unmatched_income_ids = set(person_income['PERSON_ID']) - person_ids
        if unmatched_income_ids:
            raise ExpenditureDataError('person-income records contain unknown person identifiers')

        person_counts = persons.groupby('UQNO', sort=False).size().rename('PERSON_RECORD_COUNT')
        prepared_households = households[HOUSEHOLD_COLUMNS].merge(
            geography[GEOGRAPHY_COLUMNS], on='UQNO', how='left', validate='one_to_one')
        prepared_households = prepared_households.merge(
            person_counts.reset_index(), on='UQNO', how='left', validate='one_to_one')
        prepared_households['SINGLE_PERSON_HOUSEHOLD'] = (
            prepared_households['HSIZE'].eq(1))
        hsize_mismatches = int(
            prepared_households['HSIZE'].ne(
                prepared_households['PERSON_RECORD_COUNT']).sum())

        prepared_persons = persons[PERSON_COLUMNS].merge(
            geography[GEOGRAPHY_COLUMNS], on='UQNO', how='left',
            validate='many_to_one')
        income_with_household = person_income.merge(
            persons[['PERSON_ID', 'UQNO']], on='PERSON_ID', how='left',
            validate='many_to_one')

        household_path = stage_dir / 'ies_2022_2023_households.csv'
        person_path = stage_dir / 'ies_2022_2023_persons.csv'
        income_path = stage_dir / 'ies_2022_2023_person_income.csv'
        expenditure_path = stage_dir / 'ies_2022_2023_expenditure.csv'
        expenditure_report_path = stage_dir / 'expenditure_report.json'
        _write_csv(prepared_households, household_path)
        _write_csv(prepared_persons, person_path)
        _write_csv(income_with_household, income_path)
        expenditure_report = prepare_expenditure(
            sources['total'], sources['codebook'], expenditure_path,
            expenditure_report_path, sources['geography'], mapping_path, '1.2')

        file_profiles = {
            'geography': _frame_profile(geography, ['UQNO']),
            'households': _frame_profile(households, ['UQNO']),
            'person': _frame_profile(persons, ['PERSON_ID']),
            'personincome': _frame_profile(person_income, ['PERSON_ID', 'COICOP']),
            'total': {
                **expenditure_report['profile'],
                'column_count': len(expenditure_report['source_schema']),
                'columns': expenditure_report['source_schema'],
            },
        }
        report = {
            'status': 'passed',
            'dataset': 'Stats SA Income and Expenditure Survey 2022/23',
            'catalog_reference': 'zaf-statssa-ies-2022-2023-v1.2',
            'source_files': {
                key: {'path': str(path), 'sha256': sha256_file(path),
                      'bytes': path.stat().st_size}
                for key, path in sources.items()
            },
            'discovered_files': [
                {
                    'path': str(path.relative_to(Path(input_dir))),
                    'bytes': path.stat().st_size,
                    'sha256': sha256_file(path),
                }
                for path in sorted(Path(input_dir).rglob('*'))
                if path.is_file() and path.name != '.gitkeep'
            ],
            'source_profiles': file_profiles,
            'relationships': {
                'households_without_geography': len(missing_geography),
                'person_households_without_household_record': len(missing_person_households),
                'person_income_ids_without_person_record': len(unmatched_income_ids),
                'household_size_person_count_mismatches': hsize_mismatches,
                'single_person_households': int(
                    prepared_households['SINGLE_PERSON_HOUSEHOLD'].sum()),
                'join_policy': (
                    'Expenditure remains at expenditure-unit grain. Person records '
                    'are never joined to expenditure; geography joins many-to-one by UQNO.'),
            },
            'monetary_fields': {
                'households': _money_profile(households, [
                    'HHOLD_WGT', 'EXPENDITURE', 'INCOME',
                    'EXPENDITURE_WEIGHTED', 'INCOME_WEIGHTED']),
                'personincome': _money_profile(person_income, [
                    'VALUEANNUALIZED_ADJ', 'VALUEANNUALIZED_ADJ_WGT']),
                'total': expenditure_report['amount_semantics'],
            },
            'outputs': {
                key: {
                    'filename': path.name,
                    'bytes': path.stat().st_size,
                    'sha256': sha256_file(path),
                }
                for key, path in {
                    'expenditure': expenditure_path,
                    'households': household_path,
                    'persons': person_path,
                    'person_income': income_path,
                }.items()
            },
            'warnings': [
                'Coded values such as 8, 88 and 8888 are retained as published; they are not system-missing values.',
                'Weighted monetary fields are not safe to average directly.',
                'Single-person households remain survey households and are not equivalent to one bank account.',
            ],
        }
        report_path = stage_dir / 'ies_2022_2023_quality_report.json'
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        destinations = [
            (expenditure_path, output_dir / expenditure_path.name),
            (household_path, output_dir / household_path.name),
            (person_path, output_dir / person_path.name),
            (income_path, output_dir / income_path.name),
            (report_path, output_dir / report_path.name),
        ]
        _replace_pair(destinations)
        return report
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
