"""Authenticate extension provenance before the unchanged numerical verifier."""
import argparse
import json
from pathlib import Path
import shutil

from research.final_evaluation import assert_freeze
from research.producing_extension import CONFIG, LOCK, validate_config, verify_parent
from research.release_protocol import ORIGINAL_LOCK_SHA256
from research.verify_final_evaluation import verify
from solar_recovery.pilot import digest


def main(root):
    root = Path(root)
    verify_parent()
    frozen = assert_freeze(root/'config.json', root/'protocol_lock.json')
    if digest(root/'protocol_lock.json') != digest(LOCK) or digest(root/'config.json') != digest(CONFIG):
        raise ValueError('Run does not match the separately frozen extension')
    if frozen.get('extension_parent_sha256') != ORIGINAL_LOCK_SHA256:
        raise ValueError('Extension parent authentication missing')
    validate_config(json.loads((root/'config.json').read_text()), json.loads(Path('configs/final_evaluation_v4.json').read_text()))
    if json.loads((root/'manifest.json').read_text())['status'] != 'complete frozen evaluation':
        raise ValueError('Wait for the actual run to finish')
    context = root/'extension_context.json'
    if context.exists() or (root/'verification.json').exists():
        raise FileExistsError('Extension verification records are immutable')
    snapshots = ['research/producing_extension.py', 'research/prepare_producing_extension.py',
        'research/freeze_producing_extension.py', 'research/PRODUCING_SYSTEM_EXTENSION_PROTOCOL.md',
        'research/verify_producing_extension.py', 'research/verify_final_evaluation.py',
        'research/release_protocol.py']
    for name in snapshots:
        destination = root/'extension_source'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(name, destination)
    context.write_text(json.dumps({'identity': 'separate producing-system replication after original-study performance exposure',
        'original_parent_lock_sha256': ORIGINAL_LOCK_SHA256, 'extension_lock_sha256': digest(LOCK),
        'original_parent_authenticated': True, 'extension_dependencies_verified': len(frozen['files_sha256']),
        'verifier': 'unchanged generic arithmetic/receipt verifier with authenticated extension configuration and source contracts',
        'generic_private_mode_note': 'The generic checker labels its no-release-view branch original private-workspace verification. Here its actual run lock is the separate extension lock above, not the original study lock.',
        'source_sha256': {name: digest(name) for name in snapshots},
        'limits': 'Automated verification, not independent human reproduction or physical-meter certification'}, indent=2)+'\n')
    verify(root)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run')
    main(parser.parse_args().run)
