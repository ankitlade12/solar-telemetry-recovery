"""Table I must print the multiplicity-adjusted intervals that the equivalence statements rely on."""
from pathlib import Path

import pandas as pd
import pytest

from research.export_camera_ready_table1 import EQUIVALENCE, PRIMARY, table1

ARCHIVED_TABLE = Path('paper/etic2026/camera_ready_785/source/review_evidence_20261015_v2/primary.tex')


CASES = [('nist', 'recovery_0_6', 0.0464470938, 0.0727977, -0.2533819, 0.4472764, -0.3148270, 0.5778530),
         ('nist', 'recovery_6_24', 0.0482133762, -0.0614853, -0.2004563, 0.0662043, -0.2381140, 0.1050990),
         ('reserve10', 'recovery_0_6', 0.0482165413, -0.1188720, -0.2738009, 0.0397227, -0.3208200, 0.0888910),
         ('reserve10', 'recovery_6_24', 0.0533799481, 0.1308093, 0.0080887, 0.2668938, -0.0246880, 0.3031930)]


def primary():
    return pd.DataFrame([{'site': s, 'phase': p, 'right_mean': m, 'relative_pct': e, 'relative_lower_pct': lo,
                          'relative_upper_pct': hi, 'confidence': .95, 'block_days': 7}
                         for s, p, m, e, lo, hi, _, _ in CASES])


def equivalence():
    rows = []
    for site, phase, _, est, _, _, lo, hi in CASES:
        for margin in (5.0, 1.0, .5):
            rows.append({'site': site, 'phase': phase, 'margin_pct': margin, 'confidence': .9875, 'block_days': 7,
                         'relative_pct': est, 'relative_lower_pct': lo, 'relative_upper_pct': hi})
        rows.append({'site': site, 'phase': phase, 'margin_pct': 5.0, 'confidence': .9875, 'block_days': 14,
                     'relative_pct': est, 'relative_lower_pct': 9.0, 'relative_upper_pct': 9.0})
    return pd.DataFrame(rows)


def test_rows_show_point_estimate_and_both_seven_day_intervals():
    tex = table1(primary(), equivalence())
    assert r'NIST 0--6 h & 0.04645 & +0.073 & [$-$0.253, +0.447] & [$-$0.315, +0.578] \\' in tex
    assert r'C10 6--24 h & 0.05338 & +0.131 & [+0.008, +0.267] & [$-$0.025, +0.303] \\' in tex
    assert '98.75' in tex and r'\label{tab:primary}' in tex


def test_refuses_a_source_missing_one_of_the_four_contrasts():
    with pytest.raises(ValueError, match='C10 6--24 h'):
        table1(primary().iloc[:3], equivalence())


def test_refuses_sources_that_disagree_on_the_point_estimate():
    shifted = equivalence().assign(relative_pct=lambda d: d.relative_pct + .01)
    with pytest.raises(ValueError, match='point estimate'):
        table1(primary(), shifted)


@pytest.mark.skipif(not (Path(PRIMARY).exists() and Path(EQUIVALENCE).exists()), reason='archived runs not present')
def test_archived_point_estimates_and_95_percent_intervals_are_reproduced():
    tex = table1(pd.read_csv(PRIMARY), pd.read_csv(EQUIVALENCE))
    archived = ARCHIVED_TABLE.read_text().replace('-', '$-$').replace('$-$$-$', '--')
    for line in archived.splitlines():
        if line.startswith(('NIST', 'C10')):
            assert line.removesuffix(r' \\').rstrip() in tex
