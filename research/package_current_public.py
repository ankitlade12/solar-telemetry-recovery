"""Check and archive the current public candidate locally; never publish it."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from research.package_submission import checked_path, write_archive
from research.release_protocol import PRIVATE_PRD
from solar_recovery.pilot import digest


def reviewed_selection(workspace, review_path):
    workspace = Path(workspace).resolve()
    review_path = checked_path(workspace, str(review_path))
    review = json.loads(review_path.read_text())
    if review.get('status') != 'current local review bundles built and reopened':
        raise ValueError('Require the current integrated manuscript/private review bundles')
    for archive in review['archives']:
        if digest(checked_path(workspace, str(review_path.parent/archive['file']))) != archive['sha256']:
            raise ValueError('Changed review archive')
    paths = review['public_candidate_paths']
    if not paths or len(paths) != len(set(paths)):
        raise ValueError('Require a unique nonempty reviewed file selection')
    canonical = []
    for name in paths:
        path = checked_path(workspace, name)
        relative = path.relative_to(workspace).as_posix()
        if relative == PRIVATE_PRD or relative.startswith('research/sources/'):
            raise ValueError('Private material entered the public selection')
        if digest(path) != review['source_snapshot_sha256'].get(name):
            raise ValueError('Changed or unreviewed public artifact: '+name)
        canonical.append(relative)
    if len(set(canonical)) != len(paths):
        raise ValueError('Aliased duplicate public artifacts')
    return review, sorted(canonical)


def dependency_command():
    return '''from pathlib import Path
import json,sys
from research.release_protocol import verification_protocol as original
from research.extension_release_protocol import verification_protocol as extension
import research.reproduce_public_extension, research.verify_public_extension
root=Path.cwd().resolve()
assert not (root/'Solar_Forecasting_Research_PRD.docx').exists()
_,a=original('configs/final_evaluation_v4.json','research/FINAL_PROTOCOL_LOCK.json','release/DEPENDENCY_LOCK.json')
_,b=extension('configs/producing_extension_v1.json','research/PRODUCING_EXTENSION_LOCK_V1.json','release/PRODUCING_EXTENSION_DEPENDENCY_LOCK.json')
assert a['scientific_dependencies_verified']==82 and b['scientific_dependencies_verified']==138
assert not a['private_prd_bytes_verified'] and not b['private_prd_bytes_verified']
imports={}
for name,module in sorted(sys.modules.items()):
    if name.startswith(('research.', 'solar_recovery.')) and getattr(module,'__file__',None):
        path=Path(module.__file__).resolve()
        assert path.is_relative_to(root), (name,str(path))
        imports[name]=str(path.relative_to(root))
print(json.dumps({'original':a,'extension':b,'local_imports':imports},indent=2))
'''


def package(review_manifest, output):
    workspace = Path.cwd().resolve()
    review_path = checked_path(workspace, review_manifest)
    output = Path(output).resolve()
    if not output.is_relative_to(workspace) or output.exists():
        raise ValueError('Use a fresh public-candidate directory inside the workspace')
    review, files = reviewed_selection(workspace, review_path)
    review_hash = digest(review_path)
    staging = output/'public_candidate'; staging.mkdir(parents=True)
    for name in files:
        target = staging/name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(workspace/name, target)
        if digest(target) != review['source_snapshot_sha256'][name]:
            raise ValueError('Source changed while copying: '+name)
    # The public README explicitly documents omitted private material.
    shutil.copyfile(staging/'release/README.md', staging/'README.md')
    snapshot = {name: digest(staging/name) for name in set(files)|{'README.md'}}
    checks = staging/'release/current_checks'; checks.mkdir()
    env = {**os.environ, 'PYTHONPATH': str(staging), 'MPLCONFIGDIR': str(checks/'matplotlib_cache'),
           'XDG_CACHE_HOME': str(checks/'cache')}
    commands = [[sys.executable, '-c', dependency_command()],
                [sys.executable, '-m', 'pytest', '-q'],
                [sys.executable, '-m', 'examples.synthetic_replay', '--output', 'runs/current_public_example']]
    stages = []
    for index, command in enumerate(commands, 1):
        result = subprocess.run(command, cwd=staging, env=env, capture_output=True, text=True)
        log = checks/f'stage_{index}.log'; log.write_text(result.stdout+result.stderr)
        stages.append({'command': command, 'returncode': result.returncode,
                       'log': str(log.relative_to(staging)), 'log_sha256': digest(log)})
        (output/'progress.json').write_text(json.dumps({'stages': stages}, indent=2)+'\n')
        if result.returncode:
            raise RuntimeError('Public check failed; preserve and inspect '+str(log))
    import pandas as pd
    comparisons = {}
    for name in ('synthetic_measurements.parquet', 'visible_features.parquet', 'forecasts.parquet', 'diagnostics.parquet'):
        reference = staging/'runs/clean_environment_v4/reference_example'/name
        reproduced = staging/'runs/current_public_example'/name
        pd.testing.assert_frame_equal(pd.read_parquet(reference), pd.read_parquet(reproduced), check_exact=True)
        comparisons[name] = {'exact_dataframe_equality': True, 'reference_sha256': digest(reference), 'reproduced_sha256': digest(reproduced)}
    for name, expected in snapshot.items():
        if digest(staging/name) != expected:
            raise ValueError('Candidate source changed during checks: '+name)
    if digest(review_path) != review_hash:
        raise ValueError('Source review record changed during checks')
    record = {'status': 'passed both public dependency views, full candidate tests and exact synthetic reproduction',
              'stages': stages, 'comparisons': comparisons, 'staged_source_sha256': snapshot,
              'scope': 'Same installed environment; no fresh installation, full-data refit, independent human reproduction or publication'}
    (checks/'verification.json').write_text(json.dumps(record, indent=2)+'\n')
    excluded = {'__pycache__', '.pytest_cache', 'matplotlib_cache', 'cache'}
    archive_files = [p.relative_to(staging).as_posix() for p in staging.rglob('*') if p.is_file()
                     and not excluded.intersection(p.relative_to(staging).parts) and p.suffix != '.pyc']
    archive = write_archive(output/'ccwc_public_release_candidate.zip', staging, archive_files,
                            'Current local public candidate; author/license approval pending; not published')
    final = {'status': 'current public candidate checked, archived and reopened locally', 'archive': archive,
             'recorded_at_utc': datetime.now(timezone.utc).isoformat(), 'source_review_manifest_sha256': review_hash,
             'packer_sha256': digest(Path(__file__)), 'checks_sha256': digest(checks/'verification.json'),
             'external_actions': 'None; no upload, publication, submission, contact or payment'}
    (output/'manifest.json').write_text(json.dumps(final, indent=2)+'\n')
    print('Current public candidate checked and archived locally; publication remains unauthorized')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review-manifest', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); package(args.review_manifest, args.output)
