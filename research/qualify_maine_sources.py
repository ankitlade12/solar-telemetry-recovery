"""Source-only Maine qualification; no forecasting or model selection.

Produces diagnostic hourly variants, not an approved experimental contract.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from solar_recovery.data import solar_elevation


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root=Path(__file__).resolve().parents[1]
    out=root/'research/maine_qualification_v1'
    if out.exists():
        raise FileExistsError(out)
    out.mkdir()
    inputs={};grid_rows=[];energy_rows=[];clock_rows=[];monthly=[];annual=[];exclusions=[]
    for year in (2016,2017):
        folder=root/f'data/raw/extension_v1/pvdaq_1239_{year}'
        manifest=json.loads((folder/'manifest.json').read_text())
        inputs[str((folder/'manifest.json').relative_to(root))]=digest(folder/'manifest.json')
        parts=[]
        for item in manifest['files']:
            p=folder/Path(item['key']).name
            assert digest(p)==item['sha256'],p
            if '/pvdata/' in item['key']:
                parts.append(pd.read_parquet(p,filters=[('metric_id','in',[3015,3018,3022])]))
        d=pd.concat(parts,ignore_index=True)
        d['measured_on']=pd.to_datetime(d.measured_on)
        assert not d.measured_on.isna().any()
        assert not d.groupby(['measured_on','metric_id']).value.nunique(dropna=False).gt(1).any()
        duplicate_rows=int(d.duplicated(['measured_on','metric_id']).sum())
        d=d.drop_duplicates(['measured_on','metric_id']).copy()
        meta=pd.read_parquet(folder/'metrics__system_1239__part000.parquet').set_index('metric_id')
        assert meta.loc[3015,'raw_units']=='kW' and meta.loc[3015,'units']=='W'
        assert meta.loc[3015,'calc_scale']==1000 and meta.loc[3015,'calc_offset']==0
        assert meta.loc[3018,'calc_scale']==1 and meta.loc[3018,'calc_offset']==0
        system=json.loads((folder/'1239_system_metadata.json').read_text())
        capacity=float(system['System']['power'])
        lat,lon=float(system['Site']['latitude']),float(system['Site']['longitude'])
        native=pd.date_range(f'{year}-01-01',f'{year+1}-01-01',freq='15min',inclusive='left')
        offgrid=~d.measured_on.eq(d.measured_on.dt.floor('15min'))
        ex=d.loc[offgrid,['measured_on','metric_id','value']].copy()
        ex['reason']='off_quarter_hour_grid';ex['source_year']=year;exclusions.append(ex)
        on=d.loc[~offgrid].pivot(index='measured_on',columns='metric_id',values='value').reindex(native)
        assert not on.index.duplicated().any()
        on=on.rename(columns={3015:'pv',3018:'irradiance',3022:'energy_kwh'})
        # The catalog transform raw kW -> W -> output kW cancels exactly.
        on['pv']=on.pv*float(meta.loc[3015,'calc_scale'])/1000
        for col,metric,bounds in [('pv',3015,(-.05*capacity,1.5*capacity)),('irradiance',3018,(-20,2000))]:
            bad=on[col].notna() & (~np.isfinite(on[col]) | ~on[col].between(*bounds))
            ex=pd.DataFrame({'measured_on':on.index[bad],'metric_id':metric,'value':on.loc[bad,col].to_numpy(),
                             'reason':'outside_declared_engineering_bounds','source_year':year})
            exclusions.append(ex)
            on.loc[bad,col]=np.nan
        on.to_parquet(out/f'quarter_hour_{year}.parquet')
        for metric,col in [(3015,'pv'),(3018,'irradiance'),(3022,'energy_kwh')]:
            grid_rows.append({'year':year,'metric_id':metric,'expected_quarter_hours':len(native),
                'on_grid_finite':int(np.isfinite(on[col]).sum()),'off_grid_records':int((offgrid & d.metric_id.eq(metric)).sum()),
                'identical_duplicate_rows_all_selected_channels':duplicate_rows})
        # Unit/interval consistency; positive counter increments only, with
        # both neighboring positive recorded powers. No outcome is imputed.
        delta=on.energy_kwh.diff()
        mask=delta.between(.01,10)&on.pv.gt(.1)&on.pv.shift().gt(.1)
        for kind,pred in [('current',on.pv*.25),('previous',on.pv.shift()*.25),('trapezoid',(on.pv+on.pv.shift())*.125)]:
            error=(delta-pred)[mask]
            energy_rows.append({'year':year,'alignment':kind,'pairs':int(mask.sum()),
                'mae_kwh':error.abs().mean(),'median_absolute_error_kwh':error.abs().median(),
                'observed_to_integrated_energy_ratio':delta[mask].sum()/pred[mask].sum()})
        for name in ('fixed_utc_plus_5','fixed_utc_plus_4','civil_eastern'):
            if name=='civil_eastern':
                utc=native.tz_localize('America/New_York',ambiguous='NaT',nonexistent='NaT').tz_convert('UTC')
            else:
                hours=5 if name.endswith('5') else 4
                utc=native.tz_localize('UTC')+pd.Timedelta(hours=hours)
            valid=~utc.isna()
            for shift in (-15,0,15):
                t=utc[valid]+pd.Timedelta(minutes=shift)
                elevation=solar_elevation(t,lat,lon)
                part=on.loc[valid]
                for threshold in (20,200):
                    bright=part.irradiance.gt(threshold).to_numpy()
                    clock_rows.append({'year':year,'clock':name,'measurement_shift_minutes':shift,
                        'poa_threshold':threshold,'nonexistent_or_ambiguous_grid_slots':int((~valid).sum()),
                        'bright_quarters':int(bright.sum()),'bright_quarters_geometric_night':int((bright&(elevation<=0)).sum())})
        # Fixed-EST diagnostic construction, with both interval interpretations.
        # Native clock evidence is not an operator-confirmed UTC convention.
        for alignment,shift in [('left',0),('right',-15)]:
            q=on[['pv','irradiance']].copy()
            q.index=q.index.tz_localize('UTC')+pd.Timedelta(hours=5,minutes=shift)
            means=q.resample('h',closed='left',label='right').mean()
            counts=q.resample('h',closed='left',label='right').count()
            h=means.where(counts.eq(4))
            # Additional irregular messages make that channel-hour ambiguous;
            # exclude it even if four regular slots also happen to be present.
            for metric,col in [(3015,'pv'),(3018,'irradiance')]:
                badtime=pd.DatetimeIndex(d.loc[offgrid&d.metric_id.eq(metric),'measured_on']).tz_localize('UTC')+pd.Timedelta(hours=5,minutes=shift)
                affected=badtime.floor('h')+pd.Timedelta(hours=1)
                h.loc[h.index.isin(affected),col]=np.nan
            h['pv_signed_mean_kw']=h.pv
            h['pv']=h.pv.clip(lower=0)
            midpoint=h.index-pd.Timedelta(minutes=30)
            inside=(midpoint>=pd.Timestamp(f'{year}-01-01',tz='UTC'))&(midpoint<pd.Timestamp(f'{year+1}-01-01',tz='UTC'))
            h=h.loc[inside].copy();midpoint=midpoint[inside]
            h['daylight']=solar_elevation(midpoint,lat,lon)>0
            h['month_utc']=midpoint.strftime('%Y-%m')
            h.to_parquet(out/f'hourly_diagnostic_{year}_{alignment}.parquet')
            for month,part in [('all',h),*list(h.groupby('month_utc'))]:
                sun=part[part.daylight]
                paired=sun[sun[['pv','irradiance']].notna().all(axis=1)]
                bright=paired[paired.irradiance.gt(200)]
                near=bright.pv.lt(.01*capacity)
                row={'year':year,'alignment':alignment,'month':month,'daylight_hours':len(sun),
                    'paired_daylight_hours':len(paired),'paired_fraction':len(paired)/len(sun) if len(sun) else np.nan,
                    'bright_hours':len(bright),'near_idle_bright_hours':int(near.sum()),
                    'near_idle_bright_fraction':near.mean() if len(bright) else np.nan,
                    'daylight_mean_ac_kw':paired.pv.mean(),'daylight_mean_poa_w_m2':paired.irradiance.mean()}
                (annual if month=='all' else monthly).append(row)
        # Retain transition-date counts separately from a seasonal inference.
        dst_dates=['2016-03-13','2016-11-06'] if year==2016 else ['2017-03-12','2017-11-05']
        for date in dst_dates:
            grid_rows.append({'year':year,'metric_id':'DST_date_'+date,'expected_quarter_hours':96,
                'on_grid_finite':int(on.loc[date,['pv','irradiance']].notna().all(axis=1).sum()),
                'off_grid_records':int((offgrid&d.measured_on.dt.strftime('%Y-%m-%d').eq(date)).sum()),
                'identical_duplicate_rows_all_selected_channels':duplicate_rows})
        print('Qualified descriptive source checks for',year,flush=True)
    for name,rows in [('grid_audit',grid_rows),('energy_consistency',energy_rows),('clock_diagnostics',clock_rows),('monthly_quality',monthly),('annual_quality',annual)]:
        pd.DataFrame(rows).to_csv(out/f'{name}.csv',index=False)
    pd.concat(exclusions,ignore_index=True).to_csv(out/'excluded_records.csv',index=False)
    (out/'manifest.json').write_text(json.dumps({'status':'source diagnostics complete; experimental admission pending interpretation',
        'forecast_performance_inspected':False,'code_sha256':digest(Path(__file__)),
        'source_manifests_sha256':inputs,'qualification_plan_sha256':digest(root/'research/EXTENSION_SOURCE_QUALIFICATION_PLAN.md'),
        'hourly_definition':'mean of four expected quarter-hour records; incomplete or off-grid-affected channel-hours missing; signed AC mean clipped only after aggregation',
        'clock':'fixed UTC+5 diagnostic assumption, not externally confirmed; civil and UTC+4 alternatives checked separately',
        'excluded_records_units':'Off-grid values are raw stored units; bound-failure values are transformed kW/POA W/m2',
        'outputs_sha256':{p.name:digest(p) for p in out.iterdir()}},indent=2)+'\n')
    print(pd.DataFrame(annual).to_string(index=False))


if __name__=='__main__':
    main()
