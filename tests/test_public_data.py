import csv
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
import pandas as pd
import yaml

from src.public_data.acquisition import (
    AcquisitionError, acquire_reference_files, extract_zip_archive,
)
from src.public_data.codebook import load_coicop_codebook
from src.public_data.expenditure_cleaner import ExpenditureDataError
from src.public_data.mapping import MappingError, load_mapping, map_expenditure
from src.public_data.pipeline import main as pipeline_main, prepare_expenditure
import src.public_data.pipeline as public_pipeline
from src.public_data.survey_integration import (
    HOUSEHOLD_COLUMNS, PERSON_COLUMNS, discover_sources, integrate_survey,
)


HEADERS = [
    'coicop', 'Data_Collection_Descriptions', 'CoicopType',
    'CoicopTypeDescription', 'Division', 'DivisionDescription', 'Group',
    'GroupDescription', 'Class', 'ClassDescription', 'Subclass',
    'SubclassDescription', 'SixthGroup', 'SixthGroupDescriptions',
]
CODE_ROWS = [
    ['01111100', 'Wheat', '1', 'Consumption', '01',
     'Food and non-alcoholic beverages', '011', 'Food', '0111', 'Cereals',
     '01111', 'Cereals', '011111', 'Wheat'],
    ['50111100', 'Salary', '3', 'Income', '50', 'Income', '501',
     'Income from work', '5011', 'Income', '50111', 'Income', '501111', 'Salary'],
]


