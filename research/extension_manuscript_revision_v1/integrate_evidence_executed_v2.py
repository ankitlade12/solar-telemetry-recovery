"""Present both verified studies together without pooling their inference."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from research.export_extension_evidence import checked_evidence
from research.export_paper_tables import LABELS, number, interval, table
from research.package_submission import verify_claim_ledger
from solar_recovery.pilot import digest

ROOTS = {'nist': 'runs/final_2017_v4', 'colorado': 'runs/final_2017_v4', 'reserve10': 'runs/producing_extension_v1'}
NAMES = {'nist': 'NIST', 'colorado': 'C4', 'reserve10': 'C10'}
TITLES = {'nist': 'NIST · original', 'colorado': 'Colorado 4 · original', 'reserve10': 'Colorado 10 · extension'}
PRIMARY = 'physical_recovery_minus_physical_availability'


def main():
    workspace = Path.cwd(); output = workspace/'paper/integrated_evidence_v2'
    if output.exists(): raise FileExistsError('Use a fresh integrated evidence version')
    for root, reproduction in [('runs/final_2017_v4', 'runs/final_evidence_exports_v1/reproduced_tables'),
                               ('runs/producing_extension_v1', 'runs/producing_extension_reproduced_v1')]:
        checked_evidence(workspace/root, workspace/reproduction)
    tables = {root: {name: pd.read_csv(workspace/root/'analysis'/f'{name}.csv') for name in
                    ['Summary', 'Cells', 'Contrasts', 'Diagnostics', 'Recovery', 'InterruptionComparison']} for root in set(ROOTS.values())}
    output.mkdir(); claims = {}; source_hashes = {}
    def select(site, name, where):
        source = Path(ROOTS[site])/'analysis'/f'{name}.csv'; frame = tables[ROOTS[site]][name]
        query = {'site': site, **where}
        for key, value in query.items(): frame = frame.loc[frame[key].eq(value)]
        if len(frame) != 1: raise ValueError(f'Expected a unique source row: {source}, {query}')
        row = frame.iloc[0]; values = {}
        for key, value in row.items():
            if isinstance(value, (float, int, np.number, bool)) and pd.notna(value):
                values[key] = value.item() if isinstance(value, np.generic) else value
        identity = str(source)+json.dumps(query, sort_keys=True)
        claims[identity] = {'id': 'integrated_'+str(len(claims)+1), 'statement': f'Integrated manuscript source row: {site}, {name}, {where}',
                            'source_path': str(source), 'source_sha256': digest(source), 'where': query, 'values': values}
        source_hashes[str(source)] = digest(source)
        return row
    def contrast(site, pool, endpoint, name=PRIMARY, block=7, population='recorded_ac'):
        return select(site, 'Contrasts', {'population': population, 'pool': pool, 'endpoint': endpoint,
                                         'contrast': name, 'block_days': block})
    main_rows = []; summary_points = []
    for method, label in LABELS.items():
        row = [label]
        for site in ROOTS:
            point = select(site, 'Summary', {'population': 'recorded_ac', 'endpoint': 'failure_recovery', 'method': method})
            summary_points.append(point.to_dict())
            row += [number(point.nwis), number(100*point.coverage90, 1), number(point.nwidth90, 3)]
        main_rows.append(row)
    table(output/'main_table.tex', 'Failure/recovery forecasts: original systems and separately declared extension.', 'tab:main',
          'lrrrrrrrrr', ['Method']+['NWIS', '$C_{90}$', '$W_{90}/C$']*3, main_rows, True,
          'NIST and C4 are the original study; C10 is the later producing-system replication. NWIS and width are DC-capacity normalized; coverage is percent. All fifteen outputs use the same eligible rows within each case. Equal case/horizon means are computed within each system, with no pooled-site estimate.')
    path = output/'main_table.tex'; text = path.read_text().replace(r'\tabcolsep}{4pt}', r'\tabcolsep}{2.5pt}')
    header = 'Method & NWIS & $C_{90}$ & $W_{90}/C$ & NWIS & $C_{90}$ & $W_{90}/C$ & NWIS & $C_{90}$ & $W_{90}/C$'
    grouped = r' & \multicolumn{3}{c}{NIST: original} & \multicolumn{3}{c}{C4: original} & \multicolumn{3}{c}{C10: extension} \\'+'\n'+header
    assert header in text; path.write_text(text.replace(header, grouped))
    pd.DataFrame(summary_points).to_csv(output/'method_rows.csv', index=False)
    primary_rows = []; support_rows = []; all_primary = []
    for site in ROOTS:
        for phase, label in [('recovery_0_6', '0--6 h'), ('recovery_6_24', '6--24 h')]:
            point = contrast(site, 'faulted_primary', phase)
            for block in (7, 14, 28): all_primary.append(contrast(site, 'faulted_primary', phase, block=block).to_dict())
            frame = tables[ROOTS[site]]['Cells'].query("site==@site and population=='recorded_ac' and case_group=='primary' and method=='raw' and endpoint==@phase")
            for _, item in frame.iterrows():
                select(site, 'Cells', {'population':'recorded_ac', 'case_id':item.case_id, 'method':'raw', 'horizon':int(item.horizon), 'endpoint':phase})
            support_rows.append({'site':site,'phase':phase,'minimum_pairs':int(frame.n.min()),'maximum_pairs':int(frame.n.max()),
                                 'minimum_events':int(frame.events.min()),'maximum_events':int(frame.events.max())})
            primary_rows.append([NAMES[site], label, interval(point), str(int(frame.events.min()))])
    table(output/'primary_table.tex', 'Recovery minus availability: primary phase contrasts.', 'tab:primary', 'llrl',
          ['System', 'Phase', '$10^3\\Delta$NWIS [95\\% CI]', '$E_{\\min}$'], primary_rows, False,
          'Positive differences favor availability. Seven-day paired calendar-block intervals; C10 is a later replication. $E_{\\min}$ is the smallest distinct-event count per case/horizon cell. Early windows have fewer than 200 pairs per cell. All 14/28-day intervals remain in the artifact.')
    pd.DataFrame(all_primary).to_csv(output/'primary_all_blocks.csv', index=False)
    pd.DataFrame(support_rows).to_csv(output/'support_ranges.csv', index=False)
    cases = {'joint_gradual':'Reference joint-gradual', 'no_input_age':'No explicit age', 'no_block_augmentation':'No block augmentation',
             'privileged_labels':'Privileged labels (diagnostic)', 'training_2015':'2015-trained weights',
             'cross_site_weights':'Other-site weights + local calibration', 'right_aligned':'Minute-end alignment', 'receipt_5min':'Five-minute receipt margin'}
    rows = []; sensitivity = []
    for case, label in cases.items():
        row = [label]
        for site in ROOTS:
            available = tables[ROOTS[site]]['Contrasts']
            if not ((available.site==site)&(available.pool==case)).any(): row.append('--'); continue
            row.append(interval(contrast(site,case,'recovery')))
            for block in (7,14,28): sensitivity.append(contrast(site,case,'recovery',block=block).to_dict())
        rows.append(row)
    table(output/'ablation_table.tex', 'Recovery minus availability: ablations and declared extension checks.', 'tab:ablations', 'lrrr',
          ['Joint-gradual case', 'NIST', 'C4', 'C10 (extension)'], rows, True,
          '$10^3\\Delta$NWIS and exploratory seven-day 95\\% intervals for 0--24 h recovery. Dashes denote experiments outside that system\'s declared design. Privileged labels are non-operational. Other-site weights use local calibration. All 14/28-day intervals, original duration/seed/quality/stale-transport checks and individual primary cases remain in the artifact.')
    pd.DataFrame(sensitivity).to_csv(output/'sensitivity_rows.csv', index=False)
    clean_rows = []; facts = []
    for site in ROOTS:
        clean = contrast(site,'clean','all','physical_recovery_minus_physical')
        rec, ref = float(clean.left_mean), float(clean.right_mean)
        cells = tables[ROOTS[site]]['Cells'].query("site==@site and population=='recorded_ac' and case_id=='clean' and endpoint=='all'")
        for method in ['physical','physical_recovery']:
            mean = cells.loc[cells.method.eq(method),'nwis'].mean()
            assert np.isclose(mean, ref if method=='physical' else rec, rtol=1e-12, atol=1e-12)
        tolerance = max(.02*ref,.0001)
        clean_rows.append([NAMES[site],number(ref),number(rec),interval(clean),'yes' if rec-ref<=tolerance else 'no'])
        points = pd.DataFrame(summary_points).query('site==@site').set_index('method')
        fref, frec = points.loc['physical','nwis'],points.loc['physical_recovery','nwis']
        facts.append({'site':site,'failure_physical':fref,'failure_recovery':frec,'relative_failure_difference':(frec-fref)/fref,
                      'signal_5pct':bool(frec<=.95*fref),'clean_difference':rec-ref,'clean_tolerance':tolerance,'clean_pass':bool(rec-ref<=tolerance)})
    table(output/'clean_table.tex','Clean-data tradeoff against physical context.', 'tab:clean','lrrrl',
          ['System','Physical NWIS','Recovery NWIS','$10^3\\Delta$NWIS [95\\% CI]','Tolerance met?'],clean_rows,True,
          'The point tolerance is an increase no larger than $\\max(0.02\\,\\mathrm{NWIS}_{physical},0.0001)$. C10 is the later replication. Meeting the tolerance is not an improvement, coverage or acceptance guarantee.')
    pd.DataFrame(facts).to_csv(output/'gate_facts.csv',index=False)
    # Additional extension statements needed in the narrative, including secondary findings.
    for block in (7,14,28):
        contrast('reserve10','faulted_primary','recovery_0_6','physical_recovery_minus_physical',block)
        for phase in ('recovery_0_6','recovery_6_24'):
            contrast('reserve10','faulted_primary',phase,block=block,population='exclude_bright_zero')
    select('reserve10','Summary',{'population':'exclude_bright_zero','endpoint':'failure_recovery','method':'raw'})
    select('reserve10','Diagnostics',{'case_id':'joint_gradual','phase':'recovery_0_6','method':'physical_recovery'})
    # Plot existing table values. No cross-system averaging or new interval calculation.
    plt.rcParams.update({'font.size':7,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    figures = output/'figures'; figures.mkdir()
    recovery = pd.concat([tables[r]['Recovery'] for r in sorted(set(ROOTS.values()))],ignore_index=True)
    curves = []; fig,axes=plt.subplots(2,3,figsize=(7.0,2.8),constrained_layout=True,sharex=True)
    for j,site in enumerate(ROOTS):
        for method in ['raw','recency','physical_availability','physical_recovery']:
            group=recovery.query('site==@site and method==@method').groupby('recovery_hour_bin').agg(nwis=('nwis','mean'),n=('n','sum')).reset_index()
            group['site']=site;group['method']=method;curves.append(group)
            axes[0,j].plot(group.recovery_hour_bin,group.nwis,label=method.replace('physical_',''),linewidth=1,linestyle={'raw':'-','recency':':','physical_availability':'--','physical_recovery':'-'}[method])
            if method=='raw': axes[1,j].bar(group.recovery_hour_bin,group.n,color='#a0bacc')
        axes[0,j].set(title=TITLES[site],ylabel='NWIS');axes[1,j].set(xlabel='Hours after final channel return',ylabel='Forecast-target pairs')
    fig.legend(*axes[0,-1].get_legend_handles_labels(), loc='upper center', bbox_to_anchor=(.5,1.12), ncol=4, frameon=False, fontsize=7)
    for ext in ['pdf','png']:fig.savefig(figures/f'recovery_trajectory.{ext}',dpi=200,bbox_inches='tight')
    plt.close(fig);pd.concat(curves).to_csv(output/'recovery_plot_values.csv',index=False)
    interruption=pd.concat([tables[r]['InterruptionComparison'] for r in sorted(set(ROOTS.values()))],ignore_index=True).query("population=='recorded_ac'")
    fig,axes=plt.subplots(1,3,figsize=(7.0,2.0),constrained_layout=True)
    for ax,site in zip(axes,ROOTS):
        for case,group in interruption.query('site==@site').groupby('case_id'):
            ax.plot(group.horizon,group.nwis,marker='o',markersize=2,label='clean (matched)' if case=='clean' else case.replace('_',' '),linewidth=1)
        ax.set(title=TITLES[site],xticks=[1,2,3,4],xlabel='Target-end hour offset',ylabel='Interruption NWIS')
    axes[-1].legend(fontsize=5)
    for ext in ['pdf','png']:fig.savefig(figures/f'failure_by_horizon.{ext}',dpi=200)
    plt.close(fig);interruption.to_csv(output/'interruption_plot_values.csv',index=False)
    for root in set(ROOTS.values()):
        for name in ['Recovery','InterruptionComparison']:source_hashes[f'{root}/analysis/{name}.csv']=digest(f'{root}/analysis/{name}.csv')
    ledger={'status':'reviewed against cited artifacts','scope':'Unique source-row checks for integrated tables and extension narrative; human scientific review separate','claims':list(claims.values())}
    # Give stable unique identifiers after repeated source selections were merged.
    for i,claim in enumerate(ledger['claims'],1):claim['id']=f'integrated_{i:03d}'
    verify_claim_ledger(workspace,ledger)
    (output/'claim_evidence_integrated.json').write_text(json.dumps(ledger,indent=2)+'\n')
    manifest={'status':'integrated presentation generated from verified reproduced studies; manuscript review pending','code_sha256':digest(Path(__file__)),
              'source_sha256':source_hashes,'claims':len(ledger['claims']),'sites':list(ROOTS),'inference':'Separate system estimates; no pooled-site intervals',
              'files_sha256':{p.relative_to(output).as_posix():digest(p) for p in output.rglob('*') if p.is_file()}}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Generated four integrated tables, two three-system figures and',len(ledger['claims']),'checked source-row claims')


if __name__=='__main__':main()
