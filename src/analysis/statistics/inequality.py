"""Distribution, concentration, and weighted-association helpers."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ..metrics import weighted_correlation, weighted_mean, weighted_quantile


def _weighted_arrays(values, weights, *, nonnegative=False):
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if values.ndim != 1 or weights.ndim != 1 or len(values) != len(weights):
        raise ValueError('values and weights must be equal-length one-dimensional arrays')
    if np.any(np.isfinite(weights) & (weights < 0)):
        raise ValueError('weights must not be negative')
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    values, weights = values[valid], weights[valid]
    if not len(values):
        raise ValueError('at least one finite value with a positive weight is required')
    if nonnegative and (values < 0).any():
        raise ValueError('values must be non-negative')
    return values, weights


def distribution_summary(values) -> dict:
    """Return transparent sample distribution measures for finite observations."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return {'count': 0, **{key: None for key in (
            'total', 'mean', 'median', 'standard_deviation', 'p10', 'p25',
            'p75', 'p90', 'p95', 'p99', 'iqr', 'skewness')}}
    mean = float(values.mean())
    std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    skewness = None
    if len(values) >= 3 and std > 0:
        n = len(values)
        skewness = float(
            n / ((n - 1) * (n - 2))
            * np.sum(((values - mean) / std) ** 3)
        )
    percentiles = np.quantile(values, [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
    return {
        'count': int(len(values)),
        'total': float(values.sum()),
        'mean': mean,
        'median': float(percentiles[2]),
        'standard_deviation': std,
        'p10': float(percentiles[0]),
        'p25': float(percentiles[1]),
        'p75': float(percentiles[3]),
        'p90': float(percentiles[4]),
        'p95': float(percentiles[5]),
        'p99': float(percentiles[6]),
        'iqr': float(percentiles[3] - percentiles[1]),
        'skewness': skewness,
    }


def weighted_variance(values, weights) -> float:
    values, weights = _weighted_arrays(values, weights)
    mean = np.average(values, weights=weights)
    return float(np.average((values - mean) ** 2, weights=weights))


def weighted_gini(values, weights) -> float:
    """Return the weighted Gini coefficient for a non-negative quantity."""
    values, weights = _weighted_arrays(values, weights, nonnegative=True)
    total = float(np.dot(values, weights))
    if total == 0:
        return 0.0
    order = np.argsort(values, kind='mergesort')
    values, weights = values[order], weights[order]
    population = np.concatenate(([0.0], np.cumsum(weights) / weights.sum()))
    quantity = np.concatenate(([0.0], np.cumsum(values * weights) / total))
    return float(1.0 - 2.0 * np.trapezoid(quantity, population))


def weighted_lorenz(values, weights, points: int = 101) -> pd.DataFrame:
    values, weights = _weighted_arrays(values, weights, nonnegative=True)
    order = np.argsort(values, kind='mergesort')
    values, weights = values[order], weights[order]
    total = float(np.dot(values, weights))
    population = np.concatenate(([0.0], np.cumsum(weights) / weights.sum()))
    if total:
        quantity = np.concatenate(([0.0], np.cumsum(values * weights) / total))
    else:
        quantity = np.zeros(len(values) + 1)
    if points < 2:
        raise ValueError('points must be at least two')
    grid = np.linspace(0.0, 1.0, points)
    return pd.DataFrame({
        'cumulative_household_share': grid,
        'cumulative_expenditure_share': np.interp(grid, population, quantity),
    })


def weighted_top_share(values, weights, population_share: float) -> float:
    """Share of weighted quantity held by the highest-valued population share."""
    if not 0 < population_share <= 1:
        raise ValueError('population_share must be in (0, 1]')
    values, weights = _weighted_arrays(values, weights, nonnegative=True)
    order = np.argsort(values, kind='mergesort')[::-1]
    values, weights = values[order], weights[order]
    target = weights.sum() * population_share
    remaining = target
    selected_total = 0.0
    for value, weight in zip(values, weights):
        used = min(weight, remaining)
        selected_total += value * used
        remaining -= used
        if remaining <= 0:
            break
    total = float(np.dot(values, weights))
    return 0.0 if total == 0 else float(selected_total / total)


def weighted_rank(values, weights) -> np.ndarray:
    """Return weighted mid-distribution ranks, preserving ties."""
    values, weights = _weighted_arrays(values, weights)
    order = np.argsort(values, kind='mergesort')
    sorted_values, sorted_weights = values[order], weights[order]
    ranks_sorted = np.empty(len(values), dtype=float)
    cumulative = 0.0
    index = 0
    total_weight = weights.sum()
    while index < len(values):
        end = index + 1
        while end < len(values) and sorted_values[end] == sorted_values[index]:
            end += 1
        group_weight = sorted_weights[index:end].sum()
        ranks_sorted[index:end] = (cumulative + group_weight / 2.0) / total_weight
        cumulative += group_weight
        index = end
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = ranks_sorted
    return ranks


def weighted_spearman(x, y, weights) -> float:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if x.ndim != 1 or y.ndim != 1 or weights.ndim != 1 or not (len(x) == len(y) == len(weights)):
        raise ValueError('x, y, and weights must be equal-length one-dimensional arrays')
    valid = np.isfinite(x) & np.isfinite(y) & np.isfinite(weights) & (weights > 0)
    x, y, weights_x = x[valid], y[valid], weights[valid]
    if len(x) < 2:
        return math.nan
    return weighted_correlation(
        weighted_rank(x, weights_x), weighted_rank(y, weights_x), weights_x)


def weighted_distribution_summary(values, weights) -> dict:
    values, weights = _weighted_arrays(values, weights)
    percentiles = {
        f'p{int(q * 100):02d}': weighted_quantile(values, weights, q)
        for q in (0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99)
    }
    return {
        'sample_count': int(len(values)),
        'weighted_population': float(weights.sum()),
        'weighted_mean': weighted_mean(values, weights),
        'weighted_standard_deviation': math.sqrt(weighted_variance(values, weights)),
        'weighted_median': percentiles['p50'],
        **percentiles,
        'weighted_iqr': percentiles['p75'] - percentiles['p25'],
    }
