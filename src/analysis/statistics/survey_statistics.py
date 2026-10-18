"""Household-level weighted descriptive statistics for IES 2022/23."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..metrics import weighted_correlation
from ..public_eda import analyse_public
from .inequality import (weighted_distribution_summary, weighted_gini,
                         weighted_lorenz, weighted_spearman, weighted_top_share)


def _group_summary(frame, column):
    rows = []
    for value, group in frame.groupby(column, dropna=False, sort=True):
        total = weighted_distribution_summary(group['ordinary_expenditure'], group['HHOLD_WGT'])
        per_capita = weighted_distribution_summary(
            group['ordinary_expenditure'] / group['HSIZE'], group['HHOLD_WGT'])
        rows.append({column: value, 'sample_households': len(group),
                     'weighted_households': group['HHOLD_WGT'].sum(),
                     'weighted_mean_total': total['weighted_mean'],
                     'weighted_median_total': total['weighted_median'],
                     'weighted_iqr_total': total['weighted_iqr'],
                     'weighted_mean_per_capita': per_capita['weighted_mean'],
                     'weighted_median_per_capita': per_capita['weighted_median'],
                     'weighted_gini_total': weighted_gini(group['ordinary_expenditure'], group['HHOLD_WGT'])})
    return pd.DataFrame(rows)


def _composition_by(result, group_column):
    household = result['households'][['UQNO', 'HHOLD_WGT', group_column]]
    source = result['division_household'].merge(
        household, left_on='uqno', right_on='UQNO', validate='many_to_one')
    source['weighted_expenditure'] = source['ordinary_expenditure'] * source['HHOLD_WGT']
    output = source.groupby([group_column, 'division', 'division_description'], as_index=False).agg(
        sample_households=('uqno', 'nunique'), weighted_expenditure=('weighted_expenditure', 'sum'))
    totals = output.groupby(group_column)['weighted_expenditure'].transform('sum')
    output['weighted_share'] = output['weighted_expenditure'] / totals
    return output


def analyse_survey_statistics(expenditure_path, households_path, quality_path):
    result = analyse_public(expenditure_path, households_path, quality_path)
    households = result['households'].copy()
    values, weights = households['ordinary_expenditure'], households['HHOLD_WGT']
    positive = households[(households['INCOME'] > 0) & (households['ordinary_expenditure'] > 0)].copy()
    ratio = positive['ordinary_expenditure'] / positive['INCOME']
    income_association = {
        'weighted_pearson_log_income_log_expenditure': weighted_correlation(
            np.log(positive['INCOME']), np.log(positive['ordinary_expenditure']), positive['HHOLD_WGT']),
        'weighted_spearman_income_expenditure': weighted_spearman(
            positive['INCOME'], positive['ordinary_expenditure'], positive['HHOLD_WGT']),
        'expenditure_income_ratio': weighted_distribution_summary(ratio, positive['HHOLD_WGT']),
        'interpretation': 'weighted descriptive association; no causal or significance claim',
    }
    distribution = weighted_distribution_summary(values, weights)
    distribution.update({'weighted_gini': weighted_gini(values, weights),
                         'top_10_percent_expenditure_share': weighted_top_share(values, weights, .10),
                         'top_20_percent_expenditure_share': weighted_top_share(values, weights, .20),
                         'weighted_total_expenditure': float(np.dot(values, weights))})
    weight_sum = float(weights.sum())
    metrics = {
        'estimand': 'annual household ordinary consumption (coicop_type == 1), May 2023 prices',
        'distribution': distribution,
        'income_expenditure_association': income_association,
        'validation': {'sample_households': int(len(households)), 'positive_weights': bool(weights.gt(0).all()),
                       'zero_expenditure_households': int(values.eq(0).sum()),
                       'missing_expenditure_households': int(values.isna().sum()),
                       'released_weight_sum': weight_sum,
                       'metadata_reported_weight_sum': 19050732.016,
                       'weight_sum_discrepancy': weight_sum - 19050732.016,
                       'aggregation': 'ordinary expenditure items summed to UQNO before HHOLD_WGT is applied'},
        'survey_design': {'household_weight': 'HHOLD_WGT', 'strata_available': False,
                          'primary_sampling_unit_available': False, 'replicate_weights_available': False,
                          'variance_estimation': 'unsupported from released analytical files; no confidence intervals, p-values, or inferential standard errors reported'},
        'limitations': ['Consumption inequality is not income inequality.',
                        'Per-capita values are calculated household measures and do not model economies of scale.',
                        'Released v1.2 weights differ from the total printed in the metadata; released weights are used without renormalisation.'],
    }
    result.update({'statistics_metrics': metrics, 'lorenz': weighted_lorenz(values, weights),
                   'size_statistics': _group_summary(households, 'household_size_group'),
                   'province_statistics': _group_summary(households, 'province_name'),
                   'income_statistics': _group_summary(households, 'INCOME_QUINTILE'),
                   'income_composition': _composition_by(result, 'INCOME_QUINTILE'),
                   'province_composition': _composition_by(result, 'province_name')})
    return result
