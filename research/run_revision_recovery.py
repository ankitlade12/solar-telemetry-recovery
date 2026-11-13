"""Fixed feature-family ablations and weather-correlated receipt stress experiments."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import pickle

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from research.final_evaluation import combine_years, load_input, final_scores, case_faults
from research.revision_recovery import recovery_features, RecoveryKernelCalibrator, FAMILIES, realistic_faults, transport_stress
from research.revision_calibration import DiagnosticCalibrator
from solar_recovery.baselines_v3 import QuantileForecaster, geometry
from solar_recovery.pilot import digest
from solar_recovery.replay import HOUR, observations_from_hourly
from solar_recovery.replay_v3 import calendar_faults, deliver_schedule


def calibrate(features, bases, events, contract, parameters):
    calibrators = {m: DiagnosticCalibrator(m, **parameters) for m in ('physical_availability', 'physical_recovery')}
    calibrators.update({f'kernel_{f}': RecoveryKernelCalibrator(f, **parameters) for f in [*FAMILIES, 'all']})
    labels = sorted((e for e in events if e.stream == 'pv'), key=lambda e: (e.receipt, e.end, e.id))
    pointer = 0
    predictions = {m: {h: [] for h in bases} for m in calibrators}
    solar = {h: geometry(features.index.floor('h')+h*HOUR, contract) for h in bases}
    for i, (origin, visible) in enumerate(features.iterrows()):
        while pointer < len(labels) and labels[pointer].receipt <= origin:
            for cal in calibrators.values():
                cal.receive(labels[pointer], origin)
            pointer += 1
        for h, values in bases.items():
            state = visible.copy(); base = values[i]
            state['target_solar_sine'] = solar[h][i]
            state['base_median_normalized'] = base[3]/contract['capacity_kw_dc']
            state['base_width90_normalized'] = (base[6]-base[0])/contract['capacity_kw_dc']
            for name, cal in calibrators.items():
                q, _ = cal.issue(f'{origin.isoformat()}:{h}', origin, h, base, state, solar[h][i] > 0, origin.floor('h')+h*HOUR)
                predictions[name][h].append(q)
    return {m: {h: np.array(q) for h, q in predictions[m].items()} for m in predictions}


def run(site, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    parent = Path('runs/final_2017_v4' if site == 'nist' else 'runs/producing_extension_v1')
    config = json.loads((parent/'config.json').read_text())
    training, contract = load_input(config, site, 2016, 'primary')
    evaluation, _ = load_input(config, site, 2017, 'primary')
    truth = combine_years([training, evaluation])
    model_path = parent/site/'models_2016_primary_none.pkl'
    source = json.loads((parent/'manifest.json').read_text())
    expected = source['training'][f'{site}/2016/primary/none']['model_sha256']
    if digest(model_path) != expected:
        raise ValueError('Archived model changed')
    with model_path.open('rb') as handle:
        baseline = pickle.load(handle)['quantile']
    manifest = {'status': 'running exploratory feature and synthetic-fault study', 'site': site,
                'protocol_sha256': digest('research/revision_protocol_20261015.json'),
                'code': {p: digest(p) for p in ['research/run_revision_recovery.py', 'research/revision_recovery.py']},
                'parent_model_sha256': expected, 'cases': {}}
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    # Same fixed hyperparameters, targets and augmentation schedules as the base model.
    origins = pd.date_range(pd.Timestamp(config['training_start'])+pd.Timedelta(minutes=1),
                            pd.Timestamp(config['train_end'])-HOUR+pd.Timedelta(minutes=1), freq='h')
    train_events = observations_from_hourly(training, 1)
    augmented = [recovery_features(train_events, origins, contract)]
    for j, (scenario, mode, duration) in enumerate((('joint', 'immediate', 12), ('pv_only', 'none', 24), ('irradiance_first', 'gradual', 24))):
        faults = calendar_faults(config['training_start'], config['train_end'], config['model_seed']+j+1,
                                duration_hours=duration, scenario=scenario, mode=mode)
        augmented.append(recovery_features(deliver_schedule(train_events, faults), origins, contract))
    train_features = pd.concat(augmented)
    print(f'{site}: fitting base model with all observable recovery features', flush=True)
    extended = QuantileForecaster(config['quantile_profile'], config['model_seed'], True)
    with threadpool_limits(limits=1):
        extended.fit(train_features, training, contract, config['train_end'], config['horizons'])
    with (output/'model_recovery_features.pkl').open('wb') as handle:
        pickle.dump(extended, handle)
    del augmented, train_features
    origins = pd.date_range(pd.Timestamp(config['forecast_start'])+pd.Timedelta(minutes=1),
                            pd.Timestamp(config['evaluation_end'])-HOUR+pd.Timedelta(minutes=1), freq='h')
    origins = origins[~((origins >= pd.Timestamp(config['warmup_end'])) & (origins < pd.Timestamp(config['evaluation_start'])))]
    events = observations_from_hourly(truth, 1)
    for case_id in ('joint_gradual', 'weather_independent_variable', 'weather_correlated_variable'):
        print(f'{site}: evaluating {case_id}', flush=True)
        if case_id == 'joint_gradual':
            case = next(c for c in config['cases'] if c['id'] == case_id)
            faults = case_faults(config, case)
            scheduled = deliver_schedule(events, faults)
        else:
            faults = realistic_faults(truth, contract, config['forecast_start'], config['evaluation_end'],
                                      case_id == 'weather_correlated_variable')
            scheduled = transport_stress(events, faults)
        features = recovery_features(scheduled, origins, contract)
        with threadpool_limits(limits=1):
            bases = baseline.predict(features[[c for c in features if not c.startswith('rs_')]])
            enriched = extended.predict(features)
            predictions = calibrate(features, bases, scheduled, contract, config['calibration'])
        predictions['raw'] = bases
        predictions['base_all_recovery_features'] = enriched
        # Archive-time oracle is explicitly impossible online; only evaluation distortion is studied.
        if case_id == 'joint_gradual':
            visible_oracle = recovery_features(events, origins, contract)
            with threadpool_limits(limits=1):
                predictions['archive_time_oracle'] = baseline.predict(visible_oracle[[c for c in visible_oracle if not c.startswith('rs_')]])
        scored = pd.concat([final_scores(q, features, truth, contract, faults, config, method)
                            for method, q in predictions.items()], ignore_index=True)
        scored['case_id'], scored['site'] = case_id, site
        scored.to_parquet(output/f'forecasts_{case_id}.parquet', index=False)
        features.to_parquet(output/f'features_{case_id}.parquet')
        (output/f'schedule_{case_id}.json').write_text(json.dumps([asdict(f) for f in faults], default=str, indent=2)+'\n')
        # Simulator measurements describe assumptions, not inferred operational statistics.
        manifest['cases'][case_id] = {'faults': len(faults), 'delivered_packets': len(scheduled),
                                      'forecast_sha256': digest(output/f'forecasts_{case_id}.parquet')}
        (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    manifest['status'] = 'complete exploratory feature and synthetic-fault study'
    manifest['outputs'] = {p.name: digest(p) for p in output.iterdir() if p.name != 'manifest.json'}
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', choices=['nist', 'reserve10'], required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.site, args.output)
