import numpy as np
import pandas as pd
import pytest

from research.etic785_analysis import paired_direction, aligned_methods


def test_paired_direction_includes_ties_and_preserves_orientation():
    assert paired_direction([-4, -1, 0, 2]) == -.25
    assert paired_direction([0, 0]) == 0
    with pytest.raises(ValueError):
        paired_direction([np.nan])


def test_pair_alignment_rejects_missing_and_duplicate_forecasts():
    data = pd.DataFrame({'origin':[1,1], 'horizon':[1,1],
                         'method':['physical_recovery','physical_availability'], 'actual_kw':[2.,2.]})
    a, b = aligned_methods(data)
    assert a.index.equals(b.index)
    with pytest.raises(ValueError):
        aligned_methods(data.iloc[:1])
    with pytest.raises(ValueError):
        aligned_methods(pd.concat([data, data.iloc[:1]]))
