"""Survey-aware EDA for Stats SA IES 2022/23 household expenditure."""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import household_size_group, weighted_correlation, weighted_mean, weighted_quantile


PROVINCES = {
    1: 'Western Cape', 2: 'Eastern Cape', 3: 'Northern Cape',
    4: 'Free State', 5: 'KwaZulu-Natal', 6: 'North West',
    7: 'Gauteng', 8: 'Mpumalanga', 9: 'Limpopo',
}
DIVISIONS = {
    1: 'Food and non-alcoholic beverages',
    2: 'Alcoholic beverages, tobacco and narcotics',
    3: 'Clothing and footwear',
    4: 'Housing, water, electricity, gas and other fuels',
    5: 'Furnishings, household equipment and maintenance',
    6: 'Health', 7: 'Transport', 8: 'Information and communication',
    9: 'Recreation, sport and culture', 10: 'Education services',
    11: 'Restaurants and accommodation services',
    12: 'Insurance and financial services',
    13: 'Personal care, social protection and miscellaneous goods',
}
HOUSEHOLD_COLUMNS = [
    'UQNO', 'HSIZE', 'HHOLD_WGT', 'EXPENDITURE', 'INCOME',
    'INCOME_QUINTILE', 'PROVINCE', 'SETTLEMENT_TYPE',
    'SINGLE_PERSON_HOUSEHOLD',
]
EXPENDITURE_COLUMNS = [
    'uqno', 'coicop_type', 'division', 'division_description',
    'valueannualized_adj', 'valueannualized_adj_wgt', 'comparability',
    'personal_category',
]


class PublicAnalysisError(ValueError):
    """Raised when public EDA inputs fail schema or relationship checks."""


def _read_households(path) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise PublicAnalysisError(f'household dataset does not exist: {path}')
    frame = pd.read_csv(path, usecols=HOUSEHOLD_COLUMNS, dtype={'UQNO': str})
    if frame.empty or frame['UQNO'].duplicated().any():
        raise PublicAnalysisError('household dataset must contain one row per UQNO')
    for column in ('HSIZE', 'HHOLD_WGT', 'EXPENDITURE', 'INCOME', 'PROVINCE'):
        frame[column] = pd.to_numeric(frame[column], errors='raise')
    if frame['HHOLD_WGT'].le(0).any() or frame['HSIZE'].lt(1).any():
        raise PublicAnalysisError('household weights and sizes must be positive')
    frame['province_name'] = frame['PROVINCE'].map(PROVINCES)
    if frame['province_name'].isna().any():
        raise PublicAnalysisError('household data contains an unsupported province code')
    frame['household_size_group'] = frame['HSIZE'].map(household_size_group)
    return frame


def _aggregate_expenditure(path, chunksize=100_000):
    path = Path(path)
    if not path.is_file():
        raise PublicAnalysisError(f'expenditure dataset does not exist: {path}')
    household_parts, division_parts, mapped_parts = [], [], []
    all_rows = ordinary_rows = 0
    for chunk in pd.read_csv(
            path, usecols=EXPENDITURE_COLUMNS, dtype={'uqno': str},
            chunksize=chunksize):
        all_rows += len(chunk)
        chunk['coicop_type'] = pd.to_numeric(chunk['coicop_type'], errors='raise')
        ordinary = chunk[chunk['coicop_type'].eq(1)].copy()
        ordinary_rows += len(ordinary)
        ordinary['valueannualized_adj'] = pd.to_numeric(
            ordinary['valueannualized_adj'], errors='raise')
        ordinary['valueannualized_adj_wgt'] = pd.to_numeric(
            ordinary['valueannualized_adj_wgt'], errors='raise')
        if ordinary['valueannualized_adj'].lt(0).any():
            raise PublicAnalysisError('ordinary expenditure contains negative values')
        household_parts.append(ordinary.groupby('uqno', sort=False)[
            'valueannualized_adj'].sum())
        division_parts.append(ordinary.groupby(
            ['uqno', 'division', 'division_description'], dropna=False, sort=False)[
                'valueannualized_adj'].sum())
        mapped = ordinary[ordinary['comparability'].eq('adjustment_required')]
        mapped_parts.append(mapped.groupby('uqno', sort=False)['valueannualized_adj'].sum())
    if all_rows == 0:
        raise PublicAnalysisError('expenditure dataset is empty')
    household = pd.concat(household_parts).groupby(level=0).sum().rename('ordinary_expenditure')
    division = pd.concat(division_parts).rename('ordinary_expenditure').reset_index()
    division['division'] = pd.to_numeric(division['division'], errors='raise').astype(int)
    division['division_description'] = division['division'].map(DIVISIONS)
    if division['division_description'].isna().any():
        raise PublicAnalysisError('ordinary expenditure contains an unsupported division')
    division = division.groupby(
        ['uqno', 'division', 'division_description'], sort=False,
        as_index=False)['ordinary_expenditure'].sum()
    mapped = pd.concat(mapped_parts).groupby(level=0).sum().rename('mapped_expenditure')
    return household, division, mapped, {
        'all_expenditure_records': int(all_rows),
        'ordinary_consumption_records': int(ordinary_rows),
        'source_weighted_field_not_used_for_means': True,
    }


