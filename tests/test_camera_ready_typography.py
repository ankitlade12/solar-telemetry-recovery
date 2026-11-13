"""Camera-ready table copies may change typography only, never a reported number."""
import re

import pytest

from research.camera_ready_typography import camera_ready, numbers, typeset_minus

ROW = r'C10 0--6 h & 0.04822 & -0.119 & [-0.274, +0.040] \\'


def test_negative_numbers_get_a_true_minus_sign():
    assert typeset_minus(ROW) == r'C10 0--6 h & 0.04822 & $-$0.119 & [$-$0.274, +0.040] \\'


@pytest.mark.parametrize('text', [r'0--6 h', r'6--24 h', r'$-0.119$', r'Post-review shrinkage', r'\setlength{\tabcolsep}{3pt}',
                                  r'$\Delta$ (\%)'])
def test_ranges_math_and_words_are_left_alone(text):
    assert typeset_minus(text) == text


def test_every_reported_number_survives_unchanged():
    assert numbers(typeset_minus(ROW)) == numbers(ROW) == [10, 0, 6, 0.04822, -0.119, -0.274, 0.040]


SHRINKAGE = (r'\caption{Post-review shrinkage ablation: relative NWIS difference (\%).}' '\n'
             r'$a$ in $n_{eff}/(n_{eff}+a)$ & NIST early \\' '\n'
             r'50 & -0.061 \\' '\n'
             r'\scriptsize Both matched methods use the same constant $a$. Early: 0--6 h.')


def test_table_three_gets_every_camera_ready_edit():
    tex = camera_ready('shrinkage', SHRINKAGE)
    assert r'\caption{Shrinkage ablation:' in tex
    assert r'$a$ in (\ref{eq:mixture})' in tex
    assert 'Positive: recovery worse than availability.' in tex
    assert '$-$0.061' in tex


def test_a_table_missing_an_edit_target_is_refused():
    with pytest.raises(ValueError, match='shrinkage'):
        camera_ready('shrinkage', SHRINKAGE.replace('Post-review s', 'S'))


def test_layout_lengths_are_not_reported_numbers():
    assert numbers(r'\setlength{\tabcolsep}{2.3pt} & -0.1') == [-0.1]


def test_no_hyphen_minus_remains_before_a_digit():
    assert not re.search(r'(?<![-$\w])-(?=\d)', typeset_minus(ROW))
