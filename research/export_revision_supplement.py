"""Supplement tables and complete support ledger from the recorded revision runs."""
import json
from pathlib import Path
import pandas as pd
from research.export_review_revision import table, LABELS
from solar_recovery.pilot import digest


def export():
    out=Path('paper/review_supplement_evidence_20261015');out.mkdir(parents=True,exist_ok=False)
    root=Path('runs/review_revision_20261015'); inputs={}; frames=[]; clean=[]
    for run in json.loads((root/'shrinkage/batch.json').read_text()):
        for a in (50,10,1):
            p=Path(run['path'])/f'diagnostics_{a}.parquet';inputs[str(p)]=digest(p)
            f=pd.read_parquet(p);f['site']=run['site'];f['case_id']=run['case'];f['shrinkage']=a;frames.append(f)
            if run['case']=='clean':
                for method,g in f.groupby('method'):
                    clean.append(dict(site=run['site'],shrinkage=a,method=method,nwis=g.groupby('horizon').nwis.mean().mean()))
    f=pd.concat(frames,ignore_index=True)
    rows=[]
    for keys,g in f.groupby(['site','case_id','shrinkage','method','phase']):
        row=dict(zip(['site','case_id','shrinkage','method','phase'],keys));row.update(records=len(g),
          insufficient_fraction=g.fallback.eq('insufficient_scores').mean(),no_match_fraction=g.fallback.eq('global_pool').mean(),
          genuine_zero_fraction=(g.fallback.eq('none') & g[['correction50','correction80','correction90']].eq(0).all(axis=1)).mean())
        for col in ('local_effective_n','mixing_strength','effective_n'):
            for q in (.1,.5,.9):row[f'{col}_p{int(q*100)}']=g[col].quantile(q)
        rows.append(row)
    pd.DataFrame(rows).to_csv(out/'support_by_case_phase.csv',index=False)
    pd.DataFrame(clean).to_csv(out/'clean_scores.csv',index=False)
    rows=[]
    for (site,phase),g in f.loc[f.shrinkage.eq(50)&f.method.eq('physical_recovery')&~f.case_id.eq('clean')].groupby(['site','phase']):
        quant=lambda c:'/'.join(f'{v:.2f}' for v in g[c].quantile([.1,.5,.9]))
        rows.append([LABELS[site],phase.replace('_',r'\_'),quant('local_effective_n'),quant('mixing_strength'),f'{100*g.fallback.eq("global_pool").mean():.2f}',f'{100*g.fallback.eq("insufficient_scores").mean():.2f}'])
    table(out/'support.tex','Original recovery calibrator support, pooled records from seven fault cases.','tab:support',['Site','Phase','Local ESS 10/50/90','Lambda 10/50/90','No match (\%)','Insuff. (\%)'],rows,'These are pooled-record quantiles, not quantiles of case medians. Complete case/state-phase rates, post-mixture ESS and exact-zero rates are in support\_by\_case\_phase.csv. Night targets are excluded from this daylight evaluation.')
    rows=[]
    for site in LABELS:
        for a in (50,10,1):
            g=pd.DataFrame(clean).query('site == @site and shrinkage == @a').set_index('method')
            rows.append([LABELS[site],a,f'{g.loc["physical_availability","nwis"]:.6f}',f'{g.loc["physical_recovery","nwis"]:.6f}'])
    table(out/'clean.tex','Clean-delivery scores for all shrinkage constants.','tab:clean',['Site','$a$','Availability NWIS','Recovery NWIS'],rows)
    p=root/'analysis/decision_losses.csv';inputs[str(p)]=digest(p);d=pd.read_csv(p)
    rows=[]
    for _,r in d.query('block_days == 7').iterrows():
        rows.append([LABELS[r.site],r.phase.replace('recovery_','').replace('_','--'),int(r.cost_ratio),'R--A' if r.contrast.startswith('physical_recovery') else 'A--Raw',f'{r.right_mean:.5f}',f'{r.relative_pct:+.3f}',f'[{r.relative_lower_pct:+.3f}, {r.relative_upper_pct:+.3f}]'])
    table(out/'decisions.tex','Illustrative normalized commitment loss; seven-day 95\% intervals.','tab:decision',['Site','Window (h)','$r$','Contrast','Baseline','$\Delta$ (\%)','CI (\%)'],rows,'R--A: recovery minus availability. A--Raw: availability minus raw. These are exploratory loss comparisons, not realized currency or multiplicity-adjusted claims. Full 7/14/28-day results are supplied as CSV.')
    p=root/'new_year/analysis/contrasts.csv';inputs[str(p)]=digest(p);d=pd.read_csv(p)
    table(out/'new_year.tex','C10 2021: unchanged 2016 model, fresh January calibration.','tab:year',['Pool','Window (h)','Availability NWIS','$\Delta$ (\%)','95\% CI (\%)'],[[r.pool.replace('_',r'\_'),r.phase.replace('recovery_','').replace('_','--'),f'{r.right_mean:.5f}',f'{r.relative_pct:+.3f}',f'[{r.relative_lower_pct:+.3f}, {r.relative_upper_pct:+.3f}]'] for _,r in d.query('block_days == 7').iterrows()])
    p=root/'analysis/contrasts.csv';inputs[str(p)]=digest(p);d=pd.read_csv(p)
    table(out/'equivalence.tex','Four-contrast Bonferroni intervals for the original rule.','tab:eq',['Site','Window (h)','Block (days)','$\Delta$ (\%)','98.75\% CI (\%)'],[[LABELS[r.site],r.phase.replace('recovery_','').replace('_','--'),int(r.block_days),f'{r.relative_pct:+.3f}',f'[{r.relative_lower_pct:+.3f}, {r.relative_upper_pct:+.3f}]'] for _,r in d.loc[d.confidence.eq(.9875)&d.clock.isna()].iterrows()])
    (out/'manifest.json').write_text(json.dumps(dict(code_sha256=digest(__file__),inputs=inputs,outputs={p.name:digest(p) for p in out.iterdir()}),indent=2)+'\n')

if __name__=='__main__':export()