def write_codebook(path):
    strings = []
    indexes = {}
    for value in HEADERS + [value for row in CODE_ROWS for value in row]:
        if value not in indexes:
            indexes[value] = len(strings)
            strings.append(value)
    shared = ''.join(f'<si><t>{value}</t></si>' for value in strings)
    rows = []
    for number, values in enumerate([HEADERS, *CODE_ROWS], start=1):
        cells = []
        for index, value in enumerate(values):
            column = chr(ord('A') + index)
            cells.append(
                f'<c r="{column}{number}" t="s"><v>{indexes[value]}</v></c>')
        rows.append(f'<row r="{number}">{"".join(cells)}</row>')
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(
            'xl/sharedStrings.xml',
            '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'{shared}</sst>')
        archive.writestr(
            'xl/worksheets/sheet1.xml',
            '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(rows)}</sheetData></worksheet>')


def write_csv(path, fieldnames, rows):
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_integrated_stata_fixture(root):
    for name in ('geography', 'households', 'person', 'personincome', 'total',
                 'classifications', 'documentation'):
        (root / name).mkdir(parents=True, exist_ok=True)
    uqno = '160100330000009401'
    person_id = f'{uqno}01'
    pd.DataFrame([{
        'UQNO': uqno, 'UQNO_NUM': 1, 'METRO_CODE': 1, 'PROVINCE': 1,
        'SETTLEMENT_TYPE': 1, 'SURVEYDATE': 4122022,
    }]).to_stata(root / 'geography' / 'ies-2022-2023-geography-v1.2.dta',
                 write_index=False, version=118)
    household = {column: 0 for column in HOUSEHOLD_COLUMNS}
    household.update({
        'UQNO': uqno, 'UQNO_NUM': 1, 'HSIZE': 1, 'HHOLD_WGT': 2.0,
        'EXPENDITURE': 100.0, 'INCOME': 200.0,
        'EXPENDITURE_WEIGHTED': 200.0, 'INCOME_WEIGHTED': 400.0,
    })
    pd.DataFrame([household]).to_stata(
        root / 'households' / 'ies-2022-2023-households-v1.2.dta',
        write_index=False, version=118)
    person = {column: 0 for column in PERSON_COLUMNS}
    person.update({
        'UQNO': uqno, 'UQNO_NUM': 1, 'PERSON_ID': person_id,
        'PERSONNO': 1, 'AGE': 30, 'PERSNS_WGT': 2.0,
    })
    pd.DataFrame([person]).to_stata(
        root / 'person' / 'ies-2022-2023-person-v1.2.dta',
        write_index=False, version=118)
    pd.DataFrame([{
        'PERSON_ID': person_id, 'COICOP': 50111100, 'PINCOME_QUINTILE': 3,
        'VALUEANNUALIZED_ADJ': 200.0, 'VALUEANNUALIZED_ADJ_WGT': 400.0,
    }]).to_stata(
        root / 'personincome' / 'ies-2022-2023-personincome-v1.1.dta',
        write_index=False, version=118)
    pd.DataFrame([{
        'UQNO': uqno, 'UQNO_NUM': 1, 'coicop': 1111100,
        'coicoptype': 1, 'division': 1, 'group': 11, '_class': 111,
        'subclass': 1111, 'sixthgroup': 11111,
        'valueannualized_adj': 100.0, 'valueannualized_adj_wgt': 200.0,
    }]).to_stata(root / 'total' / 'ies-2022-2023-total-v1.2.dta',
                 write_index=False, version=118)
    write_codebook(root / 'classifications' / 'IES2023_COICOP.xlsx')


def total_row(**changes):
    row = {
        'UQNO': '160100330000009401', 'UQNO_NUM': '1', 'coicop': '01111100',
        'coicoptype': '1', 'division': '01', 'group': '011', 'class': '0111',
        'subclass': '01111', 'sixthgroup': '011111',
        'valueannualized_adj': '1200.00', 'valueannualized_adj_wgt': '720000.00',
    }
    row.update(changes)
    return row


@pytest.fixture
def public_inputs(tmp_path):
    codebook = tmp_path / 'codebook.xlsx'
    total = tmp_path / 'total.csv'
    geography = tmp_path / 'geography.csv'
    write_codebook(codebook)
    write_csv(total, list(total_row()), [total_row(), total_row(valueannualized_adj='0')])
    write_csv(geography, ['UQNO', 'METRO_CODE', 'PROVINCE', 'SETTLEMENT_TYPE', 'SURVEYDATE'], [{
        'UQNO': '160100330000009401', 'METRO_CODE': '1', 'PROVINCE': 'Gauteng',
        'SETTLEMENT_TYPE': 'Urban', 'SURVEYDATE': '20230501',
    }])
    return total, geography, codebook


def test_official_codebook_structure_is_read_without_external_xlsx_dependency(tmp_path):
    path = tmp_path / 'codebook.xlsx'
    write_codebook(path)
    records = load_coicop_codebook(path)
    assert records['01111100']['division_description'] == 'Food and non-alcoholic beverages'
    assert records['50111100']['coicop_type_description'] == 'Income'


def test_repeated_codebook_code_with_same_hierarchy_retains_both_labels(tmp_path):
    path = tmp_path / 'codebook.xlsx'
    CODE_ROWS.append(['01111100', 'Other wheat label', *CODE_ROWS[0][2:]])
    try:
        write_codebook(path)
    finally:
        CODE_ROWS.pop()
    records = load_coicop_codebook(path)
    assert records['01111100']['item_description'] == 'Wheat / Other wheat label'


def test_mapping_is_conservative_and_non_consumption_is_unmapped():
    mapping = load_mapping()
    food = map_expenditure({'division': '01', 'group': '011'}, mapping)
    income = map_expenditure({'division': '50', 'group': '501'}, mapping)
    assert (food['personal_category'], food['comparability']) == (
        'Groceries', 'adjustment_required')
    assert income['personal_category'] == ''
    assert income['comparability'] == 'not_comparable'


def test_more_specific_mapping_rule_wins_stably():
    mapping = load_mapping()
    record = {'division': '08', 'group': '082', 'class': '0820',
              'subclass': '08200', 'coicop': '08200000'}
    assert map_expenditure(record, mapping)['mapping_rule_id'] == 'software'
    assert map_expenditure(record, mapping) == map_expenditure(record, mapping)


def test_invalid_mapping_configuration_is_rejected(tmp_path):
    path = tmp_path / 'mapping.yaml'
    path.write_text('version: 1\nrules: [{id: broken}]\n', encoding='utf-8')
    with pytest.raises(MappingError):
        load_mapping(path)


def test_duplicate_mapping_selector_is_rejected(tmp_path):
    source = yaml.safe_load(Path('config/expenditure_mapping.yaml').read_text())
    source['rules'].append({**source['rules'][0], 'id': 'duplicate_selector'})
    path = tmp_path / 'mapping.yaml'
    path.write_text(yaml.safe_dump(source), encoding='utf-8')
    with pytest.raises(MappingError, match='duplicate mapping selector'):
        load_mapping(path)


def test_pipeline_preserves_zero_reports_duplicates_and_joins_geography(public_inputs, tmp_path):
    total, geography, codebook = public_inputs
    output, report = tmp_path / 'output.csv', tmp_path / 'report.json'
    result = prepare_expenditure(total, codebook, output, report, geography)
    assert result['profile']['row_count'] == 2
    assert result['profile']['household_count'] == 1
    assert result['profile']['zero_adjusted_values'] == 1
    assert result['profile']['duplicate_household_coicop_rows'] == 1
    rows = list(csv.DictReader(output.open(encoding='utf-8')))
    assert rows[1]['valueannualized_adj'] == '0'
    assert rows[0]['valueannualized_adj_wgt'] == '720000.00'
    assert rows[0]['province'] == 'Gauteng'
    assert rows[0]['item_description'] == 'Wheat'
    assert json.loads(report.read_text())['inputs']['total']['sha256']
    assert result['source_schema'] == list(total_row())


def test_missing_amount_remains_missing(public_inputs, tmp_path):
    _, geography, codebook = public_inputs
    total = tmp_path / 'missing.csv'
    write_csv(total, list(total_row()), [total_row(valueannualized_adj='')])
    report = prepare_expenditure(
        total, codebook, tmp_path / 'out.csv', tmp_path / 'report.json', geography)
    row = next(csv.DictReader((tmp_path / 'out.csv').open(encoding='utf-8')))
    assert row['valueannualized_adj'] == ''
    assert report['profile']['missing_adjusted_values'] == 1


def test_missing_schema_and_household_identifier_are_rejected(public_inputs, tmp_path):
    _, geography, codebook = public_inputs
    total = tmp_path / 'bad-schema.csv'
    row = total_row()
    row.pop('valueannualized_adj_wgt')
    write_csv(total, list(row), [row])
    with pytest.raises(ExpenditureDataError, match='missing total expenditure columns'):
        prepare_expenditure(total, codebook, tmp_path / 'out.csv',
                            tmp_path / 'report.json', geography)
    write_csv(total, list(total_row()), [total_row(UQNO='')])
    with pytest.raises(ExpenditureDataError, match='uqno is missing'):
        prepare_expenditure(total, codebook, tmp_path / 'out.csv',
                            tmp_path / 'report.json', geography)


def test_pipeline_is_deterministic_and_cli_runs(public_inputs, tmp_path, capsys):
    total, geography, codebook = public_inputs
    first, first_report = tmp_path / 'first.csv', tmp_path / 'first.json'
    second, second_report = tmp_path / 'second.csv', tmp_path / 'second.json'
    prepare_expenditure(total, codebook, first, first_report, geography)
    pipeline_main([
        '--total', str(total), '--geography', str(geography),
        '--codebook', str(codebook), '--output', str(second),
        '--report', str(second_report),
    ])
    assert first.read_bytes() == second.read_bytes()
    first_json = json.loads(first_report.read_text(encoding='utf-8'))
    second_json = json.loads(second_report.read_text(encoding='utf-8'))
    first_json['inputs']['total']['path'] = second_json['inputs']['total']['path']
    assert first_json == second_json
    assert 'Processed 2 expenditure records' in capsys.readouterr().out


@pytest.mark.parametrize('field,value', [
    ('valueannualized_adj', '-1'), ('valueannualized_adj', 'NaN'),
    ('division', '02'),
])
def test_pipeline_rejects_invalid_financial_or_codebook_values(public_inputs, tmp_path, field, value):
    _, geography, codebook = public_inputs
    total = tmp_path / 'bad.csv'
    write_csv(total, list(total_row()), [total_row(**{field: value})])
    with pytest.raises(ExpenditureDataError):
        prepare_expenditure(total, codebook, tmp_path / 'out.csv',
                            tmp_path / 'report.json', geography)


def test_unknown_coicop_is_preserved_and_flagged(public_inputs, tmp_path):
    _, geography, codebook = public_inputs
    total = tmp_path / 'unknown.csv'
    write_csv(total, list(total_row()), [total_row(
        coicop='99999999', coicoptype='8', division='99', group='999',
        **{'class': '9999'}, subclass='99999', sixthgroup='999999')])
    report = prepare_expenditure(
        total, codebook, tmp_path / 'out.csv', tmp_path / 'report.json', geography)
    row = next(csv.DictReader((tmp_path / 'out.csv').open(encoding='utf-8')))
    assert row['coicop'] == '99999999'
    assert row['codebook_match_status'] == 'code_absent_from_codebook'
    assert report['profile']['codebook_exception_codes'] == ['99999999']


def test_geography_join_must_be_complete(public_inputs, tmp_path):
    total, _, codebook = public_inputs
    geography = tmp_path / 'empty-match.csv'
    write_csv(geography, ['UQNO', 'METRO_CODE', 'PROVINCE', 'SETTLEMENT_TYPE', 'SURVEYDATE'], [{
        'UQNO': 'other', 'METRO_CODE': '', 'PROVINCE': 'X',
        'SETTLEMENT_TYPE': 'X', 'SURVEYDATE': '20230101'}])
    with pytest.raises(ExpenditureDataError, match='did not match geography'):
        prepare_expenditure(total, codebook, tmp_path / 'out.csv',
                            tmp_path / 'report.json', geography)


def test_missing_source_file_fails_clearly(public_inputs, tmp_path):
    _, geography, codebook = public_inputs
    with pytest.raises(ExpenditureDataError, match='required input file'):
        prepare_expenditure(tmp_path / 'missing.csv', codebook,
                            tmp_path / 'out.csv', tmp_path / 'report.json',
                            geography)


def test_failed_pipeline_does_not_replace_existing_outputs(public_inputs, tmp_path):
    _, geography, codebook = public_inputs
    total = tmp_path / 'bad.csv'
    write_csv(total, list(total_row()), [total_row(valueannualized_adj='bad')])
    output, report = tmp_path / 'output.csv', tmp_path / 'report.json'
    output.write_text('old output', encoding='utf-8')
    report.write_text('old report', encoding='utf-8')
    with pytest.raises(ExpenditureDataError):
        prepare_expenditure(total, codebook, output, report, geography)
    assert output.read_text(encoding='utf-8') == 'old output'
    assert report.read_text(encoding='utf-8') == 'old report'


def test_paired_output_replacement_rolls_back_on_second_failure(
        public_inputs, tmp_path, monkeypatch):
    total, geography, codebook = public_inputs
    output, report = tmp_path / 'output.csv', tmp_path / 'report.json'
    output.write_text('old output', encoding='utf-8')
    report.write_text('old report', encoding='utf-8')
    real_replace = public_pipeline.os.replace
    calls = 0

    def fail_second(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError('simulated report replacement failure')
        real_replace(source, destination)

    monkeypatch.setattr(public_pipeline.os, 'replace', fail_second)
    with pytest.raises(OSError, match='simulated'):
        prepare_expenditure(total, codebook, output, report, geography)
    assert output.read_text(encoding='utf-8') == 'old output'
    assert report.read_text(encoding='utf-8') == 'old report'


def test_acquisition_verifies_hash_and_reuses_verified_file(tmp_path):
    payload = b'official reference bytes'
    digest = hashlib.sha256(payload).hexdigest()
    manifest = tmp_path / 'sources.yaml'
    manifest.write_text(yaml.safe_dump({
        'version': 1,
        'public_reference_files': {'metadata': {
            'url': 'https://example.invalid/file', 'filename': 'file.pdf',
            'sha256': digest,
        }},
    }), encoding='utf-8')

    class Response:
        def __init__(self):
            self.sent = False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, _size):
            if self.sent: return b''
            self.sent = True
            return payload

    calls = []
    def opener(url, timeout):
        calls.append((url, timeout))
        return Response()

    result = acquire_reference_files(tmp_path / 'raw', manifest, opener)
    assert result['metadata'].read_bytes() == payload
    acquire_reference_files(tmp_path / 'raw', manifest, opener)
    assert len(calls) == 1


def test_acquisition_rejects_bad_download_without_replacing_target(tmp_path):
    manifest = tmp_path / 'sources.yaml'
    manifest.write_text(yaml.safe_dump({
        'version': 1,
        'public_reference_files': {'metadata': {
            'url': 'https://example.invalid/file', 'filename': 'file.pdf',
            'sha256': '0' * 64,
        }},
    }), encoding='utf-8')

    class Response:
        def __init__(self):
            self.sent = False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, _size):
            if self.sent: return b''
            self.sent = True
            return b'wrong'

    with pytest.raises(AcquisitionError):
        acquire_reference_files(tmp_path / 'raw', manifest, lambda *_args, **_kwargs: Response())
    assert not (tmp_path / 'raw' / 'file.pdf').exists()


