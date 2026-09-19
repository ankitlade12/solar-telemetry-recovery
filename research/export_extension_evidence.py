"""Exact-source numerical exports for a verified, reproduced extension."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.export_paper_tables import LABELS, interval, number, table
from research.package_submission import verify_claim_ledger
from solar_recovery.pilot import digest

SITE = 'reserve10'
PRIMARY = 'physical_recovery_minus_physical_availability'
EXPECTED_TABLES = {'Summary', 'Cells', 'Contrasts', 'Support', 'Diagnostics', 'Recovery', 'UpdateActivity', 'InterruptionComparison'}
CASE_LABELS = {'joint_gradual': 'Joint gradual', 'right_aligned': 'Minute-end alignment',
               'receipt_5min': 'Five-minute receipt margin', 'privileged_labels': 'Privileged labels (diagnostic)'}


def checked_evidence(root, reproduced):
    manifest = json.loads((root/'manifest.json').read_text())
    verification = json.loads((root/'verification.json').read_text())
    analysis = json.loads((root/'analysis/manifest.json').read_text())
    comparison = json.loads((reproduced/'reproduction_comparison.json').read_text())
    if manifest['status'] != 'complete frozen evaluation' or not verification['status'].startswith('passed') or analysis['status'] != 'complete analysis':
        raise ValueError('Require complete verified extension analysis')
    if verification['manifest_sha256'] != digest(root/'manifest.json') or analysis['source_manifest_sha256'] != digest(root/'manifest.json'):
        raise ValueError('Extension provenance changed')
    for directory, record in [(root, verification), (root/'analysis', analysis)]:
        if not record.get('files_sha256'):
            raise ValueError('Verified snapshot hashes are required')
        for name, expected in record['files_sha256'].items():
            if digest(directory/name) != expected:
                raise ValueError('Changed verified source: '+name)
    if comparison.get('status') != 'all principal tables reproduced from verified archived forecasts':
        raise ValueError('Require completed table reproduction')
    if set(analysis['tables']) != EXPECTED_TABLES or set(comparison['comparisons']) != EXPECTED_TABLES:
        raise ValueError('Require all eight analysis and reproduction tables')
    if comparison['original_analysis_manifest_sha256'] != digest(root/'analysis/manifest.json'):
        raise ValueError('Reproduction does not cover the current analysis tables')
    for name, row in comparison['comparisons'].items():
        original, copy = root/'analysis'/f'{name}.csv', reproduced/f'{name}.csv'
        if not row['matched'] or digest(original) != row['original_sha256'] or digest(copy) != row['reproduced_sha256']:
            raise ValueError('Changed or unmatched reproduced table: '+name)
        pd.testing.assert_frame_equal(pd.read_csv(original), pd.read_csv(copy), check_exact=False, rtol=1e-12, atol=1e-12)
    return manifest


def export(root, reproduced, output):
    workspace = Path.cwd().resolve()
    root, reproduced, output = map(lambda p: Path(p).resolve(), (root, reproduced, output))
    if not all(p.is_relative_to(workspace) for p in (root, reproduced, output)):
        raise ValueError('Evidence and output must be inside the review workspace')
    if output.exists():
        raise FileExistsError('Numerical exports are immutable')
    manifest = checked_evidence(root, reproduced)
    frames = {n: pd.read_csv(root/'analysis'/f'{n}.csv') for n in ('Summary', 'Cells', 'Contrasts')}
    if any(set(d.site.unique()) != {SITE} for d in frames.values()):
        raise ValueError('Expected only the declared reserve10 extension')
    output.mkdir(parents=True)
    claims = []
    def claim(name, where, columns, statement):
        source = root/'analysis'/f'{name}.csv'; data = frames[name]
        for key, value in where.items(): data = data[data[key].eq(value)]
        if len(data) != 1: raise ValueError('Absent or ambiguous export source row: '+str(where))
        row = data.iloc[0]; values = {}; unavailable = []
        for column in columns:
            value = row[column]
            if pd.isna(value): unavailable.append(column); continue
            values[column] = value.item() if isinstance(value, np.generic) else value
        if not values: raise ValueError('No checkable values in source row')
        claims.append({'id': f'extension_{len(claims)+1:03d}', 'statement': statement,
            'source_path': str(source.relative_to(workspace)), 'source_sha256': digest(source),
            'where': where, 'values': values, 'unavailable_source_columns': unavailable})
        return row
    common = {'site': SITE, 'population': 'recorded_ac'}
    main = frames['Summary'].query("population == 'recorded_ac' and endpoint == 'failure_recovery'")
    if set(main.method) != set(LABELS) or len(main) != len(LABELS):
        raise ValueError('All fifteen primary outputs must be exported exactly once')
    main.to_csv(output/'main_claim_rows.csv', index=False)
    rows = []
    for method, label in LABELS.items():
        point = claim('Summary', {**common, 'endpoint': 'failure_recovery', 'method': method},
            ['nwis', 'nmae', 'coverage90', 'nwidth90', 'forecast_target_pairs', 'min_events_per_stratum', 'min_cases_per_stratum'],
            f'System 10 failure/recovery summary for {method}; equal supported case/horizon means')
        rows.append([label, number(point.nwis), number(point.nmae), number(point.coverage90*100, 1), number(point.nwidth90, 3)])
    table(output/'extension_methods.tex', 'Separately declared producing-system replication: failure and recovery.',
        'tab:extension-methods', 'lrrrr', ['Method', 'NWIS', 'NMAE', '$C_{90}$ (\\%)', '$W_{90}/C$'], rows, True,
        'System 10 is adjacent to original Colorado system 4; it is not an independent climate. All fifteen outputs and the same observed daylight rows are retained. Receipt times are simulated; the target is recorded AC.')
    rows = []; primary_rows = []
    for phase, label in [('recovery_0_6', '0--6 h'), ('recovery_6_24', '6--24 h')]:
        for block in (7, 14, 28):
            point = claim('Contrasts', {**common, 'pool': 'faulted_primary', 'endpoint': phase, 'contrast': PRIMARY, 'block_days': block},
                ['supported', 'difference', 'ci_lower', 'ci_upper', 'paired_rows', 'calendar_blocks', 'valid_replicates', 'rejected_fraction'],
                f'System 10 recovery-minus-availability NWIS, {phase}, {block}-day blocks; positive is worse')
            primary_rows.append(point.to_dict())
            rows.append([label, str(block), interval(point), str(int(point.paired_rows)) if pd.notna(point.paired_rows) else '--'])
    table(output/'extension_primary.tex', 'Extension recovery-minus-availability contrasts and block-length sensitivity.',
        'tab:extension-primary', 'llrl', ['Phase', 'Block days', '$10^3\\Delta$NWIS [95\\% CI]', 'Pairs'], rows, True,
        'Both recovery windows and all three declared block lengths are reported together. Calendar blocks keep common-weather replays together. Overlapping forecast-target pairs are not independent observations; this is a fixed-system extension after original-result exposure.')
    pd.DataFrame(primary_rows).to_csv(output/'primary_claim_rows.csv', index=False)
    rows = []; sensitivity_rows = []
    for case, label in CASE_LABELS.items():
        for block in (7, 14, 28):
            point = claim('Contrasts', {**common, 'pool': case, 'endpoint': 'recovery', 'contrast': PRIMARY, 'block_days': block},
                ['supported', 'difference', 'ci_lower', 'ci_upper', 'paired_rows', 'valid_replicates', 'rejected_fraction'],
                f'Extension declared {case} recovery contrast, {block}-day blocks; privileged labels remain non-operational')
            sensitivity_rows.append(point.to_dict())
            if block == 7: rows.append([label, interval(point)])
    table(output/'extension_sensitivities.tex', 'Declared extension alignment, receipt and information-access checks.',
        'tab:extension-sensitivity', 'lr', ['Joint-gradual case', '$10^3\\Delta$NWIS [95\\% CI]'], rows, True,
        'Seven-day intervals shown; 14/28-day versions remain in the source CSV. All contrasts are recovery minus availability. Privileged labels deliberately change information access and are excluded from deployable rankings.')
    pd.DataFrame(sensitivity_rows).to_csv(output/'sensitivity_claim_rows.csv', index=False)
    cells = frames['Cells'].query("population == 'recorded_ac'")
    clean = cells.query("case_id == 'clean' and endpoint == 'all'").groupby('method').nwis.mean()
    for method in ('physical', 'physical_recovery'):
        for _, row in cells.query("case_id == 'clean' and endpoint == 'all'").loc[lambda d: d.method.eq(method)].iterrows():
            claim('Cells', {**common, 'case_id': 'clean', 'endpoint': 'all', 'method': method, 'horizon': int(row.horizon)},
                ['nwis', 'n', 'events'], 'Extension clean point gate uses equal horizon means')
    indexed = main.set_index('method'); ref = float(indexed.loc['physical', 'nwis']); rec = float(indexed.loc['physical_recovery', 'nwis'])
    clean_ref, clean_rec = float(clean.physical), float(clean.physical_recovery)
    tolerance = max(.02*clean_ref, .0001)
    facts = {'site': SITE, 'physical_failure_recovery_nwis': ref, 'recovery_failure_recovery_nwis': rec,
        'relative_failure_recovery_difference': (rec-ref)/ref if ref else np.nan,
        'signal_point_gate_5pct': bool(ref > 0 and rec <= .95*ref),
        'clean_physical_nwis': clean_ref, 'clean_recovery_nwis': clean_rec, 'clean_difference': clean_rec-clean_ref,
        'clean_tolerance': tolerance, 'clean_point_gate': bool(clean_rec-clean_ref <= tolerance),
        'recovery_coverage90': float(indexed.loc['physical_recovery', 'coverage90'])}
    for phase in ('recovery_0_6', 'recovery_6_24'):
        support = cells.loc[cells.case_group.eq('primary') & cells.method.eq('raw') & cells.endpoint.eq(phase)]
        facts[phase+'_minimum_pairs'] = int(support.n.min())
        facts[phase+'_minimum_events'] = int(support.events.min())
        facts[phase+'_all_cells_meet_support'] = bool(support.n.ge(200).all() and support.events.ge(30).all())
    pd.DataFrame([facts]).to_csv(output/'engineering_gate_facts.csv', index=False)
    ledger = {'status': 'reviewed against cited artifacts', 'scope': 'Automated unique-source-row checks; narrative and human review pending',
        'claims': claims, 'derived_facts': {'path': str((output/'engineering_gate_facts.csv').relative_to(workspace)),
            'source_tables': ['Summary', 'Cells'], 'formula': '5% relative point gate against physical; clean increase <= max(0.02*physical,0.0001); support min over raw primary cells',
            'note': 'Derived gate arithmetic is tested separately; unavailable relative effect at zero denominator is NaN, not zero'}}
    verify_claim_ledger(workspace, ledger)
    (output/'claim_evidence_extension.json').write_text(json.dumps(ledger, indent=2)+'\n')
    result = {'status': 'verified extension numerical export; narrative review pending', 'run': str(root.relative_to(workspace)),
        'data_kind': manifest.get('data_kind', 'recorded PVDAQ extension'), 'code_sha256': digest(Path(__file__)),
        'source_sha256': {str(p.relative_to(workspace)): digest(p) for p in [root/'manifest.json', root/'verification.json',
            root/'analysis/manifest.json', reproduced/'reproduction_comparison.json']},
        'claims_checked': len(claims), 'files_sha256': {p.name: digest(p) for p in output.iterdir()},
        'limits': 'Point gates are not significance or acceptance guarantees; no independent human review or population-site inference'}
    (output/'manifest.json').write_text(json.dumps(result, indent=2)+'\n')
    print('Exported three tables and', len(claims), 'source-row claims; narrative interpretation pending')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run'); parser.add_argument('--reproduced', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); export(args.run, args.reproduced, args.output)
