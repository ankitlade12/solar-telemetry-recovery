"""Post-hoc ETIC review diagnostics from archived forecasts; no model refitting."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.analyze_final_evaluation import paired_days
from research.revision_analysis import paired_interval, daily_scores, PHASES, ROOTS
from solar_recovery.pilot import digest

OUT = Path('paper/etic2026/camera_ready_785/evidence')


def paired_direction(values):
    """Paired win-minus-loss effect, ties zero; positive means higher loss."""
    values = np.asarray(values, dtype=float)
    if not values.size or not np.isfinite(values).all():
        raise ValueError('Finite paired differences required')
    return float(np.sign(values).mean())


def aligned_methods(frame):
    keys = ['origin', 'horizon']
    a = frame.loc[frame.method.eq('physical_recovery')].set_index(keys).sort_index()
    b = frame.loc[frame.method.eq('physical_availability')].set_index(keys).sort_index()
    if not a.index.is_unique or not a.index.equals(b.index):
        raise ValueError('Forecast pairs differ or contain duplicates')
    if not a.actual_kw.equals(b.actual_kw):
        raise ValueError('Paired targets differ')
    return a, b


def analyze():
    OUT.mkdir(parents=True, exist_ok=True)
    inputs, effects, methods, scenario, thresholds = {}, [], [], [], []
    def read(path):
        path = Path(path)
        inputs[str(path)] = digest(path)
        return pd.read_parquet(path)
    for site, root in ROOTS.items():
        daily = read(root/'analysis/daily_scores.parquet')
        daily = daily.loc[daily.site.eq(site) & daily.population.eq('recorded_ac') &
                          daily.case_group.eq('primary') & ~daily.case_id.eq('clean')]
        for phase in PHASES:
            paired = paired_days(daily, 'physical_recovery', 'physical_availability', [phase])
            # Cluster summaries preserve pairing; descriptive direction is not Cliff's independent-sample delta.
            paired['block'] = ((paired.day-pd.Timestamp('2017-02-01T00:00Z')).dt.days//7)
            totals = paired.groupby(['block', 'case_id', 'horizon'])[['n','left_nwis','right_nwis']].sum()
            delta = ((totals.left_nwis-totals.right_nwis)/totals.n).groupby('block').mean()
            estimate = paired_interval(paired)
            effects.append(dict(site=site, phase=phase, paired_direction=paired_direction(delta),
                                nonempty_blocks=len(delta), **estimate))
        for method in sorted(daily.method.unique()):
            paired = paired_days(daily, method, method, [*PHASES, 'outage', 'partial_restoration'])
            for metric in ('nwis', 'coverage90'):
                # Difference against zero yields a marginal interval for the identical equal-cell estimand.
                paired['right_'+metric] = 0.
                est = paired_interval(paired, metric=metric)
                methods.append(dict(site=site, method=method, metric=metric, **est))
        batch_path = Path('runs/review_revision_20261015/shrinkage/batch.json')
        inputs[str(batch_path)] = digest(batch_path)
        batch = json.loads(batch_path.read_text())
        gated = {k: [] for k in (0, 3, 5, 10, 20)}
        cases = [r for r in batch if r['site'] == site and r['case'] != 'clean']
        if len(cases) != 7 or len({r['case'] for r in cases}) != 7:
            raise ValueError('Expected all seven primary fault scenarios')
        for run in cases:
            case = Path(run['path'])
            for strength in (50, 10, 1):
                frame = read(case/f'forecasts_{strength}.parquet')
                frame = frame.loc[frame.valid_target & frame.daylight & frame.within_period & frame.period.eq('evaluation')].copy()
                frame['case_id'] = run['case']
                diagnostic = read(case/f'diagnostics_{strength}.parquet')
                rec, avail = aligned_methods(frame)
                support = diagnostic.loc[diagnostic.method.eq('physical_recovery')].set_index(['origin','horizon']).sort_index()
                if not support.index.is_unique or not rec.index.isin(support.index).all():
                    raise ValueError('Support alignment failed')
                support = support.loc[rec.index]
                days = daily_scores(frame)
                for phase in PHASES:
                    paired = paired_days(days, 'physical_recovery', 'physical_availability', [phase])
                    stats = support.loc[rec.phase.eq(phase)]
                    est = paired_interval(paired)
                    scenario.append(dict(site=site, case_id=run['case'], a=strength, phase=phase,
                        local_ess_p10=stats.local_effective_n.quantile(.1),
                        local_ess_median=stats.local_effective_n.median(),
                        local_ess_p90=stats.local_effective_n.quantile(.9),
                        lambda_median=stats.mixing_strength.median(),
                        events=rec.loc[rec.phase.eq(phase),'event_id'].nunique(), **est))
                if strength == 50:
                    for minimum in gated:
                        selected = rec.copy()
                        use_local = support.local_effective_n.ge(minimum)
                        selected['nwis'] = rec.nwis.where(use_local, avail.nwis)
                        selected['method'] = 'threshold'
                        selected['uses_recovery'] = use_local
                        gated[minimum].append(pd.concat([selected.reset_index(), avail.reset_index()], ignore_index=True))
        for minimum, frames in gated.items():
            combined = pd.concat(frames, ignore_index=True)
            days = daily_scores(combined)
            for phase in PHASES:
                paired = paired_days(days, 'threshold', 'physical_availability', [phase])
                selected = combined.loc[combined.method.eq('threshold') & combined.phase.eq(phase)]
                for block in (7, 14, 28):
                    thresholds.append(dict(site=site, minimum_local_ess=minimum, phase=phase,
                        recovery_fraction=selected.uses_recovery.mean(), **paired_interval(paired, block_days=block)))
        print('Completed', site, flush=True)
    for name, rows in [('paired_effects',effects),('method_uncertainty',methods),
                       ('scenario_shrinkage',scenario),('minimum_ess',thresholds)]:
        pd.DataFrame(rows).to_csv(OUT/f'{name}.csv', index=False)
    for effect in effects:
        baseline = next(r for r in thresholds if r['site'] == effect['site'] and
                        r['phase'] == effect['phase'] and r['minimum_local_ess'] == 0 and r['block_days'] == 7)
        if baseline['pairs'] != effect['pairs'] or not np.isclose(baseline['difference'], effect['difference'], atol=1e-12):
            raise ValueError('Threshold zero must reproduce original matched comparison')
    (OUT/'analysis_manifest.json').write_text(json.dumps(dict(
        analysis_date='2026-11-09', code_sha256=digest(__file__), inputs=inputs,
        seed=20261015, bootstrap_draws=10000, model_refits=0,
        interpretation='Post-hoc exploratory; scenario/method/threshold intervals are pointwise, not simultaneous. Thresholds switch to the saved matched availability forecast below local ESS; no retraining or claimed optimal threshold.',
        outputs={p.name:digest(p) for p in OUT.glob('*.csv')}), indent=2)+'\n')


if __name__ == '__main__':
    analyze()
