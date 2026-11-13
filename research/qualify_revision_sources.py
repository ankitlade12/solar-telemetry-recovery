"""Qualify newly downloaded sources before any new-year forecast inspection."""
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from research.prepare_producing_extension import normalize_selected, SPEC
from solar_recovery.baselines_v3 import geometry
from solar_recovery.pilot import digest
from solar_recovery.data_v2 import normalize


def qualify(year, output=None):
    root = Path(f'data/raw/review_revision_20261015/pvdaq_10_{year}')
    manifest = json.loads((root/'manifest.json').read_text())
    frames = []
    for item in manifest['files']:
        p = root/Path(item['key']).name
        if digest(p) != item['sha256']:
            raise ValueError(f'Changed public source {p}')
        if '/pvdata/' in item['key']:
            frames.append(pd.read_parquet(p, filters=[('metric_id', 'in', [421, 423])]))
    raw = pd.concat(frames, ignore_index=True)
    metrics = pd.read_parquet(root/'metrics__system_10__part000.parquet').set_index('metric_id').loc[[421, 423]]
    if not metrics.calc_scale.eq(1).all() or not metrics.calc_offset.eq(0).all() or not metrics.aggregation_type.eq('avg').all():
        raise ValueError('Changed channel semantics')
    if metrics.loc[421, 'units'] != 'W/m^2' or metrics.loc[423, 'units'] != 'W':
        raise ValueError('Changed units')
    contract = json.loads(Path('data/processed/producing_extension_v1/reserve10/2017/primary/contract.json').read_text())
    metadata = json.loads((root/'10_system_metadata.json').read_text())
    if float(metadata['System']['power']) != contract['capacity_kw_dc']:
        raise ValueError('Changed system capacity')
    output = Path(output or f'data/processed/review_revision_20261015/reserve10_{year}')
    output.mkdir(parents=True, exist_ok=False)
    if not raw.utc_measured_on.notna().all():
        raise ValueError('New year has incomplete source UTC; cannot admit using old fixed-offset assumption')
    # Existing normalizer accepts a source-UTC/native consistency pair. Here both
    # coordinates explicitly represent source UTC; original raw files stay intact.
    raw['measured_on'] = raw['utc_measured_on']
    # Conflicting duplicates have no defensible value: exclude every conflicting
    # record, leaving its minute/hour missing rather than selecting a winner.
    keys = ['utc_measured_on', 'metric_id']
    conflict = raw.groupby(keys).value.transform(lambda x: x.nunique(dropna=False)).gt(1)
    raw.loc[conflict].to_parquet(output/'conflicting_source_records.parquet', index=False)
    raw = raw.loc[~conflict].copy()
    specification = {**SPEC, 'utc_add_hours': 0}
    monthly = []
    for alignment, shift in [('primary', 0), ('right_aligned', -1)]:
        hourly, exclusions, audit = normalize(raw, specification, contract['capacity_kw_dc'], timestamp_shift_minutes=shift)
        folder = output/alignment; folder.mkdir()
        hourly.to_parquet(folder/'hourly.parquet')
        exclusions.to_parquet(folder/'exclusions.parquet', index=False)
        updated = {**contract, 'year': year, 'status': 'post-review source qualification before forecast inspection',
                   'specification': specification, 'timestamp_source': 'source UTC used directly; native-clock offsets not used',
                   'variant': alignment, 'timestamp_shift_minutes': shift, 'source_manifest_sha256': digest(root/'manifest.json'),
                   'hourly_sha256': digest(folder/'hourly.parquet')}
        (folder/'contract.json').write_text(json.dumps(updated, indent=2)+'\n')
        # Reindex the entire year: absent source days/months must count against support.
        full = pd.date_range(f'{year}-01-01T01:00Z', f'{year+1}-01-01T00:00Z', freq='h')
        frame = hourly.reindex(full)
        frame['daylight'] = geometry(frame.index, contract) > 0
        frame['month'] = (frame.index-pd.Timedelta(minutes=30)).month
        for month, group in frame.groupby('month'):
            day = group.loc[group.daylight]
            paired = day.loc[day[['pv', 'irradiance']].notna().all(axis=1)]
            bright = paired.loc[paired.irradiance > 200]
            monthly.append({'variant': alignment, 'month': month, 'daylight_hours': len(day), 'paired_hours': len(paired),
                            'paired_fraction': len(paired)/len(day), 'bright_hours': len(bright),
                            'near_idle_fraction': (bright.pv < .01*contract['capacity_kw_dc']).mean() if len(bright) else np.nan})
        (folder/'audit.json').write_text(json.dumps(audit, indent=2)+'\n')
    table = pd.DataFrame(monthly)
    table.to_csv(output/'monthly_quality.csv', index=False)
    admitted = bool(table.paired_fraction.ge(.7).all() and table.near_idle_fraction.notna().all() and table.near_idle_fraction.le(.1).all())
    decision = {'admitted': admitted, 'forecast_performance_inspected': False,
                'scope': 'new year at same system; no new independent climate; source UTC with alignment sensitivity',
                'inputs': {str(root/'manifest.json'): digest(root/'manifest.json')}, 'code_sha256': digest(__file__),
                'outputs': {str(p.relative_to(output)): digest(p) for p in output.rglob('*') if p.is_file()},
                'other_candidates': {'nist_2018': '73 daily files; fails all-month source coverage',
                                     '1199': 'Downloaded 2016/2017; catalog has no irradiance channel; not eligible for unchanged PV/POA experiment'}}
    (output/'decision.json').write_text(json.dumps(decision, indent=2)+'\n')
    print(table.to_string(index=False)); print('Admitted:', admitted)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--year', type=int, default=2019)
    parser.add_argument('--output')
    args = parser.parse_args()
    qualify(args.year, args.output)
