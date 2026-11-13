"""Fig. 2 of ETIC paper 785 must stay legible at its printed single-column size."""
import numpy as np
import pandas as pd
import pytest
from matplotlib.text import Text

from research.export_camera_ready_figure import COLUMN_WIDTH_IN, MIN_FONT_PT, recovery_difference_figure

SITES = ('nist', 'reserve10')


def curve():
    hours = np.arange(24)
    rows = []
    for offset, site in enumerate(SITES):
        difference = (hours - 12 + offset) * 1e-5
        rows.append(pd.DataFrame({'site': site, 'hour': hours, 'difference': difference,
                                  'ci_lower': difference - 2e-4, 'ci_upper': difference + 2e-4}))
    return pd.concat(rows, ignore_index=True)


def drawn(fig):
    fig.canvas.draw()
    return fig.canvas.get_renderer()


def visible_texts(fig):
    return [t for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()]


def test_figure_is_drawn_at_the_printed_column_width():
    fig = recovery_difference_figure(curve())
    assert fig.get_size_inches()[0] == pytest.approx(COLUMN_WIDTH_IN)
    assert COLUMN_WIDTH_IN == pytest.approx(252 / 72.27)  # IEEEtran conference \columnwidth


def test_every_label_meets_the_minimum_size_and_lies_inside_the_canvas():
    fig = recovery_difference_figure(curve())
    renderer = drawn(fig)
    canvas = fig.bbox
    texts = visible_texts(fig)
    assert texts
    for text in texts:
        box = text.get_window_extent(renderer)
        assert text.get_fontsize() >= MIN_FONT_PT, text.get_text()
        assert box.x0 >= canvas.x0 - 0.5 and box.x1 <= canvas.x1 + 0.5, text.get_text()
        assert box.y0 >= canvas.y0 - 0.5 and box.y1 <= canvas.y1 + 0.5, text.get_text()


def test_panels_plot_each_site_difference_in_thousandths():
    data = curve()
    fig = recovery_difference_figure(data)
    assert [ax.get_title() for ax in fig.axes] == ['NIST', 'C10']
    for ax, site in zip(fig.axes, SITES):
        expected = 1000 * data.loc[data.site.eq(site), 'difference'].to_numpy()
        assert any(np.allclose(line.get_ydata(), expected) for line in ax.get_lines())


def test_rejects_a_curve_without_interval_bounds():
    with pytest.raises(ValueError, match='ci_upper'):
        recovery_difference_figure(curve().drop(columns='ci_upper'))
