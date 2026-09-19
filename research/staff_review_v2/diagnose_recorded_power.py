"""Post-exposure source diagnostics; no fitting, exclusions or significance tests.

Run from repository root: python3 -m research.staff_review_v2.diagnose_recorded_power
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from solar_recovery.data import solar_elevation


def main():
    root = Path(__file__).resolve().parents[2]
    out = Path(__file__).resolve().parent / 'diagnostics'
    if out.exists():
        raise FileExistsError(out)
    lock = json.loads((root / 'research/FINAL_PROTOCOL_LOCK.json').read_text())
    hashes = lock['files_sha256']
    for name, expected in hashes.items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest() == expected, name
    out.mkdir()
    inputs = {}
    def read(path):
        inputs[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return pd.read_parquet(path)
    monthly, totals = [], []
    for site in ('nist', 'colorado'):
        for year in (2016, 2017):
            for variant in (('primary','narrow_quality','right_aligned') if site == 'colorado' and year == 2017 else ('primary',)):
                base = root/f'data/processed/final_v4/{site}/{year}/{variant}'
                c = json.loads((base/'contract.json').read_text())
                cap = c['capacity_kw_dc']
                d = read(base/'hourly.parquet')
                midpoint = d.index-pd.Timedelta(minutes=30)
                use = ((midpoint >= pd.Timestamp(f'{year}-02-01',tz='UTC')) &
                       (midpoint < pd.Timestamp(f'{year+1}-01-01',tz='UTC')) &
                       (solar_elevation(midpoint,c['latitude'],c['longitude'])>0))
                d = d.loc[use].copy()
                d['month'] = (d.index-pd.Timedelta(minutes=30)).strftime('%Y-%m')
                for month, part in [('all',d),*list(d.groupby('month'))]:
                    valid = part.pv.notna()
                    bright = valid & part.irradiance.gt(200)
                    near = valid & part.pv.lt(.01*cap)
                    row = dict(site=site,year=year,variant=variant,month=month,
                               geometric_daylight_hours=len(part),valid_pv_hours=int(valid.sum()),
                               pv_mean_kw=part.pv.mean(),pv_median_kw=part.pv.median(),
                               pv_min_kw=part.pv.min(),pv_max_kw=part.pv.max(),
                               poa_mean_w_m2=part.irradiance.mean(),exact_zero_hours=int(part.pv.eq(0).sum()),
                               below_one_percent_capacity_hours=int(near.sum()),
                               bright_valid_hours=int(bright.sum()),bright_near_idle_hours=int((bright & near).sum()))
                    (totals if month=='all' else monthly).append(row)
    pd.DataFrame(monthly).to_csv(out/'monthly_source_power.csv',index=False)
    pd.DataFrame(totals).to_csv(out/'source_power_summary.csv',index=False)
    # Deduplicate targets: neither methods nor four overlapping horizons are extra observations.
    target_rows=[]
    for site in ('nist','colorado'):
        d=read(root/f'runs/final_2017_v4/{site}/forecasts_clean.parquet')
        d=d[d.method.eq('raw') & d.period.eq('evaluation') & d.within_period & d.valid_target & d.daylight]
        assert not d.empty
        assert d.groupby('target_end').actual_kw.nunique().eq(1).all()
        unique=d.drop_duplicates('target_end').sort_values('target_end')
        source=read(root/f'data/processed/final_v4/{site}/2017/primary/hourly.parquet')
        assert np.array_equal(unique.actual_kw.to_numpy(),source.reindex(unique.target_end).pv.to_numpy())
        cap=float(unique.capacity_kw_dc.iloc[0])
        target_rows.append(dict(site=site,unique_scored_targets=len(unique),
          below_one_percent_capacity_targets=int(unique.actual_kw.lt(.01*cap).sum()),
          exact_zero_targets=int(unique.actual_kw.eq(0).sum()),median_kw=unique.actual_kw.median()))
    pd.DataFrame(target_rows).to_csv(out/'unique_scored_target_audit.csv',index=False)
    summary=root/'runs/final_2017_v4/analysis/Summary.csv'
    inputs[str(summary.relative_to(root))]=hashlib.sha256(summary.read_bytes()).hexdigest()
    s=pd.read_csv(summary)
    s=s[s.population.eq('recorded_ac') & s.endpoint.eq('failure_recovery') &
        s.method.isin(['raw','physical','physical_availability','physical_recovery','previous_day','geometric_persistence'])]
    assert len(s)==12
    s.to_csv(out/'existing_summary_rows.csv',index=False)
    result=dict(status='post-hoc descriptive diagnosis; no changed scientific experiment',
                original_protocol_files_verified=len(hashes),inputs_sha256=inputs,
                code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                scope='February-December geometric-daylight source hours, grouped by target midpoint; scored-target counts separately use original clean evaluation eligibility',
                threshold='recorded power < 0.01 * DC capacity; selected after performance exposure, diagnostic only',
                excluded_targets=0,models_refit=0,
                outputs_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob('*.csv'))})
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(pd.DataFrame(totals).to_string(index=False))
    print(pd.DataFrame(target_rows).to_string(index=False))


if __name__=='__main__':
    main()
