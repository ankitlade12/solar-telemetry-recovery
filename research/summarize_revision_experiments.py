"""Summarize every fixed revision variant, retaining adverse and sparse results."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.analyze_final_evaluation import paired_days
from research.revision_analysis import paired_interval, daily_scores, PHASES
from solar_recovery.pilot import digest
from solar_recovery.replay import HOUR
from solar_recovery.replay_v3 import Fault


def latest_phase(origins, faults):
    """A reconnect outage supersedes the earlier event's recovery window."""
    faults = sorted(faults, key=lambda f: f.start)
    rows = []
    pointer = -1
    for origin in origins:
        while pointer+1 < len(faults) and faults[pointer+1].start <= origin:
            pointer += 1
        phase, event, hour = 'normal', -1, np.nan
        if pointer >= 0:
            f = faults[pointer]
            first, last = min(f.pv_return, f.irradiance_return), max(f.pv_return, f.irradiance_return)
            if origin < last+24*HOUR:
                event = pointer
                if origin < first:
                    phase = 'outage'
                elif origin < last:
                    phase = 'partial_restoration'
                else:
                    hour = (origin-last)/HOUR
                    phase = PHASES[0] if hour < 6 else PHASES[1]
        rows.append((phase, event, hour))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(origins, name='origin'), columns=['phase', 'event_id', 'recovery_hour'])


def summarize(output='runs/review_revision_20261015/experimental_analysis'):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    rows, support, hashes = [], [], {}
    batch = json.loads(Path('runs/review_revision_20261015/shrinkage/batch.json').read_text())
    for site in ('nist', 'reserve10'):
        runs = [r for r in batch if r['site'] == site and r['case'] != 'clean']
        for shrinkage in (50, 10, 1):
            frames = []
            for run in runs:
                path = Path(run['path'])/f'forecasts_{shrinkage}.parquet'
                hashes[str(path)] = digest(path)
                frame = pd.read_parquet(path)
                frame['case_id'] = run['case']; frames.append(frame)
                if shrinkage == 50:
                    stats = pd.read_csv(Path(run['path'])/'support_summary.csv')
                    stats['site'], stats['case_id'] = site, run['case']; support.append(stats)
            all_rows = pd.concat(frames, ignore_index=True)
            all_rows = all_rows.loc[all_rows.valid_target & all_rows.daylight & all_rows.within_period & all_rows.period.eq('evaluation')]
            daily = daily_scores(all_rows)
            for phase in PHASES:
                paired = paired_days(daily, 'physical_recovery', 'physical_availability', [phase])
                group = all_rows.loc[all_rows.method.eq('physical_recovery') & all_rows.phase.eq(phase)]
                counts = group.groupby(['case_id', 'horizon']).agg(n=('nwis', 'size'), events=('event_id', 'nunique'))
                for block in (7, 14, 28):
                    rows.append({'study': 'shrinkage', 'site': site, 'variant': shrinkage, 'phase': phase,
                                 'contrast': 'physical_recovery_minus_physical_availability',
                                 'min_pairs': counts.n.min(), 'min_events': counts.events.min(),
                                 **paired_interval(paired, block_days=block)})
        folder = Path('runs/review_revision_20261015/recovery')/site
        manifest = json.loads((folder/'manifest.json').read_text())
        if not manifest['status'].startswith('complete'):
            raise ValueError(f'Experiment not complete: {folder}')
        for case in manifest['cases']:
            case_folder = folder if case == 'joint_gradual' else Path('runs/review_revision_20261015/stress_v2')/site
            case_manifest = json.loads((case_folder/'manifest.json').read_text())
            if not case_manifest['status'].startswith('complete'):
                raise ValueError(f'Corrected stress run not complete: {case_folder}')
            path = case_folder/f'forecasts_{case}.parquet'; hashes[str(path)] = digest(path)
            frame = pd.read_parquet(path)
            if case != 'joint_gradual':
                faults = [Fault(**f) for f in json.loads((case_folder/f'schedule_{case}.json').read_text())]
                phases = latest_phase(pd.DatetimeIndex(sorted(frame.origin.unique())), faults)
                frame = frame.drop(columns=['phase', 'event_id', 'recovery_hour']).merge(phases, left_on='origin', right_index=True, validate='many_to_one')
            frame = frame.loc[frame.valid_target & frame.daylight & frame.within_period & frame.period.eq('evaluation')]
            frame.to_parquet(output/f'eligible_{site}_{case}.parquet', index=False)
            daily = daily_scores(frame)
            methods = [m for m in frame.method.unique() if m not in ['raw', 'physical_availability']]
            for method in methods:
                control = 'raw' if method in ['base_all_recovery_features', 'archive_time_oracle'] else 'physical_availability'
                for phase in [*PHASES, 'failure_recovery']:
                    phases = PHASES+['outage', 'partial_restoration'] if phase == 'failure_recovery' else [phase]
                    paired = paired_days(daily, method, control, phases)
                    counts = frame.loc[frame.method.eq(method) & frame.phase.isin(phases)].groupby(['case_id', 'horizon']).agg(n=('nwis', 'size'), events=('event_id', 'nunique'))
                    for block in (7, 14, 28):
                        rows.append({'study': 'features_and_faults', 'site': site, 'variant': case, 'phase': phase,
                                     'contrast': method+'_minus_'+control, 'min_pairs': counts.n.min(), 'min_events': counts.events.min(),
                                     **paired_interval(paired, block_days=block)})
    pd.DataFrame(rows).to_csv(output/'contrasts.csv', index=False)
    pd.concat(support, ignore_index=True).to_csv(output/'support.csv', index=False)
    (output/'manifest.json').write_text(json.dumps({'status': 'complete exploratory experimental summaries',
        'code_sha256': digest(__file__), 'inputs': hashes, 'outputs': {p.name: digest(p) for p in output.iterdir()},
        'phase_policy': 'Latest reconnect supersedes prior recovery; derived scoring only; issued forecasts unchanged',
        'scope': 'All fixed variants reported; confidence intervals exploratory and unadjusted; no selected superiority claim'}, indent=2)+'\n')


if __name__ == '__main__':
    summarize()
