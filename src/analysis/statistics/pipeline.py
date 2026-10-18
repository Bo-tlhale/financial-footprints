"""Reproducible Checkpoint 7 statistical-analysis command line."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ..pipeline import _publish, _stage
from .modelling import fit_expenditure_model
from .personal_statistics import analyse_personal_statistics
from .survey_statistics import analyse_survey_statistics
from .visualisations import calibration_chart, grouped_bar, lorenz_chart, personal_distribution
from ..visualisations import comparison_bar, horizontal_share_chart, line_chart


def _json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def run_personal(input_path, validation_path, destination):
    stage = _stage(destination)
    try:
        result = analyse_personal_statistics(input_path, validation_path)
        _json(stage / 'personal_statistics.json', result['metrics'])
        for key, name in {'categories': 'category_concentration.csv', 'merchants': 'merchant_concentration.csv',
                          'daily': 'daily_purchase_expenditure.csv', 'unusual': 'unusual_observations.csv',
                          'recurring': 'recurring_evidence.csv'}.items():
            result[key].to_csv(stage / name, index=False, lineterminator='\n')
        personal_distribution(result['daily']['purchase_expenditure'], 'Daily purchase expenditure over all covered days', stage / 'daily_purchase_distribution.png')
        coverage = result['metrics']['classification_coverage']
        horizontal_share_chart(
            result['categories'], 'final_category', 'share',
            'Resolved eligible expenditure concentration\n'
            f'{coverage["eligible_expenditure_coverage_percent"]:.2f}% covered; '
            f'{coverage["excluded_unresolved_purchase_count"]} unresolved purchases '
            f'(R{coverage["excluded_unresolved_purchase_value"]:,.2f}) excluded',
            stage / 'category_concentration.png')
        counts = result['recurring']['classification'].value_counts().rename_axis('classification').reset_index(name='count')
        comparison_bar(counts, 'classification', 'count', 'Recurring-payment evidence', 'Merchant patterns', stage / 'recurring_evidence.png')
        _publish(stage, destination)
        return result['metrics']
    finally:
        if stage.exists(): shutil.rmtree(stage)


def _public_analysis(public_input):
    return analyse_survey_statistics(public_input / 'ies_2022_2023_expenditure.csv',
                                     public_input / 'ies_2022_2023_households.csv',
                                     public_input / 'ies_2022_2023_quality_report.json')


def run_public(public_input, destination):
    stage = _stage(destination)
    try:
        result = _public_analysis(Path(public_input))
        _json(stage / 'public_statistics.json', result['statistics_metrics'])
        for key, name in {'lorenz': 'lorenz_curve.csv', 'size_statistics': 'household_size_statistics.csv',
                          'province_statistics': 'province_statistics.csv', 'income_statistics': 'income_group_statistics.csv',
                          'income_composition': 'income_group_composition.csv', 'province_composition': 'province_composition.csv'}.items():
            result[key].to_csv(stage / name, index=False, lineterminator='\n')
        lorenz_chart(result['lorenz'], stage / 'weighted_lorenz_curve.png')
        comparison_bar(result['size_statistics'], 'household_size_group', 'weighted_median_total',
                       'Weighted median consumption by household size', 'Annual rand', stage / 'household_size_distribution.png')
        comparison_bar(result['province_statistics'], 'province_name', 'weighted_median_total',
                       'Weighted median consumption by province', 'Annual rand', stage / 'province_distribution.png')
        grouped_bar(result['income_composition'], 'INCOME_QUINTILE', 'division_description', 'weighted_share',
                    'Largest consumption shares by income quintile', stage / 'income_composition.png')
        grouped_bar(result['province_composition'], 'province_name', 'division_description', 'weighted_share',
                    'Largest consumption shares by province', stage / 'province_composition.png')
        _publish(stage, destination)
        return result['statistics_metrics']
    finally:
        if stage.exists(): shutil.rmtree(stage)


def run_modelling(public_input, destination):
    stage = _stage(destination)
    try:
        survey = _public_analysis(Path(public_input))
        result = fit_expenditure_model(survey['households'])
        _json(stage / 'model_summary.json', {'metadata': result['metadata'], 'diagnostics': result['diagnostics']})
        result['coefficients'].to_csv(stage / 'model_coefficients.csv', index=False, lineterminator='\n')
        result['stability'].to_csv(stage / 'coefficient_stability.csv', index=False, lineterminator='\n')
        result['calibration'].to_csv(stage / 'model_calibration.csv', index=False, lineterminator='\n')
        calibration_chart(result['calibration'], stage / 'model_calibration.png')
        _publish(stage, destination)
        return result['diagnostics']
    finally:
        if stage.exists(): shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run Checkpoint 7 statistical analysis')
    parser.add_argument('--track', choices=('personal', 'public', 'modelling', 'all'), default='all')
    parser.add_argument('--personal-input', type=Path, default=Path('data/private/curated_transactions.csv'))
    parser.add_argument('--validation', type=Path, default=Path('data/private/validation.json'))
    parser.add_argument('--public-input', type=Path, default=Path('data/public/processed'))
    parser.add_argument('--reports', type=Path, default=Path('reports'))
    args = parser.parse_args(argv)
    try:
        if args.track in {'personal', 'all'}:
            metrics = run_personal(args.personal_input, args.validation, args.reports / 'private' / 'statistics')
            coverage = metrics['classification_coverage']
            print(f'Personal statistics complete: {coverage["excluded_unresolved_purchase_count"]} unresolved purchases '
                  f'(R{coverage["excluded_unresolved_purchase_value"]:,.2f}) excluded; '
                  f'{coverage["eligible_expenditure_coverage_percent"]:.2f}% value coverage. Private output written.')
        if args.track in {'public', 'all'}:
            metrics = run_public(args.public_input, args.reports / 'public' / 'statistics')
            print(f'Public weighted statistics complete for {metrics["validation"]["sample_households"]} households.')
        if args.track in {'modelling', 'all'}:
            diagnostics = run_modelling(args.public_input, args.reports / 'public' / 'statistics_model')
            print(f'Exploratory model complete for {diagnostics["sample_households"]} households; no inferential uncertainty reported.')
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'error: {exc}\n')


if __name__ == '__main__':
    main()
