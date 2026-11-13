"""Corrected mixed timely/delayed stress replay using already fitted models."""
from dataclasses import asdict
import json
from pathlib import Path
import pickle
import argparse

import pandas as pd
from threadpoolctl import threadpool_limits

from research.final_evaluation import combine_years, load_input, final_scores
from research.run_revision_recovery import calibrate
from research.revision_recovery import recovery_features, realistic_faults, transport_stress
from research.summarize_revision_experiments import latest_phase
from solar_recovery.pilot import digest
from solar_recovery.replay import HOUR, observations_from_hourly


def run(site):
    parent=Path('runs/final_2017_v4' if site=='nist' else 'runs/producing_extension_v1')
    original=Path('runs/review_revision_20261015/recovery')/site
    out=Path('runs/review_revision_20261015/stress_v2')/site;out.mkdir(parents=True,exist_ok=False)
    config=json.loads((parent/'config.json').read_text())
    training,contract=load_input(config,site,2016,'primary');evaluation,_=load_input(config,site,2017,'primary')
    truth=combine_years([training,evaluation])
    model_path=parent/site/'models_2016_primary_none.pkl'
    extended_path=original/'model_recovery_features.pkl'
    old=json.loads((original/'manifest.json').read_text())
    if digest(extended_path)!=old['outputs']['model_recovery_features.pkl']:
        raise ValueError('Extended model changed')
    if digest(model_path)!=old['parent_model_sha256']:
        raise ValueError('Base model changed')
    with model_path.open('rb') as f:baseline=pickle.load(f)['quantile']
    with extended_path.open('rb') as f:extended=pickle.load(f)
    origins=pd.date_range(pd.Timestamp(config['forecast_start'])+pd.Timedelta(minutes=1),pd.Timestamp(config['evaluation_end'])-HOUR+pd.Timedelta(minutes=1),freq='h')
    origins=origins[~((origins>=pd.Timestamp(config['warmup_end']))&(origins<pd.Timestamp(config['evaluation_start'])))]
    events=observations_from_hourly(truth,1)
    record={'status':'running corrected exploratory stress','code':{str(p):digest(p) for p in [Path(__file__),Path('research/revision_recovery.py'),Path('research/run_revision_recovery.py')]},
            'amendment_sha256':digest('research/revision_transport_amendment_20261015.json'),'model_sha256':digest(extended_path),'cases':{}}
    (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    for case in ('weather_independent_variable','weather_correlated_variable'):
        print(site,case,flush=True)
        faults=realistic_faults(truth,contract,config['forecast_start'],config['evaluation_end'],case=='weather_correlated_variable')
        schedule=transport_stress(events,faults)
        features=recovery_features(schedule,origins,contract)
        if not 0<features.pv_current.mean()<1 or not 0<features.irradiance_current.mean()<1:
            raise ValueError('Transport stress must permit both fresh and stale observations')
        with threadpool_limits(limits=1):
            bases=baseline.predict(features[[c for c in features if not c.startswith('rs_')]])
            predictions=calibrate(features,bases,schedule,contract,config['calibration'])
            predictions['base_all_recovery_features']=extended.predict(features)
        predictions['raw']=bases
        scored=pd.concat([final_scores(q,features,truth,contract,faults,config,m) for m,q in predictions.items()],ignore_index=True)
        scored=scored.drop(columns=['phase','event_id','recovery_hour']).merge(latest_phase(origins,faults),left_on='origin',right_index=True,validate='many_to_one')
        scored['case_id'],scored['site']=case,site
        scored.to_parquet(out/f'forecasts_{case}.parquet',index=False)
        features.to_parquet(out/f'features_{case}.parquet')
        (out/f'schedule_{case}.json').write_text(json.dumps([asdict(f) for f in faults],default=str,indent=2)+'\n')
        record['cases'][case]={'forecast_sha256':digest(out/f'forecasts_{case}.parquet'),'pv_current_fraction':float(features.pv_current.mean()),'irradiance_current_fraction':float(features.irradiance_current.mean())}
        (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    record['status']='complete corrected exploratory stress'
    record['outputs']={p.name:digest(p) for p in out.iterdir() if p.name!='manifest.json'}
    (out/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--site',required=True,choices=['nist','reserve10'])
    run(parser.parse_args().site)
