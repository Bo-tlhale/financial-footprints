import numpy as np
import pandas as pd
import pytest

from src.analysis.statistics.modelling import fit_expenditure_model


def model_fixture():
    provinces = ['Western Cape', 'Gauteng', 'Limpopo']
    rows = []
    for index in range(60):
        income = 1000 + index * 100
        size = index % 5 + 1
        province = provinces[index % 3]
        expenditure = np.exp(3 + .65 * np.log(income) + .2 * np.log(size) + (.1 if province == 'Gauteng' else 0))
        rows.append({'UQNO': f'H{index:03d}', 'ordinary_expenditure': expenditure,
                     'INCOME': income, 'HSIZE': size, 'HHOLD_WGT': index % 4 + 1,
                     'province_name': province})
    return pd.DataFrame(rows)


def test_exploratory_model_is_deterministic_and_omits_inference():
    first = fit_expenditure_model(model_fixture())
    second = fit_expenditure_model(model_fixture())
    pd.testing.assert_frame_equal(first['coefficients'], second['coefficients'])
    assert first['diagnostics']['weighted_r_squared'] > .99
    assert 'standard error' not in ' '.join(first['coefficients'].columns).lower()
    assert 'no standard errors' in first['metadata']['inference']
    assert set(first['stability']['split']) == {'deterministic_half_1', 'deterministic_half_2'}


def test_model_excludes_nonpositive_outcomes_and_rejects_missing_schema():
    frame = model_fixture()
    frame.loc[0, 'ordinary_expenditure'] = 0
    assert fit_expenditure_model(frame)['diagnostics']['sample_households'] == 59
    with pytest.raises(ValueError, match='missing columns'):
        fit_expenditure_model(frame.drop(columns='INCOME'))
