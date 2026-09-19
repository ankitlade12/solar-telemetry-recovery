"""Exact public dependency view for the separately frozen system-10 extension."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from research.final_evaluation import assert_freeze
from research.release_protocol import ORIGINAL_LOCK_SHA256, PRIVATE_PRD, PRIVATE_PRD_SHA256
from solar_recovery.pilot import digest

EXTENSION_LOCK_SHA256 = '436d6fb991c1f3365c724d6b7ac17b058ddf22430096c06f16109dd697049464'
PARENT = Path('research/PRODUCING_EXTENSION_LOCK_V1.json')
ORIGINAL = Path('research/FINAL_PROTOCOL_LOCK.json')
PUBLIC = Path('release/PRODUCING_EXTENSION_DEPENDENCY_LOCK.json')
NATURE = 'Derived public extension reproduction dependency view; not a new prospective freeze'


def authenticated_parents():
    if digest(PARENT) != EXTENSION_LOCK_SHA256 or digest(ORIGINAL) != ORIGINAL_LOCK_SHA256:
        raise ValueError('An authenticated original/extension parent lock changed')
    parent, original = json.loads(PARENT.read_text()), json.loads(ORIGINAL.read_text())
    if parent['extension_parent_sha256'] != ORIGINAL_LOCK_SHA256:
        raise ValueError('Extension does not authenticate the original experiment')
    for name, expected in original['files_sha256'].items():
        if parent['files_sha256'].get(name) != expected:
            raise ValueError('Extension changed an original frozen dependency')
    return parent


def validate_public_view(view, parent):
    expected = dict(parent['files_sha256'])
    if expected.pop(PRIVATE_PRD) != PRIVATE_PRD_SHA256:
        raise ValueError('Private PRD identity changed')
    if view.get('files_sha256') != expected:
        raise ValueError('Public view changed a scientific dependency')
    if set(view) != set(parent) | {'public_extension_derivation'}:
        raise ValueError('Public view has unexpected fields')
    for key, value in parent.items():
        if key not in {'files_sha256', 'nature', 'performance_exposure'} and view.get(key) != value:
            raise ValueError('Public view changed frozen field: '+key)
    d = view.get('public_extension_derivation', {})
    if d.get('parent_path') != str(PARENT) or d.get('parent_sha256') != EXTENSION_LOCK_SHA256:
        raise ValueError('Public extension parent identity is wrong')
    if d.get('original_parent_sha256') != ORIGINAL_LOCK_SHA256 or d.get('omitted_private_files') != {PRIVATE_PRD: PRIVATE_PRD_SHA256}:
        raise ValueError('Public view lacks exact original/omission provenance')
    if view.get('nature') != NATURE:
        raise ValueError('A public dependency view is not a new prospective freeze')


def derive(output=PUBLIC):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Never overwrite a public dependency view')
    parent = authenticated_parents()
    view = dict(parent)
    view['files_sha256'] = {k: v for k, v in parent['files_sha256'].items() if k != PRIVATE_PRD}
    view['nature'] = NATURE
    view['performance_exposure'] = 'No new prospective claim. Original-study results were exposed before the separately frozen extension; see unchanged parent records.'
    view['public_extension_derivation'] = {'parent_path': str(PARENT), 'parent_sha256': EXTENSION_LOCK_SHA256,
        'original_parent_sha256': ORIGINAL_LOCK_SHA256, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'omitted_private_files': {PRIVATE_PRD: PRIVATE_PRD_SHA256},
        'scope': 'Only private PRD bytes omitted; every scientific hash, configuration, environment constraint and original parent identity retained'}
    validate_public_view(view, parent)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as handle:
        handle.write(json.dumps(view, indent=2)+'\n')
    print('Derived public extension view:', len(view['files_sha256']), 'scientific dependencies; private PRD omitted')


def verification_protocol(config_path, run_lock, release_lock=None):
    if release_lock is None:
        raise ValueError('Public extension verification requires an explicit public dependency view')
    parent = authenticated_parents()
    release_lock = Path(release_lock)
    view = json.loads(release_lock.read_text())
    validate_public_view(view, parent)
    if digest(run_lock) not in {EXTENSION_LOCK_SHA256, digest(release_lock)}:
        raise ValueError('Run lock is neither the preserved extension nor its validated public view')
    assert_freeze(config_path, release_lock)
    if Path(PRIVATE_PRD).exists() and digest(PRIVATE_PRD) != PRIVATE_PRD_SHA256:
        raise ValueError('Present private PRD has changed')
    return json.loads(Path(run_lock).read_text()), {
        'mode': 'explicit public extension verification', 'extension_parent_sha256': EXTENSION_LOCK_SHA256,
        'original_parent_sha256': ORIGINAL_LOCK_SHA256, 'release_view_sha256': digest(release_lock),
        'scientific_dependencies_verified': len(view['files_sha256']), 'private_prd_bytes_verified': Path(PRIVATE_PRD).is_file(),
        'declared_omissions': view['public_extension_derivation']['omitted_private_files']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(PUBLIC))
    derive(parser.parse_args().output)
