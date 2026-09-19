"""Source-only channel/cadence screen of the declared Nevada and Maine candidates."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'research/extension_source_screen_v1'
    assert not out.exists()
    folders=[root/f'data/raw/extension_v1/pvdaq_{s}_{y}' for s in (1367,1239) for y in (2016,2017)]
    assert all((p/'manifest.json').exists() for p in folders),'Wait for acquisition to complete'
    out.mkdir()
    rows=[];inputs={};summaries=[]
    for site,ids in [(1367,[3091,4195]),(1239,[3015,3018])]:
        for year in (2016,2017):
            folder=root/f'data/raw/extension_v1/pvdaq_{site}_{year}'
            manifest=json.loads((folder/'manifest.json').read_text())
            inputs[str((folder/'manifest.json').relative_to(root))]=sha(folder/'manifest.json')
            parts=[]
            for item in manifest['files']:
                p=folder/Path(item['key']).name
                assert sha(p)==item['sha256'],p
                if '/pvdata/' in item['key'] and p.suffix=='.parquet':
                    d=pd.read_parquet(p,filters=[('metric_id','in',ids)])
                    parts.append(d)
            d=pd.concat(parts,ignore_index=True)
            d['measured_on']=pd.to_datetime(d.measured_on)
            assert not d.measured_on.isna().any()
            conflicts=int(d.groupby(['metric_id','measured_on']).value.nunique(dropna=False).gt(1).sum())
            d=d.drop_duplicates(['metric_id','measured_on','value'])
            metadata=pd.read_parquet(folder/f'metrics__system_{site}__part000.parquet').set_index('metric_id')
            system=json.loads((folder/f'{site}_system_metadata.json').read_text())
            summaries.append({'system_id':site,'year':year,'capacity_kw_dc':float(system['System']['power']),
                'selected_channel_conflicts':conflicts,'utc_populated_rows':int(d.utc_measured_on.notna().sum()),
                'selected_rows':len(d),'status':'not yet qualified: native-clock screening only; scaling/cadence/physical plausibility need review'})
            for metric in ids:
                all_metric=d[d.metric_id.eq(metric)].sort_values('measured_on')
                m=metadata.loc[metric]
                for month in range(1,13):
                    part=all_metric[all_metric.measured_on.dt.month.eq(month)]
                    values=part.value.replace([np.inf,-np.inf],np.nan).dropna()
                    times=part.measured_on.drop_duplicates()
                    delta=times.diff().dt.total_seconds()
                    short=delta[(delta>0)&(delta<=3600)]
                    rows.append({'system_id':site,'year':year,'month':month,'metric_id':metric,
                        'sensor_name':m.sensor_name,'catalog_units':m.units,'catalog_scale':m.calc_scale,'catalog_offset':m.calc_offset,
                        'rows':len(part),'distinct_native_timestamps':len(times),'finite_values':len(values),
                        'utc_populated':int(part.utc_measured_on.notna().sum()),'positive_values':int(values.gt(0).sum()),
                        'raw_min':values.min(),'raw_median':values.median(),'raw_q99':values.quantile(.99),'raw_max':values.max(),
                        'short_gap_median_seconds':short.median(),'short_gap_mode_seconds':short.mode().iloc[0] if len(short) else np.nan,
                        'native_hours_with_samples':int(times.dt.floor('h').nunique())})
            print('Screened',site,year,'selected rows',len(d),flush=True)
    pd.DataFrame(rows).to_csv(out/'monthly_channel_inventory.csv',index=False)
    pd.DataFrame(summaries).to_csv(out/'candidate_status.csv',index=False)
    record={'status':'completed descriptive source screen; no candidate admitted to forecasting',
        'code_sha256':sha(Path(__file__)),'plan_sha256':sha(root/'research/EXTENSION_SOURCE_QUALIFICATION_PLAN.md'),
        'input_manifests_sha256':inputs,'outputs_sha256':{p.name:sha(p) for p in out.glob('*.csv')},
        'scope':'All acquired daily objects hash-checked; only preselected AC/POA channel values inspected. Native clock, untransformed raw value summaries; no claim that UTC, scale or interval alignment is qualified.'}
    (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    print(pd.DataFrame(summaries).to_string(index=False))


if __name__=='__main__':
    main()
