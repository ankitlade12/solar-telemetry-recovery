"""Create a distinct authenticated lock after extension input and test checks."""
from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys

from research.final_evaluation import forecast_sources
from research.producing_extension import CONFIG, LOCK, validate_config, verify_parent
from research.release_protocol import ORIGINAL_LOCK_SHA256
from solar_recovery.pilot import digest


def main():
    if LOCK.exists():
        raise FileExistsError('Never overwrite the extension lock')
    parent = verify_parent()
    config = json.loads(CONFIG.read_text())
    validate_config(config, json.loads(Path('configs/final_evaluation_v4.json').read_text()))
    input_root = Path(config['input_root'])
    prepared = json.loads((input_root/'manifest.json').read_text())
    for name, expected in prepared['files_sha256'].items():
        if digest(input_root/name) != expected:
            raise ValueError(f'Prepared input changed: {name}')
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q'], capture_output=True, text=True)
    evidence = Path('research/producing_extension_test_record.json')
    record = {'command': [sys.executable, '-m', 'pytest', '-q'], 'returncode': result.returncode,
        'stdout': result.stdout, 'stderr': result.stderr, 'utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'Entire existing test suite plus extension boundary tests; no extension observed-data forecast scores inspected',
        'preflight_fixture_correction': 'First new test used algebraic zero and observed floating residue 4.3e-20; changed fixture to a strictly negative mean to test clipping without a false exact-zero assumption. No production code changed.'}
    with evidence.open('x') as handle:
        handle.write(json.dumps(record, indent=2)+'\n')
    print(result.stdout, end='', flush=True)
    if result.returncode:
        raise RuntimeError('Tests failed; no extension lock or forecasts')
    files = set(Path(p) for p in parent['files_sha256'])
    files.update(forecast_sources())
    files.update(Path('tests').glob('test_*.py'))
    files.update(p for p in input_root.rglob('*') if p.is_file())
    files.update([CONFIG, Path('research/FINAL_PROTOCOL_LOCK.json'),
        Path('configs/final_evaluation_v4.json'), Path('research/PRODUCING_SYSTEM_EXTENSION_PROTOCOL.md'),
        Path('research/producing_extension.py'), Path('research/prepare_producing_extension.py'), Path(__file__), evidence,
        Path('research/RESERVE_SOURCE_10_PLAN.md'), Path('research/EXTENSION_SOURCE_QUALIFICATION_PLAN.md'),
        Path('research/qualify_reserve_source.py'), Path('research/release_protocol.py')])
    files.update(p for p in Path('research/reserve_10_qualification_v1').iterdir() if p.is_file())
    for year in (2016, 2017):
        files.add(Path(f'data/raw/extension_v1/pvdaq_10_{year}/manifest.json'))
    normalized = {str(p.relative_to(Path.cwd()) if p.is_absolute() else p): digest(p) for p in sorted(files)}
    record = {'version': 'producing-extension-1', 'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
        'extension_parent_sha256': ORIGINAL_LOCK_SHA256, 'config_sha256': digest(CONFIG),
        'files_sha256': normalized, 'environment': {p: version(p) for p in parent['environment']},
        'python': platform.python_version(), 'case_count': 11, 'site_case_count': 11,
        'primary_contrast': config['inference']['primary_contrast'],
        'performance_exposure': 'Original study results already exposed. System 10 source distributions inspected for qualification; no extension model fitting or forecast performance inspected.',
        'nature': 'Separate internal pre-forecast extension freeze after original-study exposure; not public preregistration',
        'primary_protocol': str(config['extension']['protocol'])}
    with LOCK.open('x') as handle:
        handle.write(json.dumps(record, indent=2)+'\n')
    print('Locked separate extension:', len(normalized), 'files, 11 cases', flush=True)


if __name__ == '__main__':
    main()
