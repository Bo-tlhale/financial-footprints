"""Validation rules for public expenditure preparation."""

from pathlib import Path

from .expenditure_cleaner import ExpenditureDataError


def validate_paths(total_path, codebook_path, output_path, report_path,
                   geography_path=None):
    inputs = [Path(total_path), Path(codebook_path)]
    if geography_path is not None:
        inputs.append(Path(geography_path))
    for path in inputs:
        if not path.is_file():
            raise ExpenditureDataError(f'required input file does not exist: {path}')
    destinations = [Path(output_path), Path(report_path)]
    resolved = [path.resolve() for path in inputs + destinations]
    if len(resolved) != len(set(resolved)):
        raise ExpenditureDataError('input and output paths must all be different')


def validate_profile(profile, geography_supplied):
    if profile['row_count'] == 0:
        raise ExpenditureDataError('total expenditure file contains no records')
    if profile['household_count'] == 0:
        raise ExpenditureDataError('no household identifiers were found')
    if geography_supplied and profile['missing_geography_rows']:
        raise ExpenditureDataError(
            f'{profile["missing_geography_rows"]} rows did not match geography data')
