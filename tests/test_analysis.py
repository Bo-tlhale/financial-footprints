import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from src.analysis.metrics import weighted_mean, weighted_quantile
from src.analysis.personal_eda import analyse_personal, load_personal_data
from src.analysis.pipeline import run_personal
from src.analysis.public_eda import analyse_public
from src.analysis.visualisations import horizontal_share_chart


PERSONAL_COLUMNS = [
    'transaction_id', 'transaction_date', 'debit', 'credit', 'fee',
    'source_file', 'movement_type', 'final_merchant', 'final_category',
    'final_subcategory', 'classification_source', 'review_status',
    'review_required',
]


def write_csv(path, columns, rows):
    with Path(path).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def personal_rows():
    base = {
        'credit': '0.00', 'fee': '0.00', 'source_file': 'statement.pdf',
        'final_merchant': '', 'final_category': '', 'final_subcategory': '',
        'classification_source': 'automatic', 'review_status': 'pending',
        'review_required': 'False',
    }
    return [
        {**base, 'transaction_id': 'a', 'transaction_date': '2026-08-01',
         'debit': '100.00', 'movement_type': 'Purchase',
         'final_merchant': 'Synthetic Shop', 'final_category': 'Groceries',
         'final_subcategory': 'Supermarkets'},
        {**base, 'transaction_id': 'b', 'transaction_date': '2026-08-15',
         'debit': '50.00', 'movement_type': 'Purchase',
         'final_merchant': 'Unknown Shop', 'review_required': 'True'},
        {**base, 'transaction_id': 'c', 'transaction_date': '2026-08-16',
         'debit': '0.00', 'credit': '20.00', 'movement_type': 'Refund'},
        {**base, 'transaction_id': 'd', 'transaction_date': '2026-08-20',
         'debit': '0.00', 'fee': '2.00', 'movement_type': 'Bank Fee',
         'final_category': 'Financial Charges',
         'final_subcategory': 'Bank Fees'},
        {**base, 'transaction_id': 'e', 'transaction_date': '2026-08-21',
         'debit': '40.00', 'movement_type': 'Outgoing Transfer'},
        {**base, 'transaction_id': 'f', 'transaction_date': '2026-08-22',
         'debit': '0.00', 'credit': '40.00', 'movement_type': 'Reversal'},
    ]


def validation_report(path):
    Path(path).write_text(json.dumps({'statements': [{
        'period_start': '2026-08-01', 'period_end': '2026-08-31',
        'transactions': 6,
    }]}), encoding='utf-8')


def test_weighted_metrics():
    assert weighted_mean([10, 20], [1, 3]) == pytest.approx(17.5)
    assert weighted_quantile([10, 20, 30], [1, 2, 1], 0.5) == 20


def test_personal_spending_excludes_unresolved_and_movements(tmp_path):
    source = tmp_path / 'curated.csv'
    validation = tmp_path / 'validation.json'
    write_csv(source, PERSONAL_COLUMNS, personal_rows())
    validation_report(validation)
    result = analyse_personal(load_personal_data(source), validation)
    assert result['metrics']['identified_expenditure'] == '152.00'
    assert result['metrics']['unresolved_purchase_count'] == 1
    assert result['metrics']['unresolved_purchase_value'] == '50.00'
    assert result['metrics']['resolved_category_expenditure'] == '102.00'
    assert result['metrics']['eligible_expenditure_coverage_percent'] == 67.11
    assert result['category']['expenditure'].sum() == pytest.approx(102.0)
    assert result['category']['excluded_unresolved_purchase_count'].unique().tolist() == [1]
    assert result['category']['excluded_unresolved_purchase_value'].unique().tolist() == ['50.00']
    assert result['category']['eligible_expenditure_coverage_percent'].unique().tolist() == [67.11]
    assert result['metrics']['movement_counts']['Refund'] == 1
    assert result['metrics']['movement_counts']['Reversal'] == 1


def test_personal_partial_month_and_output_generation(tmp_path):
    source = tmp_path / 'curated.csv'
    validation = tmp_path / 'validation.json'
    write_csv(source, PERSONAL_COLUMNS, personal_rows())
    Path(validation).write_text(json.dumps({'statements': [{
        'period_start': '2026-08-10', 'period_end': '2026-08-25',
        'transactions': 6,
    }]}), encoding='utf-8')
    destination = tmp_path / 'private-report'
    run_personal(source, validation, destination)
    monthly = pd.read_csv(destination / 'monthly_expenditure.csv')
    assert monthly.loc[0, 'coverage'] == 'partial or gapped calendar month'
    assert (destination / 'personal_category_shares.png').stat().st_size > 0


