"""Coverage-aware statistical profiling of private curated transactions."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..personal_eda import analyse_personal, load_personal_data
from .inequality import distribution_summary, weighted_gini


def _concentration(frame, label, amount):
    if frame.empty or frame[amount].sum() <= 0:
        return pd.DataFrame(columns=[label, 'observations', 'expenditure', 'share'])
    result = frame.groupby(label, dropna=False).agg(
        observations=(amount, 'size'), expenditure=(amount, 'sum')).reset_index()
    result['share'] = result['expenditure'] / result['expenditure'].sum()
    return result.sort_values(['expenditure', label], ascending=[False, True]).reset_index(drop=True)


def _unusual(purchases):
    columns = ['transaction_id', 'transaction_date', 'final_category', 'debit',
               'global_iqr_candidate', 'global_mad_candidate',
               'category_iqr_candidate', 'category_threshold_supported']
    if purchases.empty:
        return pd.DataFrame(columns=columns)
    values = purchases['debit'].astype(float)
    q1, q3 = values.quantile([.25, .75])
    iqr_limit = q3 + 1.5 * (q3 - q1)
    median = values.median()
    mad = float(np.median(np.abs(values - median)))
    mad_score = (0.6745 * (values - median).abs() / mad) if mad else pd.Series(0.0, index=values.index)
    result = purchases[['transaction_id', 'transaction_date', 'final_category', 'debit']].copy()
    result['global_iqr_candidate'] = values > iqr_limit
    result['global_mad_candidate'] = mad_score > 3.5
    result['category_iqr_candidate'] = False
    result['category_threshold_supported'] = False
    for _, index in purchases.groupby('final_category', dropna=False).groups.items():
        if len(index) < 20:
            continue
        group = values.loc[index]
        low, high = group.quantile([.25, .75])
        result.loc[index, 'category_threshold_supported'] = True
        result.loc[index, 'category_iqr_candidate'] = group > high + 1.5 * (high - low)
    return result[(result['global_iqr_candidate'] | result['global_mad_candidate'] |
                   result['category_iqr_candidate'])].reset_index(drop=True)


def _recurrence(purchases):
    columns = ['merchant', 'observations', 'median_amount', 'amount_deviation_ratio',
               'median_interval_days', 'interval_mad_days',
               'monthly_interval_share', 'classification']
    rows = []
    identified = purchases[purchases['final_merchant'].str.strip().ne('')]
    for merchant, group in identified.groupby('final_merchant', sort=True):
        group = group.sort_values('transaction_date')
        if len(group) < 2:
            continue
        amounts = group['debit'].astype(float)
        intervals = group['transaction_date'].diff().dt.days.dropna().astype(float)
        median_amount = float(amounts.median())
        amount_ratio = float(np.median(np.abs(amounts - median_amount)) / median_amount) if median_amount else 0.0
        monthly_share = float(intervals.between(20, 40).mean())
        interval_mad = float(np.median(np.abs(intervals - intervals.median())))
        if len(group) >= 3 and amount_ratio <= .05 and monthly_share >= .75 and interval_mad <= 7:
            label = 'strong recurring candidate'
        elif amount_ratio <= .15 and monthly_share >= .5:
            label = 'possible recurring candidate'
        else:
            label = 'insufficient evidence'
        rows.append({'merchant': merchant, 'observations': int(len(group)),
                     'median_amount': median_amount, 'amount_deviation_ratio': amount_ratio,
                     'median_interval_days': float(intervals.median()),
                     'interval_mad_days': interval_mad, 'monthly_interval_share': monthly_share,
                     'classification': label})
    return pd.DataFrame(rows, columns=columns)


def analyse_personal_statistics(input_path, validation_path):
    frame = load_personal_data(input_path)
    eda = analyse_personal(frame, validation_path)
    purchases = frame[frame['movement_type'].eq('Purchase')].copy()
    purchase_resolved = (purchases['review_required'].eq(False) & purchases['final_category'].str.strip().ne('')
                         & purchases['final_category'].ne('Uncategorised'))
    unresolved = purchases[~purchase_resolved]
    eligible = frame[frame['movement_type'].isin({'Purchase', 'Bank Fee'})].copy()
    eligible['category_amount'] = np.where(eligible['movement_type'].eq('Purchase'), eligible['debit'], eligible['fee'])
    eligible_resolved = (eligible['review_required'].eq(False) & eligible['final_category'].str.strip().ne('')
                         & eligible['final_category'].ne('Uncategorised'))
    categories = _concentration(eligible[eligible_resolved], 'final_category', 'category_amount')
    merchant_source = purchases[purchases['final_merchant'].str.strip().ne('')]
    merchants = _concentration(merchant_source, 'final_merchant', 'debit')
    start = pd.Timestamp(eda['metrics']['coverage_start'])
    end = pd.Timestamp(eda['metrics']['coverage_end'])
    days = pd.date_range(start, end)
    for gap in eda['metrics']['coverage_gaps']:
        days = days[~days.isin(pd.date_range(gap['gap_start'], gap['gap_end']))]
    daily = purchases.groupby('transaction_date')['debit'].sum().reindex(days, fill_value=0.0)
    category_value = float(eligible.loc[eligible_resolved, 'category_amount'].sum())
    coverage_percent = eda['metrics']['eligible_expenditure_coverage_percent']
    categories['excluded_unresolved_purchase_count'] = int(len(unresolved))
    categories['excluded_unresolved_purchase_value'] = round(float(unresolved['debit'].sum()), 2)
    categories['eligible_expenditure_coverage_percent'] = coverage_percent
    metrics = {
        'unit_notes': {'transactions': 'purchase transaction', 'daily': 'covered calendar day'},
        'purchase_distribution': distribution_summary(purchases['debit']),
        'resolved_purchase_distribution': distribution_summary(purchases.loc[purchase_resolved, 'debit']),
        'unresolved_purchase_distribution': distribution_summary(unresolved['debit']),
        'daily_purchase_distribution': distribution_summary(daily),
        'category_concentration': {
            'denominator': 'resolved purchase expenditure',
            'gini': None if categories.empty else weighted_gini(categories['expenditure'], np.ones(len(categories))),
            'top_category_share': None if categories.empty else float(categories.iloc[0]['share']),
            'top_five_share': None if categories.empty else float(categories.head(5)['share'].sum()),
        },
        'merchant_concentration': {
            'denominator': 'merchant-identified purchase expenditure',
            'covered_purchase_count': int(len(merchant_source)),
            'covered_purchase_value': float(merchant_source['debit'].sum()),
            'top_merchant_share': None if merchants.empty else float(merchants.iloc[0]['share']),
            'top_five_share': None if merchants.empty else float(merchants.head(5)['share'].sum()),
        },
        'classification_coverage': {
            'eligible_transaction_count': int(len(eligible)),
            'eligible_expenditure_value': float(eligible['category_amount'].sum()),
            'resolved_category_transaction_count': int(eligible_resolved.sum()),
            'resolved_category_expenditure_value': round(category_value, 2),
            'excluded_unresolved_purchase_count': int(len(unresolved)),
            'excluded_unresolved_purchase_value': round(float(unresolved['debit'].sum()), 2),
            'eligible_expenditure_coverage_percent': coverage_percent,
        },
        'coverage': {'covered_days': int(len(days)), 'uncovered_periods': eda['metrics']['coverage_gaps']},
        'limitations': ['One bank account is observed; repeated transactions are not independent people.',
                        'Outliers are statistical review candidates, not evidence of fraud.',
                        'Recurring labels are descriptive evidence, not confirmed subscriptions.'],
    }
    return {'metrics': metrics, 'categories': categories, 'merchants': merchants,
            'daily': daily.rename_axis('date').rename('purchase_expenditure').reset_index(),
            'unusual': _unusual(purchases), 'recurring': _recurrence(purchases)}
