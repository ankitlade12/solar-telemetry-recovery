import json

import pytest

from research.revision_package_selection import add_claim_and_lock_dependencies, verified_extension_files
from research.release_protocol import PRIVATE_PRD
from solar_recovery.pilot import digest


def test_all_revision_ledgers_and_nonprivate_lock_dependencies_are_closed(tmp_path):
    (tmp_path/'diagnostic.csv').write_text('site,value\nreserve,12\n')
    (tmp_path/'adapter.py').write_text('# synthetic dependency\n')
    ledger = {'status': 'reviewed against cited artifacts', 'claims': [{'id': 'posthoc',
        'statement': 'Synthetic source count', 'source_path': 'diagnostic.csv',
        'source_sha256': digest(tmp_path/'diagnostic.csv'), 'where': {'site': 'reserve'}, 'values': {'value': 12}}]}
    (tmp_path/'posthoc.json').write_text(json.dumps(ledger))
    lock = {'files_sha256': {'adapter.py': digest(tmp_path/'adapter.py'), PRIVATE_PRD: 'private omitted'}}
    (tmp_path/'lock.json').write_text(json.dumps(lock))
    selected = add_claim_and_lock_dependencies(tmp_path, set(), ['posthoc.json'], ['lock.json'])
    assert selected == {'diagnostic.csv', 'adapter.py', 'posthoc.json', 'lock.json'}
    (tmp_path/'adapter.py').write_text('# changed\n')
    with pytest.raises(ValueError, match='Changed locked'):
        add_claim_and_lock_dependencies(tmp_path, set(), ['posthoc.json'], ['lock.json'])
    (tmp_path/'diagnostic.csv').write_text('site,value\nreserve,13\n')
    with pytest.raises(ValueError, match='Changed claim source'):
        add_claim_and_lock_dependencies(tmp_path, set(), ['posthoc.json'], [])


def test_private_file_cannot_enter_through_initial_selection(tmp_path):
    (tmp_path/PRIVATE_PRD).write_text('synthetic private planning document')
    with pytest.raises(ValueError, match='Private planning'):
        add_claim_and_lock_dependencies(tmp_path, {PRIVATE_PRD}, [], [])


def test_incomplete_or_changed_extension_cannot_enter_package(tmp_path):
    folder = tmp_path/'run';folder.mkdir()
    (folder/'manifest.json').write_text(json.dumps({'status': 'running frozen evaluation'}))
    with pytest.raises(ValueError, match='must finish'):
        verified_extension_files(tmp_path, 'run')
    (folder/'manifest.json').write_text(json.dumps({'status': 'complete frozen evaluation'}))
    checksum = digest(folder/'manifest.json')
    (folder/'forecast.csv').write_text('synthetic\n')
    (folder/'verification.json').write_text(json.dumps({'status': 'passed synthetic fixture',
        'manifest_sha256': checksum, 'files_sha256': {'forecast.csv': digest(folder/'forecast.csv')}}))
    analysis = folder/'analysis';analysis.mkdir()
    (analysis/'table.csv').write_text('synthetic table\n')
    (analysis/'manifest.json').write_text(json.dumps({'status': 'complete analysis',
        'source_manifest_sha256': checksum, 'files_sha256': {'table.csv': digest(analysis/'table.csv')}}))
    assert 'run/analysis/table.csv' in verified_extension_files(tmp_path, 'run')
    (analysis/'table.csv').write_text('changed\n')
    with pytest.raises(ValueError, match='artifact changed'):
        verified_extension_files(tmp_path, 'run')
