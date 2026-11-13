"""Export revised paper assets from measured tables; keep original exports immutable."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
matplotlib.rcParams['pdf.fonttype'] = 42
import pandas as pd

from solar_recovery.pilot import digest

ROOTS = {'nist': Path('runs/final_2017_v4/analysis'), 'reserve10': Path('runs/producing_extension_v1/analysis')}
LABELS = {'nist': 'NIST', 'reserve10': 'C10'}


def table(path, caption, label, columns, rows, note=''):
    text = '\\begin{table}[t]\n\\centering\\footnotesize\n'
    text += f'\\caption{{{caption}}}\\label{{{label}}}\n'
    text += '\\setlength{\\tabcolsep}{3pt}\n\\begin{tabular}{'+('l'+'r'*(len(columns)-1))+'}\n\\hline\n'
    text += ' & '.join(columns)+' \\\\\n\\hline\n'
    text += '\n'.join(' & '.join(map(str, row))+' \\\\' for row in rows)
    text += '\n\\hline\n\\end{tabular}\n'
    if note:
        text += '\\par\\smallskip\\begin{minipage}{\\columnwidth}\\scriptsize '+note+'\\end{minipage}\n'
    text += '\\end{table}\n'
    path.write_text(text)


def export(output='paper/review_evidence_20261015_v2'):
    out = Path(output); out.mkdir(parents=True, exist_ok=False)
    inputs = {}
    def read(path):
        path = Path(path); inputs[str(path)] = digest(path); return pd.read_csv(path)
    analysis = Path('runs/review_revision_20261015/analysis')
    contrasts = read(analysis/'contrasts.csv')
    main = contrasts.loc[contrasts.confidence.eq(.95) & contrasts.block_days.eq(7) & contrasts.clock.isna()].copy()
    main.to_csv(out/'primary_source.csv', index=False)
    rows = []
    for _, row in main.iterrows():
        phase = '0--6 h' if row.phase == 'recovery_0_6' else '6--24 h'
        rows.append([LABELS[row.site]+' '+phase, f'{row.right_mean:.5f}', f'{row.relative_pct:+.3f}',
                     f'[{row.relative_lower_pct:+.3f}, {row.relative_upper_pct:+.3f}]'])
    table(out/'primary.tex', 'Recovery-age grouping versus availability calibration.', 'tab:primary',
          ['System/window', 'Avail. NWIS', '$\\Delta$ (\\%)', '95\\% CI (\\%)'], rows,
          'Equal scenario/horizon means; negative differences favor recovery. Paired seven-day calendar blocks. C10 is post-hoc. All block lengths, absolute contrasts and support counts are supplied in the supplement and artifact.')
    summaries = {s: read(r/'Summary.csv').query("population == 'recorded_ac' and endpoint == 'failure_recovery' and site == @s").set_index('method') for s, r in ROOTS.items()}
    names = [('raw','Quantile HGB'), ('rolling','Rolling'), ('recency','Recency'), ('physical','Physical context'),
             ('physical_availability','Availability'), ('physical_recovery','Recovery age'), ('mask50','50-slot mask'),
             ('aci_bounded','Bounded ACI'), ('persistence','Latest persistence'), ('geometric_persistence','Geometric persistence'),
             ('previous_day','Previous day'), ('carry_forward','Carry forward'), ('single_imputation','Single imputation'),
             ('multiple_imputation','Multiple imputation'), ('mi_recency','MI + recency')]
    rows = []
    for method, label in names:
        values = [label]
        for site in ROOTS:
            row = summaries[site].loc[method]
            values.extend([f'{row.nwis:.5f}', f'{100*row.coverage90:.1f}'])
        rows.append(values)
    table(out/'methods.tex', 'Failure/recovery performance on identical eligible rows.', 'tab:main',
          ['Method','NIST NWIS','$C_{90}$','C10 NWIS','$C_{90}$'], rows,
          '$C_{90}$ is empirical 90\\% interval coverage in percent. HGB: histogram gradient boosting; ACI: adaptive conformal inference; MI: multiple imputation. Rankings are descriptive.')
    experiment = read('runs/review_revision_20261015/experimental_analysis/contrasts.csv')
    shrink = experiment.query("study == 'shrinkage' and block_days == 7")
    rows=[]
    for strength in (50,10,1):
        row=[str(strength)]
        for site in ROOTS:
            for phase in ('recovery_0_6','recovery_6_24'):
                r=shrink.loc[shrink.site.eq(site)&shrink.variant.astype(str).eq(str(strength))&shrink.phase.eq(phase)].iloc[0]
                row.append(f'{r.relative_pct:+.3f}')
        rows.append(row)
    table(out/'shrinkage.tex', 'Post-review shrinkage ablation: relative NWIS difference (\\%).', 'tab:shrinkage',
          ['$a$ in $n_{eff}/(n_{eff}+a)$','NIST early','NIST late','C10 early','C10 late'], rows,
          'Both matched methods use the same constant $a$. Early: 0--6 h; late: 6--24 h. All primary fault scenarios are included; intervals and clean tradeoffs remain in the artifact.')
    family = experiment.query("study == 'features_and_faults' and variant == 'joint_gradual' and phase == 'failure_recovery' and block_days == 7")
    rows=[]
    for method,label in [('kernel_age','Continuous age'),('kernel_history','History restoration'),('kernel_transport','Receipt dynamics'),
                         ('kernel_labels','Label availability'),('kernel_all','All families, calibration'),
                         ('base_all_recovery_features','All families, base model')]:
        row=[label]
        for site in ROOTS:
            r=family.loc[family.site.eq(site)&family.contrast.str.startswith(method+'_minus_')].iloc[0]
            row.extend([f'{r.relative_pct:+.3f}',f'[{r.relative_lower_pct:+.2f}, {r.relative_upper_pct:+.2f}]'])
        rows.append(row)
    table(out/'families.tex', 'Structured recovery-feature ablations (relative NWIS, \\%).', 'tab:families',
          ['Feature entry','NIST','95\\% CI','C10','95\\% CI'], rows,
          'Calibration variants compare with availability; the base-model variant compares with the raw base forecast. Same fixed training profile; no test-based feature selection. Intervals are exploratory, not multiplicity-adjusted.')
    # Plot overlapping interruption curves with distinguishable open markers and line styles.
    fig,axes=plt.subplots(1,2,figsize=(7,2.3),constrained_layout=True)
    styles={'clean':('s','--'),'pv_only':('^','-'),'irradiance_only':('v',':'),'joint_immediate':('o','-'),'joint_gradual':('x','--')}
    for ax,site in zip(axes,ROOTS):
        curve=read(ROOTS[site]/'InterruptionComparison.csv').query("population == 'recorded_ac' and site == @site")
        for case,group in curve.groupby('case_id'):
            marker,line=styles[case]
            ax.plot(group.horizon,group.nwis,marker=marker,linestyle=line,fillstyle='none',markersize=5,
                    linewidth=1,label=case.replace('_',' '))
        ax.set(title=LABELS[site],xticks=[1,2,3,4],xlabel='Target-end hour offset',ylabel='Interruption NWIS')
    axes[-1].legend(fontsize=6)
    for ext in ('pdf','png'):fig.savefig(out/f'interruption.{ext}',dpi=200)
    plt.close(fig)
    curve = read(analysis/'recovery_difference.csv')
    fig, axes = plt.subplots(1, 2, figsize=(7, 2.5), constrained_layout=True)
    for ax, site in zip(axes, ROOTS):
        d = curve.query('site == @site').dropna(subset=['difference'])
        ax.plot(d.hour, 1000*d.difference, marker='.', linewidth=1)
        ax.fill_between(d.hour, 1000*d.ci_lower, 1000*d.ci_upper, alpha=.2)
        ax.axhline(0, color='black', linewidth=.5)
        ax.set(title=LABELS[site], xlabel='Hours after scheduled return', ylabel=r'$10^3$ (recovery − availability) NWIS')
    for ext in ('pdf', 'png'):fig.savefig(out/f'recovery_difference.{ext}', dpi=200)
    plt.close(fig)
    # Retain C4 in a dedicated data-quality supplement instead of production evidence.
    c4=read('runs/final_2017_v4/analysis/Summary.csv').query("site == 'colorado' and population == 'recorded_ac' and endpoint == 'failure_recovery'")
    table(out/'c4.tex','C4 near-idle recorded-output case, retained separately.','tab:c4',
          ['Method','NWIS','$C_{90}$ (\\%)'], [[r.method.replace('_',r'\_'),f'{r.nwis:.5f}',f'{100*r.coverage90:.1f}'] for _,r in c4.iterrows()],
          'Near-zero targets do not imply near-zero forecast scores: an inaccurate forecast can still incur a substantial WIS. C4 is not counted as normally producing corroboration.')
    eq=read(analysis/'equivalence.csv')
    facts={'equivalence_all_1pct':bool(eq.query('margin_pct == 1 and confidence == .9875').equivalent_within_margin.all()),
           'equivalence_all_05pct':bool(eq.query('margin_pct == .5 and confidence == .9875').equivalent_within_margin.all()),
           'primary_records':main.to_dict(orient='records')}
    (out/'facts.json').write_text(json.dumps(facts,indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps({'status':'measured revision assets exported; manuscript integration review separate',
        'code_sha256':digest(__file__),'inputs':inputs,'outputs':{p.name:digest(p) for p in out.iterdir()}},indent=2)+'\n')


if __name__ == '__main__':
    export()
