"""Table I of ETIC 785 with the Bonferroni-adjusted intervals that its equivalence statements rely on.

The archived Table I printed only seven-day 95% intervals, while the text's equivalence claims (all four adjusted
intervals inside +/-1%; +/-0.5% not met everywhere; C10 late includes zero only at seven days) use the 98.75%
intervals in equivalence.csv. This table prints both, built from the archived CSVs rather than edited LaTeX.
"""
from pathlib import Path

import pandas as pd

PRIMARY = 'paper/etic2026/camera_ready_785/source/review_evidence_20261015_v2/primary_source.csv'
EQUIVALENCE = 'runs/review_revision_20261015/analysis/equivalence.csv'
OUTPUT = Path('paper/etic2026/camera_ready_785/source/tables_cr/primary.tex')
ROWS = [('nist', 'recovery_0_6', 'NIST 0--6 h'), ('nist', 'recovery_6_24', 'NIST 6--24 h'),
        ('reserve10', 'recovery_0_6', 'C10 0--6 h'), ('reserve10', 'recovery_6_24', 'C10 6--24 h')]
NOTE = (r'Windows: hours after scheduled return. Equal scenario/horizon means. Avail.: availability-calibration NWIS. $\Delta$: recovery minus availability NWIS, relative to availability; '
        r'negative favors recovery. Intervals in \%, paired seven-day calendar blocks; 98.75\%: Bonferroni-adjusted '
        r'for the four contrasts. C10 is post-hoc. All block lengths, absolute contrasts and support counts are '
        r'supplied in the supplement and artifact.')


def signed(value):
    return f'{value:+.3f}'.replace('-', '$-$')


def interval(lower, upper):
    return f'[{signed(lower)}, {signed(upper)}]'


def adjusted(equivalence):
    seven = equivalence[(equivalence.confidence.round(4) == .9875) & (equivalence.block_days == 7)]
    return seven.drop_duplicates(subset=['site', 'phase']).set_index(['site', 'phase'])


def table1(primary, equivalence):
    base = primary[(primary.confidence.round(4) == .95) & (primary.block_days == 7)].set_index(['site', 'phase'])
    wide = adjusted(equivalence)
    lines = []
    for site, phase, label in ROWS:
        if (site, phase) not in base.index or (site, phase) not in wide.index:
            raise ValueError(f'{label}: contrast missing from the 95% or 98.75% source')
        p, q = base.loc[(site, phase)], wide.loc[(site, phase)]
        if abs(p.relative_pct - q.relative_pct) > 1e-6:
            raise ValueError(f'{label}: sources disagree on the point estimate')
        lines.append(f'{label} & {p.right_mean:.5f} & {signed(p.relative_pct)} & '
                     f'{interval(p.relative_lower_pct, p.relative_upper_pct)} & '
                     f'{interval(q.relative_lower_pct, q.relative_upper_pct)} \\\\')
    return ('\\begin{table}[t]\n\\centering\\footnotesize\n'
            '\\caption{Recovery-age grouping versus availability calibration.}\\label{tab:primary}\n'
            '\\setlength{\\tabcolsep}{2.5pt}\n\\begin{tabular}{lrrrr}\n\\hline\n'
            'System/window & Avail. & $\\Delta$ (\\%) & 95\\% CI & 98.75\\% CI \\\\\n\\hline\n'
            + '\n'.join(lines) + '\n\\hline\n\\end{tabular}\n'
            '\\par\\smallskip\\begin{minipage}{\\columnwidth}\\scriptsize ' + NOTE + '\\end{minipage}\n\\end{table}\n')


def export(output=OUTPUT):
    output.parent.mkdir(exist_ok=True)
    output.write_text(table1(pd.read_csv(PRIMARY), pd.read_csv(EQUIVALENCE)))
    return output


if __name__ == '__main__':
    print(export())
