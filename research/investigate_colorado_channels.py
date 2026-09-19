"""Post-hoc cross-channel source investigation; never changes forecasting inputs.

Minute readings are joined only for diagnostic comparisons. No physical fault
label is inferred, and electrical identities are consistency checks rather than
independent metrological validation.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


CHANNELS={313:'poa_w_m2',314:'dc_w',315:'ac_w',316:'dc_v',317:'dc_a',
          318:'ac_v',319:'ac_a',321:'module_temp_c',327:'power_factor'}


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main(output):
    root=Path(__file__).resolve().parents[1]
    out=Path(output)
    if out.exists():
        raise FileExistsError('Use a new diagnostic output directory')
    lock=json.loads((root/'research/FINAL_PROTOCOL_LOCK.json').read_text())
    for name,expected in lock['files_sha256'].items():
        assert digest(root/name)==expected,name
    out.mkdir(parents=True)
    tables=[]
    sources={}
    records=[]
    for year in (2016,2017):
        folder=root/f'data/raw/pvdaq_4_{year}'
        manifest=json.loads((folder/'manifest.json').read_text())
        sources[str((folder/'manifest.json').relative_to(root))]=digest(folder/'manifest.json')
        for item in manifest['files']:
            if '/pvdata/' not in item['key'] or not item['key'].endswith('.parquet'):
                continue
            p=folder/Path(item['key']).name
            assert digest(p)==item['sha256'],p
            sources[str(p.relative_to(root))]=item['sha256']
            d=pd.read_parquet(p,columns=['measured_on','metric_id','value'],filters=[('metric_id','in',list(CHANNELS))])
            d['measured_on']=pd.to_datetime(d.measured_on)
            assert not d.measured_on.isna().any()
            assert not d.groupby(['measured_on','metric_id']).value.nunique(dropna=False).gt(1).any()
            d=d.drop_duplicates(['measured_on','metric_id'])
            w=d.pivot(index='measured_on',columns='metric_id',values='value').rename(columns=CHANNELS).sort_index()
            assert set(CHANNELS.values())<=set(w.columns)
            w=w.replace([np.inf,-np.inf],np.nan)
            # Preserve the repeated invalid temperature code in its own count; no
            # sentinel value enters a temperature average or forecasting data.
            sentinel=w.module_temp_c.eq(-7999)
            w['module_temp_sentinel']=sentinel.astype(float)
            w.loc[sentinel,'module_temp_c']=np.nan
            w['dc_vi_w']=w.dc_v*w.dc_a
            w['ac_vipf_w']=w.ac_v*w.ac_a*w.power_factor
            w['abs_dc_identity_error_w']=(w.dc_w-w.dc_vi_w).abs()
            w['abs_ac_identity_error_w']=(w.ac_w-w.ac_vipf_w).abs()
            count=w.resample('h').count()
            h=w.resample('h').mean().where(count.eq(60))
            h['native_hour_start']=h.index
            h['source_year']=year
            h['valid_ac_minutes']=count.ac_w
            h['valid_dc_minutes']=count.dc_w
            tables.append(h.reset_index(drop=True))
        print(f'Checked and summarized source year {year}',flush=True)
    hourly=pd.concat(tables,ignore_index=True).sort_values('native_hour_start')
    assert not hourly.native_hour_start.duplicated().any()
    hourly.to_csv(out/'hourly_cross_channel.csv',index=False)
    hourly['month']=hourly.native_hour_start.dt.strftime('%Y-%m')
    # Thresholds are post-hoc diagnostic descriptions, not exclusion rules.
    for month,part in hourly.groupby('month'):
        bright=part[part.poa_w_m2.gt(200)&part.ac_w.notna()&part.dc_w.notna()]
        near=bright[bright.ac_w.lt(10)]
        row={'month':month,'complete_bright_ac_dc_hours':len(bright),
             'bright_ac_below_10w_hours':len(near),
             'bright_ac_and_dc_below_10w_hours':int((bright.ac_w.lt(10)&bright.dc_w.lt(10)).sum()),
             'bright_module_temp_sentinel_hours':int(bright.module_temp_sentinel.eq(1).sum())}
        for name in ('ac_w','dc_w','dc_v','dc_a','ac_v','ac_a','power_factor','poa_w_m2','abs_dc_identity_error_w','abs_ac_identity_error_w'):
            row[f'bright_median_{name}']=bright[name].median()
            row[f'near_idle_median_{name}']=near[name].median()
        records.append(row)
    monthly=pd.DataFrame(records)
    monthly.to_csv(out/'monthly_cross_channel.csv',index=False)
    bright=hourly[hourly.poa_w_m2.gt(200)&hourly.ac_w.notna()&hourly.dc_w.notna()].copy()
    bright['native_date']=bright.native_hour_start.dt.date.astype(str)
    daily=bright.groupby('native_date').agg(bright_hours=('ac_w','size'),
        ac_max_w=('ac_w','max'),ac_median_w=('ac_w','median'),dc_max_w=('dc_w','max'),
        dc_median_w=('dc_w','median'),dc_v_median=('dc_v','median'),poa_median=('poa_w_m2','median'),
        module_sentinel_fraction=('module_temp_sentinel','mean')).reset_index()
    daily['all_observed_bright_ac_below_10w']=daily.ac_max_w.lt(10)
    daily.to_csv(out/'daily_bright_regime.csv',index=False)
    # Cross-check the existing primary target independently, preserving its
    # fixed +7h convention and left-hour averaging contract.
    matching=[]
    for year in (2016,2017):
        src=root/f'data/processed/final_v4/colorado/{year}/primary/hourly.parquet'
        d=pd.read_parquet(src)
        h=hourly[hourly.source_year.eq(year)].copy()
        h.index=pd.DatetimeIndex(h.native_hour_start).tz_localize('UTC')+pd.Timedelta(hours=8)
        target=d.reindex(h.index).pv
        raw=(h.ac_w/1000).clip(lower=0)
        valid=raw.notna()&target.notna()
        assert np.allclose(raw[valid],target[valid],rtol=1e-12,atol=1e-12)
        matching.append({'year':year,'compared_hours':int(valid.sum()),'maximum_absolute_error_kw':float((raw[valid]-target[valid]).abs().max())})
    pd.DataFrame(matching).to_csv(out/'normalization_crosscheck.csv',index=False)
    meta=root/'data/metadata/development_screen/metrics__system_4__part000.parquet'
    catalog=pd.read_parquet(meta)
    catalog[catalog.metric_id.isin(CHANNELS)].to_csv(out/'channel_catalog.csv',index=False)
    sources[str(meta.relative_to(root))]=digest(meta)
    result={'status':'completed post-hoc cross-channel investigation; physical cause unresolved',
      'previous_goal_turn':'progress: literature and data review changed the readiness assessment',
      'code_sha256':digest(Path(__file__)),'original_protocol_hashes_verified':len(lock['files_sha256']),
      'input_sha256':sources,'raw_daily_objects_verified':sum(k.endswith('.parquet') and '/raw/' in k for k in sources),
      'source_timezone':'native clock; crosscheck uses unchanged primary +7h to UTC and +1h interval end',
      'diagnostic_thresholds':{'bright_poa_w_m2':200,'near_idle_ac_w':10,'near_idle_dc_w':10},
      'limitations':['Thresholds and investigation selected after final-result exposure',
        'Nearby electrical channels can share sensors or calculations; not independent validation',
        'No operational incident log, module-disconnection record or calibrated instrument traceability supplied',
        'No source or forecast rows excluded or replaced'],
      'outputs_sha256':{p.name:digest(p) for p in out.glob('*.csv')}}
    (out/'manifest.json').write_text(json.dumps(result,indent=2)+'\n')
    print(monthly[['month','complete_bright_ac_dc_hours','bright_ac_below_10w_hours','bright_ac_and_dc_below_10w_hours','bright_median_dc_v','bright_module_temp_sentinel_hours']].to_string(index=False))
    print(pd.DataFrame(matching).to_string(index=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    main(parser.parse_args().output)