def test_interrupted_acquisition_leaves_no_partial_target(tmp_path):
    manifest = tmp_path / 'sources.yaml'
    manifest.write_text(yaml.safe_dump({
        'version': 1,
        'public_reference_files': {'metadata': {
            'url': 'https://example.invalid/file', 'filename': 'file.pdf',
            'sha256': hashlib.sha256(b'complete').hexdigest(),
        }},
    }), encoding='utf-8')

    class InterruptedResponse:
        calls = 0
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, _size):
            self.calls += 1
            if self.calls == 1:
                return b'partial'
            raise OSError('connection interrupted')

    with pytest.raises(OSError, match='interrupted'):
        acquire_reference_files(
            tmp_path / 'raw', manifest,
            lambda *_args, **_kwargs: InterruptedResponse())
    assert not (tmp_path / 'raw' / 'file.pdf').exists()


def test_archive_extraction_is_safe_and_idempotent(tmp_path):
    archive = tmp_path / 'download.zip'
    with zipfile.ZipFile(archive, 'w') as handle:
        handle.writestr('total/source.dta', b'official bytes')
    paths = extract_zip_archive(archive, tmp_path / 'raw')
    assert paths[0].read_bytes() == b'official bytes'
    assert extract_zip_archive(archive, tmp_path / 'raw') == paths


