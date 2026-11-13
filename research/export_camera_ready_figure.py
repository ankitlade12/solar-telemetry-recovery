"""Redraw Fig. 2 of ETIC paper 785 at its printed size.

The archived figure was drawn 7 in wide and scaled into a 3.49 in column, which printed its text at about 5 pt and
clipped the y-axis label. Drawing at the column width keeps every font at its stated size. The data and the interval
definition are unchanged: the input is the archived recovery_difference.csv (paired seven-day calendar-block 95%
pointwise intervals).
"""
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

COLUMN_WIDTH_IN = 252 / 72.27  # IEEEtran conference \columnwidth (252 TeX pt)
MIN_FONT_PT = 7
EARLY_WINDOW_END_H = 6
LABELS = {'nist': 'NIST', 'reserve10': 'C10'}
COLUMNS = ('site', 'hour', 'difference', 'ci_lower', 'ci_upper')
STYLE = {'pdf.fonttype': 42, 'font.family': 'STIXGeneral', 'mathtext.fontset': 'stix', 'font.size': 8,
         'axes.titlesize': 8, 'axes.labelsize': 8, 'xtick.labelsize': MIN_FONT_PT, 'ytick.labelsize': MIN_FONT_PT,
         'axes.linewidth': .6, 'xtick.major.width': .6, 'ytick.major.width': .6}

SOURCE = Path('runs/review_revision_20261015/analysis/recovery_difference.csv')
OUTPUT = Path('paper/etic2026/camera_ready_785/source/figures/recovery_difference_cr')


def checked(curve):
    missing = [c for c in COLUMNS if c not in curve.columns]
    if missing:
        raise ValueError(f'recovery-difference curve lacks columns: {", ".join(missing)}')
    unknown = set(curve.site) - set(LABELS)
    if unknown:
        raise ValueError(f'unexpected sites: {sorted(unknown)}')
    return curve


def recovery_difference_figure(curve):
    curve = checked(curve)
    with plt.rc_context(STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(COLUMN_WIDTH_IN, 1.75), sharey=True, layout='constrained')
        for ax, site in zip(axes, LABELS):
            d = curve.query('site == @site').dropna(subset=['difference']).sort_values('hour')
            ax.fill_between(d.hour, 1000*d.ci_lower, 1000*d.ci_upper, color='tab:blue', alpha=.22, linewidth=0)
            ax.plot(d.hour, 1000*d.difference, color='tab:blue', marker='o', markersize=2, linewidth=.9)
            ax.axhline(0, color='black', linewidth=.6)
            ax.axvline(EARLY_WINDOW_END_H, color='0.35', linestyle=':', linewidth=.8)
            ax.set(title=LABELS[site], xlim=(-.5, 23.5), xticks=[0, 6, 12, 18])
        axes[0].set_ylabel(r'$\Delta$NWIS ($\times10^{-3}$)')
        fig.supxlabel('Hours after scheduled return', fontsize=8)
    return fig


def export(source=SOURCE, output=OUTPUT):
    fig = recovery_difference_figure(pd.read_csv(source))
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output.with_suffix('.pdf'))
    fig.savefig(output.with_suffix('.png'), dpi=600)
    plt.close(fig)
    return output


if __name__ == '__main__':
    print(export())