def test_personal_coverage_excludes_statement_gaps(tmp_path):
    source = tmp_path / 'curated.csv'
    validation = tmp_path / 'validation.json'
    write_csv(source, PERSONAL_COLUMNS, personal_rows())
    validation.write_text(json.dumps({'statements': [
        {'period_start': '2026-08-01', 'period_end': '2026-08-10', 'transactions': 3},
        {'period_start': '2026-08-13', 'period_end': '2026-08-31', 'transactions': 3},
    ]}), encoding='utf-8')
    result = analyse_personal(load_personal_data(source), validation)
    assert result['metrics']['observed_days'] == 29
    assert result['metrics']['coverage_gaps'] == [{
        'gap_start': '2026-08-11', 'gap_end': '2026-08-12', 'days': 2,
    }]
    assert result['monthly'].loc[0, 'coverage'] == 'partial or gapped calendar month'


def public_fixture(tmp_path):
    households = pd.DataFrame([
        {'UQNO': 'A', 'HSIZE': 1, 'HHOLD_WGT': 1, 'EXPENDITURE': 150,
         'INCOME': 200, 'INCOME_QUINTILE': 1, 'PROVINCE': 7,
         'SETTLEMENT_TYPE': 1, 'SINGLE_PERSON_HOUSEHOLD': True},
        {'UQNO': 'B', 'HSIZE': 2, 'HHOLD_WGT': 3, 'EXPENDITURE': 200,
         'INCOME': 500, 'INCOME_QUINTILE': 2, 'PROVINCE': 1,
         'SETTLEMENT_TYPE': 1, 'SINGLE_PERSON_HOUSEHOLD': False},
        {'UQNO': 'C', 'HSIZE': 5, 'HHOLD_WGT': 2, 'EXPENDITURE': 100,
         'INCOME': 300, 'INCOME_QUINTILE': 1, 'PROVINCE': 7,
         'SETTLEMENT_TYPE': 2, 'SINGLE_PERSON_HOUSEHOLD': False},
    ])
    expenditure = pd.DataFrame([
        {'uqno': 'A', 'coicop_type': 1, 'division': 1,
         'division_description': 'Food and non-alcoholic beverages',
         'valueannualized_adj': 100, 'valueannualized_adj_wgt': 100,
         'comparability': 'adjustment_required', 'personal_category': 'Groceries'},
        {'uqno': 'A', 'coicop_type': 1, 'division': 7,
         'division_description': 'Transport', 'valueannualized_adj': 50,
         'valueannualized_adj_wgt': 50, 'comparability': 'adjustment_required',
         'personal_category': 'Transport'},
        {'uqno': 'B', 'coicop_type': 1, 'division': 1,
         'division_description': 'Food and non-alcoholic beverages',
         'valueannualized_adj': 200, 'valueannualized_adj_wgt': 600,
         'comparability': 'adjustment_required', 'personal_category': 'Groceries'},
        {'uqno': 'C', 'coicop_type': 1, 'division': 4,
         'division_description': '', 'valueannualized_adj': 100,
         'valueannualized_adj_wgt': 200, 'comparability': 'not_comparable',
         'personal_category': ''},
        {'uqno': 'C', 'coicop_type': 5, 'division': 50,
         'division_description': 'Income', 'valueannualized_adj': 999,
         'valueannualized_adj_wgt': 1998, 'comparability': 'not_comparable',
         'personal_category': ''},
    ])
    h_path = tmp_path / 'households.csv'
    e_path = tmp_path / 'expenditure.csv'
    q_path = tmp_path / 'quality.json'
    households.to_csv(h_path, index=False)
    expenditure.to_csv(e_path, index=False)
    q_path.write_text(json.dumps({'source_profiles': {
        'households': {'row_count': 3}, 'person': {'row_count': 8},
        'personincome': {'row_count': 4},
    }}), encoding='utf-8')
    return e_path, h_path, q_path


def test_public_household_aggregation_weighting_and_scopes(tmp_path):
    result = analyse_public(*public_fixture(tmp_path))
    metrics = result['metrics']
    assert metrics['verified_counts']['expenditure_records'] == 5
    assert metrics['readiness_checks']['ordinary_consumption_records'] == 4
    assert metrics['weighted_population_statistics']['mean_annual_expenditure'] == pytest.approx(158.333333)
    assert metrics['single_person_households']['sample_count'] == 1
    assert result['category']['weighted_share'].sum() == pytest.approx(1.0)
    assert set(result['category']['division']) == {1, 4, 7}
    assert result['metrics']['comparison_readiness']['nominal_amount_comparison_supported'] is False


def test_chart_handles_empty_data(tmp_path):
    path = tmp_path / 'empty.png'
    horizontal_share_chart(
        pd.DataFrame(columns=['label', 'share']), 'label', 'share',
        'Empty chart', path)
    assert path.stat().st_size > 0


def test_notebooks_are_output_free():
    for path in Path('notebooks').glob('*.ipynb'):
        notebook = json.loads(path.read_text(encoding='utf-8'))
        for cell in notebook.get('cells', []):
            assert cell.get('outputs', []) == []
            assert cell.get('execution_count') is None
