"""Synthetic evidence only: prevent selective or numerically misleading exports."""
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from research.export_extension_evidence import CASE_LABELS, LABELS, PRIMARY, export
from solar_recovery.pilot import digest


def seal(run, reproduced):
    analysis = run/'analysis'
    for p in analysis.glob('*.csv'):
        shutil.copyfile(p, reproduced/p.name)
    (analysis/'manifest.json').write_text(json.dumps({'status': 'complete analysis',
        'source_manifest_sha256': digest(run/'manifest.json'),
        'tables': {p.stem: len(pd.read_csv(p)) for p in analysis.glob('*.csv')},
        'files_sha256': {p.name: digest(p) for p in analysis.glob('*.csv')}}))
    (run/'verification.json').write_text(json.dumps({'status': 'passed synthetic fixture',
        'manifest_sha256': digest(run/'manifest.json'), 'files_sha256': {'manifest.json': digest(run/'manifest.json')}}))
    (reproduced/'reproduction_comparison.json').write_text(json.dumps({
        'status': 'all principal tables reproduced from verified archived forecasts',
        'original_analysis_manifest_sha256': digest(analysis/'manifest.json'),
        'comparisons': {p.stem: {'matched': True, 'original_sha256': digest(p),
            'reproduced_sha256': digest(reproduced/p.name)} for p in analysis.glob('*.csv')}}))


def fixture(tmp_path):
    run, reproduced = tmp_path/'synthetic', tmp_path/'reproduced'
    analysis = run/'analysis';analysis.mkdir(parents=True);reproduced.mkdir()
    (run/'manifest.json').write_text(json.dumps({'status': 'complete frozen evaluation', 'data_kind': 'explicitly synthetic export fixture'}))
    common = {'site': 'reserve10', 'population': 'recorded_ac'}
    summary = [{**common, 'endpoint': 'failure_recovery', 'method': method,
        'nwis': .094 if method == 'physical_recovery' else .1, 'nmae': .05, 'coverage90': .9, 'nwidth90': .3,
        'forecast_target_pairs': 2000, 'min_events_per_stratum': 29, 'min_cases_per_stratum': 124} for method in LABELS]
    cells = [{**common, 'case_id': 'clean', 'case_group': 'primary', 'method': method, 'endpoint': 'all',
        'horizon': h, 'nwis': .103 if method == 'physical_recovery' else .1, 'n': 1000, 'events': 0}
        for method in LABELS for h in (1, 2, 3, 4)]
    for phase in ('recovery_0_6', 'recovery_6_24'):
        cells += [{**common, 'case_id': 'joint_gradual', 'case_group': 'primary', 'method': 'raw', 'endpoint': phase,
            'horizon': h, 'nwis': .1, 'n': 124+h, 'events': 29+h%2} for h in (1, 2, 3, 4)]
    contrasts = []
    for pool, phases in [('faulted_primary', ['recovery_0_6', 'recovery_6_24']), *[(c, ['recovery']) for c in CASE_LABELS]]:
        for phase in phases:
            for block in (7, 14, 28):
                contrasts.append({**common, 'pool': pool, 'endpoint': phase, 'contrast': PRIMARY, 'block_days': block,
                    'supported': True, 'difference': .001234, 'ci_lower': -.002 if block != 28 else np.nan,
                    'ci_upper': .003 if block != 28 else np.nan, 'paired_rows': 500, 'calendar_blocks': 12,
                    'valid_replicates': 100 if block != 28 else 0, 'rejected_fraction': 0. if block != 28 else 1.})
    for name, rows in [('Summary', summary), ('Cells', cells), ('Contrasts', contrasts),
        *[(n, [{'synthetic': True}]) for n in ['Support', 'Diagnostics', 'Recovery', 'UpdateActivity', 'InterruptionComparison']]]:
        pd.DataFrame(rows).to_csv(analysis/f'{name}.csv', index=False)
    seal(run, reproduced)
    return run, reproduced


def test_export_retains_all_methods_sign_scaling_missing_intervals_and_support(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path);run, reproduced = fixture(tmp_path)
    out = tmp_path/'export';export(run, reproduced, out)
    for label in LABELS.values(): assert label in (out/'extension_methods.tex').read_text()
    text = (out/'extension_primary.tex').read_text()
    assert '1.234 [-2.000, 3.000]' in text and '1.234 [--, --]' in text
    primary = pd.read_csv(out/'primary_claim_rows.csv')
    assert len(primary) == 6 and primary.difference.eq(.001234).all()
    assert primary.loc[primary.block_days.eq(28), 'ci_lower'].isna().all()
    facts = pd.read_csv(out/'engineering_gate_facts.csv').iloc[0]
    assert facts.relative_failure_recovery_difference == pytest.approx(-.06)
    assert facts.signal_point_gate_5pct and not facts.clean_point_gate
    assert facts.clean_difference == pytest.approx(.003) and facts.clean_tolerance == pytest.approx(.002)
    assert facts.recovery_0_6_minimum_pairs == 125 and facts.recovery_0_6_minimum_events == 29
    assert not facts.recovery_0_6_all_cells_meet_support
    ledger = json.loads((out/'claim_evidence_extension.json').read_text())
    assert len(ledger['claims']) == 41
    assert any('ci_lower' in c['unavailable_source_columns'] for c in ledger['claims'])
    assert json.loads((out/'manifest.json').read_text())['data_kind'] == 'explicitly synthetic export fixture'
    with pytest.raises(FileExistsError): export(run, reproduced, out)
    (reproduced/'Contrasts.csv').write_text((reproduced/'Contrasts.csv').read_text()+'\n')
    with pytest.raises(ValueError, match='reproduced table'):
        export(run, reproduced, tmp_path/'changed')


def test_zero_baseline_cannot_claim_five_percent_improvement(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path);run, reproduced = fixture(tmp_path)
    path = run/'analysis/Summary.csv';d = pd.read_csv(path)
    d.loc[d.method.isin(['physical', 'physical_recovery']), 'nwis'] = 0.
    d.to_csv(path, index=False);seal(run, reproduced)
    export(run, reproduced, tmp_path/'zero')
    facts = pd.read_csv(tmp_path/'zero/engineering_gate_facts.csv').iloc[0]
    assert np.isnan(facts.relative_failure_recovery_difference) and not facts.signal_point_gate_5pct


def test_omitted_comparator_is_rejected_even_if_other_hashes_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path);run, reproduced = fixture(tmp_path)
    path = run/'analysis/Summary.csv';d = pd.read_csv(path);d.iloc[:-1].to_csv(path,index=False);seal(run,reproduced)
    with pytest.raises(ValueError, match='fifteen'):
        export(run, reproduced, tmp_path/'missing_method')


def test_partial_reproduction_manifest_cannot_pass_export_gate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path);run, reproduced = fixture(tmp_path)
    path = reproduced/'reproduction_comparison.json';j = json.loads(path.read_text())
    j['comparisons'].pop('Support');path.write_text(json.dumps(j))
    with pytest.raises(ValueError, match='all eight'):
        export(run, reproduced, tmp_path/'partial')
