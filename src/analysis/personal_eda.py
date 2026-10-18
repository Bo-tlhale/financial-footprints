"""Private exploratory analysis of curated bank transactions."""

from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .metrics import decimal_sum


REQUIRED_COLUMNS = {
    'transaction_id', 'transaction_date', 'debit', 'credit', 'fee',
    'source_file', 'movement_type', 'final_merchant', 'final_category',
    'final_subcategory', 'classification_source', 'review_status',
    'review_required',
}
MOVEMENT_ORDER = [
    'Purchase', 'Income', 'Incoming Transfer', 'Outgoing Transfer', 'Refund',
    'Cash Withdrawal', 'Bank Fee', 'Reversal', 'Informational', 'Unknown',
]


class PersonalAnalysisError(ValueError):
    """Raised when private EDA inputs are incomplete or invalid."""


def _as_bool(series: pd.Series) -> pd.Series:
    mapping = {'true': True, 'false': False}
    values = series.astype(str).str.strip().str.casefold().map(mapping)
    if values.isna().any():
        raise PersonalAnalysisError('review_required contains non-boolean values')
    return values.astype(bool)


def load_personal_data(path) -> pd.DataFrame:
    path = Path(path)
    if not path.is_file():
        raise PersonalAnalysisError(f'curated personal dataset does not exist: {path}')
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise PersonalAnalysisError(f'curated dataset is missing columns: {missing}')
    if frame.empty or frame['transaction_id'].duplicated().any():
        raise PersonalAnalysisError('curated dataset must contain unique transactions')
    frame['transaction_date'] = pd.to_datetime(
        frame['transaction_date'], format='%Y-%m-%d', errors='raise')
    for column in ('debit', 'credit', 'fee'):
        frame[column] = pd.to_numeric(frame[column], errors='raise')
        if frame[column].lt(0).any():
            raise PersonalAnalysisError(f'{column} contains negative values')
    frame['review_required'] = _as_bool(frame['review_required'])
    return frame


def _coverage(validation_path, transactions):
    path = Path(validation_path)
    periods = []
    if path.is_file():
        report = json.loads(path.read_text(encoding='utf-8'))
        for statement in report.get('statements', []):
            periods.append({
                'period_start': statement.get('period_start'),
                'period_end': statement.get('period_end'),
                'transactions': statement.get('transactions'),
            })
    if periods:
        periods.sort(key=lambda item: (item['period_start'], item['period_end']))
        intervals = [
            (pd.Timestamp(item['period_start']), pd.Timestamp(item['period_end']))
            for item in periods
        ]
        start = intervals[0][0]
        end = max(interval[1] for interval in intervals)
    else:
        start, end = transactions['transaction_date'].min(), transactions['transaction_date'].max()
        intervals = [(start, end)]
    merged = []
    for interval_start, interval_end in intervals:
        if interval_end < interval_start:
            raise PersonalAnalysisError('statement period ends before it starts')
        if not merged or interval_start > merged[-1][1] + pd.Timedelta(days=1):
            merged.append([interval_start, interval_end])
        else:
            merged[-1][1] = max(merged[-1][1], interval_end)
    gaps = []
    for left, right in zip(merged, merged[1:]):
        gap_start = left[1] + pd.Timedelta(days=1)
        gap_end = right[0] - pd.Timedelta(days=1)
        gaps.append({
            'gap_start': gap_start.date().isoformat(),
            'gap_end': gap_end.date().isoformat(),
            'days': int((gap_end - gap_start).days + 1),
        })
    covered_days = sum(int((right - left).days + 1) for left, right in merged)
    return periods, start, end, covered_days, gaps


def _spend_amount(frame):
    amount = pd.Series(0.0, index=frame.index)
    amount.loc[frame['movement_type'].eq('Purchase')] = frame['debit']
    amount.loc[frame['movement_type'].eq('Bank Fee')] = frame['fee']
    return amount


