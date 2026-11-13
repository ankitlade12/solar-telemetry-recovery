"""Verify revision archives and selected manuscript claims against saved measurements."""
import json
from pathlib import Path
import pandas as pd
from solar_recovery.pilot import digest


def verify():
    root=Path('runs/review_revision_20261015');out=root/'verification';out.mkdir(exist_ok=True)
    checked={}; claims={}
    manifests=[Path(r['path'])/'manifest.json' for r in json.loads((root/'shrinkage/batch.json').read_text())]
    manifests += [p/'manifest.json' for p in [root/'analysis',root/'experimental_analysis',root/'new_year/analysis',root/'new_year/analysis_reproduced_v2',Path('paper/review_evidence_20261015_v2'),Path('paper/review_supplement_evidence_20261015')]]
    manifests += list((root/'recovery').glob('*/manifest.json'))+list((root/'stress_v2').glob('*/manifest.json'))
    for path in manifests:
        manifest=json.loads(path.read_text());checked[str(path)]=digest(path)
        for name,expected in manifest.get('outputs',{}).items():
            if isinstance(expected,str) and len(expected)==64:
                p=path.parent/name
                assert digest(p)==expected, f'Changed output {p}'
                checked[str(p)]=expected
        for name,expected in manifest.get('verified_replay_dependencies',{}).items():
            assert digest(name)==expected,f'Frozen dependency changed {name}'
            checked[name]=expected
    batch=json.loads((root/'shrinkage/batch.json').read_text())
    assert len(batch)==16 and all(json.loads((Path(r['path'])/'manifest.json').read_text())['original_forecasts_reproduced_exactly'] for r in batch)
    claims['all_16_original_replays_exact']=True
    eq=pd.read_csv(root/'analysis/equivalence.csv');q=eq.query('confidence == .9875')
    assert len(q.query('margin_pct == 1'))==12
    claims['adjusted_1pct_all_blocks']=bool(q.query('margin_pct == 1').equivalent_within_margin.all())
    claims['adjusted_half_percent_all_blocks']=bool(q.query('margin_pct == .5').equivalent_within_margin.all())
    assert claims['adjusted_1pct_all_blocks'] and not claims['adjusted_half_percent_all_blocks']
    support=pd.read_csv(root/'experimental_analysis/support.csv')
    s=support.query("method == 'physical_recovery' and shrinkage == 50 and phase == 'recovery_0_6'")
    claims['early_case_horizon_median_ranges']=s.groupby('site')[['local_effective_n_p50','mixing_strength_p50']].agg(['min','max']).to_json()
    d=pd.read_csv(root/'analysis/decision_losses.csv').query("block_days == 7 and contrast == 'physical_recovery_minus_physical_availability' and cost_ratio != 1")
    assert len(d)==8 and d.ci_lower.le(0).all() and d.ci_upper.ge(0).all()
    claims['all_eight_seven_day_asymmetric_recovery_intervals_include_zero']=True
    a=pd.read_csv(root/'new_year/analysis/contrasts.csv');b=pd.read_csv(root/'new_year/analysis_reproduced_v2/contrasts.csv')
    pd.testing.assert_frame_equal(a,b);claims['new_year_18_contrast_rows_reproduced_exactly']=len(a)==18
    clock=pd.read_csv(root/'analysis/clock_summary.csv')
    assert clock.offset_median_h.eq(0).all() and clock.offset_p95_h.eq(0).all() and clock.offset_max_h.max()==22
    claims['clock_max_hours']=22
    for site in ('nist','reserve10'):
        m=json.loads((root/'stress_v2'/site/'manifest.json').read_text())
        claims[site+'_stress_status']=m['status']
    year=json.loads((root/'new_year/manifest.json').read_text())
    for case,record in year['cases'].items():
        p=root/'new_year'/f'forecasts_{case}.parquet';assert digest(p)==record['forecast_sha256'];checked[str(p)]=digest(p)
    log=(out/'pytest.log').read_text();assert '105 passed' in log
    for mode in ('named','anonymous'):
        p=Path('paper/build')/mode; audit=json.loads((p/'final_audit.json').read_text())
        assert audit['pdf_sha256']==digest(p/'manuscript.pdf') and audit['all_fonts_embedded'] and audit['pages']<=7
        checked[str(p/'manuscript.pdf')]=digest(p/'manuscript.pdf')
    code={str(p):digest(p) for directory in ('research','tests','solar_recovery') for p in Path(directory).glob('*.py')}
    result=dict(status='passed automated archive and numerical-claim checks',code_sha256=digest(__file__),claims=claims,
                checked_files=checked,current_python_source_hashes=code,test_log_sha256=digest(out/'pytest.log'),
                limits=['No human author sign-off or independent scientific replication','Original full-project lock includes missing historical author document; used replay dependencies verified','No qualified independent new climate or verified PV receipt logs','NWP field acquired but no fitted NWP model'])
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'Verified {len(checked)} archive/dependency files and manuscript claims; 105 tests passed.')

if __name__=='__main__':verify()
