"""Reproduce the separate C10 2021 analysis into a fresh directory."""
import argparse
import json
from pathlib import Path
import pandas as pd
from research.revision_analysis import daily_scores, paired_interval, PHASES
from research.analyze_final_evaluation import paired_days
from solar_recovery.pilot import digest


def analyze(output):
    root=Path('runs/review_revision_20261015/new_year')
    output=Path(output); output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((root/'manifest.json').read_text())
    frames=[]; hashes={}
    for path in sorted(root.glob('forecasts_*.parquet')):
        hashes[str(path)]=digest(path)
        if manifest['cases'][path.stem.removeprefix('forecasts_')]['forecast_sha256'] != digest(path):
            raise ValueError(f'Changed forecast: {path}')
        f=pd.read_parquet(path); f['case_id']=path.stem.removeprefix('forecasts_')
        frames.append(f.loc[f.valid_target & f.daylight & f.within_period & f.period.eq('evaluation')])
    frame=pd.concat(frames,ignore_index=True); rows=[]
    for pool in ('primary','joint_gradual','right_aligned'):
        f=frame.loc[~frame.case_id.isin(['clean','right_aligned'])] if pool=='primary' else frame.loc[frame.case_id.eq(pool)]
        daily=daily_scores(f)
        for phase in PHASES:
            paired=paired_days(daily,'physical_recovery','physical_availability',[phase])
            counts=f.loc[f.method.eq('physical_recovery') & f.phase.eq(phase)].groupby(['case_id','horizon']).agg(n=('nwis','size'),events=('event_id','nunique'))
            for block in (7,14,28):
                rows.append(dict(pool=pool,phase=phase,min_pairs=int(counts.n.min()),min_events=int(counts.events.min()),
                    **paired_interval(paired,block_days=block,start='2021-02-01T00:00Z',end='2022-01-01T00:00Z')))
    pd.DataFrame(rows).to_csv(output/'contrasts.csv',index=False)
    frame.groupby(['case_id','method','phase','horizon']).agg(n=('nwis','size'),nwis=('nwis','mean'),coverage90=('coverage90','mean')).reset_index().to_csv(output/'cells.csv',index=False)
    (output/'manifest.json').write_text(json.dumps(dict(status='complete separately declared new-year analysis',code_sha256=digest(__file__),inputs=hashes,outputs={p.name:digest(p) for p in output.iterdir()}),indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',required=True)
    analyze(parser.parse_args().output)
