"""Separate replication configuration and runner; preserve original freeze."""
import argparse
import copy
import json
from pathlib import Path

from research.final_evaluation import assert_freeze, run
from research.release_protocol import ORIGINAL_LOCK_SHA256
from solar_recovery.pilot import digest

CONFIG = Path('configs/producing_extension_v1.json')
LOCK = Path('research/PRODUCING_EXTENSION_LOCK_V1.json')
EXTRA_CASES = {'right_aligned', 'receipt_5min', 'privileged_labels'}


def expected_config(parent):
    config = copy.deepcopy(parent)
    config['sites'] = ['reserve10']
    config['input_root'] = 'data/processed/producing_extension_v1'
    config['cases'] = [c for c in config['cases'] if c['group'] == 'primary' or c['id'] in EXTRA_CASES]
    for case in config['cases']:
        if 'sites' in case:
            case['sites'] = ['reserve10']
    config['extension'] = {'identity': 'producing-system replication v1',
        'protocol': 'research/PRODUCING_SYSTEM_EXTENSION_PROTOCOL.md',
        'parent_lock_sha256': ORIGINAL_LOCK_SHA256,
        'exposure': 'Original 2017 results already inspected; no extension forecasts inspected at freeze',
        'scope': 'Additional recorded-AC system at nearby Colorado location; not an independent climate'}
    return config


def validate_config(config, parent):
    if config != expected_config(parent):
        raise ValueError('Extension deviates from fixed parent settings or declared site/case scope')
    assert len(config['cases']) == 11
    assert sum(c['group'] == 'primary' for c in config['cases']) == 8


def verify_parent():
    if digest('research/FINAL_PROTOCOL_LOCK.json') != ORIGINAL_LOCK_SHA256:
        raise ValueError('Original protocol lock changed')
    return assert_freeze('configs/final_evaluation_v4.json', 'research/FINAL_PROTOCOL_LOCK.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-config', action='store_true')
    parser.add_argument('--output', default='runs/producing_extension_v1')
    args = parser.parse_args()
    verify_parent()
    parent = json.loads(Path('configs/final_evaluation_v4.json').read_text())
    if args.write_config:
        with CONFIG.open('x') as handle:
            handle.write(json.dumps(expected_config(parent), indent=2)+'\n')
        print('Wrote separate extension configuration; no fitting or evaluation')
        return
    config = json.loads(CONFIG.read_text()); validate_config(config, parent)
    lock = assert_freeze(CONFIG, LOCK)
    if lock.get('extension_parent_sha256') != ORIGINAL_LOCK_SHA256:
        raise ValueError('Missing extension parent authentication')
    print('Starting separately frozen producing-system replication; original study is unchanged', flush=True)
    run(CONFIG, LOCK, args.output)


if __name__ == '__main__':
    main()
