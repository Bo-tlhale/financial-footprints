"""Interpretable exploratory weighted log-linear expenditure model."""

from __future__ import annotations

import hashlib
import math

import numpy as np
import pandas as pd


def _design(frame, reference='Western Cape'):
    if frame.empty:
        raise ValueError('model population is empty')
    required = {'UQNO', 'ordinary_expenditure', 'INCOME', 'HSIZE', 'HHOLD_WGT', 'province_name'}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f'model data is missing columns: {sorted(missing)}')
    valid = frame[list(required)].copy()
    valid = valid.replace([np.inf, -np.inf], np.nan).dropna()
    valid = valid[(valid['ordinary_expenditure'] > 0) & (valid['INCOME'] > 0) &
                  (valid['HSIZE'] > 0) & (valid['HHOLD_WGT'] > 0)]
    provinces = pd.get_dummies(valid['province_name'], prefix='province', dtype=float)
    ref = f'province_{reference}'
    if ref not in provinces:
        raise ValueError(f'model reference province is absent: {reference}')
    provinces = provinces.drop(columns=ref)
    log_income = np.log(valid['INCOME'].to_numpy(float))
    log_size = np.log(valid['HSIZE'].to_numpy(float))
    columns = ['intercept', 'log_income_centered', 'log_household_size_centered', *provinces.columns]
    matrix = np.column_stack([np.ones(len(valid)), log_income - log_income.mean(),
                              log_size - log_size.mean(), provinces.to_numpy(float)])
    return valid, matrix, np.log(valid['ordinary_expenditure'].to_numpy(float)), columns


def _fit(frame):
    valid, matrix, outcome, columns = _design(frame)
    weights = valid['HHOLD_WGT'].to_numpy(float)
    weights = weights / weights.mean()
    root = np.sqrt(weights)
    coefficients, _, _, singular = np.linalg.lstsq(matrix * root[:, None], outcome * root, rcond=None)
    fitted = matrix @ coefficients
    residual = outcome - fitted
    mean_y = np.average(outcome, weights=weights)
    r_squared = 1 - np.sum(weights * residual ** 2) / np.sum(weights * (outcome - mean_y) ** 2)
    return valid, pd.Series(coefficients, index=columns), fitted, residual, {
        'sample_households': int(len(valid)), 'weighted_r_squared': float(r_squared),
        'weighted_rmse_log_rand': float(np.sqrt(np.average(residual ** 2, weights=weights))),
        'weighted_mae_log_rand': float(np.average(np.abs(residual), weights=weights)),
        'weighted_mean_residual': float(np.average(residual, weights=weights)),
        'condition_number': float(singular.max() / singular.min()),
    }


def fit_expenditure_model(households):
    valid, coefficients, fitted, residual, diagnostics = _fit(households)
    split = valid['UQNO'].astype(str).map(lambda value: int(hashlib.sha256(value.encode()).hexdigest(), 16) % 2)
    stability = []
    for part in (0, 1):
        _, estimate, _, _, _ = _fit(valid[split.eq(part)])
        for name, value in estimate.items():
            stability.append({'split': f'deterministic_half_{part + 1}', 'term': name, 'coefficient': value})
    coefficient_table = coefficients.rename('coefficient').rename_axis('term').reset_index()
    coefficient_table['multiplicative_factor'] = np.exp(coefficient_table['coefficient'])
    calibration = pd.DataFrame({'fitted_log_expenditure': fitted,
                                'observed_log_expenditure': fitted + residual,
                                'weight': valid['HHOLD_WGT'].to_numpy(float)})
    calibration['fitted_decile'] = pd.qcut(calibration['fitted_log_expenditure'], 10, labels=False, duplicates='drop') + 1
    calibration = calibration.groupby('fitted_decile', as_index=False).apply(
        lambda group: pd.Series({'weighted_fitted_log_expenditure': np.average(group['fitted_log_expenditure'], weights=group['weight']),
                                 'weighted_observed_log_expenditure': np.average(group['observed_log_expenditure'], weights=group['weight']),
                                 'sample_households': len(group)}), include_groups=False).reset_index(drop=True)
    metadata = {'objective': 'explain variation in annual ordinary household consumption',
                'outcome': 'natural log of positive annual ordinary household consumption',
                'predictors': ['centered log household income', 'centered log household size', 'province indicators'],
                'reference_province': 'Western Cape', 'weights': 'HHOLD_WGT normalised to mean one',
                'excluded_predictors': {'published expenditure': 'outcome leakage', 'income quintile': 'derived from income and redundant',
                                        'PersonIncome': 'individual rather than household unit',
                                        'settlement type': 'local code frequencies conflict with metadata label ordering'},
                'inference': 'exploratory coefficients only; no standard errors, confidence intervals, or p-values',
                'prediction': 'not an objective; no train-test split or forecasting claim'}
    return {'metadata': metadata, 'diagnostics': diagnostics, 'coefficients': coefficient_table,
            'stability': pd.DataFrame(stability), 'calibration': calibration}
