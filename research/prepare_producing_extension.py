"""Qualify full native-year system-10 inputs for the separate replication."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.final_evaluation import combine_years
from solar_recovery.data_v2 import normalize
from solar_recovery.pilot import digest

SPEC = {'pv': 423, 'irradiance': 421, 'pv_unit': 'W', 'pv_to_kw': .001,
        'utc_add_hours': 7, 'alignment': 'unspecified instrument alignment; declared minute timestamp bins and full -1 minute sensitivity'}


def normalize_selected(raw, shift):
    if set(raw.metric_id.unique()) != {421, 423}:
        raise ValueError('Only the two predeclared source channels are allowed')
    if not raw.utc_measured_on.isna().all():
        raise ValueError('Source UTC availability differs from qualified snapshot')
    return normalize(raw, SPEC, 1.12, timestamp_shift_minutes=shift)


def prepare(output='data/processed/producing_extension_v1'):
    root = Path.cwd(); output = Path(output)
    if output.exists():
        raise FileExistsError('Input snapshots are immutable')
    qualification = root/'research/reserve_10_qualification_v1'
    evidence = json.loads((qualification/'manifest.json').read_text())
    decision = json.loads((qualification/'decision.json').read_text())
    for name, expected in decision['evidence_sha256'].items():
        if digest(name) != expected:
            raise ValueError(f'Qualification decision dependency changed: {name}')
    for name, expected in evidence['outputs_sha256'].items():
        if digest(qualification/name) != expected:
            raise ValueError(f'Qualification output changed: {name}')
    output.mkdir(parents=True)
    records = []; normalized = {'primary': [], 'right_aligned': []}
    for year in (2016, 2017):
        source = root/f'data/raw/extension_v1/pvdaq_10_{year}'
        manifest = json.loads((source/'manifest.json').read_text())
        expected = evidence['source_manifests_sha256'][str((source/'manifest.json').relative_to(root))]
        if digest(source/'manifest.json') != expected:
            raise ValueError('Acquired source manifest changed')
        parts = []
        for item in manifest['files']:
            path = source/Path(item['key']).name
            if digest(path) != item['sha256']:
                raise ValueError(f'Raw source changed: {path}')
            if '/pvdata/' in item['key']:
                parts.append(pd.read_parquet(path, filters=[('metric_id', 'in', [421, 423])]))
        raw = pd.concat(parts, ignore_index=True)
        raw['measured_on'] = pd.to_datetime(raw.measured_on)
        meta = json.loads((source/'10_system_metadata.json').read_text())
        metrics = pd.read_parquet(source/'metrics__system_10__part000.parquet').set_index('metric_id').loc[[421, 423]]
        assert metrics.calc_scale.eq(1).all() and metrics.calc_offset.eq(0).all()
        assert metrics.aggregation_type.eq('avg').all()
        assert metrics.loc[423, 'units'] == metrics.loc[423, 'raw_units'] == 'W'
        assert metrics.loc[421, 'units'] == metrics.loc[421, 'raw_units'] == 'W/m^2'
        assert float(meta['System']['power']) == 1.12
        assert float(meta['Site']['latitude']) == 39.7404 and float(meta['Site']['longitude']) == -105.1774
        for variant, shift, old_name in [('primary', 0, 'left'), ('right_aligned', -1, 'right')]:
            hourly, exclusions, audit = normalize_selected(raw, shift)
            # Independently constructed source-screen hourly values must agree
            # on their UTC-year subset. Final inputs retain full boundary bins.
            previous = pd.read_parquet(qualification/f'hourly_diagnostic_{year}_{old_name}.parquet')
            for col in ['pv', 'irradiance', 'pv_signed_mean_kw']:
                np.testing.assert_allclose(hourly[col].reindex(previous.index), previous[col], rtol=1e-12, atol=1e-12, equal_nan=True)
            # Direct raw productive-hour recomputation, not a model check.
            lo = pd.Timestamp(f'{year}-06-15T12:00') - pd.Timedelta(minutes=shift)
            part = raw[raw.measured_on.ge(lo) & raw.measured_on.lt(lo+pd.Timedelta(hours=1))]
            ac = part.loc[part.metric_id.eq(423), 'value']
            poa = part.loc[part.metric_id.eq(421), 'value']
            assert len(ac) == len(poa) == 60
            end = pd.Timestamp(f'{year}-06-15T20:00Z')
            np.testing.assert_allclose(hourly.loc[end, 'pv'], max(ac.mean()/1000, 0), rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(hourly.loc[end, 'irradiance'], poa.mean(), rtol=1e-12, atol=1e-12)
            folder = output/'reserve10'/str(year)/variant
            folder.mkdir(parents=True)
            hourly.to_parquet(folder/'hourly.parquet')
            exclusions.to_parquet(folder/'excluded_measurements.parquet', index=False)
            audit.update({'year': year, 'variant': variant, 'hours': len(hourly),
                'first_interval_end': hourly.index.min().isoformat(), 'last_interval_end': hourly.index.max().isoformat(),
                'diagnostic_hours_crosschecked': len(previous), 'raw_hour_ac_w': float(ac.mean()),
                'raw_hour_poa_w_m2': float(poa.mean()), 'raw_hour_target_end': end.isoformat(),
                'raw_hour_each_channel_count': 60, 'source_objects_verified': len(manifest['files'])})
            contract = {'system_id': 10, 'year': year, 'name': meta['System']['public_name'],
                'latitude': 39.7404, 'longitude': -105.1774, 'capacity_kw_dc': 1.12, 'specification': SPEC,
                'target': 'nonnegative mean of 60 recorded minute AC values in a declared timestamp bin, kW; not verified physical energy',
                'target_transform': 'max(mean(signed valid minute AC), 0); incomplete hours remain missing',
                'hour_definition': 'left-closed timestamp bins, labelled at next hour; all 60 valid distinct minutes required per channel',
                'timestamp_source': 'UTC = native +7 hours, inferred fixed MST from source qualification; not operator-confirmed',
                'timestamp_shift_minutes': shift, 'variant': variant,
                'quality_bounds': {'ac_min_kw': -.05*1.12, 'ac_max_kw': 1.5*1.12, 'poa_min_w_m2': -20., 'poa_max_w_m2': 2000.},
                'receipt_assumption': 'simulated release at bin end plus at least one minute; five-minute sensitivity; no measured arrival logs',
                'status': 'separate extension input; original experiment results already exposed; no extension forecast performance inspected',
                'source_manifest_sha256': digest(source/'manifest.json'), 'qualification_decision_sha256': digest(qualification/'decision.json'),
                'adapter_sha256': digest(Path(__file__)), 'normalizer_sha256': digest('solar_recovery/data_v2.py'),
                'hourly_sha256': digest(folder/'hourly.parquet'), 'license': manifest['license'], 'doi': manifest['doi'],
                'limitations': ['Fixed-site recorded-sample estimand; no meter certification', 'Nearby original Colorado site; no independent climate',
                    'Unspecified physical interval alignment retained through sensitivity; no arbitrary clock-drift bound',
                    'All seasons and low-output values retained under stated bounds; no label imputation']}
            (folder/'contract.json').write_text(json.dumps(contract, indent=2)+'\n')
            (folder/'audit.json').write_text(json.dumps(audit, indent=2)+'\n')
            normalized[variant].append(hourly); records.append(audit)
            print('Verified extension input', year, variant, len(hourly), 'hours', flush=True)
    merge = {}
    for variant, frames in normalized.items():
        combined = combine_years(frames)
        boundary = combined.loc['2017-01-01T06:00Z':'2017-01-01T09:00Z']
        merge[variant] = {'hours': len(combined), 'duplicate_intervals': int(combined.index.duplicated().sum()),
            'boundary_paired_validity': {str(t): bool(row.notna().all()) for t, row in boundary.iterrows()},
            'partial_bin_policy': 'partial source-year means remain missing; no imputation or combination of partial means'}
    (output/'manifest.json').write_text(json.dumps({'status': 'qualified extension inputs; no forecasts',
        'records': records, 'cross_year_merge': merge,
        'files_sha256': {str(p.relative_to(output)): digest(p) for p in output.rglob('*') if p.is_file()}}, indent=2)+'\n')


if __name__ == '__main__':
    prepare()
