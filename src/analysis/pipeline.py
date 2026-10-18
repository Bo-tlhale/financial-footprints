"""Command-line orchestration for private and public exploratory analysis."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from .personal_eda import PersonalAnalysisError, analyse_personal, load_personal_data
from .public_eda import PublicAnalysisError, analyse_public
from .visualisations import (
    comparison_bar, distribution_histogram, horizontal_share_chart, line_chart,
)


def _write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n',
        encoding='utf-8')


def _publish(stage, destination):
    destination = Path(destination)
    backup = destination.with_name(f'.{destination.name}.backup')
    if backup.exists():
        shutil.rmtree(backup)
    try:
        if destination.exists():
            os.replace(destination, backup)
        os.replace(stage, destination)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        if backup.exists():
            os.replace(backup, destination)
        raise


def _stage(destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f'.{destination.name}-stage-', dir=destination.parent))


def run_personal(input_path, validation_path, destination):
    stage = _stage(destination)
    try:
        result = analyse_personal(load_personal_data(input_path), validation_path)
        _write_json(stage / 'personal_metrics.json', result['metrics'])
        for key, filename in {
            'movement': 'movement_summary.csv', 'category': 'category_summary.csv',
            'merchant': 'merchant_summary.csv', 'recurring': 'recurring_candidates.csv',
            'daily': 'daily_expenditure.csv', 'weekly': 'weekly_expenditure.csv',
            'monthly': 'monthly_expenditure.csv', 'day_type': 'weekday_weekend.csv',
        }.items():
            result[key].to_csv(stage / filename, index=False, lineterminator='\n')
        horizontal_share_chart(
            result['category'], 'final_category', 'share_of_resolved_expenditure',
            'Personal expenditure by resolved category\n'
            f'{result["metrics"]["eligible_expenditure_coverage_percent"]:.2f}% of eligible expenditure covered; '
            f'{result["metrics"]["unresolved_purchase_count"]} unresolved purchases '
            f'(R{float(result["metrics"]["unresolved_purchase_value"]):,.2f}) excluded',
            stage / 'personal_category_shares.png')
        line_chart(
            result['weekly'], 'week_start', 'spend_amount',
            'Identified expenditure by week', 'Expenditure (rand)',
            stage / 'personal_weekly_expenditure.png')
        comparison_bar(
            result['day_type'], 'day_type', 'expenditure',
            'Weekday and weekend identified expenditure', 'Expenditure (rand)',
            stage / 'personal_weekday_weekend.png')
        _publish(stage, destination)
        return result['metrics']
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def run_public(expenditure_path, households_path, quality_path, destination):
    stage = _stage(destination)
    try:
        result = analyse_public(expenditure_path, households_path, quality_path)
        _write_json(stage / 'public_metrics.json', result['metrics'])
        for key, filename in {
            'category': 'coicop_division_summary.csv',
            'composition': 'household_size_summary.csv',
            'single_category': 'single_person_category_summary.csv',
            'province': 'province_summary.csv',
            'income': 'income_quintile_summary.csv',
        }.items():
            result[key].to_csv(stage / filename, index=False, lineterminator='\n')
        horizontal_share_chart(
            result['category'], 'division_description', 'weighted_share',
            'Weighted household consumption share by COICOP division',
            stage / 'coicop_division_shares.png')
        distribution_histogram(
            result['households']['ordinary_expenditure'],
            'Sample distribution of annual household consumption',
            'Annual ordinary consumption (rand, May 2023 prices)',
            stage / 'household_expenditure_distribution.png')
        comparison_bar(
            result['composition'], 'household_size_group',
            'weighted_median_annual_expenditure',
            'Weighted median consumption by household size',
            'Annual ordinary consumption (rand)',
            stage / 'household_size_expenditure.png')
        comparison_bar(
            result['province'], 'province_name',
            'weighted_median_annual_expenditure',
            'Weighted median consumption by province',
            'Annual ordinary consumption (rand)',
            stage / 'province_expenditure.png')
        comparison_bar(
            result['income'], 'INCOME_QUINTILE',
            'weighted_mean_annual_expenditure',
            'Weighted mean consumption by published income quintile',
            'Annual ordinary consumption (rand)',
            stage / 'income_quintile_expenditure.png')
        _publish(stage, destination)
        return result['metrics']
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run Financial Footprints EDA')
    parser.add_argument('--track', choices=('personal', 'public', 'all'), default='all')
    parser.add_argument('--personal-input', type=Path, default=Path('data/private/curated_transactions.csv'))
    parser.add_argument('--validation', type=Path, default=Path('data/private/validation.json'))
    parser.add_argument('--public-input', type=Path, default=Path('data/public/processed'))
    parser.add_argument('--reports', type=Path, default=Path('reports'))
    args = parser.parse_args(argv)
    try:
        if args.track in {'personal', 'all'}:
            metrics = run_personal(
                args.personal_input, args.validation, args.reports / 'private')
            print(
                f'Personal EDA completed for {metrics["transaction_count"]} transactions; '
                f'{metrics["unresolved_purchase_count"]} unresolved purchases '
                f'(R{float(metrics["unresolved_purchase_value"]):,.2f}) remain outside category findings; '
                f'{metrics["eligible_expenditure_coverage_percent"]:.2f}% of eligible expenditure is covered.')
            print(f'Private outputs: {args.reports / "private"}')
        if args.track in {'public', 'all'}:
            metrics = run_public(
                args.public_input / 'ies_2022_2023_expenditure.csv',
                args.public_input / 'ies_2022_2023_households.csv',
                args.public_input / 'ies_2022_2023_quality_report.json',
                args.reports / 'public')
            counts = metrics['verified_counts']
            print(
                f'Public EDA completed for {counts["households"]} households and '
                f'{counts["expenditure_records"]} expenditure records.')
            print(f'Public outputs: {args.reports / "public"}')
    except (OSError, ValueError, PersonalAnalysisError, PublicAnalysisError) as exc:
        parser.exit(1, f'error: {exc}\n')


if __name__ == '__main__':
    main()
