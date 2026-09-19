"""Descriptive qualification of predeclared PVDAQ system 10; no forecasts."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from solar_recovery.data import solar_elevation


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / 'research/reserve_10_qualification_v1'
    folders = [root / f'data/raw/extension_v1/pvdaq_10_{y}' for y in (2016, 2017)]
    assert all((p / 'manifest.json').exists() for p in folders), 'Wait for acquisition'
    assert not out.exists(), out
    out.mkdir()
    inputs = {}; inventory = []; grid_rows = []; clock_rows = []; quality = []; excluded = []
    for year, folder in zip((2016, 2017), folders):
        manifest = json.loads((folder / 'manifest.json').read_text())
        inputs[str((folder / 'manifest.json').relative_to(root))] = sha(folder / 'manifest.json')
        parts = []
        for item in manifest['files']:
            path = folder / Path(item['key']).name
            assert sha(path) == item['sha256'], path
            if '/pvdata/' in item['key']:
                parts.append(pd.read_parquet(path, filters=[('metric_id', 'in', [421, 423])]))
        d = pd.concat(parts, ignore_index=True)
        d['measured_on'] = pd.to_datetime(d.measured_on)
        assert not d.measured_on.isna().any()
        conflicts = d.groupby(['metric_id', 'measured_on']).value.nunique(dropna=False).gt(1)
        assert not conflicts.any(), 'Conflicting timestamp/channel values: stop qualification'
        duplicates = int(d.duplicated(['metric_id', 'measured_on']).sum())
        d = d.drop_duplicates(['metric_id', 'measured_on']).copy()
        meta = pd.read_parquet(folder / 'metrics__system_10__part000.parquet').set_index('metric_id')
        assert meta.loc[423, 'raw_units'] == meta.loc[423, 'units'] == 'W'
        assert (meta.loc[[421, 423], 'calc_scale'] == 1).all()
        assert (meta.loc[[421, 423], 'calc_offset'] == 0).all()
        system = json.loads((folder / '10_system_metadata.json').read_text())
        capacity = float(system['System']['power'])
        lat, lon = float(system['Site']['latitude']), float(system['Site']['longitude'])
        for metric in (421, 423):
            channel = d[d.metric_id.eq(metric)].sort_values('measured_on')
            gaps = channel.measured_on.diff().dt.total_seconds()
            short = gaps[(gaps > 0) & (gaps <= 3600)]
            assert short.mode().iloc[0] == 60, 'Nominal cadence differs: record before adapting'
            for month in range(1, 13):
                part = channel[channel.measured_on.dt.month.eq(month)]
                values = part.value.replace([np.inf, -np.inf], np.nan).dropna()
                inventory.append({'year': year, 'month': month, 'metric_id': metric,
                    'rows': len(part), 'utc_populated': int(part.utc_measured_on.notna().sum()),
                    'raw_min': values.min(), 'raw_median': values.median(), 'raw_max': values.max(),
                    'nominal_cadence_seconds': 60})
        native = pd.date_range(f'{year}-01-01', f'{year+1}-01-01', freq='min', inclusive='left')
        offgrid = ~d.measured_on.eq(d.measured_on.dt.floor('min'))
        ex = d.loc[offgrid, ['measured_on', 'metric_id', 'value']].copy()
        ex['reason'] = 'off_minute_grid'; ex['source_year'] = year; excluded.append(ex)
        on = d.loc[~offgrid].pivot(index='measured_on', columns='metric_id', values='value').reindex(native)
        on = on.rename(columns={421: 'irradiance', 423: 'pv'})
        on['pv'] = on.pv / 1000
        for col, metric, bounds in [('pv', 423, (-.05*capacity, 1.5*capacity)), ('irradiance', 421, (-20, 2000))]:
            bad = on[col].notna() & (~np.isfinite(on[col]) | ~on[col].between(*bounds))
            ex = pd.DataFrame({'measured_on': on.index[bad], 'metric_id': metric,
                'value': on.loc[bad, col].to_numpy(), 'reason': 'outside_declared_engineering_bounds', 'source_year': year})
            excluded.append(ex); on.loc[bad, col] = np.nan
            grid_rows.append({'year': year, 'metric_id': metric, 'expected_minutes': len(native),
                'finite_valid_minutes': int(np.isfinite(on[col]).sum()),
                'off_grid_records': int((offgrid & d.metric_id.eq(metric)).sum()),
                'bound_failures': int(bad.sum()), 'identical_duplicates_both_channels': duplicates})
        on.to_parquet(out / f'minute_{year}.parquet')
        for clock in ('fixed_mst', 'fixed_mdt', 'civil_mountain'):
            if clock == 'civil_mountain':
                utc = native.tz_localize('America/Denver', ambiguous='NaT', nonexistent='NaT').tz_convert('UTC')
            else:
                utc = native.tz_localize('UTC') + pd.Timedelta(hours=7 if clock == 'fixed_mst' else 6)
            valid = ~utc.isna()
            for shift in (-1, 0, 1):
                elevation = solar_elevation(utc[valid] + pd.Timedelta(minutes=shift), lat, lon)
                part = on.loc[valid]
                for threshold in (20, 200):
                    bright = part.irradiance.gt(threshold).to_numpy()
                    clock_rows.append({'year': year, 'clock': clock, 'measurement_shift_minutes': shift,
                        'poa_threshold': threshold, 'ambiguous_or_nonexistent_slots': int((~valid).sum()),
                        'bright_minutes': int(bright.sum()), 'bright_minutes_geometric_night': int((bright & (elevation <= 0)).sum())})
        for alignment, shift in [('left', 0), ('right', -1)]:
            q = on.copy()
            q.index = q.index.tz_localize('UTC') + pd.Timedelta(hours=7, minutes=shift)
            means = q.resample('h', closed='left', label='right').mean()
            counts = q.resample('h', closed='left', label='right').count()
            hourly = means.where(counts.eq(60))
            for metric, col in [(423, 'pv'), (421, 'irradiance')]:
                badtime = pd.DatetimeIndex(d.loc[offgrid & d.metric_id.eq(metric), 'measured_on']).tz_localize('UTC')
                badtime = badtime + pd.Timedelta(hours=7, minutes=shift)
                affected = badtime.floor('h') + pd.Timedelta(hours=1)
                hourly.loc[hourly.index.isin(affected), col] = np.nan
            hourly['pv_signed_mean_kw'] = hourly.pv
            hourly['pv'] = hourly.pv.clip(lower=0)
            mid = hourly.index - pd.Timedelta(minutes=30)
            inside = (mid >= pd.Timestamp(f'{year}-01-01', tz='UTC')) & (mid < pd.Timestamp(f'{year+1}-01-01', tz='UTC'))
            hourly = hourly.loc[inside].copy(); mid = mid[inside]
            hourly['daylight'] = solar_elevation(mid, lat, lon) > 0
            hourly['month_utc'] = mid.strftime('%Y-%m')
            hourly.to_parquet(out / f'hourly_diagnostic_{year}_{alignment}.parquet')
            for month, part in [('all', hourly), *list(hourly.groupby('month_utc'))]:
                sun = part[part.daylight]
                paired = sun[sun[['pv', 'irradiance']].notna().all(axis=1)]
                bright = paired[paired.irradiance.gt(200)]
                near = bright.pv.lt(.01 * capacity)
                quality.append({'year': year, 'alignment': alignment, 'month': month,
                    'daylight_hours': len(sun), 'paired_daylight_hours': len(paired),
                    'paired_fraction': len(paired)/len(sun) if len(sun) else np.nan,
                    'bright_hours': len(bright), 'near_idle_bright_hours': int(near.sum()),
                    'near_idle_bright_fraction': near.mean() if len(bright) else np.nan,
                    'daylight_mean_ac_kw': paired.pv.mean(), 'daylight_mean_poa_w_m2': paired.irradiance.mean()})
        print('Completed source-only checks for reserve system 10,', year, flush=True)
    for name, rows in [('monthly_inventory', inventory), ('grid_audit', grid_rows), ('clock_diagnostics', clock_rows), ('quality', quality)]:
        pd.DataFrame(rows).to_csv(out / f'{name}.csv', index=False)
    pd.concat(excluded, ignore_index=True).to_csv(out / 'excluded_records.csv', index=False)
    (out / 'code_snapshot.py').write_bytes(Path(__file__).read_bytes())
    record = {'status': 'diagnostics complete; admission pending interpretation', 'forecast_performance_inspected': False,
        'code_sha256': sha(Path(__file__)), 'source_manifests_sha256': inputs,
        'plan_sha256': sha(root / 'research/RESERVE_SOURCE_10_PLAN.md'),
        'clock': 'fixed MST assumed for hourly diagnostics; alternative clocks checked; not operator-confirmed',
        'excluded_units': 'off-grid raw W or W/m2; bound-failures transformed kW or W/m2',
        'outputs_sha256': {p.name: sha(p) for p in out.iterdir()}}
    (out / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n')
    print(pd.DataFrame(quality).query("month == 'all'").to_string(index=False))


if __name__ == '__main__':
    main()
