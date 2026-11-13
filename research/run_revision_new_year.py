"""Declared 2021 evaluation of unchanged archived 2016 models."""
import json
from pathlib import Path
import pickle

import pandas as pd
from threadpoolctl import threadpool_limits

from research.final_evaluation import combine_years, training_features, final_scores, case_faults
from research.run_annual_calibration import causal_forecasts
from solar_recovery.baselines_v3 import QuantileForecaster
from solar_recovery.pilot import digest
from solar_recovery.replay import HOUR, observations_from_hourly
from solar_recovery.replay_v3 import replay_features, deliver_schedule


def run():
    roots = {2021: Path('data/processed/review_revision_20261015/reserve10_2021')}
    for root in roots.values():
        decision = json.loads((root/'decision.json').read_text())
        if not decision['admitted'] or decision['forecast_performance_inspected']:
            raise ValueError('Source qualification did not admit an untouched new-year input')
        for name, expected in decision['outputs'].items():
            if digest(root/name) != expected:
                raise ValueError('Qualified source changed')
    output = Path('runs/review_revision_20261015/new_year')
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads(Path('configs/producing_extension_v1.json').read_text())
    config.update(forecast_start='2021-01-03T00:00Z', evaluation_start='2021-02-01T04:00Z',
                  warmup_end='2021-02-01T00:00Z', evaluation_end='2022-01-01T00:00Z')
    config['cases'] = [c for c in config['cases'] if c['group'] == 'primary']
    (output/'config.json').write_text(json.dumps(config, indent=2)+'\n')
    record = {'status': 'running new-year extension', 'code_sha256': digest(__file__),
              'protocol_sha256': digest('research/new_year_protocol_20261015.json'),
              'conflict_amendment_sha256': digest('research/new_year_protocol_20261015_conflict_amendment.json'),
              'evaluation_amendment_sha256': digest('research/new_year_protocol_2021_amendment.json'),
              'source_decisions': {str(r): digest(r/'decision.json') for r in roots.values()}, 'cases': {}}
    (output/'manifest.json').write_text(json.dumps(record, indent=2)+'\n')
    for variant in ('primary', 'right_aligned'):
        evaluation = pd.read_parquet(roots[2021]/variant/'hourly.parquet')
        contract = json.loads((roots[2021]/variant/'contract.json').read_text())
        truth = evaluation[['pv', 'irradiance']]
        model_path = Path('runs/producing_extension_v1/reserve10')/f'models_2016_{variant}_none.pkl'
        parent = json.loads(Path('runs/producing_extension_v1/manifest.json').read_text())
        if digest(model_path) != parent['training'][f'reserve10/2016/{variant}/none']['model_sha256']:
            raise ValueError('Archived 2016 model changed')
        with model_path.open('rb') as f:
            model = pickle.load(f)['quantile']
        record.setdefault('model_sha256', {})[str(model_path)] = digest(model_path)
        events = observations_from_hourly(truth, 1)
        origins = pd.date_range(pd.Timestamp(config['forecast_start'])+pd.Timedelta(minutes=1),
                                pd.Timestamp(config['evaluation_end'])-HOUR+pd.Timedelta(minutes=1), freq='h')
        origins = origins[~((origins >= pd.Timestamp(config['warmup_end'])) & (origins < pd.Timestamp(config['evaluation_start'])))]
        for case in config['cases']:
            if variant == 'right_aligned' and case['id'] != 'joint_gradual':
                continue
            name = case['id'] if variant == 'primary' else 'right_aligned'
            print(f'Evaluating 2021: {name}', flush=True)
            faults = case_faults(config, case)
            schedule = deliver_schedule(events, faults)
            features = replay_features(schedule, origins)
            with threadpool_limits(limits=1):
                bases = model.predict(features)
                predictions, diagnostics, counts = causal_forecasts(features, bases, schedule, contract,
                    config['calibration'], ['raw', 'physical_availability', 'physical_recovery'])
            scored = pd.concat([final_scores(q, features, truth, contract, faults, config, method)
                                for method, q in predictions.items()], ignore_index=True)
            scored['case_id'], scored['site'] = name, 'reserve10_2021'
            scored.to_parquet(output/f'forecasts_{name}.parquet', index=False)
            diagnostics.to_parquet(output/f'diagnostics_{name}.parquet', index=False)
            record['cases'][name] = {'forecast_sha256': digest(output/f'forecasts_{name}.parquet'), 'updates': counts}
            (output/'manifest.json').write_text(json.dumps(record, indent=2)+'\n')
    record['status'] = 'complete new-year same-system extension; no independent-climate claim'
    record['outputs'] = {p.name: digest(p) for p in output.iterdir() if p.name != 'manifest.json'}
    (output/'manifest.json').write_text(json.dumps(record, indent=2)+'\n')


if __name__ == '__main__':
    run()
