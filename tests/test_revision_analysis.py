import numpy as np
import pandas as pd
import pytest

from research.revision_analysis import asymmetric_loss, equivalence, paired_interval
from research.analyze_final_evaluation import calendar_bootstrap


def test_paired_intervals_match_frozen_estimator_and_use_paired_ratios():
    data = pd.DataFrame({'day': pd.date_range('2017-02-01', periods=100, tz='UTC'),
                         'case_id': 'a', 'horizon': 1, 'n': 2,
                         'left_nwis': np.arange(100)/100+2, 'right_nwis': np.arange(100)/100+2.01})
    old = calendar_bootstrap(data, '2017-02-01T00:00Z', '2018-01-01T00:00Z', 7, 1000, 20261015)
    new = paired_interval(data, replicates=1000)
    for field in ('difference', 'ci_lower', 'ci_upper', 'left_mean', 'right_mean'):
        assert new[field] == pytest.approx(old[field])
    assert new['relative_lower_pct'] == pytest.approx(100*old['relative_ci_lower'])
    assert equivalence(new, 1)
    assert not equivalence(new, .01)
    data['right_nwis'] = 0.
    assert not equivalence(paired_interval(data, replicates=1000), 5)


def test_asymmetric_decision_loss_has_expected_cost_and_no_negative_loss():
    np.testing.assert_array_equal(asymmetric_loss(np.array([1, 2, 3]), np.array([2, 2, 2]), 4), [1, 0, 4])
    with pytest.raises(ValueError):
        asymmetric_loss(1, 2, -1)