def _recurring_candidates(purchases: pd.DataFrame) -> pd.DataFrame:
    columns = [
        'merchant', 'observations', 'first_date', 'last_date',
        'median_amount', 'median_interval_days', 'classification',
    ]
    rows = []
    purchases = purchases[purchases['final_merchant'].str.strip().ne('')].copy()
    for merchant, group in purchases.groupby('final_merchant', sort=True):
        group = group.sort_values('transaction_date')
        if len(group) < 2:
            continue
        intervals = group['transaction_date'].diff().dt.days.dropna()
        median_amount = group['debit'].median()
        tolerance = max(1.0, abs(median_amount) * 0.05)
        stable_amount = (group['debit'] - median_amount).abs().le(tolerance).mean() >= 0.75
        plausible_interval = intervals.between(20, 40).mean() >= 0.5
        if not (stable_amount and plausible_interval):
            continue
        rows.append({
            'merchant': merchant,
            'observations': int(len(group)),
            'first_date': group['transaction_date'].min().date().isoformat(),
            'last_date': group['transaction_date'].max().date().isoformat(),
            'median_amount': float(median_amount),
            'median_interval_days': float(intervals.median()),
            'classification': (
                'possible recurring pattern' if len(group) < 3
                else 'recurring candidate requiring confirmation'
            ),
        })
    return pd.DataFrame(rows, columns=columns)


