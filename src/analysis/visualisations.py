"""Small, deterministic Matplotlib charts for EDA outputs."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_MPL_CACHE = Path(tempfile.gettempdir()) / 'financial-footprints-matplotlib'
_MPL_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('MPLCONFIGDIR', str(_MPL_CACHE))

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


COLOUR = '#2C6E6F'
ACCENT = '#D9822B'


def _save(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches='tight', facecolor='white')
    plt.close(fig)


def horizontal_share_chart(frame, label, share, title, path, top=None):
    data = frame[[label, share]].copy()
    data[label] = data[label].fillna('Unlabelled')
    data = data.groupby(label, as_index=False)[share].sum()
    if top:
        data = data.nlargest(top, share)
    data = data.sort_values(share)
    fig, ax = plt.subplots(figsize=(9, max(4.5, len(data) * 0.38)))
    ax.barh(data[label], data[share] * 100, color=COLOUR)
    ax.set_xlabel('Share of expenditure (%)')
    ax.set_title(title, loc='left', weight='bold')
    ax.grid(axis='x', alpha=0.2)
    ax.spines[['top', 'right', 'left']].set_visible(False)
    _save(fig, path)


def line_chart(frame, x, y, title, ylabel, path):
    fig, ax = plt.subplots(figsize=(9, 4.8))
    if not frame.empty:
        ax.plot(frame[x].astype(str), frame[y], marker='o', color=COLOUR)
    ax.set_title(title, loc='left', weight='bold')
    ax.set_ylabel(ylabel)
    ax.set_xlabel('')
    ax.tick_params(axis='x', rotation=35)
    ax.grid(axis='y', alpha=0.2)
    ax.spines[['top', 'right']].set_visible(False)
    _save(fig, path)


def comparison_bar(frame, label, value, title, ylabel, path):
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(frame[label].astype(str), frame[value], color=COLOUR)
    ax.set_title(title, loc='left', weight='bold')
    ax.set_ylabel(ylabel)
    ax.set_xlabel('')
    ax.tick_params(axis='x', rotation=25)
    ax.grid(axis='y', alpha=0.2)
    ax.spines[['top', 'right']].set_visible(False)
    _save(fig, path)


def distribution_histogram(values, title, xlabel, path):
    fig, ax = plt.subplots(figsize=(9, 4.8))
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    if len(values):
        bins = np.logspace(np.log10(values.min()), np.log10(values.max()), 41)
        ax.hist(values, bins=bins, color=COLOUR, alpha=0.9)
    ax.set_xscale('log')
    ax.set_title(title, loc='left', weight='bold')
    ax.set_xlabel(xlabel)
    ax.set_ylabel('Sample households')
    ax.grid(axis='y', alpha=0.2)
    ax.spines[['top', 'right']].set_visible(False)
    _save(fig, path)
