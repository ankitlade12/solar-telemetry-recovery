"""New boundary risks: fixed replication scope and source-hour semantics."""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.final_evaluation import combine_years
from research.prepare_producing_extension import normalize_selected
from research.producing_extension import expected_config, validate_config


def fixture_raw():
    stamps = pd.date_range('2016-12-31T23:00', periods=120, freq='min')
    return pd.DataFrame({'measured_on': np.repeat(stamps, 2), 'utc_measured_on': pd.NaT,
        'metric_id': np.tile([423, 421], 120), 'value': np.tile([-1., 300.], 120)})


def test_signed_aggregation_missingness_and_alignment():
    raw = fixture_raw()
    raw.loc[(raw.metric_id == 423) & (raw.measured_on.dt.minute == 0), 'value'] = 58.
    primary, _, _ = normalize_selected(raw, 0)
    assert primary.pv.eq(0).all()  # mean before clipping, not mean of clipped samples
    bad = raw.drop(raw.index[2])  # one AC record absent; POA still complete
    incomplete, _, _ = normalize_selected(bad, 0)
    assert np.isnan(incomplete.iloc[0].pv) and incomplete.iloc[0].irradiance == 300
    right, _, _ = normalize_selected(raw, -1)
    assert right.pv_sample_count.tolist() == [1, 60, 59]
    assert right.pv.iloc[[0, 2]].isna().all()
    first = raw[raw.measured_on.dt.year == 2016]
    second = raw[raw.measured_on.dt.year == 2017]
    merged = combine_years([normalize_selected(first, -1)[0], normalize_selected(second, -1)[0]])
    assert np.isnan(merged.loc[pd.Timestamp('2017-01-01T07:00Z'), 'pv'])
    # Partial source-year means cannot be reconstructed by picking a nonmissing value.
    assert not merged.index.duplicated().any()


def test_source_conflicts_and_unexpected_channels_stop():
    raw = fixture_raw()
    conflicting = pd.concat([raw, raw.iloc[[0]].assign(value=100.)], ignore_index=True)
    with pytest.raises(ValueError, match='Conflicting'):
        normalize_selected(conflicting, 0)
    raw.loc[0, 'metric_id'] = 422
    with pytest.raises(ValueError, match='predeclared'):
        normalize_selected(raw, 0)


def test_extension_scope_rejects_retuning_or_case_loss():
    parent = json.loads(Path('configs/final_evaluation_v4.json').read_text())
    expected = expected_config(parent)
    validate_config(expected, parent)
    for change in ('seed', 'drop', 'site', 'privilege'):
        altered = copy.deepcopy(expected)
        if change == 'seed': altered['model_seed'] += 1
        if change == 'drop': altered['cases'].pop(0)
        if change == 'site': altered['sites'] = ['colorado']
        if change == 'privilege': altered['cases'][0]['privileged_labels'] = True
        with pytest.raises(ValueError, match='deviates'):
            validate_config(altered, parent)