def analyse_personal(transactions: pd.DataFrame, validation_path) -> dict:
    frame = transactions.copy()
    periods, coverage_start, coverage_end, observed_days, coverage_gaps = _coverage(
        validation_path, frame)
    frame['spend_amount'] = _spend_amount(frame)
    frame['financially_active'] = frame[['debit', 'credit', 'fee']].gt(0).any(axis=1)
    eligible = frame['movement_type'].isin({'Purchase', 'Bank Fee'})
    resolved = (
        eligible & ~frame['review_required']
        & frame['final_category'].str.strip().ne('')
        & frame['final_category'].ne('Uncategorised')
    )
    unresolved_purchase = frame['movement_type'].eq('Purchase') & ~resolved
    identified_total = decimal_sum(
        frame.loc[eligible, 'spend_amount'].map(lambda value: f'{value:.2f}'))
    resolved_value = decimal_sum(
        frame.loc[resolved, 'spend_amount'].map(lambda value: f'{value:.2f}'))
    unresolved_value = decimal_sum(
        frame.loc[unresolved_purchase, 'debit'].map(lambda value: f'{value:.2f}'))
    category_coverage_percent = (
        round(float(resolved_value / identified_total * 100), 2)
        if identified_total else 0.0
    )

    movement = frame.groupby('movement_type', dropna=False).agg(
        transaction_count=('transaction_id', 'size'),
        debit_total=('debit', 'sum'), credit_total=('credit', 'sum'),
        fee_total=('fee', 'sum'),
    ).reindex(MOVEMENT_ORDER, fill_value=0).reset_index()

    category = frame.loc[resolved].groupby(
        ['final_category', 'final_subcategory'], dropna=False).agg(
            transaction_count=('transaction_id', 'size'),
            expenditure=('spend_amount', 'sum'),
        ).reset_index()
    resolved_total = category['expenditure'].sum()
    category['share_of_resolved_expenditure'] = (
        category['expenditure'] / resolved_total if resolved_total else 0.0)
    category['eligible_expenditure'] = str(identified_total.quantize(Decimal('0.01')))
    category['resolved_category_expenditure'] = str(
        resolved_value.quantize(Decimal('0.01')))
    category['excluded_unresolved_purchase_count'] = int(unresolved_purchase.sum())
    category['excluded_unresolved_purchase_value'] = str(
        unresolved_value.quantize(Decimal('0.01')))
    category['eligible_expenditure_coverage_percent'] = category_coverage_percent
    category = category.sort_values(
        ['expenditure', 'final_category', 'final_subcategory'],
        ascending=[False, True, True]).reset_index(drop=True)

    purchases = frame[frame['movement_type'].eq('Purchase')].copy()
    merchant = purchases[purchases['final_merchant'].str.strip().ne('')].groupby(
        'final_merchant').agg(
            transaction_count=('transaction_id', 'size'),
            expenditure=('debit', 'sum'), average_transaction=('debit', 'mean'),
        ).reset_index().sort_values(
            ['expenditure', 'final_merchant'], ascending=[False, True])
    merchant_total = merchant['expenditure'].sum()
    merchant['share_of_merchant_identified_purchases'] = (
        merchant['expenditure'] / merchant_total if merchant_total else 0.0)

    frame['day'] = frame['transaction_date'].dt.date.astype(str)
    frame['week_start'] = (
        frame['transaction_date'] - pd.to_timedelta(frame['transaction_date'].dt.weekday, unit='D')
    ).dt.date.astype(str)
    frame['month'] = frame['transaction_date'].dt.to_period('M').astype(str)
    frame['day_type'] = frame['transaction_date'].dt.weekday.ge(5).map(
        {True: 'Weekend', False: 'Weekday'})
    spending = frame[eligible]
    daily = spending.groupby('day', as_index=False)['spend_amount'].sum()
    weekly = spending.groupby('week_start', as_index=False)['spend_amount'].sum()
    monthly = spending.groupby('month', as_index=False)['spend_amount'].sum()
    def month_coverage(value):
        month = pd.Period(value)
        month_start, month_end = month.start_time, month.end_time.normalize()
        gap_intersects = any(
            pd.Timestamp(gap['gap_start']) <= month_end
            and pd.Timestamp(gap['gap_end']) >= month_start
            for gap in coverage_gaps
        )
        return (
            'complete within available statement coverage'
            if month_start >= coverage_start and month_end <= coverage_end
            and not gap_intersects else 'partial or gapped calendar month'
        )
    monthly['coverage'] = monthly['month'].map(month_coverage)
    day_type = spending.groupby('day_type', as_index=False).agg(
        transaction_count=('transaction_id', 'size'), expenditure=('spend_amount', 'sum'))
    recurring = _recurring_candidates(purchases)

    movement_counts = Counter(frame['movement_type'])
    purchase_values = purchases['debit']
    metrics = {
        'source_scope': 'available activity from one bank account only',
        'coverage_start': coverage_start.date().isoformat(),
        'coverage_end': coverage_end.date().isoformat(),
        'observed_days': int(observed_days),
        'coverage_gaps': coverage_gaps,
        'source_statement_count': int(frame['source_file'].nunique()),
        'statement_periods': periods,
        'transaction_count': int(len(frame)),
        'financially_active_transactions': int(frame['financially_active'].sum()),
        'movement_counts': {name: int(movement_counts.get(name, 0)) for name in MOVEMENT_ORDER},
        'identified_expenditure': str(identified_total.quantize(Decimal('0.01'))),
        'identified_expenditure_definition': 'purchase debits plus separately recorded bank fees; refunds and transfers are not netted',
        'purchase_average': None if purchase_values.empty else round(float(purchase_values.mean()), 2),
        'purchase_median': None if purchase_values.empty else round(float(purchase_values.median()), 2),
        'spending_per_observed_day': round(float(identified_total / observed_days), 2),
        'resolved_category_transactions': int(resolved.sum()),
        'resolved_category_expenditure': str(
            resolved_value.quantize(Decimal('0.01'))),
        'unresolved_purchase_count': int(unresolved_purchase.sum()),
        'unresolved_purchase_value': str(unresolved_value.quantize(Decimal('0.01'))),
        'eligible_expenditure_coverage_percent': category_coverage_percent,
        'manual_review_coverage': {
            'manual_approvals': int(frame['classification_source'].eq('manual_approval').sum()),
            'manual_corrections': int(frame['classification_source'].eq('manual_correction').sum()),
            'deferred': int(frame['classification_source'].eq('deferred').sum()),
            'still_requires_review': int(frame['review_required'].sum()),
        },
        'merchant_concentration': {
            'identified_merchant_count': int(len(merchant)),
            'top_merchant_share': None if merchant.empty else round(float(merchant.iloc[0]['share_of_merchant_identified_purchases']), 6),
            'top_five_share': None if merchant.empty else round(float(merchant.head(5)['share_of_merchant_identified_purchases'].sum()), 6),
        },
        'recurring_candidate_count': int(len(recurring)),
        'limitations': [
            'The file represents one bank account, not all personal finances.',
            'Boundary calendar months are partial and are not directly comparable with complete months.',
            'Unresolved purchases are excluded from category and subcategory findings.',
            'Merchant and recurrence results remain rule-based candidates, not confirmed subscriptions.',
        ],
    }
    return {
        'metrics': metrics, 'movement': movement, 'category': category,
        'merchant': merchant, 'recurring': recurring, 'daily': daily,
        'weekly': weekly, 'monthly': monthly, 'day_type': day_type,
    }