def test_archive_extraction_rejects_path_traversal(tmp_path):
    archive = tmp_path / 'unsafe.zip'
    with zipfile.ZipFile(archive, 'w') as handle:
        handle.writestr('../escape.dta', b'bad')
    with pytest.raises(AcquisitionError, match='unsafe archive member'):
        extract_zip_archive(archive, tmp_path / 'raw')
    assert not (tmp_path / 'escape.dta').exists()


def test_discovery_requires_every_official_dataset(tmp_path):
    with pytest.raises(ExpenditureDataError, match='missing official dataset'):
        discover_sources(tmp_path)


def test_stata_full_integration_discovers_relationships_and_restores_codes(tmp_path):
    raw = tmp_path / 'raw'
    output = tmp_path / 'processed'
    write_integrated_stata_fixture(raw)
    report = integrate_survey(raw, output)
    assert report['status'] == 'passed'
    assert report['relationships']['single_person_households'] == 1
    assert report['relationships']['household_size_person_count_mismatches'] == 0
    expenditure = next(csv.DictReader(
        (output / 'ies_2022_2023_expenditure.csv').open(encoding='utf-8')))
    assert expenditure['coicop'] == '01111100'
    assert expenditure['division'] == '01'
    assert expenditure['personal_category'] == 'Groceries'
    assert (output / 'ies_2022_2023_households.csv').is_file()
    assert (output / 'ies_2022_2023_persons.csv').is_file()
    assert (output / 'ies_2022_2023_person_income.csv').is_file()
