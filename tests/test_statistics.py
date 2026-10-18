import numpy as np
import pandas as pd
import pytest

from src.analysis.statistics.inequality import (
    distribution_summary, weighted_distribution_summary, weighted_gini,
    weighted_spearman, weighted_top_share,
)
from src.analysis.statistics.personal_statistics import _recurrence, _unusual


def test_distribution_statistics_and_empty_input():
    result = distribution_summary([1, 2, 3, 100])
    assert result['count'] == 4
    assert result['median'] == 2.5
    assert result['iqr'] == pytest.approx(25.5)
    assert distribution_summary([])['count'] == 0


def test_weighted_distribution_gini_top_share_and_rank_correlation():
    result = weighted_distribution_summary([10, 20], [1, 3])
    assert result['weighted_mean'] == pytest.approx(17.5)
    assert result['weighted_median'] == 20
    assert weighted_gini([0, 1], [1, 1]) == pytest.approx(.5)
    assert weighted_top_share([1, 2, 3, 4], [1, 1, 1, 1], .25) == pytest.approx(.4)
    assert weighted_spearman([1, 2, 3], [3, 2, 1], [1, 1, 1]) == pytest.approx(-1)


@pytest.mark.parametrize('weights', [[0, 0], [-1, 1], [np.nan, 0]])
def test_weighted_statistics_reject_invalid_weights(weights):
    with pytest.raises(ValueError):
        weighted_gini([1, 2], weights)


def test_unusual_transaction_and_sparse_category_handling():
    values = [10.0] * 20 + [1000.0]
    frame = pd.DataFrame({'transaction_id': [str(i) for i in range(21)],
                          'transaction_date': pd.date_range('2026-01-01', periods=21),
                          'final_category': ['Food'] * 21, 'debit': values})
    unusual = _unusual(frame)
    assert unusual.iloc[-1]['transaction_id'] == '20'
    assert bool(unusual.iloc[-1]['category_threshold_supported'])
    sparse = _unusual(frame.iloc[:5].assign(debit=[1, 1, 1, 1, 100]))
    assert not sparse['category_threshold_supported'].any()


def test_recurring_evidence_labels_and_movement_exclusion_is_upstream():
    frame = pd.DataFrame({'final_merchant': ['A', 'A', 'A', 'B', 'B'],
                          'transaction_date': pd.to_datetime(['2026-01-01', '2026-02-01', '2026-03-01', '2026-01-01', '2026-01-05']),
                          'debit': [100, 101, 100, 10, 100]})
    result = _recurrence(frame).set_index('merchant')
    assert result.loc['A', 'classification'] == 'strong recurring candidate'
    assert result.loc['B', 'classification'] == 'insufficient evidence'
