"""Run all producing-system primary shrinkage checks, two processes at a time."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys


def run_one(task):
    parent, site, case = task
    output = Path('runs/review_revision_20261015/shrinkage')/site/case
    output.parent.mkdir(parents=True, exist_ok=True)
    existing = Path('runs/revision_shrinkage_c10_v1') if site == 'reserve10' and case == 'joint_gradual' else output
    if (existing/'manifest.json').exists():
        manifest = json.loads((existing/'manifest.json').read_text())
        if manifest['status'] == 'complete exploratory shrinkage replay':
            print(f'Reusing completed {site}/{case}: {existing}', flush=True)
            return {'site': site, 'case': case, 'path': str(existing), 'returncode': 0}
        raise RuntimeError(f'Incomplete output requires inspection: {existing}')
    with output.with_suffix('.log').open('w') as log:
        result = subprocess.run([sys.executable, '-m', 'research.run_revision_shrinkage', '--parent', parent,
                                 '--site', site, '--case', case, '--output', str(output)], stdout=log, stderr=subprocess.STDOUT)
    print(f'Completed {site}/{case}: exit {result.returncode}', flush=True)
    return {'site': site, 'case': case, 'path': str(output), 'returncode': result.returncode}


if __name__ == '__main__':
    tasks = []
    for parent, site in [('runs/final_2017_v4', 'nist'), ('runs/producing_extension_v1', 'reserve10')]:
        config = json.loads((Path(parent)/'config.json').read_text())
        tasks.extend((parent, site, c['id']) for c in config['cases'] if c['group'] == 'primary')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run_one, tasks))
    Path('runs/review_revision_20261015/shrinkage/batch.json').write_text(json.dumps(results, indent=2)+'\n')
    if any(r['returncode'] for r in results):
        raise SystemExit('Some revision runs failed; inspect case logs')
