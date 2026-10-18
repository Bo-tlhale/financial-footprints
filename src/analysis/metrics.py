"""Shared descriptive-statistics helpers used by both EDA tracks."""

from __future__ import annotations

import math
from decimal import Decimal

import numpy as np
import pandas as pd


def decimal_sum(values) -> Decimal:
    """Sum monetary strings without binary floating-point arithmetic."""
    return sum((Decimal(str(value)) for value in values), Decimal('0'))


def weighted_mean(values, weights) -> float:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not valid.any():
        return math.nan
    return float(np.average(values[valid], weights=weights[valid]))


def weighted_quantile(values, weights, quantile: float) -> float:
    """Return a deterministic frequency-weighted quantile."""
    if not 0 <= quantile <= 1:
        raise ValueError('quantile must be between zero and one')
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not valid.any():
        return math.nan
    values, weights = values[valid], weights[valid]
    order = np.argsort(values, kind='mergesort')
    values, weights = values[order], weights[order]
    cumulative = np.cumsum(weights)
    target = quantile * cumulative[-1]
    return float(values[np.searchsorted(cumulative, target, side='left')])


def weighted_correlation(x, y, weights) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    weights = np.asarray(weights, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(weights) & (weights > 0)
    if valid.sum() < 2:
        return math.nan
    x, y, weights = x[valid], y[valid], weights[valid]
    mean_x = np.average(x, weights=weights)
    mean_y = np.average(y, weights=weights)
    covariance = np.average((x - mean_x) * (y - mean_y), weights=weights)
    variance_x = np.average((x - mean_x) ** 2, weights=weights)
    variance_y = np.average((y - mean_y) ** 2, weights=weights)
    if variance_x <= 0 or variance_y <= 0:
        return math.nan
    return float(covariance / math.sqrt(variance_x * variance_y))


def household_size_group(size) -> str:
    size = int(size)
    if size == 1:
        return '1 person'
    if size == 2:
        return '2 people'
    if size <= 4:
        return '3–4 people'
    return '5+ people'


def dataframe_records(frame: pd.DataFrame) -> list[dict]:
    """Convert a result table to JSON-safe records."""
    clean = frame.replace({np.nan: None, np.inf: None, -np.inf: None})
    return clean.to_dict(orient='records')
