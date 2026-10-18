"""Privacy-aware charts for statistical outputs."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from ..visualisations import ACCENT, COLOUR, _save


def lorenz_chart(lorenz, path):
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot(lorenz['cumulative_household_share'], lorenz['cumulative_expenditure_share'], color=COLOUR, lw=2)
    ax.plot([0, 1], [0, 1], '--', color='#777777')
    ax.set(xlabel='Cumulative weighted household share', ylabel='Cumulative weighted expenditure share')
    ax.set_title('Weighted household consumption Lorenz curve', loc='left', weight='bold')
    ax.grid(alpha=.2)
    _save(fig, path)


def grouped_bar(frame, group, category, value, title, path, top_categories=5):
    top = frame.groupby(category)[value].sum().nlargest(top_categories).index
    table = frame[frame[category].isin(top)].pivot(index=group, columns=category, values=value).fillna(0)
    ax = table.plot(kind='bar', figsize=(10, 5), color=plt.cm.Set2(np.linspace(0, 1, len(table.columns))))
    ax.set_title(title, loc='left', weight='bold')
    ax.set_ylabel('Share of weighted expenditure')
    ax.set_xlabel('')
    ax.tick_params(axis='x', rotation=25)
    ax.legend(title='COICOP division', fontsize=8)
    ax.grid(axis='y', alpha=.2)
    _save(ax.figure, path)


def calibration_chart(frame, path):
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(frame['weighted_fitted_log_expenditure'], frame['weighted_observed_log_expenditure'], marker='o', color=COLOUR)
    limits = [min(frame.iloc[:, 1:3].min()), max(frame.iloc[:, 1:3].max())]
    ax.plot(limits, limits, '--', color='#777777')
    ax.set(xlabel='Weighted mean fitted log expenditure', ylabel='Weighted mean observed log expenditure')
    ax.set_title('Exploratory model calibration by fitted decile', loc='left', weight='bold')
    ax.grid(alpha=.2)
    _save(fig, path)


def personal_distribution(values, title, path):
    fig, ax = plt.subplots(figsize=(8, 4.8))
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if len(values):
        ax.hist(values, bins=np.logspace(np.log10(values.min()), np.log10(values.max()), 30), color=COLOUR)
        ax.set_xscale('log')
    ax.set(title=title, xlabel='Rand (log scale)', ylabel='Observations')
    ax.grid(axis='y', alpha=.2)
    _save(fig, path)