def _group_statistics(frame, group_column):
    rows = []
    for group, subset in frame.groupby(group_column, sort=False, dropna=False):
        rows.append({
            group_column: group,
            'sample_households': int(len(subset)),
            'weighted_households': float(subset['HHOLD_WGT'].sum()),
            'unweighted_mean_annual_expenditure': float(subset['ordinary_expenditure'].mean()),
            'unweighted_median_annual_expenditure': float(subset['ordinary_expenditure'].median()),
            'weighted_mean_annual_expenditure': weighted_mean(
                subset['ordinary_expenditure'], subset['HHOLD_WGT']),
            'weighted_median_annual_expenditure': weighted_quantile(
                subset['ordinary_expenditure'], subset['HHOLD_WGT'], 0.5),
        })
    return pd.DataFrame(rows)


def analyse_public(expenditure_path, households_path, quality_report_path) -> dict:
    households = _read_households(households_path)
    household_total, division_household, mapped, readiness = _aggregate_expenditure(
        expenditure_path)
    analytical = households.merge(
        household_total, left_on='UQNO', right_index=True, how='left', validate='one_to_one')
    analytical = analytical.merge(
        mapped, left_on='UQNO', right_index=True, how='left', validate='one_to_one')
    analytical[['ordinary_expenditure', 'mapped_expenditure']] = analytical[[
        'ordinary_expenditure', 'mapped_expenditure']].fillna(0.0)

    quality = json.loads(Path(quality_report_path).read_text(encoding='utf-8'))
    expected = quality['source_profiles']
    verified_counts = {
        'expenditure_records': readiness['all_expenditure_records'],
        'households': int(len(households)),
        'persons': int(expected['person']['row_count']),
        'person_income_observations': int(expected['personincome']['row_count']),
        'single_person_households': int(households['SINGLE_PERSON_HOUSEHOLD'].astype(str).str.casefold().eq('true').sum()),
    }
    if verified_counts['households'] != int(expected['households']['row_count']):
        raise PublicAnalysisError('household row count does not match the quality report')

    division_household = division_household.merge(
        households[['UQNO', 'HHOLD_WGT']], left_on='uqno', right_on='UQNO',
        how='left', validate='many_to_one')
    if division_household['HHOLD_WGT'].isna().any():
        raise PublicAnalysisError('expenditure contains an unknown household identifier')
    division_household['weighted_expenditure'] = (
        division_household['ordinary_expenditure'] * division_household['HHOLD_WGT'])
    category = division_household.groupby(
        ['division', 'division_description'], dropna=False).agg(
            sample_expenditure=('ordinary_expenditure', 'sum'),
            weighted_expenditure=('weighted_expenditure', 'sum'),
            sample_households=('uqno', 'nunique'),
        ).reset_index()
    category['weighted_share'] = (
        category['weighted_expenditure'] / category['weighted_expenditure'].sum())
    category['unweighted_share'] = (
        category['sample_expenditure'] / category['sample_expenditure'].sum())
    category = category.sort_values('weighted_share', ascending=False).reset_index(drop=True)

    composition = _group_statistics(analytical, 'household_size_group')
    group_order = ['1 person', '2 people', '3–4 people', '5+ people']
    composition['order'] = composition['household_size_group'].map(
        {name: index for index, name in enumerate(group_order)})
    composition = composition.sort_values('order').drop(columns='order').reset_index(drop=True)

    single = analytical[analytical['HSIZE'].eq(1)].copy()
    single_category_source = division_household[
        division_household['uqno'].isin(set(single['UQNO']))]
    single_category = single_category_source.groupby(
        ['division', 'division_description'], dropna=False).agg(
            sample_expenditure=('ordinary_expenditure', 'sum'),
            weighted_expenditure=('weighted_expenditure', 'sum')).reset_index()
    single_category['weighted_share'] = (
        single_category['weighted_expenditure'] / single_category['weighted_expenditure'].sum())
    single_category = single_category.sort_values('weighted_share', ascending=False)

    province = _group_statistics(analytical, 'province_name').sort_values(
        'weighted_median_annual_expenditure', ascending=False).reset_index(drop=True)
    income = _group_statistics(analytical, 'INCOME_QUINTILE').sort_values(
        'INCOME_QUINTILE').reset_index(drop=True)
    valid_income = analytical[(analytical['INCOME'] > 0) & (analytical['ordinary_expenditure'] > 0)]
    log_income_correlation = weighted_correlation(
        np.log(valid_income['INCOME']), np.log(valid_income['ordinary_expenditure']),
        valid_income['HHOLD_WGT'])

    metrics = {
        'dataset': 'Stats SA Income and Expenditure Survey 2022/23',
        'estimand': 'annual household ordinary consumption where coicop_type == 1, May 2023 price basis',
        'verified_counts': verified_counts,
        'sample_statistics': {
            'mean_annual_expenditure': float(analytical['ordinary_expenditure'].mean()),
            'median_annual_expenditure': float(analytical['ordinary_expenditure'].median()),
            'standard_deviation_annual_expenditure': float(analytical['ordinary_expenditure'].std()),
            'p90_annual_expenditure': float(analytical['ordinary_expenditure'].quantile(0.9)),
        },
        'weighted_population_statistics': {
            'estimated_households': float(analytical['HHOLD_WGT'].sum()),
            'mean_annual_expenditure': weighted_mean(
                analytical['ordinary_expenditure'], analytical['HHOLD_WGT']),
            'median_annual_expenditure': weighted_quantile(
                analytical['ordinary_expenditure'], analytical['HHOLD_WGT'], 0.5),
            'p90_annual_expenditure': weighted_quantile(
                analytical['ordinary_expenditure'], analytical['HHOLD_WGT'], 0.9),
        },
        'single_person_households': {
            'sample_count': int(len(single)),
            'estimated_households': float(single['HHOLD_WGT'].sum()),
            'weighted_mean_annual_expenditure': weighted_mean(
                single['ordinary_expenditure'], single['HHOLD_WGT']),
            'weighted_median_annual_expenditure': weighted_quantile(
                single['ordinary_expenditure'], single['HHOLD_WGT'], 0.5),
        },
        'gauteng': {
            'sample_households': int(analytical['province_name'].eq('Gauteng').sum()),
            'single_person_sample_households': int(
                (analytical['province_name'].eq('Gauteng') & analytical['HSIZE'].eq(1)).sum()),
        },
        'income_expenditure_association': {
            'measure': 'survey-weighted Pearson correlation of log household income and log ordinary expenditure',
            'value': log_income_correlation,
            'interpretation': 'descriptive association only; no causal or inferential claim',
        },
        'mapped_scope_weighted_share': float(
            (analytical['mapped_expenditure'] * analytical['HHOLD_WGT']).sum()
            / (analytical['ordinary_expenditure'] * analytical['HHOLD_WGT']).sum()),
        'weighting': {
            'method': 'aggregate unweighted item values to households, then apply HHOLD_WGT',
            'variance_estimation': 'not performed because no supported design-variable variance procedure is implemented',
            'confidence_intervals': 'not reported',
        },
        'comparison_readiness': {
            'nominal_amount_comparison_supported': False,
            'composition_comparison_supported_now': False,
            'reason': 'personal review coverage is incomplete and the 2026 account period is not price-aligned with May 2023 household expenditure',
        },
        'limitations': [
            'Weighted estimates use household weights but do not include design-based variance estimates.',
            'Provincial and subgroup results are descriptive and not causal.',
            'Per-capita household values are not interpreted as observed individual expenditure.',
            'PersonIncome is not aggregated into household income; the published household INCOME field is used.',
        ],
        'readiness_checks': readiness,
    }
    return {
        'metrics': metrics, 'households': analytical, 'category': category,
        'composition': composition, 'single_category': single_category,
        'province': province, 'income': income,
    }
