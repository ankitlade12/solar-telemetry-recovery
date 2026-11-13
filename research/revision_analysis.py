"""Post-review paired uncertainty, decision losses and clock diagnostics."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from research.analyze_final_evaluation import paired_days, SCORES
from solar_recovery.pilot import digest
from solar_recovery.replay_v3 import Fault

ROOTS = {'nist': Path('runs/final_2017_v4'), 'reserve10': Path('runs/producing_extension_v1')}
PHASES = ['recovery_0_6', 'recovery_6_24']


def paired_interval(paired, block_days=7, replicates=10000, confidence=.95, seed=20261015,
                    start='2017-02-01T00:00Z', end='2018-01-01T00:00Z', metric='nwis'):
    """Paired calendar resampling; equal case/horizon means, including empty blocks."""
    if paired.empty or not 0 < confidence < 1 or block_days < 1 or replicates < 100:
        raise ValueError('Nonempty paired data and valid bootstrap settings required')
    anchor, last = pd.Timestamp(start).floor('D'), pd.Timestamp(end).ceil('D')
    nblocks = int(np.ceil((last-anchor).days/block_days))
    data = paired.copy()
    data['block'] = ((pd.to_datetime(data.day)-anchor).dt.days//block_days).astype(int)
    if not data.block.between(0, nblocks-1).all():
        raise ValueError('Dates outside declared calendar frame')
    strata = ['case_id', 'horizon']
    names = ['n', 'left_'+metric, 'right_'+metric]
    totals = data.groupby(strata)[names].sum()
    matrices = {name: data.groupby(['block', *strata])[name].sum().unstack(strata).reindex(
        index=range(nblocks), columns=totals.index).fillna(0).to_numpy() for name in names}
    weights = np.random.default_rng(seed).multinomial(nblocks, np.full(nblocks, 1/nblocks), size=replicates)
    with threadpool_limits(limits=1):
        counts = weights@matrices['n']
        valid = (counts > 0).all(axis=1)
        a = (weights[valid]@matrices[names[1]]/counts[valid]).mean(axis=1)
        b = (weights[valid]@matrices[names[2]]/counts[valid]).mean(axis=1)
    if valid.mean() < .95 or len(a) < 100:
        raise ValueError('Too many bootstrap draws omit supported strata; inference unsupported')
    left, right = [(totals[n]/totals.n).mean() for n in names[1:]]
    alpha = (1-confidence)/2
    lo, hi = np.quantile(a-b, [alpha, 1-alpha])
    relative_ok = bool(right > 0 and (b > 0).all())
    rlo, rhi = np.quantile(100*(a-b)/b, [alpha, 1-alpha]) if relative_ok else (np.nan, np.nan)
    return {'left_mean': left, 'right_mean': right, 'difference': left-right, 'ci_lower': lo, 'ci_upper': hi,
            'relative_pct': 100*(left-right)/right if relative_ok else np.nan,
            'relative_lower_pct': rlo, 'relative_upper_pct': rhi, 'relative_supported': relative_ok,
            'confidence': confidence, 'block_days': block_days, 'replicates': replicates,
            'valid_replicates': len(a), 'rejected_fraction': 1-valid.mean(), 'strata': len(totals),
            'pairs': int(totals.n.sum()), 'calendar_blocks': nblocks}


def equivalence(interval, margin_pct):
    if not np.isfinite(margin_pct) or margin_pct <= 0:
        raise ValueError('Equivalence margin must be finite and positive')
    return bool(interval['relative_supported'] and interval['relative_lower_pct'] > -margin_pct
                and interval['relative_upper_pct'] < margin_pct)


def asymmetric_loss(actual, commitment, under_over_ratio):
    if not np.isfinite(under_over_ratio) or under_over_ratio <= 0:
        raise ValueError('Cost ratio must be positive')
    return under_over_ratio*np.maximum(actual-commitment, 0)+np.maximum(commitment-actual, 0)


def daily_scores(scored):
    part = scored.copy()
    part['day'] = part.origin.dt.floor('D')
    return part.groupby(['day', 'case_id', 'horizon', 'phase', 'method']).agg(
        n=('nwis', 'size'), **{'sum_'+m: (m, 'sum') for m in SCORES}).reset_index()


def analyze(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    hashes, contrasts, equivalences, decisions, clocks, clock_summaries, trajectories, transfer = {}, [], [], [], [], [], [], []
    for site, root in ROOTS.items():
        config = json.loads((root/'config.json').read_text())
        daily_path = root/'analysis/daily_scores.parquet'
        hashes[str(daily_path)] = digest(daily_path)
        daily = pd.read_parquet(daily_path)
        daily = daily.loc[daily.site.eq(site) & daily.population.eq('recorded_ac') & daily.case_group.eq('primary') & ~daily.case_id.eq('clean')]
        for phase in PHASES:
            paired = paired_days(daily, 'physical_recovery', 'physical_availability', [phase])
            for block in (7, 14, 28):
                for confidence in (.95, .9875):
                    estimate = paired_interval(paired, block_days=block, confidence=confidence)
                    contrasts.append({'site': site, 'phase': phase, **estimate})
                    for margin in (5., 1., .5):
                        equivalences.append({'site': site, 'phase': phase, 'margin_pct': margin,
                            'equivalent_within_margin': equivalence(estimate, margin),
                            'interpretation': 'post-hoc conservative CI-inclusion equivalence; conditional fixed-site inference', **estimate})
        scenario_rows = []
        for case in (c for c in config['cases'] if c['group'] == 'primary' and c['id'] != 'clean'):
            path = root/site/f"forecasts_{case['id']}.parquet"
            expected = json.loads((root/'manifest.json').read_text())['cases'][f"{site}/{case['id']}"]['forecasts_sha256']
            hashes[str(path)] = digest(path)
            if hashes[str(path)] != expected:
                raise ValueError(f'Changed forecast archive: {path}')
            scored = pd.read_parquet(path)
            scored = scored.loc[scored.valid_target & scored.daylight & scored.within_period & scored.period.eq('evaluation') &
                                scored.method.isin(['raw', 'physical_availability', 'physical_recovery'])].copy()
            scenario_rows.append(scored)
            features_path = root/site/f"features_{case['id']}.parquet"
            hashes[str(features_path)] = digest(features_path)
            features = pd.read_parquet(features_path)
            schedule_path = root/site/f"schedule_{case['id']}.json"
            hashes[str(schedule_path)] = digest(schedule_path)
            faults = [Fault(**f) for f in json.loads(schedule_path.read_text())]
            rec = scored.loc[scored.method.eq('raw') & scored.phase.isin(PHASES)].merge(
                features, left_on='origin', right_index=True, validate='many_to_one')
            for event_id, group in rec.groupby('event_id'):
                fault = faults[int(event_id)]
                affected = [s for s in ('pv', 'irradiance') if getattr(fault, s+'_return') > fault.start]
                for origin, row in group.drop_duplicates('origin').set_index('origin').iterrows():
                    ages = [row[s+'_recovery'] for s in affected]
                    available = all(row[s+'_current'] > 0 and row[s+'_recovery'] >= 0 for s in affected)
                    age = min(ages) if available else np.nan
                    observed_return = origin-pd.Timedelta(hours=age) if available else pd.NaT
                    offset = (observed_return-max(fault.pv_return, fault.irradiance_return)).total_seconds()/3600 if available else np.nan
                    clocks.append({'site': site, 'case_id': case['id'], 'event_id': event_id, 'origin': origin,
                                   'scheduled_phase': row['phase'], 'current_recovery_observed': available,
                                   'observed_recovery_age_h': age, 'return_offset_h': offset})
        all_rows = pd.concat(scenario_rows, ignore_index=True)
        for ratio, quantile in ((1, .5), (4, .8), (9, .9)):
            part = all_rows.loc[all_rows.phase.isin(PHASES)].copy()
            q = part.q50 if quantile == .5 else part.q90 if quantile == .9 else part.q75+(part.q90-part.q75)/3
            part['loss'] = asymmetric_loss(part.actual_kw.to_numpy(), q.to_numpy(), ratio)/part.capacity_kw_dc
            part['day'] = part.origin.dt.floor('D')
            grouped = part.groupby(['day', 'case_id', 'horizon', 'phase', 'method']).agg(n=('loss', 'size'), total=('loss', 'sum')).reset_index()
            for phase in PHASES:
                for left, right in [('physical_recovery', 'physical_availability'), ('physical_availability', 'raw')]:
                    keys = ['day', 'case_id', 'horizon']
                    a = grouped.loc[grouped.phase.eq(phase) & grouped.method.eq(left)].set_index(keys)
                    b = grouped.loc[grouped.phase.eq(phase) & grouped.method.eq(right)].set_index(keys)
                    if not a.index.equals(b.index) or not a.n.equals(b.n):
                        raise ValueError('Decision-loss pairs differ')
                    paired = a[['n']].assign(left_nwis=a.total, right_nwis=b.total).reset_index()
                    for block in (7, 14, 28):
                        decisions.append({'site': site, 'phase': phase, 'cost_ratio': ratio, 'quantile': quantile,
                            'contrast': left+'_minus_'+right, **paired_interval(paired, block_days=block)})
        recovery = all_rows.loc[all_rows.phase.isin(PHASES)].copy()
        recovery['bin'] = np.floor(recovery.recovery_hour).astype(int)
        for hour, group in recovery.groupby('bin'):
            paired = paired_days(daily_scores(group), 'physical_recovery', 'physical_availability')
            try:
                estimate = paired_interval(paired)
                trajectories.append({'site': site, 'hour': hour, **estimate})
            except ValueError as exc:
                trajectories.append({'site': site, 'hour': hour, 'unsupported': str(exc)})
        # Compare scheduled and observed clocks on exactly the same row population.
        clock = pd.DataFrame(clocks).query('site == @site')
        clock_summaries.append(clock.groupby(['site', 'case_id', 'scheduled_phase']).agg(
            origins=('origin', 'size'), observed_fraction=('current_recovery_observed', 'mean'),
            offset_median_h=('return_offset_h', 'median'), offset_p95_h=('return_offset_h', lambda x: x.quantile(.95)),
            offset_max_h=('return_offset_h', 'max')).reset_index())
        matched = all_rows.merge(clock[['case_id', 'origin', 'observed_recovery_age_h']], on=['case_id', 'origin'], validate='many_to_one')
        matched['phase'] = np.where(matched.observed_recovery_age_h < 6, PHASES[0], PHASES[1])
        matched = matched.loc[matched.observed_recovery_age_h.between(0, 24, inclusive='left')]
        for phase in PHASES:
            paired = paired_days(daily_scores(matched), 'physical_recovery', 'physical_availability', [phase])
            for block in (7, 14, 28):
                contrasts.append({'site': site, 'phase': phase, 'clock': 'observed; restricted to original scheduled recovery rows',
                                  **paired_interval(paired, block_days=block)})
        if site == 'nist':
            cells = pd.read_csv(root/'analysis/Cells.csv')
            transfer.append(cells.loc[cells.site.eq(site) & cells.case_id.isin(['joint_gradual', 'cross_site_weights']) &
                cells.population.eq('recorded_ac') & cells.endpoint.eq('recovery') &
                cells.method.isin(['raw', 'physical', 'physical_availability', 'physical_recovery'])])
    tables = {'contrasts': pd.DataFrame(contrasts), 'equivalence': pd.DataFrame(equivalences),
              'decision_losses': pd.DataFrame(decisions), 'clock_rows': pd.DataFrame(clocks),
              'clock_summary': pd.concat(clock_summaries), 'recovery_difference': pd.DataFrame(trajectories),
              'transfer_diagnostics': pd.concat(transfer)}
    for name, frame in tables.items():
        frame.to_csv(output/f'{name}.csv', index=False)
    fig, axes = plt.subplots(1, 2, figsize=(7, 2.5), constrained_layout=True)
    for ax, site in zip(axes, ROOTS):
        d = tables['recovery_difference'].query('site == @site').dropna(subset=['difference'])
        ax.plot(d.hour, 1000*d.difference, marker='.', linewidth=1)
        ax.fill_between(d.hour, 1000*d.ci_lower, 1000*d.ci_upper, alpha=.2)
        ax.axhline(0, color='black', linewidth=.5)
        ax.set(title='NIST' if site == 'nist' else 'C10 (post-hoc)', xlabel='Hours after scheduled return', ylabel=r'$10^3$ (recovery − availability) NWIS')
    for ext in ('pdf', 'png'):
        fig.savefig(output/f'recovery_difference.{ext}', dpi=200)
    plt.close(fig)
    (output/'manifest.json').write_text(json.dumps({'status': 'complete post-review exploratory analysis',
        'code_sha256': digest(__file__), 'protocol_sha256': digest('research/revision_protocol_20261015.json'),
        'inputs': hashes, 'outputs': {p.name: digest(p) for p in output.iterdir()},
        'limits': ['Equivalence margins chosen after original results; no retrospective preregistration',
                   'Four site/phase contrasts use 98.75% Bonferroni intervals; 7/14/28 days are sensitivity specifications',
                   'Hourly bands and decision-loss intervals are pointwise exploratory',
                   'Illustrative asymmetric loss, not observed currency or dispatch performance']}, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    analyze(parser.parse_args().output)
